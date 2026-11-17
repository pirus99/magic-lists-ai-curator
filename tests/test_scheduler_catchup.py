"""Tests for startup catch-up behaviour.

Regression coverage for the bug where a restart re-refreshed playlists that had
already been refreshed recently: ``next_refresh`` was never advanced after a
run, so every restart saw the schedule as overdue.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core import scheduler as scheduler_module
from backend.database import DatabaseManager


@pytest.fixture
def db(tmp_path):
    """A fresh database in a temporary directory."""
    return DatabaseManager(str(tmp_path / "scheduler.db"))


def _seed_schedule(db, *, next_refresh, last_refreshed, server_id="p1"):
    """Insert a playlist plus a schedule row with explicit timestamps."""
    async def scenario():
        await db.init_db()
        await db.create_playlist(
            artist_id="a1",
            playlist_name="Test Playlist",
            navidrome_playlist_id=server_id,
            playlist_type="genre_mix",
        )
        await db.upsert_schedule(
            playlist_type="genre_mix",
            navidrome_playlist_id=server_id,
            refresh_frequency="daily",
            next_refresh=next_refresh,
            schedule_json='{"kind": "daily", "time": "01:00", "weekdays": [0], '
                          '"day_of_month": 1, "interval_hours": 24, "cron": null}',
        )
        # last_refreshed is written by update_playlist_content in production.
        import aiosqlite
        async with aiosqlite.connect(db.db_path) as conn:
            await conn.execute(
                "UPDATE playlists SET last_refreshed = ? WHERE navidrome_playlist_id = ?",
                (last_refreshed.isoformat(), server_id),
            )
            await conn.commit()

    asyncio.run(scenario())


def test_recently_refreshed_playlist_is_not_requeued(db, monkeypatch):
    """A playlist refreshed after it became due must not be caught up again."""
    now = datetime.now()
    # Schedule became due an hour ago, but the playlist was refreshed 30 min ago.
    _seed_schedule(
        db,
        next_refresh=now - timedelta(hours=1),
        last_refreshed=now - timedelta(minutes=30),
    )

    queued = []

    async def fake_enqueue(server_id, playlist_type, playlist_name=None):
        queued.append(server_id)
        return True

    monkeypatch.setattr(scheduler_module, "enqueue_scheduled_refresh", fake_enqueue)
    monkeypatch.setattr(scheduler_module, "sync_playlist_job", lambda row: True)

    asyncio.run(scheduler_module.rehydrate_jobs(db))

    assert queued == [], "already-refreshed playlist must not be re-queued"


def test_genuinely_overdue_playlist_is_requeued(db, monkeypatch):
    """A playlist that has not been refreshed since it became due is caught up."""
    now = datetime.now()
    _seed_schedule(
        db,
        next_refresh=now - timedelta(hours=1),
        last_refreshed=now - timedelta(days=2),
    )

    queued = []

    async def fake_enqueue(server_id, playlist_type, playlist_name=None):
        queued.append(server_id)
        return True

    monkeypatch.setattr(scheduler_module, "enqueue_scheduled_refresh", fake_enqueue)
    monkeypatch.setattr(scheduler_module, "sync_playlist_job", lambda row: True)

    asyncio.run(scheduler_module.rehydrate_jobs(db))

    assert queued == ["p1"]


def test_never_refreshed_playlist_is_requeued(db, monkeypatch):
    """A playlist with no last_refreshed value is treated as overdue."""
    now = datetime.now()
    _seed_schedule(
        db,
        next_refresh=now - timedelta(hours=1),
        last_refreshed=None,
    )

    queued = []

    async def fake_enqueue(server_id, playlist_type, playlist_name=None):
        queued.append(server_id)
        return True

    monkeypatch.setattr(scheduler_module, "enqueue_scheduled_refresh", fake_enqueue)
    monkeypatch.setattr(scheduler_module, "sync_playlist_job", lambda row: True)

    asyncio.run(scheduler_module.rehydrate_jobs(db))

    assert queued == ["p1"]


def test_advance_next_refresh_moves_timestamp_forward(db):
    """After a refresh the stored next_refresh must be in the future."""
    past = datetime.now() - timedelta(hours=5)
    _seed_schedule(db, next_refresh=past, last_refreshed=None)

    asyncio.run(scheduler_module.advance_next_refresh(db, "p1"))

    async def read():
        return await db.get_schedule_by_navidrome_id("p1")

    row = asyncio.run(read())
    assert row is not None
    stored = datetime.fromisoformat(row["next_refresh"])
    assert stored > datetime.now(), "next_refresh should have been advanced"


def test_advance_next_refresh_is_safe_without_schedule(db):
    """Advancing a playlist with no schedule row must not raise."""
    async def scenario():
        await db.init_db()
        await scheduler_module.advance_next_refresh(db, "does-not-exist")

    asyncio.run(scenario())
