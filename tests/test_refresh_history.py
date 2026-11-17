"""Tests for refresh-history storage and pruning."""
import os
import sys
from datetime import datetime

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import DatabaseManager
from backend.database.history import MAX_ROWS_PER_PLAYLIST


@pytest.fixture
def db(tmp_path):
    """A fresh database in a temporary directory."""
    return DatabaseManager(str(tmp_path / "history.db"))


def test_record_and_read_history(db):
    """A recorded refresh is returned newest-first."""
    async def scenario():
        await db.init_db()
        await db.record_refresh(
            navidrome_playlist_id="p1",
            status="success",
            started_at=datetime(2026, 1, 1, 1, 0, 0),
            finished_at=datetime(2026, 1, 1, 1, 0, 30),
            duration_seconds=30.0,
            track_count=25,
            playlist_name="One",
            playlist_type="this_is",
        )
        await db.record_refresh(
            navidrome_playlist_id="p1",
            status="failed",
            started_at=datetime(2026, 1, 2, 1, 0, 0),
            finished_at=datetime(2026, 1, 2, 1, 0, 5),
            duration_seconds=5.0,
            error="boom",
            playlist_name="One",
            playlist_type="this_is",
        )

        rows = await db.get_recent_refreshes("p1")
        assert len(rows) == 2
        assert rows[0]["status"] == "failed"
        assert rows[0]["error"] == "boom"
        assert rows[1]["status"] == "success"
        assert rows[1]["track_count"] == 25

    import asyncio
    asyncio.run(scenario())


def test_history_is_pruned_per_playlist(db):
    """Only the newest MAX_ROWS_PER_PLAYLIST rows are retained."""
    async def scenario():
        await db.init_db()
        for index in range(MAX_ROWS_PER_PLAYLIST + 5):
            await db.record_refresh(
                navidrome_playlist_id="p1",
                status="success",
                started_at=datetime(2026, 1, 1, 0, index % 60, 0),
                finished_at=datetime(2026, 1, 1, 0, index % 60, 1),
                duration_seconds=1.0,
                track_count=index,
            )

        rows = await db.get_recent_refreshes("p1", limit=100)
        assert len(rows) == MAX_ROWS_PER_PLAYLIST
        # Newest first: the last inserted row has the highest track_count.
        assert rows[0]["track_count"] == MAX_ROWS_PER_PLAYLIST + 4

    import asyncio
    asyncio.run(scenario())


def test_latest_per_playlist(db):
    """The overview page needs exactly one (newest) row per playlist."""
    async def scenario():
        await db.init_db()
        for server_id in ("p1", "p2"):
            await db.record_refresh(
                navidrome_playlist_id=server_id,
                status="success",
                started_at=datetime(2026, 1, 1, 1, 0, 0),
                finished_at=datetime(2026, 1, 1, 1, 0, 1),
                duration_seconds=1.0,
                track_count=10,
            )
        await db.record_refresh(
            navidrome_playlist_id="p1",
            status="failed",
            started_at=datetime(2026, 1, 2, 1, 0, 0),
            finished_at=datetime(2026, 1, 2, 1, 0, 1),
            duration_seconds=1.0,
            error="later failure",
        )

        latest = await db.get_latest_refresh_per_playlist()
        assert set(latest) == {"p1", "p2"}
        assert latest["p1"]["status"] == "failed"
        assert latest["p2"]["status"] == "success"

    import asyncio
    asyncio.run(scenario())


def test_clear_history_for_one_playlist(db):
    """Clearing one playlist leaves the others untouched."""
    async def scenario():
        await db.init_db()
        for server_id in ("p1", "p2"):
            await db.record_refresh(
                navidrome_playlist_id=server_id,
                status="success",
                started_at=datetime(2026, 1, 1, 1, 0, 0),
                finished_at=datetime(2026, 1, 1, 1, 0, 1),
                duration_seconds=1.0,
                track_count=10,
            )

        removed = await db.clear_refresh_history("p1")
        assert removed == 1
        assert await db.get_recent_refreshes("p1") == []
        assert len(await db.get_recent_refreshes("p2")) == 1

    import asyncio
    asyncio.run(scenario())


def test_clear_all_history(db):
    """Clearing everything empties the table."""
    async def scenario():
        await db.init_db()
        for server_id in ("p1", "p2"):
            await db.record_refresh(
                navidrome_playlist_id=server_id,
                status="success",
                started_at=datetime(2026, 1, 1, 1, 0, 0),
                finished_at=datetime(2026, 1, 1, 1, 0, 1),
                duration_seconds=1.0,
                track_count=10,
            )

        removed = await db.clear_refresh_history()
        assert removed == 2
        assert await db.get_latest_refresh_per_playlist() == {}

    import asyncio
    asyncio.run(scenario())
