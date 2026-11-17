"""Structured refresh-schedule specification.

A ``ScheduleSpec`` is the single source of truth for *when* a playlist should
refresh. It replaces the old opaque ``refresh_frequency`` string ("daily",
"weekly", ...) which could only ever express "somewhere in a 12-hour window".

The spec is stored as JSON in ``scheduled_playlists.schedule_json`` and is
translated into an APScheduler trigger by :func:`build_trigger`. Legacy
frequencies are still accepted and converted by :func:`spec_from_frequency`,
so existing rows and old API clients keep working.

Times are interpreted in the server's local timezone (no per-playlist
timezone support by design).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Literal, Optional

from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger("scheduler")

# Weekday names indexed 0=Monday .. 6=Sunday (matches APScheduler's day_of_week).
WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

ScheduleKind = Literal["daily", "weekly", "monthly", "interval", "cron"]


class ScheduleSpec(BaseModel):
    """A structured, per-playlist refresh schedule.

    Attributes:
        kind: Which scheduling strategy to use.
        time: ``HH:MM`` (24h) used by the daily/weekly/monthly kinds.
        weekdays: Days of week for ``weekly`` (0=Monday .. 6=Sunday).
        day_of_month: Day for ``monthly`` (1-28, capped to avoid short months).
        interval_hours: Hours between runs for ``interval``.
        cron: Raw 5-field crontab expression for ``cron``.
    """

    kind: ScheduleKind = "daily"
    time: str = "01:00"
    weekdays: List[int] = Field(default_factory=lambda: [0])
    day_of_month: int = Field(default=1, ge=1, le=28)
    interval_hours: int = Field(default=24, ge=1, le=8760)
    cron: Optional[str] = None

    @field_validator("time")
    @classmethod
    def _validate_time(cls, value: str) -> str:
        """Ensure ``time`` is a valid ``HH:MM`` string."""
        parse_time(value)
        return value

    @field_validator("weekdays")
    @classmethod
    def _validate_weekdays(cls, value: List[int]) -> List[int]:
        """Ensure weekday indexes are within 0-6 and deduplicated."""
        cleaned = sorted({int(day) for day in value})
        if not cleaned:
            raise ValueError("weekly schedules need at least one weekday")
        if any(day < 0 or day > 6 for day in cleaned):
            raise ValueError("weekdays must be between 0 (Mon) and 6 (Sun)")
        return cleaned

    @field_validator("cron")
    @classmethod
    def _validate_cron(cls, value: Optional[str]) -> Optional[str]:
        """Validate a raw crontab expression eagerly so bad input fails at save time."""
        if value is None or not value.strip():
            return None
        try:
            CronTrigger.from_crontab(value.strip())
        except Exception as exc:  # noqa: BLE001 - surface any parser error to the caller
            raise ValueError(f"invalid cron expression: {exc}") from exc
        return value.strip()


def parse_time(value: str) -> tuple[int, int]:
    """Parse an ``HH:MM`` string into ``(hour, minute)``.

    Raises:
        ValueError: If the string is not a valid 24-hour time.
    """
    try:
        hour_str, minute_str = value.strip().split(":")
        hour, minute = int(hour_str), int(minute_str)
    except (AttributeError, ValueError) as exc:
        raise ValueError(f"time must be HH:MM, got {value!r}") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"time out of range: {value!r}")
    return hour, minute


def build_trigger(spec: ScheduleSpec) -> BaseTrigger:
    """Translate a :class:`ScheduleSpec` into an APScheduler trigger."""
    if spec.kind == "interval":
        return IntervalTrigger(hours=spec.interval_hours)

    if spec.kind == "cron":
        if not spec.cron:
            raise ValueError("cron schedule requires a cron expression")
        return CronTrigger.from_crontab(spec.cron)

    hour, minute = parse_time(spec.time)

    if spec.kind == "daily":
        return CronTrigger(hour=hour, minute=minute)

    if spec.kind == "weekly":
        day_of_week = ",".join(str(day) for day in spec.weekdays)
        return CronTrigger(day_of_week=day_of_week, hour=hour, minute=minute)

    if spec.kind == "monthly":
        return CronTrigger(day=spec.day_of_month, hour=hour, minute=minute)

    raise ValueError(f"unsupported schedule kind: {spec.kind}")


def spec_from_frequency(frequency: Optional[str]) -> Optional[ScheduleSpec]:
    """Convert a legacy ``refresh_frequency`` value into a :class:`ScheduleSpec`.

    Returns ``None`` for "none"/"never"/unknown values, meaning "do not schedule".
    """
    if not frequency:
        return None
    normalized = frequency.strip().lower()
    if normalized in ("none", "never", "manual", ""):
        return None
    if normalized == "daily":
        return ScheduleSpec(kind="daily", time="01:00")
    if normalized == "weekly":
        return ScheduleSpec(kind="weekly", time="01:00", weekdays=[0])
    if normalized == "monthly":
        return ScheduleSpec(kind="monthly", time="01:00", day_of_month=1)
    logger.warning("Unknown refresh_frequency %r, treating as manual", frequency)
    return None


def frequency_from_spec(spec: Optional[ScheduleSpec]) -> str:
    """Derive a legacy ``refresh_frequency`` label from a spec (for display/compat)."""
    if spec is None:
        return "none"
    if spec.kind == "daily":
        return "daily"
    if spec.kind == "weekly":
        return "weekly"
    if spec.kind == "monthly":
        return "monthly"
    return "custom"


def describe_schedule(spec: Optional[ScheduleSpec]) -> str:
    """Return a short human-readable description of a schedule."""
    if spec is None:
        return "Manual only"

    if spec.kind == "interval":
        hours = spec.interval_hours
        if hours % 24 == 0 and hours >= 24:
            days = hours // 24
            return f"Every {days} day{'s' if days != 1 else ''}"
        return f"Every {hours} hour{'s' if hours != 1 else ''}"

    if spec.kind == "cron":
        return f"Cron: {spec.cron}"

    hour, minute = parse_time(spec.time)
    clock = f"{hour:02d}:{minute:02d}"

    if spec.kind == "daily":
        return f"Daily at {clock}"

    if spec.kind == "weekly":
        days = ", ".join(WEEKDAY_NAMES[day] for day in spec.weekdays)
        return f"Weekly on {days} at {clock}"

    if spec.kind == "monthly":
        return f"Monthly on day {spec.day_of_month} at {clock}"

    return "Manual only"


def to_naive_local(value: Optional[datetime]) -> Optional[datetime]:
    """Normalise a datetime to naive server-local time.

    APScheduler returns timezone-aware datetimes (in the scheduler's timezone,
    which defaults to the server's local zone). The rest of the application
    stores and compares naive local datetimes, so every value crossing that
    boundary must be converted here. Mixing the two raises
    ``TypeError: can't compare offset-naive and offset-aware datetimes``.

    Args:
        value: A datetime, possibly timezone-aware.

    Returns:
        The same instant as a naive local datetime, or ``None``.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    # Convert to the server's local zone, then drop the tzinfo.
    return value.astimezone().replace(tzinfo=None)


def upcoming_runs(spec: Optional[ScheduleSpec], count: int = 3, now: Optional[datetime] = None) -> List[datetime]:
    """Return the next ``count`` fire times for a spec (used by the detail panel).

    All returned datetimes are naive server-local time.
    """
    if spec is None:
        return []
    try:
        trigger = build_trigger(spec)
    except Exception as exc:  # noqa: BLE001 - a bad stored spec must not break the API
        logger.warning("Could not build trigger for preview: %s", exc)
        return []

    runs: List[datetime] = []
    previous = to_naive_local(now) or datetime.now()
    for _ in range(max(0, count)):
        next_run = to_naive_local(trigger.get_next_fire_time(None, previous))
        if next_run is None:
            break
        runs.append(next_run)
        # Nudge forward by a second so the same instant is not returned twice.
        previous = next_run.replace(microsecond=0) + timedelta(seconds=1)
    return runs
