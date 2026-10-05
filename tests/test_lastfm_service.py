"""Tests for Last.fm top-track resolution and the top-track strategy selection."""
import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.services import top_tracks_service
from backend.services.lastfm_client import LastFmClient
from backend.services.lastfm_service import (
    TOP_TRACK_STRATEGY_LABELS,
    artists_match,
    normalize_artist,
    normalize_title,
    resolve_top_tracks,
    top_tracks_strategy_label,
)


def run(coro):
    """Run an async coroutine (repo convention: no pytest-asyncio)."""
    return asyncio.run(coro)


class FakeLastFmClient:
    """Minimal Last.fm client stand-in returning canned top tracks."""

    def __init__(self, tracks=None, configured=True, error=None):
        self._tracks = tracks or []
        self._configured = configured
        self._error = error
        self.calls = []

    def is_configured(self):
        return self._configured

    async def get_top_tracks(self, artist_name, *, artist_mbid=None, limit=50):
        self.calls.append(("top", artist_name, artist_mbid, limit))
        if self._error:
            raise self._error
        return self._tracks[:limit]


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Creep - Remastered 2011", "creep"),
        ("Everything In Its Right Place - 2011 Remaster", "everything in its right place"),
        ("No Surprises - Live at Wembley", "no surprises"),
        ("Roads - Portishead Remix", "roads"),
        ("One More Time - Radio Edit", "one more time"),
        ("Karma Police (feat. Someone)", "karma police"),
        ("Song [Acoustic]", "song"),
        ("Rocket Man (I Think It's Going To Be A Long, Long Time)", "rocket man"),
        ("A Day in the Life", "a day in the life"),
        ("1999", "1999"),
    ],
)
def test_normalize_title_strips_noise_but_keeps_real_titles(raw, expected):
    assert normalize_title(raw) == expected


def test_normalize_title_of_pure_noise_is_empty():
    assert normalize_title("(Remastered)") == ""


def test_normalize_artist_handles_accents_and_case():
    assert normalize_artist("Björk") == "bjork"
    assert normalize_artist("BEATLES") == "beatles"


def test_artists_match_tolerates_leading_the_and_missing_values():
    assert artists_match("The Beatles", "Beatles") is True
    assert artists_match("Beatles", "The Beatles") is True
    assert artists_match("", "Beatles") is True
    assert artists_match("ABBA", "Madonna") is False


# ---------------------------------------------------------------------------
# Top-track resolution
# ---------------------------------------------------------------------------
def local_tracks():
    return [
        {"id": "1", "title": "Creep", "artist": "Radiohead", "play_count": 5},
        {"id": "2", "title": "Karma Police", "artist": "Radiohead", "play_count": 3},
        {"id": "3", "title": "Paranoid Android", "artist": "Radiohead", "play_count": 9},
    ]


def test_resolve_top_tracks_preserves_local_ids_and_lastfm_order():
    client = FakeLastFmClient(tracks=[
        {"name": "Paranoid Android", "artist": "Radiohead"},
        {"name": "Creep", "artist": "Radiohead"},
    ])
    result = run(resolve_top_tracks("Radiohead", local_tracks(), limit=5, client=client))
    assert [t["id"] for t in result] == ["3", "1"]
    assert all(t["is_top_track"] for t in result)


def test_resolve_top_tracks_matches_through_noise_suffixes():
    client = FakeLastFmClient(tracks=[
        {"name": "Creep - Remastered 2011", "artist": "Radiohead"},
    ])
    result = run(resolve_top_tracks("Radiohead", local_tracks(), limit=5, client=client))
    assert [t["id"] for t in result] == ["1"]


def test_resolve_top_tracks_does_not_reuse_a_local_track():
    client = FakeLastFmClient(tracks=[
        {"name": "Creep", "artist": "Radiohead"},
        {"name": "Creep", "artist": "Radiohead"},
    ])
    result = run(resolve_top_tracks("Radiohead", local_tracks(), limit=5, client=client))
    assert [t["id"] for t in result] == ["1"]


def test_resolve_top_tracks_returns_empty_when_nothing_matches():
    client = FakeLastFmClient(tracks=[{"name": "Unknown Song", "artist": "Radiohead"}])
    assert run(resolve_top_tracks("Radiohead", local_tracks(), client=client)) == []


