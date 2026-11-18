"""Tests for the throttled refresh queue.

The queue is the component that guarantees two playlists never refresh at the
same time and that consecutive refreshes are spaced out.
"""
import asyncio
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core import refresh_queue as queue_module
from backend.core.refresh_queue import RefreshJob, RefreshQueue


class _FakeDb:
    """Minimal stand-in for DatabaseManager used by the queue worker."""

    def __init__(self, playlists):
        self.playlists = playlists
        self.records = []

    async def get_playlist_by_navidrome_id_with_schedule_info(self, server_id):
        return self.playlists.get(server_id)

    async def record_refresh(self, **kwargs):
        self.records.append(kwargs)


@pytest.fixture
def fake_db(monkeypatch):
    """Patch the queue's database factory to return a controllable fake."""
    playlists = {
        "p1": {"navidrome_playlist_id": "p1", "playlist_name": "One", "playlist_type": "this_is"},
        "p2": {"navidrome_playlist_id": "p2", "playlist_name": "Two", "playlist_type": "this_is"},
        "p3": {"navidrome_playlist_id": "p3", "playlist_name": "Three", "playlist_type": "this_is"},
    }
    db = _FakeDb(playlists)
    monkeypatch.setattr(queue_module, "DatabaseManager", lambda *a, **k: db)
    monkeypatch.setattr(queue_module, "get_database_path", lambda: ":memory:")
    return db


def test_submit_deduplicates_in_flight_playlists():
    """A playlist already queued cannot be queued a second time."""
    async def scenario():
        queue = RefreshQueue(max_concurrency=1, min_gap_seconds=0)
        job = RefreshJob(navidrome_playlist_id="p1", playlist_type="this_is")

        assert await queue.submit(job) is True
        assert await queue.submit(job) is False
        assert queue.is_busy("p1") is True

    asyncio.run(scenario())


def test_snapshot_reports_queue_state():
    """The status API relies on the snapshot shape."""
    async def scenario():
        queue = RefreshQueue(max_concurrency=1, min_gap_seconds=0)
        await queue.submit(RefreshJob(navidrome_playlist_id="p1", playlist_type="this_is"))

        snapshot = queue.snapshot()
        assert snapshot["max_concurrency"] == 1
        assert snapshot["min_gap_seconds"] == 0
        assert len(snapshot["queued"]) == 1
        assert snapshot["queued"][0]["navidrome_playlist_id"] == "p1"
        assert snapshot["running"] is None

    asyncio.run(scenario())


def test_worker_never_runs_two_refreshes_concurrently(fake_db, monkeypatch):
    """With max_concurrency=1 the handlers must never overlap."""
    overlap = {"max": 0, "current": 0}

    async def handler(playlist, db):
        overlap["current"] += 1
        overlap["max"] = max(overlap["max"], overlap["current"])
        await asyncio.sleep(0.02)
        overlap["current"] -= 1
        return 5

    monkeypatch.setattr(
        "backend.core.scheduler._REFRESH_REGISTRY",
        {"this_is": handler},
        raising=False,
    )

    async def scenario():
        queue = RefreshQueue(max_concurrency=1, min_gap_seconds=0)
        queue.start()
        try:
            for server_id in ("p1", "p2", "p3"):
                await queue.submit(
                    RefreshJob(navidrome_playlist_id=server_id, playlist_type="this_is")
                )
            # Wait for the queue to drain.
            await asyncio.wait_for(queue._queue.join(), timeout=5)
        finally:
            await queue.stop()

    asyncio.run(scenario())
    assert overlap["max"] == 1
    assert len(fake_db.records) == 3
    assert all(record["status"] == "success" for record in fake_db.records)


def test_worker_records_failures(fake_db, monkeypatch):
    """A raising handler is recorded as a failed refresh, not swallowed."""
    async def handler(playlist, db):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "backend.core.scheduler._REFRESH_REGISTRY",
        {"this_is": handler},
        raising=False,
    )

    async def scenario():
        queue = RefreshQueue(max_concurrency=1, min_gap_seconds=0)
        queue.start()
        try:
            await queue.submit(RefreshJob(navidrome_playlist_id="p1", playlist_type="this_is"))
            await asyncio.wait_for(queue._queue.join(), timeout=5)
        finally:
            await queue.stop()

    asyncio.run(scenario())
    assert len(fake_db.records) == 1
    assert fake_db.records[0]["status"] == "failed"
    assert "boom" in fake_db.records[0]["error"]


def test_worker_records_missing_handler(fake_db, monkeypatch):
    """An unregistered playlist type fails loudly instead of silently."""
    monkeypatch.setattr(
        "backend.core.scheduler._REFRESH_REGISTRY",
        {},
        raising=False,
    )

    async def scenario():
        queue = RefreshQueue(max_concurrency=1, min_gap_seconds=0)
        queue.start()
        try:
            await queue.submit(RefreshJob(navidrome_playlist_id="p1", playlist_type="unknown"))
            await asyncio.wait_for(queue._queue.join(), timeout=5)
        finally:
            await queue.stop()

    asyncio.run(scenario())
    assert len(fake_db.records) == 1
    assert fake_db.records[0]["status"] == "failed"
    assert "No refresh handler" in fake_db.records[0]["error"]


def test_min_gap_is_enforced_between_starts(fake_db, monkeypatch):
    """Consecutive refreshes are spaced by at least min_gap_seconds."""
    starts = []

    async def handler(playlist, db):
        starts.append(datetime.now())
        return 1

    monkeypatch.setattr(
        "backend.core.scheduler._REFRESH_REGISTRY",
        {"this_is": handler},
        raising=False,
    )

    async def scenario():
        queue = RefreshQueue(max_concurrency=1, min_gap_seconds=1)
        queue.start()
        try:
            await queue.submit(RefreshJob(navidrome_playlist_id="p1", playlist_type="this_is"))
            await queue.submit(RefreshJob(navidrome_playlist_id="p2", playlist_type="this_is"))
            await asyncio.wait_for(queue._queue.join(), timeout=10)
        finally:
            await queue.stop()

    asyncio.run(scenario())
    assert len(starts) == 2
    gap = (starts[1] - starts[0]).total_seconds()
    assert gap >= 0.9, f"expected >= ~1s gap, got {gap}"
