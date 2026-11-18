"""Single-worker refresh queue.

All playlist refreshes — scheduled or manual — funnel through this queue so
that:

* **Two playlists never refresh at the same time** (``REFRESH_MAX_CONCURRENCY``,
  default 1).
* **Refreshes are spaced out** by ``REFRESH_MIN_GAP_SECONDS`` (default 45) so a
  burst of due playlists cannot trip AI-provider rate limits.
* **A playlist is never queued twice** — the in-flight set deduplicates by
  media-server playlist ID, so a manual refresh cannot collide with a
  scheduled one for the same playlist.

The queue owns the *pacing*; APScheduler owns the *timing* (see
``core.scheduler``). Handlers are plain ``async def handler(playlist, db)``
callables registered in ``core.scheduler._REFRESH_REGISTRY``.
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from ..database import DatabaseManager, get_database_path
from ..logging_config import STARTUP_FLAG
from .curation_notices import (
    has_ai_failure,
    start_collecting,
    stop_collecting,
    summarize,
)

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    """Read a positive integer from the environment, falling back to ``default``."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r, using default %s", name, raw, default)
        return default
    return value if value > 0 else default


@dataclass
class RefreshJob:
    """A single queued refresh request."""

    navidrome_playlist_id: str
    playlist_type: str
    trigger: str = "scheduled"  # "scheduled" | "manual"
    playlist_name: Optional[str] = None
    enqueued_at: datetime = field(default_factory=datetime.now)

    @property
    def label(self) -> str:
        """Human-readable identifier used in logs and API payloads."""
        return self.playlist_name or self.navidrome_playlist_id