def test_resolve_top_tracks_returns_empty_when_api_errors():
    client = FakeLastFmClient(error=RuntimeError("Last.fm returned HTTP 403"))
    assert run(resolve_top_tracks("Radiohead", local_tracks(), client=client)) == []


def test_resolve_top_tracks_returns_empty_when_not_configured():
    client = FakeLastFmClient(tracks=[{"name": "Creep"}], configured=False)
    assert run(resolve_top_tracks("Radiohead", local_tracks(), client=client)) == []
    assert client.calls == []


def test_resolve_top_tracks_does_not_mutate_the_local_tracks():
    tracks = local_tracks()
    client = FakeLastFmClient(tracks=[{"name": "Creep", "artist": "Radiohead"}])
    run(resolve_top_tracks("Radiohead", tracks, client=client))
    assert "is_top_track" not in tracks[0]


def test_resolve_top_tracks_respects_limit():
    client = FakeLastFmClient(tracks=[
        {"name": "Creep", "artist": "Radiohead"},
        {"name": "Karma Police", "artist": "Radiohead"},
        {"name": "Paranoid Android", "artist": "Radiohead"},
    ])
    result = run(resolve_top_tracks("Radiohead", local_tracks(), limit=2, client=client))
    assert len(result) == 2


# ---------------------------------------------------------------------------
# MBID override plumbing
# ---------------------------------------------------------------------------
def test_resolve_top_tracks_forwards_user_mbid():
    client = FakeLastFmClient(tracks=[{"name": "Creep", "artist": "Radiohead"}])
    run(resolve_top_tracks("Radiohead", local_tracks(), limit=5, artist_mbid="user-mbid", client=client))
    assert client.calls == [("top", "Radiohead", "user-mbid", 5)]


def test_resolve_top_tracks_falls_back_to_artist_name_without_mbid():
    client = FakeLastFmClient(tracks=[{"name": "Creep", "artist": "Radiohead"}])
    run(resolve_top_tracks("Radiohead", local_tracks(), limit=5, client=client))
    assert client.calls == [("top", "Radiohead", None, 5)]


def test_jellyfin_top_tracks_prefers_user_mbid_over_library(monkeypatch):
    """A user-supplied MBID must win over the library's own value."""
    from backend.jellyfin import JellyfinClient

    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.setenv("JELLYFIN_URL", "http://jellyfin")
    monkeypatch.setenv("JELLYFIN_API_KEY", "key")

    client = JellyfinClient()
    client.find_artist_by_name = AsyncMock(
        return_value={"id": "a1", "name": "Radiohead", "mbid": "library-mbid"}
    )
    client.get_tracks_by_artist = AsyncMock(return_value=[
        {"id": "jf-1", "title": "Creep", "artist": "Radiohead"},
    ])

    fake = FakeLastFmClient(tracks=[{"name": "Creep", "artist": "Radiohead"}])

    async def fake_resolve(artist_name, local, *, artist_mbid=None, limit=20):
        return await resolve_top_tracks(
            artist_name, local, artist_mbid=artist_mbid, limit=limit, client=fake
        )

    monkeypatch.setattr("backend.jellyfin.tracks.resolve_top_tracks", fake_resolve)

    tracks = run(client.get_top_songs_by_artist("Radiohead", 5, artist_mbid="user-mbid"))
    assert [t["id"] for t in tracks] == ["jf-1"]
    assert fake.calls[0][2] == "user-mbid"


def test_jellyfin_top_tracks_uses_library_mbid_without_override(monkeypatch):
    from backend.jellyfin import JellyfinClient

    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.setenv("JELLYFIN_URL", "http://jellyfin")
    monkeypatch.setenv("JELLYFIN_API_KEY", "key")

    client = JellyfinClient()
    client.find_artist_by_name = AsyncMock(
        return_value={"id": "a1", "name": "Radiohead", "mbid": "library-mbid"}
    )
    client.get_tracks_by_artist = AsyncMock(return_value=[
        {"id": "jf-1", "title": "Creep", "artist": "Radiohead"},
    ])

    fake = FakeLastFmClient(tracks=[{"name": "Creep", "artist": "Radiohead"}])

    async def fake_resolve(artist_name, local, *, artist_mbid=None, limit=20):
        return await resolve_top_tracks(
            artist_name, local, artist_mbid=artist_mbid, limit=limit, client=fake
        )

    monkeypatch.setattr("backend.jellyfin.tracks.resolve_top_tracks", fake_resolve)

    run(client.get_top_songs_by_artist("Radiohead", 5))
    assert fake.calls[0][2] == "library-mbid"


