"""Tests for the This Is Last.fm MusicBrainz ID override."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.schemas import CreatePlaylistRequest
from backend.this_is import builder as this_is_builder
from backend.this_is import routes


def run(coro):
    """Run an async coroutine (repo convention: no pytest-asyncio)."""
    return asyncio.run(coro)


LIBRARY_ARTISTS = [
    {"id": "a1", "name": "Radiohead", "mbid": "a74b1b7f-71a5-4011-9441-d0b5e4122711"},
    {"id": "a3", "name": "Björk", "mbid": None},
]


# ---------------------------------------------------------------------------
# Route: artist always comes from artist_ids
# ---------------------------------------------------------------------------
def test_missing_artist_id_returns_400():
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        run(routes.create_playlist(CreatePlaylistRequest(artist_ids=[]), db=MagicMock()))
    assert exc.value.status_code == 400


def test_unknown_artist_id_returns_404(monkeypatch):
    from fastapi import HTTPException

    client = MagicMock()
    client.get_artists = AsyncMock(return_value=LIBRARY_ARTISTS)
    monkeypatch.setattr(routes, "get_server_client", lambda: client)

    with pytest.raises(HTTPException) as exc:
        run(routes.create_playlist(
            CreatePlaylistRequest(artist_ids=["nope"]), db=MagicMock()
        ))
    assert exc.value.status_code == 404


def test_artist_name_field_no_longer_exists():
    """The free-text artist-name fallback was removed."""
    assert "artist_name" not in CreatePlaylistRequest.model_fields
    assert "artist_mbid" in CreatePlaylistRequest.model_fields


# ---------------------------------------------------------------------------
# Builder: override is threaded into the top-tracks lookup
# ---------------------------------------------------------------------------
def make_client(tracks):
    client = MagicMock()
    client.get_tracks_by_artist = AsyncMock(return_value=tracks)
    return client


def patch_fetch(monkeypatch, captured):
    async def fake_fetch(artist_ids, library_ids, count, artist_mbids=None):
        captured["artist_mbids"] = artist_mbids
        return []

    monkeypatch.setattr(this_is_builder, "fetch_top_tracks", fake_fetch)


def test_fetch_passes_user_mbid_override(monkeypatch):
    client = make_client([{"id": "t1", "title": "Creep"}])
    captured = {}
    monkeypatch.setattr(this_is_builder, "get_server_client", lambda: client)
    patch_fetch(monkeypatch, captured)

    request = CreatePlaylistRequest(
        artist_ids=["a3"],
        artist_mbid="user-supplied-mbid",
        top_tracks_enabled=True,
        top_tracks_count=5,
    )
    run(this_is_builder.fetch_this_is_tracks(request=request))

    assert captured["artist_mbids"] == {"a3": "user-supplied-mbid"}


def test_fetch_omits_override_when_not_supplied(monkeypatch):
    client = make_client([{"id": "t1", "title": "Creep"}])
    captured = {}
    monkeypatch.setattr(this_is_builder, "get_server_client", lambda: client)
    patch_fetch(monkeypatch, captured)

    request = CreatePlaylistRequest(artist_ids=["a1"], top_tracks_enabled=True, top_tracks_count=5)
    run(this_is_builder.fetch_this_is_tracks(request=request))

    assert captured["artist_mbids"] is None


def test_fetch_uses_saved_override_on_refresh(monkeypatch):
    client = make_client([{"id": "t1", "title": "Creep"}])
    captured = {}
    monkeypatch.setattr(this_is_builder, "get_server_client", lambda: client)
    patch_fetch(monkeypatch, captured)

    playlist = {"id": 1, "artist_id": "a3"}
    settings = {
        "artist_id": "a3",
        "top_tracks_enabled": True,
        "top_tracks_count": 4,
        "artist_mbid_override": "saved-mbid",
    }
    run(this_is_builder.fetch_this_is_tracks(playlist=playlist, settings=settings))

    assert captured["artist_mbids"] == {"a3": "saved-mbid"}


# ---------------------------------------------------------------------------
# Persisted settings
# ---------------------------------------------------------------------------
def test_settings_persist_user_mbid():
    request = CreatePlaylistRequest(artist_ids=["a3"], artist_mbid="user-mbid")
    settings = this_is_builder.extra_this_is_settings(request=request, artist_name="Björk")
    assert settings["artist_mbid_override"] == "user-mbid"
    assert settings["artist_id"] == "a3"


def test_settings_omit_empty_mbid():
    """An empty override must not shadow the library's own MBID on refresh."""
    request = CreatePlaylistRequest(artist_ids=["a1"], artist_mbid="   ")
    settings = this_is_builder.extra_this_is_settings(request=request, artist_name="Radiohead")
    assert "artist_mbid_override" not in settings


def test_settings_omit_mbid_when_absent():
    request = CreatePlaylistRequest(artist_ids=["a1"])
    settings = this_is_builder.extra_this_is_settings(request=request, artist_name="Radiohead")
    assert "artist_mbid_override" not in settings