class RefreshQueue:
    """Serialises playlist refreshes with a configurable gap between them."""

    def __init__(
        self,
        max_concurrency: Optional[int] = None,
        min_gap_seconds: Optional[int] = None,
    ) -> None:
        self.max_concurrency = max_concurrency or _env_int("REFRESH_MAX_CONCURRENCY", 1)
        self.min_gap_seconds = (
            min_gap_seconds if min_gap_seconds is not None
            else _env_int("REFRESH_MIN_GAP_SECONDS", 45)
        )

        self._queue: "asyncio.Queue[RefreshJob]" = asyncio.Queue()
        self._pending: List[RefreshJob] = []
        self._in_flight: set[str] = set()
        self._running: Optional[RefreshJob] = None
        self._workers: List[asyncio.Task] = []
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._last_start: Optional[datetime] = None
        self._start_lock: Optional[asyncio.Lock] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the worker tasks. Safe to call more than once."""
        if self._workers:
            return
        self._semaphore = asyncio.Semaphore(self.max_concurrency)
        self._start_lock = asyncio.Lock()
        for index in range(self.max_concurrency):
            self._workers.append(asyncio.create_task(self._worker(index)))
        logger.info(
            "Refresh queue started (max_concurrency=%s, min_gap=%ss)",
            self.max_concurrency,
            self.min_gap_seconds,
            extra={STARTUP_FLAG: True},
        )

    async def stop(self) -> None:
        """Cancel worker tasks and clear queue state."""
        for worker in self._workers:
            worker.cancel()
        for worker in self._workers:
            try:
                await worker
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown is best-effort
                pass
        self._workers.clear()
        self._pending.clear()
        self._in_flight.clear()
        self._running = None
        logger.info("Refresh queue stopped", extra={STARTUP_FLAG: True})

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    async def submit(self, job: RefreshJob) -> bool:
        """Enqueue a refresh.

        Returns:
            ``True`` if the job was queued, ``False`` if that playlist is
            already queued or currently running.
        """
        if job.navidrome_playlist_id in self._in_flight:
            logger.info(
                "Skipping refresh for '%s': already queued or running",
                job.label,
            )
            return False

        self._in_flight.add(job.navidrome_playlist_id)
        self._pending.append(job)
        await self._queue.put(job)
        logger.info(
            "Queued %s refresh for '%s' (queue depth: %s)",
            job.trigger,
            job.label,
            len(self._pending),
        )
        return True

    def is_busy(self, navidrome_playlist_id: str) -> bool:
        """Return ``True`` when a playlist is queued or running."""
        return navidrome_playlist_id in self._in_flight

    def snapshot(self) -> Dict[str, Any]:
        """Return the current queue state for the status API."""
        return {
            "max_concurrency": self.max_concurrency,
            "min_gap_seconds": self.min_gap_seconds,
            "queued": [
                {
                    "navidrome_playlist_id": job.navidrome_playlist_id,
                    "playlist_name": job.playlist_name,
                    "playlist_type": job.playlist_type,
                    "trigger": job.trigger,
                    "enqueued_at": job.enqueued_at.isoformat(),
                }
                for job in self._pending
            ],
            "running": (
                {
                    "navidrome_playlist_id": self._running.navidrome_playlist_id,
                    "playlist_name": self._running.playlist_name,
                    "playlist_type": self._running.playlist_type,
                    "trigger": self._running.trigger,
                    "enqueued_at": self._running.enqueued_at.isoformat(),
                }
                if self._running
                else None
            ),
            "in_flight": sorted(self._in_flight),
        }

    # ------------------------------------------------------------------
    # Worker
    # ------------------------------------------------------------------
    async def _wait_for_gap(self) -> None:
        """Block until ``min_gap_seconds`` have elapsed since the last start."""
        if self._last_start is None or self.min_gap_seconds <= 0:
            return
        elapsed = (datetime.now() - self._last_start).total_seconds()
        remaining = self.min_gap_seconds - elapsed
        if remaining > 0:
            logger.debug("Waiting %.1fs before next refresh (rate-limit guard)", remaining)
            await asyncio.sleep(remaining)

    async def _worker(self, index: int) -> None:
        """Consume jobs forever, one at a time per worker."""
        from .scheduler import _REFRESH_REGISTRY

        while True:
            job = await self._queue.get()
            try:
                assert self._semaphore is not None and self._start_lock is not None
                async with self._semaphore:
                    # Serialise the gap check so concurrent workers cannot both
                    # start at the same instant.
                    async with self._start_lock:
                        await self._wait_for_gap()
                        self._last_start = datetime.now()

                    self._running = job
                    if job in self._pending:
                        self._pending.remove(job)

                    await self._execute(job, _REFRESH_REGISTRY)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - a worker must never die
                logger.exception("Unexpected error in refresh worker %s: %s", index, exc)
            finally:
                self._running = None
                self._in_flight.discard(job.navidrome_playlist_id)
                self._queue.task_done()

    async def _execute(self, job: RefreshJob, registry: Dict[str, Any]) -> None:
        """Run one refresh and record its outcome in the history table."""
        # Imported lazily: scheduler imports this module at load time.
        from .scheduler import advance_next_refresh

        db = DatabaseManager(get_database_path())
        started_at = datetime.now()

        playlist = await db.get_playlist_by_navidrome_id_with_schedule_info(
            job.navidrome_playlist_id
        )
        if not playlist:
            logger.warning(
                "Playlist '%s' no longer exists locally, dropping refresh",
                job.label,
            )
            await db.record_refresh(
                navidrome_playlist_id=job.navidrome_playlist_id,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(),
                duration_seconds=0.0,
                error="Playlist no longer exists locally",
                playlist_type=job.playlist_type,
                trigger=job.trigger,
            )
            return

        playlist_name = playlist.get("playlist_name") or job.playlist_name
        playlist_type = playlist.get("playlist_type") or job.playlist_type
        label = playlist_name or job.navidrome_playlist_id

        handler = registry.get(playlist_type)
        if handler is None:
            message = f"No refresh handler registered for playlist type '{playlist_type}'"
            logger.warning("%s (playlist '%s')", message, label)
            await db.record_refresh(
                navidrome_playlist_id=job.navidrome_playlist_id,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(),
                duration_seconds=0.0,
                error=message,
                playlist_name=playlist_name,
                playlist_type=playlist_type,
                trigger=job.trigger,
            )
            return

        logger.info(
            "Starting %s refresh for '%s' (%s)",
            job.trigger,
            label,
            playlist_type,
        )

        # Curation code records notices here (AI failures, fallback usage) so
        # the outcome can be reported accurately without changing every
        # curation signature.
        start_collecting()

        try:
            track_count = await handler(playlist, db)
        except Exception as exc:  # noqa: BLE001 - record and continue with the queue
            notices = stop_collecting()
            finished_at = datetime.now()
            logger.error(
                "Refresh failed for '%s': %s",
                label,
                exc,
                exc_info=True,
            )
            await db.record_refresh(
                navidrome_playlist_id=job.navidrome_playlist_id,
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=(finished_at - started_at).total_seconds(),
                error=summarize(notices) or str(exc),
                playlist_name=playlist_name,
                playlist_type=playlist_type,
                trigger=job.trigger,
            )
            return

        notices = stop_collecting()
        finished_at = datetime.now()
        notice_text = summarize(notices)

        # An AI failure means the playlist was rebuilt by a fallback algorithm
        # rather than curated. The playlist exists, but the refresh did not do
        # what was asked, so it is reported as failed.
        if has_ai_failure(notices):
            logger.error(
                "Refresh for '%s' completed with an AI failure: %s",
                label,
                notice_text,
            )
            await db.record_refresh(
                navidrome_playlist_id=job.navidrome_playlist_id,
                status="failed",
                started_at=started_at,
                finished_at=finished_at,
                duration_seconds=(finished_at - started_at).total_seconds(),
                track_count=track_count,
                error=notice_text,
                playlist_name=playlist_name,
                playlist_type=playlist_type,
                trigger=job.trigger,
            )
            await advance_next_refresh(db, job.navidrome_playlist_id)
            return

        await db.record_refresh(
            navidrome_playlist_id=job.navidrome_playlist_id,
            status="success",
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=(finished_at - started_at).total_seconds(),
            track_count=track_count,
            # A legitimate fallback (e.g. no listening history) still succeeds,
            # but the reason is kept so the user can see why.
            error=notice_text,
            playlist_name=playlist_name,
            playlist_type=playlist_type,
            trigger=job.trigger,
        )
        logger.info(
            "Finished %s refresh for '%s' (%s tracks in %.1fs)%s",
            job.trigger,
            label,
            track_count,
            (finished_at - started_at).total_seconds(),
            f" — {notice_text}" if notice_text else "",
        )

        # Keep the stored next_refresh in step with the schedule so a restart
        # does not treat this playlist as overdue and refresh it again.
        await advance_next_refresh(db, job.navidrome_playlist_id)


# Module-level singleton, created lazily so importing this module never needs a
# running event loop.
_queue: Optional[RefreshQueue] = None


def get_refresh_queue() -> RefreshQueue:
    """Return the process-wide refresh queue, creating it on first use."""
    global _queue
    if _queue is None:
        _queue = RefreshQueue()
    return _queue