def test_both_clients_accept_the_same_signature():
    """Shared code passes artist_mbid; both clients must accept it."""
    import inspect

    from backend.jellyfin import JellyfinClient
    from backend.navidrome import NavidromeClient

    for cls in (NavidromeClient, JellyfinClient):
        params = inspect.signature(cls.get_top_songs_by_artist).parameters
        assert "artist_mbid" in params, f"{cls.__name__} is missing artist_mbid"
        assert params["artist_mbid"].default is None


# ---------------------------------------------------------------------------
# Strategy selection + labels
# ---------------------------------------------------------------------------
def test_strategy_is_native_on_navidrome(monkeypatch):
    monkeypatch.setenv("SERVER_TYPE", "navidrome")
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    assert top_tracks_service.top_tracks_strategy() == "native"
    assert top_tracks_service.top_tracks_supported() is True


def test_strategy_is_lastfm_on_jellyfin_even_without_key(monkeypatch):
    """The strategy reflects capability, so the UI can keep the control visible."""
    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    assert top_tracks_service.top_tracks_strategy() == "lastfm"
    assert top_tracks_service.top_tracks_supported() is True
    # ...but it is not usable yet, which the UI surfaces as a setup prompt.
    assert top_tracks_service.top_tracks_configured() is False


def test_strategy_is_configured_on_jellyfin_with_key(monkeypatch):
    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.setenv("LASTFM_API_KEY", "key")
    assert top_tracks_service.top_tracks_strategy() == "lastfm"
    assert top_tracks_service.top_tracks_configured() is True


def test_navidrome_is_always_configured(monkeypatch):
    monkeypatch.setenv("SERVER_TYPE", "navidrome")
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    assert top_tracks_service.top_tracks_supported() is True
    assert top_tracks_service.top_tracks_configured() is True


def test_top_tracks_settings_preserved_for_jellyfin(monkeypatch):
    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.setenv("LASTFM_API_KEY", "key")
    assert top_tracks_service.top_tracks_settings(True, 15, max_count=20) == {
        "top_tracks_enabled": True,
        "top_tracks_count": 15,
    }


def test_top_tracks_settings_preserved_without_lastfm_key(monkeypatch):
    """Settings survive so a stored preference isn't lost while Last.fm is unconfigured."""
    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.delenv("LASTFM_API_KEY", raising=False)
    assert top_tracks_service.top_tracks_settings(True, 15, max_count=20) == {
        "top_tracks_enabled": True,
        "top_tracks_count": 15,
    }


def test_top_tracks_settings_disabled_on_unknown_server_type(monkeypatch):
    monkeypatch.setenv("SERVER_TYPE", "something-else")
    assert top_tracks_service.top_tracks_supported() is False
    assert top_tracks_service.top_tracks_settings(True, 15, max_count=20) == {
        "top_tracks_enabled": False,
        "top_tracks_count": 0,
    }


def test_top_tracks_settings_clamps_count(monkeypatch):
    monkeypatch.setenv("SERVER_TYPE", "navidrome")
    assert top_tracks_service.top_tracks_settings(True, 999, max_count=20)["top_tracks_count"] == 20
    assert top_tracks_service.top_tracks_settings(True, -5)["top_tracks_enabled"] is False


def test_strategy_labels_are_short_and_stable():
    assert TOP_TRACK_STRATEGY_LABELS == {
        "native": "Native",
        "lastfm": "Last.fm",
        "hybrid": "Hybrid",
        "off": "Off",
    }
    assert top_tracks_strategy_label("lastfm") == "Last.fm"
    assert top_tracks_strategy_label("unknown-key") == "unknown-key"


# ---------------------------------------------------------------------------
# Client behaviour
# ---------------------------------------------------------------------------
def test_client_requires_api_key():
    client = LastFmClient()
    previous = os.environ.pop("LASTFM_API_KEY", None)
    try:
        assert client.is_configured() is False
        with pytest.raises(RuntimeError, match="LASTFM_API_KEY"):
            run(client.get_top_tracks("Radiohead"))
    finally:
        if previous is not None:
            os.environ["LASTFM_API_KEY"] = previous


