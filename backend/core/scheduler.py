"""Scheduler: per-playlist APScheduler jobs + refresh dispatch.

Design
------
APScheduler owns *timing*: every scheduled playlist gets its own job
(``playlist:{schedule_id}``) built from a :class:`ScheduleSpec`. The
:class:`~backend.core.refresh_queue.RefreshQueue` owns *pacing*: it runs one
refresh at a time with a configurable gap so a burst of due playlists cannot
trip AI-provider rate limits.

Because the trigger is authoritative, ``next_run`` is read straight from
``job.next_run_time`` instead of being written back to the database by each
handler. That removes the class of bug where a handler forgets to advance
``next_refresh`` and the playlist silently stops refreshing.

Per-type refresh callables are registered in ``_REFRESH_REGISTRY`` by
``main.py`` at startup, so this module never imports the type packages
(avoiding circular imports).
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..database import DatabaseManager
from .refresh_queue import RefreshJob, get_refresh_queue
from .schedule_spec import (
    ScheduleSpec,
    build_trigger,
    describe_schedule,
    frequency_from_spec,
    spec_from_frequency,
    to_naive_local,
    upcoming_runs,
)


scheduler_logger = logging.getLogger(__name__)

# The scheduler instance is owned by the application lifecycle (see main.py).
scheduler: AsyncIOScheduler = None  # type: ignore

# Registry mapping playlist_type -> async refresh callable. Populated by
# main.py on startup so this module never imports the type packages directly.
_REFRESH_REGISTRY: Dict[str, Callable[[Dict[str, Any], DatabaseManager], Awaitable[int]]] = {}

# How far back a missed refresh is still caught up on startup. A refresh that
# was missed more than a day ago is treated as stale intent, not a real miss.
CATCHUP_WINDOW_HOURS = 24

JOB_PREFIX = "playlist:"


def register_refresh_handler(playlist_type: str, handler) -> None:
    """Register an async refresh handler for a given playlist type."""
    _REFRESH_REGISTRY[playlist_type] = handler


# ---------------------------------------------------------------------------
# Next-run calculation
# ---------------------------------------------------------------------------
def next_run_for_spec(spec: ScheduleSpec, now: Optional[datetime] = None) -> datetime:
    """Return the next fire time for a spec as naive server-local time.

    APScheduler returns timezone-aware datetimes; they are normalised here so
    callers can safely compare them against ``datetime.now()``.
    """
    try:
        trigger = build_trigger(spec)
        next_run = to_naive_local(trigger.get_next_fire_time(None, now or datetime.now()))
        return next_run or datetime.now()
    except Exception as exc:  # noqa: BLE001 - never let a bad spec break scheduling
        scheduler_logger.warning("Could not compute next run for %s: %s", spec, exc)
        return datetime.now()


def calculate_next_refresh(frequency: str) -> datetime:
    """Calculate the next refresh time based on a legacy frequency string.

    Retained for callers that still create schedules from a plain frequency.
    New code should use :func:`next_run_for_spec`.
    """
    spec = spec_from_frequency(frequency)
    if spec is None:
        return datetime.now()
    return next_run_for_spec(spec)


# ---------------------------------------------------------------------------
# Job management
# ---------------------------------------------------------------------------
def _job_id(schedule_id: int) -> str:
    """Return the APScheduler job id for a schedule row."""
    return f"{JOB_PREFIX}{schedule_id}"


def _parse_spec(schedule_row: Dict[str, Any]) -> Optional[ScheduleSpec]:
    """Deserialize the schedule spec from a DB row, falling back to the frequency."""
    raw = schedule_row.get("schedule_json")
    if raw:
        try:
            return ScheduleSpec.model_validate_json(raw)
        except Exception as exc:  # noqa: BLE001 - fall back to the legacy frequency
            scheduler_logger.warning(
                "Invalid schedule_json for schedule %s (%s), falling back to frequency",
                schedule_row.get("id"),
                exc,
            )
    return spec_from_frequency(schedule_row.get("refresh_frequency"))


def sync_playlist_job(schedule_row: Dict[str, Any]) -> bool:
    """Create, replace, or remove the APScheduler job for one schedule row.

    Args:
        schedule_row: Row from ``db.get_all_schedules()`` / ``get_schedule_by_navidrome_id``.

    Returns:
        ``True`` when a job is registered, ``False`` when the schedule is
        disabled or has no usable spec (any existing job is removed).
    """
    if scheduler is None:
        scheduler_logger.warning("Scheduler not initialised; cannot sync job")
        return False

    schedule_id = schedule_row.get("id")
    enabled = schedule_row.get("enabled", 1)
    spec = _parse_spec(schedule_row)

    if not enabled or spec is None:
        remove_playlist_job(schedule_id)
        return False

    try:
        trigger = build_trigger(spec)
    except Exception as exc:  # noqa: BLE001 - a bad spec must not crash startup
        scheduler_logger.error("Cannot build trigger for schedule %s: %s", schedule_id, exc)
        remove_playlist_job(schedule_id)
        return False

    scheduler.add_job(
        enqueue_scheduled_refresh,
        trigger=trigger,
        id=_job_id(schedule_id),
        args=[
            schedule_row.get("navidrome_playlist_id"),
            schedule_row.get("playlist_type"),
            schedule_row.get("playlist_name"),
        ],
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )
    scheduler_logger.info(
        "Scheduled '%s' (%s)",
        schedule_row.get("playlist_name") or schedule_row.get("navidrome_playlist_id"),
        describe_schedule(spec),
    )
    return True


def remove_playlist_job(schedule_id: int) -> None:
    """Remove the APScheduler job for a schedule row, if present."""
    if scheduler is None:
        return
    job_id = _job_id(schedule_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        scheduler_logger.info("Removed refresh job %s", job_id)


async def advance_next_refresh(db: DatabaseManager, navidrome_playlist_id: str) -> None:
    """Persist the next run time for a playlist after a refresh completes.

    The APScheduler trigger is authoritative for *when* a job fires, but the
    ``next_refresh`` column is what startup catch-up reads. Without this update
    the column stays frozen at the value written when the schedule was created,
    so every restart would treat the playlist as overdue and refresh it again.

    Best-effort: a failure here must never fail the refresh itself.
    """
    try:
        schedule_row = await db.get_schedule_by_navidrome_id(navidrome_playlist_id)
        if not schedule_row:
            return

        spec = _parse_spec(schedule_row)
        if spec is None:
            return

        next_run = next_run_for_spec(spec)
        await db.update_scheduled_playlist_next_refresh(schedule_row["id"], next_run)
        scheduler_logger.info(
            "Next refresh for '%s' set to %s",
            schedule_row.get("playlist_name") or navidrome_playlist_id,
            next_run.strftime("%Y-%m-%d %H:%M:%S"),
        )
    except Exception as exc:  # noqa: BLE001 - never fail a refresh over bookkeeping
        scheduler_logger.warning(
            "Could not advance next_refresh for %s: %s", navidrome_playlist_id, exc
        )


async def rehydrate_jobs(db: DatabaseManager) -> int:
    """Rebuild all per-playlist jobs from the database on startup.

    Also enqueues a catch-up refresh for schedules that were missed within
    :data:`CATCHUP_WINDOW_HOURS`.

    Each row is processed independently: a failure on one schedule must never
    abort the loop and leave the remaining playlists without a job.

    Returns:
        The number of jobs registered.
    """
    rows = await db.get_all_schedules()
    registered = 0
    now = datetime.now()

    for row in rows:
        label = row.get("playlist_name") or row.get("navidrome_playlist_id")

        try:
            if sync_playlist_job(row):
                registered += 1
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the rest
            scheduler_logger.error("Failed to register refresh job for '%s': %s", label, exc)
            continue

        # Bounded catch-up: only schedules missed within the window.
        if not row.get("enabled", 1):
            continue
        next_refresh = row.get("next_refresh")
        if not next_refresh:
            continue
        try:
            # Stored values may carry a UTC offset from older versions; normalise
            # to naive server-local time before comparing with ``now``.
            scheduled_time = to_naive_local(datetime.fromisoformat(next_refresh))
        except (TypeError, ValueError):
            continue
        if scheduled_time is None or scheduled_time >= now:
            continue

        # Guard against a stale next_refresh: if the playlist was already
        # refreshed after it became due, the schedule is satisfied and must not
        # be re-queued. This covers databases written before next_refresh was
        # advanced after each run.
        last_refreshed = row.get("last_refreshed")
        if last_refreshed:
            try:
                last_refreshed_at = to_naive_local(datetime.fromisoformat(last_refreshed))
            except (TypeError, ValueError):
                last_refreshed_at = None
            if last_refreshed_at is not None and last_refreshed_at >= scheduled_time:
                scheduler_logger.info(
                    "Skipping catch-up for '%s': already refreshed at %s (was due %s)",
                    label,
                    last_refreshed_at.strftime("%Y-%m-%d %H:%M:%S"),
                    scheduled_time.strftime("%Y-%m-%d %H:%M:%S"),
                )
                # Bring the stored value forward so the next restart is clean.
                await advance_next_refresh(db, row.get("navidrome_playlist_id"))
                continue

        if now - scheduled_time > timedelta(hours=CATCHUP_WINDOW_HOURS):
            scheduler_logger.info(
                "Skipping stale catch-up for '%s' (missed by %.1fh)",
                label,
                (now - scheduled_time).total_seconds() / 3600,
            )
            continue
        scheduler_logger.info(
            "Catching up on overdue playlist '%s' (missed by %.1fh)",
            label,
            (now - scheduled_time).total_seconds() / 3600,
        )
        try:
            await enqueue_scheduled_refresh(
                row.get("navidrome_playlist_id"),
                row.get("playlist_type"),
                row.get("playlist_name"),
            )
        except Exception as exc:  # noqa: BLE001 - catch-up is best-effort
            scheduler_logger.error("Failed to queue catch-up refresh for '%s': %s", label, exc)

    scheduler_logger.info("Rehydrated %s playlist refresh job(s)", registered)
    return registered


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------
async def enqueue_scheduled_refresh(
    navidrome_playlist_id: str,
    playlist_type: str,
    playlist_name: Optional[str] = None,
) -> bool:
    """APScheduler job body: hand a due playlist to the throttled queue."""
    if not navidrome_playlist_id:
        return False
    queue = get_refresh_queue()
    return await queue.submit(
        RefreshJob(
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_type=playlist_type or "this_is",
            trigger="scheduled",
            playlist_name=playlist_name,
        )
    )


async def enqueue_manual_refresh(
    navidrome_playlist_id: str,
    playlist_type: str,
    playlist_name: Optional[str] = None,
) -> bool:
    """Queue a user-triggered refresh (used by the manual refresh endpoint)."""
    queue = get_refresh_queue()
    return await queue.submit(
        RefreshJob(
            navidrome_playlist_id=navidrome_playlist_id,
            playlist_type=playlist_type or "this_is",
            trigger="manual",
            playlist_name=playlist_name,
        )
    )


async def enqueue_all_due(db: DatabaseManager) -> int:
    """Queue every enabled schedule whose next run has passed.

    Used by the manual ``/api/scheduler/trigger`` endpoint. Returns the number
    of playlists queued.
    """
    rows = await db.get_all_schedules()
    now = datetime.now()
    queued = 0

    for row in rows:
        if not row.get("enabled", 1):
            continue
        next_refresh = row.get("next_refresh")
        if not next_refresh:
            continue
        try:
            # Normalise any stored UTC offset to naive server-local time.
            scheduled_time = to_naive_local(datetime.fromisoformat(next_refresh))
        except (TypeError, ValueError):
            continue
        if scheduled_time is None or scheduled_time > now:
            continue

        # Same stale-schedule guard as rehydrate_jobs: a playlist refreshed
        # after it became due is already satisfied.
        last_refreshed = row.get("last_refreshed")
        if last_refreshed:
            try:
                last_refreshed_at = to_naive_local(datetime.fromisoformat(last_refreshed))
            except (TypeError, ValueError):
                last_refreshed_at = None
            if last_refreshed_at is not None and last_refreshed_at >= scheduled_time:
                await advance_next_refresh(db, row.get("navidrome_playlist_id"))
                continue

        if await enqueue_scheduled_refresh(
            row.get("navidrome_playlist_id"),
            row.get("playlist_type"),
            row.get("playlist_name"),
        ):
            queued += 1

    return queued


# ---------------------------------------------------------------------------
# Introspection (used by the API)
# ---------------------------------------------------------------------------
def get_next_run_times() -> Dict[str, datetime]:
    """Return ``{navidrome_playlist_id: next_run}`` for all registered jobs.

    Values are naive server-local datetimes, matching the rest of the app.
    """
    if scheduler is None:
        return {}

    result: Dict[str, datetime] = {}
    for job in scheduler.get_jobs():
        if not job.id.startswith(JOB_PREFIX):
            continue
        if not job.next_run_time:
            continue
        args = job.args or ()
        if not args:
            continue
        next_run = to_naive_local(job.next_run_time)
        if next_run is not None:
            result[str(args[0])] = next_run
    return result


def get_job_info() -> List[Dict[str, Any]]:
    """Return a serialisable description of every registered playlist job."""
    if scheduler is None:
        return []

    info: List[Dict[str, Any]] = []
    for job in scheduler.get_jobs():
        if not job.id.startswith(JOB_PREFIX):
            continue
        args = job.args or ()
        info.append({
            "id": job.id,
            "navidrome_playlist_id": str(args[0]) if args else None,
            "playlist_name": str(args[2]) if len(args) > 2 and args[2] else None,
            "playlist_type": str(args[1]) if len(args) > 1 else None,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        })
    return info


def build_schedule_payload(schedule_row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the schedule portion of the scheduler overview payload."""
    if not schedule_row:
        return {
            "enabled": False,
            "schedule": None,
            "schedule_description": "Manual only",
            "refresh_frequency": "none",
            "next_run": None,
            "upcoming": [],
        }

    spec = _parse_spec(schedule_row)
    enabled = bool(schedule_row.get("enabled", 1))
    next_run = get_next_run_times().get(str(schedule_row.get("navidrome_playlist_id")))

    # Fall back to computing from the spec when no live job is registered (for
    # example if job registration failed). This keeps the tile consistent with
    # the detail modal, which always derives its preview from the spec.
    if next_run is None and enabled and spec is not None:
        next_run = next_run_for_spec(spec)

    upcoming: List[str] = []
    if enabled and spec is not None:
        if next_run:
            upcoming.append(next_run.isoformat())
        # Preview the runs after the next one so the detail panel can show a list.
        for run in upcoming_runs(spec, count=4):
            iso = run.isoformat()
            if iso not in upcoming:
                upcoming.append(iso)
        upcoming = upcoming[:4]

    return {
        "enabled": enabled,
        "schedule": spec.model_dump() if spec else None,
        "schedule_description": describe_schedule(spec) if enabled else "Paused",
        "refresh_frequency": frequency_from_spec(spec),
        "next_run": next_run.isoformat() if next_run else None,
        "upcoming": upcoming,
    }
