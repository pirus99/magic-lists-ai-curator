"""Tests for reconciling locally-tracked playlists with the media server.

Covers the scenario where a playlist is deleted directly in Navidrome/Jellyfin
and therefore lingers in Magic Lists, and where deleting it again from Magic
Lists must not fail with "playlist not found".
"""
import asyncio
import os
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import DatabaseManager
from backend.services.playlist_sync_service import reconcile_playlists_with_server


# (server playlist id, display name) for the seeded fixtures.
SEED_PLAYLISTS = [
    ("111", "Still There"),
    ("222", "Deleted in Navidrome"),
    ("333", "Deleted in Jellyfin"),
]


async def _seed_db(tmp_path) -> DatabaseManager:
    """Create a database containing all three seeded playlists."""
    db = DatabaseManager(str(tmp_path / "test.db"))
    await db.init_db()

    for server_id, name in SEED_PLAYLISTS:
        await db.create_playlist(
            artist_id="a1",
            playlist_name=name,
            navidrome_playlist_id=server_id,
            playlist_type="this_is",
        )
        await db.create_scheduled_playlist(
            playlist_type="this_is",
            navidrome_playlist_id=server_id,
            refresh_frequency="daily",
            next_refresh=datetime.now(),
        )

    return db


def _make_db(tmp_path) -> DatabaseManager:
    return asyncio.run(_seed_db(tmp_path))


async def _remaining_server_ids(db) -> set:
    return {
        p["navidrome_playlist_id"]
        for p in await db.get_all_playlists_with_schedule_info()
    }


async def _remaining_schedule_ids(db) -> set:
    rows = await db.get_scheduled_playlists_due(
        datetime.now(), grace_hours=10_000
    )
    return {sp.navidrome_playlist_id for sp in rows}


def _reconcile(db, existing_ids):
    """Run one reconciliation pass against a fake server holding `existing_ids`."""
    client = AsyncMock()
    client.get_playlist_ids.return_value = set(existing_ids)
    with patch(
        "backend.services.playlist_sync_service.get_server_client",
        return_value=client,
    ):
        return asyncio.run(reconcile_playlists_with_server(db))


def test_reconcile_removes_playlists_missing_from_server(tmp_path):
    """Playlists deleted on the server are dropped from the local DB."""
    db = _make_db(tmp_path)

    result = _reconcile(db, ["111"])

    assert result["orphaned"] is False
    assert result["checked"] == 3
    assert set(result["removed_names"]) == {
        "Deleted in Navidrome",
        "Deleted in Jellyfin",
    }
    assert len(result["removed_ids"]) == 2
    assert asyncio.run(_remaining_server_ids(db)) == {"111"}


def test_reconcile_keeps_playlists_still_on_server(tmp_path):
    """A full match is a no-op."""
    db = _make_db(tmp_path)

    result = _reconcile(db, ["111", "222", "333"])

    assert result["removed_ids"] == []
    assert asyncio.run(_remaining_server_ids(db)) == {"111", "222", "333"}


def test_reconcile_never_deletes_when_server_unreachable(tmp_path):
    """A network failure must not destroy local tracking data."""
    db = _make_db(tmp_path)

    client = AsyncMock()
    client.get_playlist_ids.side_effect = Exception("connection refused")
    with patch(
        "backend.services.playlist_sync_service.get_server_client",
        return_value=client,
    ):
        result = asyncio.run(reconcile_playlists_with_server(db))

    assert result["orphaned"] is True
    assert result["removed_ids"] == []
    assert asyncio.run(_remaining_server_ids(db)) == {"111", "222", "333"}


def test_reconcile_drops_schedules_for_missing_playlists(tmp_path):
    """Schedules are removed so the scheduler stops refreshing dead playlists."""
    db = _make_db(tmp_path)

    _reconcile(db, ["111"])

    assert asyncio.run(_remaining_schedule_ids(db)) == {"111"}


def _navidrome_client():
    """Build a NavidromeClient with auth + HTTP stubbed out."""
    from backend.navidrome import NavidromeClient

    env = {
        "NAVIDROME_URL": "http://nd",
        "NAVIDROME_USERNAME": "u",
        "NAVIDROME_PASSWORD": "p",
    }
    with patch.dict(os.environ, env):
        client = NavidromeClient()

    client._ensure_authenticated = AsyncMock()
    client._get_subsonic_params = lambda: {}
    client.client = AsyncMock()
    return client


def _jellyfin_client():
    """Build a JellyfinClient with auth + HTTP stubbed out."""
    from backend.jellyfin import JellyfinClient

    env = {
        "SERVER_TYPE": "jellyfin",
        "JELLYFIN_URL": "http://jf",
        "JELLYFIN_API_KEY": "key",
    }
    with patch.dict(os.environ, env):
        client = JellyfinClient()

    client._ensure_authenticated = AsyncMock()
    client._get_auth_headers = lambda: {}
    client.client = AsyncMock()
    return client


def test_navidrome_delete_is_idempotent_for_missing_playlist():
    """Deleting an already-deleted Navidrome playlist reports success."""
    client = _navidrome_client()

    # httpx.Response.raise_for_status() is synchronous -> use a MagicMock.
    response = MagicMock()
    response.json.return_value = {
        "subsonic-response": {
            "status": "failed",
            "error": {"code": 70, "message": "Playlist not found"},
        }
    }
    client.client.get.return_value = response

    assert asyncio.run(client.delete_playlist("gone")) is True


def test_navidrome_delete_still_raises_on_real_errors():
    """Non-"not found" Subsonic errors must still surface."""
    client = _navidrome_client()

    response = MagicMock()
    response.json.return_value = {
        "subsonic-response": {
            "status": "failed",
            "error": {"code": 0, "message": "Generic error"},
        }
    }
    client.client.get.return_value = response

    with pytest.raises(Exception, match="Generic error"):
        asyncio.run(client.delete_playlist("broken"))


def test_navidrome_get_playlist_ids_parses_response():
    """get_playlist_ids returns the set of ids reported by getPlaylists."""
    client = _navidrome_client()

    response = MagicMock()
    response.json.return_value = {
        "subsonic-response": {
            "status": "ok",
            "playlists": {
                "playlist": [
                    {"id": "1", "name": "A"},
                    {"id": "2", "name": "B"},
                ]
            },
        }
    }
    client.client.get.return_value = response

    assert asyncio.run(client.get_playlist_ids()) == {"1", "2"}


def test_jellyfin_delete_treats_404_as_deleted():
    """Jellyfin's DELETE /Items/{id} returning 404 counts as already deleted."""
    client = _jellyfin_client()

    response = MagicMock()
    response.status_code = 404
    client.client.delete.return_value = response

    assert asyncio.run(client.delete_playlist("gone")) is True
    response.raise_for_status.assert_not_called()


def test_jellyfin_get_playlist_ids_parses_response():
    """get_playlist_ids returns the set of ids from GET /Playlists."""
    client = _jellyfin_client()
    # API-key auth has no user, so /Users would be queried first.
    client._resolve_user_id = AsyncMock(return_value="user1")

    response = MagicMock()
    response.json.return_value = {
        "Items": [{"Id": "p1"}, {"Id": "p2"}, {"Id": None}]
    }
    client.client.get.return_value = response

    assert asyncio.run(client.get_playlist_ids()) == {"p1", "p2"}