def test_client_parses_top_tracks(monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "key")
    client = LastFmClient()
    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {
            "result": {
                "toptracks": {
                    "track": [
                        {
                            "name": "Creep",
                            "artist": {"name": "Radiohead", "mbid": "a74b"},
                            "listeners": "1000",
                            "playcount": "5000",
                            "@attr": {"rank": "1"},
                            "url": "https://example.test",
                        }
                    ]
                }
            }
        },
    )
    client.client.get = AsyncMock(return_value=response)

    tracks = run(client.get_top_tracks("Radiohead", limit=10))
    assert tracks == [{
        "name": "Creep",
        "artist": "Radiohead",
        "mbid": "a74b",
        "listeners": 1000,
        "playcount": 5000,
        "rank": 1,
        "url": "https://example.test",
    }]
    _, kwargs = client.client.get.await_args
    assert kwargs["params"]["method"] == "artist.getTopTracks"
    assert kwargs["params"]["artist"] == "Radiohead"
    assert kwargs["params"]["api_key"] == "key"


def test_client_surfaces_lastfm_error_payload(monkeypatch):
    monkeypatch.setenv("LASTFM_API_KEY", "bad")
    client = LastFmClient()
    client.client.get = AsyncMock(
        return_value=SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"error": 6, "message": "Artist not found"},
        )
    )
    with pytest.raises(RuntimeError, match="Artist not found"):
        run(client.get_top_tracks("Nobody"))


# ---------------------------------------------------------------------------
# Client parity invariant
# ---------------------------------------------------------------------------
def test_both_clients_expose_get_top_songs_by_artist():
    """Shared code calls get_top_songs_by_artist; both clients must implement it."""
    from backend.jellyfin import JellyfinClient
    from backend.navidrome import NavidromeClient

    for cls in (NavidromeClient, JellyfinClient):
        assert callable(getattr(cls, "get_top_songs_by_artist", None)), (
            f"{cls.__name__} is missing get_top_songs_by_artist"
        )


def test_jellyfin_top_tracks_degrade_when_artist_unknown(monkeypatch):
    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.setenv("JELLYFIN_URL", "http://jellyfin")
    monkeypatch.setenv("JELLYFIN_API_KEY", "key")
    from backend.jellyfin import JellyfinClient

    client = JellyfinClient()
    client.find_artist_by_name = AsyncMock(return_value=None)
    assert run(client.get_top_songs_by_artist("Nobody", 5)) == []


def test_jellyfin_top_tracks_return_zero_count_early():
    from backend.jellyfin import JellyfinClient

    client = JellyfinClient.__new__(JellyfinClient)
    assert run(client.get_top_songs_by_artist("Radiohead", 0)) == []


def test_jellyfin_top_tracks_resolve_via_lastfm(monkeypatch):
    """End-to-end: local tracks come back stamped with real Jellyfin item ids."""
    from backend.jellyfin import JellyfinClient

    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.setenv("JELLYFIN_URL", "http://jellyfin")
    monkeypatch.setenv("JELLYFIN_API_KEY", "key")

    client = JellyfinClient()
    client.find_artist_by_name = AsyncMock(
        return_value={"id": "a1", "name": "Radiohead", "mbid": "a74b"}
    )
    client.get_tracks_by_artist = AsyncMock(return_value=[
        {"id": "jf-1", "title": "Creep", "artist": "Radiohead"},
        {"id": "jf-2", "title": "Karma Police", "artist": "Radiohead"},
    ])

    fake = FakeLastFmClient(tracks=[
        {"name": "Karma Police", "artist": "Radiohead"},
        {"name": "Creep", "artist": "Radiohead"},
    ])

    async def fake_resolve(artist_name, local_tracks, *, artist_mbid=None, limit=20):
        return await resolve_top_tracks(
            artist_name, local_tracks, artist_mbid=artist_mbid, limit=limit, client=fake
        )

    monkeypatch.setattr("backend.jellyfin.tracks.resolve_top_tracks", fake_resolve)

    tracks = run(client.get_top_songs_by_artist("Radiohead", 5))
    assert [t["id"] for t in tracks] == ["jf-2", "jf-1"]
    assert all(t["is_top_track"] for t in tracks)