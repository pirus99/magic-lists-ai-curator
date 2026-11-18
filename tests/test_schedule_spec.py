"""Tests for the structured refresh-schedule specification."""
import os
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.schedule_spec import (
    ScheduleSpec,
    build_trigger,
    describe_schedule,
    frequency_from_spec,
    spec_from_frequency,
    to_naive_local,
    upcoming_runs,
)


def test_spec_from_frequency_maps_legacy_values():
    """Legacy frequency strings translate to the documented defaults."""
    daily = spec_from_frequency("daily")
    assert daily.kind == "daily"
    assert daily.time == "01:00"

    weekly = spec_from_frequency("weekly")
    assert weekly.kind == "weekly"
    assert weekly.weekdays == [0]

    monthly = spec_from_frequency("monthly")
    assert monthly.kind == "monthly"
    assert monthly.day_of_month == 1


@pytest.mark.parametrize("value", ["none", "never", "manual", "", None])
def test_spec_from_frequency_returns_none_for_manual(value):
    """Manual/absent frequencies produce no schedule."""
    assert spec_from_frequency(value) is None


def test_frequency_from_spec_round_trips():
    """Deriving a legacy label from a spec is stable for the simple kinds."""
    assert frequency_from_spec(spec_from_frequency("daily")) == "daily"
    assert frequency_from_spec(spec_from_frequency("weekly")) == "weekly"
    assert frequency_from_spec(spec_from_frequency("monthly")) == "monthly"
    assert frequency_from_spec(None) == "none"
    assert frequency_from_spec(ScheduleSpec(kind="interval", interval_hours=6)) == "custom"


def test_describe_schedule_is_human_readable():
    """Descriptions are what the UI shows, so they must be readable."""
    assert describe_schedule(None) == "Manual only"
    assert describe_schedule(ScheduleSpec(kind="daily", time="03:30")) == "Daily at 03:30"
    assert describe_schedule(
        ScheduleSpec(kind="weekly", time="04:00", weekdays=[0, 2])
    ) == "Weekly on Mon, Wed at 04:00"
    assert describe_schedule(
        ScheduleSpec(kind="monthly", time="02:00", day_of_month=15)
    ) == "Monthly on day 15 at 02:00"
    assert describe_schedule(ScheduleSpec(kind="interval", interval_hours=48)) == "Every 2 days"
    assert describe_schedule(ScheduleSpec(kind="interval", interval_hours=6)) == "Every 6 hours"


def test_invalid_time_is_rejected():
    """A malformed time must fail at validation time, not at fire time."""
    with pytest.raises(Exception):
        ScheduleSpec(kind="daily", time="25:00")
    with pytest.raises(Exception):
        ScheduleSpec(kind="daily", time="not-a-time")


def test_invalid_cron_is_rejected():
    """Bad cron expressions are rejected eagerly."""
    with pytest.raises(Exception):
        ScheduleSpec(kind="cron", cron="this is not cron")


def test_weekly_requires_at_least_one_day():
    """An empty weekday list would silently never fire."""
    with pytest.raises(Exception):
        ScheduleSpec(kind="weekly", weekdays=[])


def test_build_trigger_produces_future_runs():
    """Every supported kind yields a trigger with a future fire time."""
    now = datetime(2026, 1, 1, 12, 0, 0)
    specs = [
        ScheduleSpec(kind="daily", time="01:00"),
        ScheduleSpec(kind="weekly", time="01:00", weekdays=[0]),
        ScheduleSpec(kind="monthly", time="01:00", day_of_month=1),
        ScheduleSpec(kind="interval", interval_hours=6),
        ScheduleSpec(kind="cron", cron="0 3 * * 1"),
    ]
    for spec in specs:
        trigger = build_trigger(spec)
        next_run = trigger.get_next_fire_time(None, now)
        assert next_run is not None
        assert next_run > now


def test_upcoming_runs_returns_requested_count():
    """The detail panel previews several future runs."""
    spec = ScheduleSpec(kind="daily", time="01:00")
    runs = upcoming_runs(spec, count=3, now=datetime(2026, 1, 1, 12, 0, 0))
    assert len(runs) == 3
    assert runs == sorted(runs)
    assert len(set(runs)) == 3


def test_upcoming_runs_handles_manual_schedule():
    """A manual schedule has no upcoming runs."""
    assert upcoming_runs(None, count=3) == []


def test_spec_json_round_trip():
    """Specs survive the JSON round trip used by the database column."""
    spec = ScheduleSpec(kind="weekly", time="05:15", weekdays=[1, 3, 5])
    restored = ScheduleSpec.model_validate_json(spec.model_dump_json())
    assert restored == spec


def test_to_naive_local_strips_timezone():
    """Aware datetimes are converted to naive local time."""
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    naive = to_naive_local(aware)
    assert naive is not None
    assert naive.tzinfo is None


def test_to_naive_local_passes_through_naive():
    """Naive datetimes are returned unchanged."""
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert to_naive_local(naive) == naive


def test_to_naive_local_handles_none():
    """``None`` is passed through so callers can chain the helper."""
    assert to_naive_local(None) is None


def test_aware_and_naive_are_comparable_after_normalisation():
    """Regression: mixing aware and naive datetimes raised TypeError on startup.

    APScheduler returns tz-aware fire times; comparing them directly against
    ``datetime.now()`` crashed job rehydration.
    """
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    now = datetime(2026, 1, 1, 13, 0, 0)

    # This is what used to raise: aware >= naive
    with pytest.raises(TypeError):
        _ = aware >= now

    # After normalisation the comparison is safe.
    assert to_naive_local(aware) < now


def test_upcoming_runs_returns_naive_datetimes():
    """Preview runs must be naive so the API can serialise and compare them."""
    spec = ScheduleSpec(kind="daily", time="01:00")
    runs = upcoming_runs(spec, count=2, now=datetime(2026, 1, 1, 12, 0, 0))
    assert runs
    assert all(run.tzinfo is None for run in runs)
