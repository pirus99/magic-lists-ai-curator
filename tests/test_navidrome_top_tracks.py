from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

@pytest.fixture
def anyio_backend():
    return "asyncio"

from backend.navidrome import NavidromeClient
from backend.services import top_tracks_service
from backend.services.track_scoring_service import calculate_track_score


def test_top_track_receives_fixed_score_bonus():
    assert calculate_track_score({"play_count": 10, "is_top_track": True}) == 165
    assert calculate_track_score({"play_count": 10}) == 15


@pytest.mark.anyio
async def test_get_top_songs_by_artist_uses_artist_name_and_slices(monkeypatch):
    monkeypatch.setenv("NAVIDROME_URL", "http://navidrome")
    client = NavidromeClient()
    client._ensure_authenticated = AsyncMock()
    client._get_subsonic_params = lambda: {"f": "json"}
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "subsonic-response": {
                "status": "ok",
                "topSongs": {
                    "song": [
                        {"id": str(index), "title": f"Song {index}", "artist": "ABBA", "album": "Album"}
                        for index in range(1, 6)
                    ]
                },
            }
        },
    )
    http_response = SimpleNamespace()
    client.client.get = AsyncMock(return_value=response)

    tracks = await client.get_top_songs_by_artist("ABBA", 3)

    assert [track["id"] for track in tracks] == ["1", "2", "3"]
    args, kwargs = client.client.get.await_args
    assert args[0].endswith("/rest/getTopSongs.view")
    assert kwargs["params"]["artist"] == "ABBA"
    await client.client.aclose()


@pytest.mark.anyio
async def test_top_tracks_service_keeps_jellyfin_enabled(monkeypatch):
    """Jellyfin is a supported top-track source, so settings are no longer zeroed out.

    Previously the feature was hard-gated to Navidrome, which hid the whole control in
    the UI. Jellyfin now resolves top tracks via Last.fm instead.
    """
    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.setenv("LASTFM_API_KEY", "key")

    assert top_tracks_service.top_tracks_settings(True, 5) == {
        "top_tracks_enabled": True,
        "top_tracks_count": 5,
    }


@pytest.mark.anyio
async def test_top_tracks_service_degrades_when_lastfm_unreachable(monkeypatch):
    """A missing client/failed lookup must yield no top tracks, never an exception."""
    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.delenv("JELLYFIN_URL", raising=False)

    result = await top_tracks_service.fetch_top_tracks(["artist"], [], 5)

    assert result == []


def test_this_is_top_tracks_allow_twenty_tracks(monkeypatch):
    monkeypatch.setenv("SERVER_TYPE", "navidrome")

    assert top_tracks_service.top_tracks_settings(True, 20, max_count=20) == {
        "top_tracks_enabled": True,
        "top_tracks_count": 20,
    }
