"""Tests for the 'This Is' manual artist fallback (artist_name / artist_mbid)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.schemas import CreatePlaylistRequest
from backend.this_is import routes


def run(coro):
    """Run an async coroutine (repo convention: no pytest-asyncio)."""
    return asyncio.run(coro)


LIBRARY_ARTISTS = [
    {"id": "a1", "name": "Radiohead", "mbid": "a74b1b7f-71a5-4011-9441-d0b5e4122711"},
    {"id": "a2", "name": "The Beatles", "mbid": "b9d12f9a-3f8a-4f1e-9d0a-1234567890ab"},
    {"id": "a3", "name": "Björk", "mbid": None},
]


def make_request(**kwargs):
    defaults = {"artist_ids": [], "artist_name": None, "artist_mbid": None}
    defaults.update(kwargs)
    return CreatePlaylistRequest(**defaults)


def test_resolves_by_artist_id():
    request = make_request(artist_ids=["a1"])
    artist, name = run(routes._resolve_artist(request, LIBRARY_ARTISTS))
    assert artist["id"] == "a1"
    assert name == "Radiohead"


def test_unknown_artist_id_raises_404():
    from fastapi import HTTPException

    request = make_request(artist_ids=["nope"])
    with pytest.raises(HTTPException) as exc:
        run(routes._resolve_artist(request, LIBRARY_ARTISTS))
    assert exc.value.status_code == 404


def test_raises_400_when_no_id_and_no_name():
    from fastapi import HTTPException

    request = make_request()
    with pytest.raises(HTTPException) as exc:
        run(routes._resolve_artist(request, LIBRARY_ARTISTS))
    assert exc.value.status_code == 400


def test_resolves_by_mbid_without_lastfm(monkeypatch):
    request = make_request(
        artist_name="Radiohead",
        artist_mbid="a74b1b7f-71a5-4011-9441-d0b5e4122711",
    )
    # An explicit MBID must not require a Last.fm round trip.
    monkeypatch.setattr(routes, "resolve_artist_mbid", AsyncMock(return_value=None))
    artist, name = run(routes._resolve_artist(request, LIBRARY_ARTISTS))
    assert artist["id"] == "a1"
    assert name == "Radiohead"


def test_resolves_by_name_when_lastfm_returns_mbid(monkeypatch):
    request = make_request(artist_name="Björk")
    monkeypatch.setattr(routes, "resolve_artist_mbid", AsyncMock(return_value="bjk-mbid"))
    artist, name = run(routes._resolve_artist(request, LIBRARY_ARTISTS))
    # Björk has no MBID locally, so the normalized-name match wins.
    assert artist["id"] == "a3"
    assert name == "Björk"


def test_lastfm_mbid_matches_library_artist(monkeypatch):
    request = make_request(artist_name="Beatles")
    monkeypatch.setattr(routes, "resolve_artist_mbid", AsyncMock(return_value="b9d12f9a-3f8a-4f1e-9d0a-1234567890ab"))
    artist, name = run(routes._resolve_artist(request, LIBRARY_ARTISTS))
    assert artist["id"] == "a2"


def test_mbid_match_prefers_library_canonical_name(monkeypatch):
    """An MBID hit is authoritative, so the library's spelling is displayed."""
    request = make_request(
        artist_name="  radiohead  ",
        artist_mbid="a74b1b7f-71a5-4011-9441-d0b5e4122711",
    )
    monkeypatch.setattr(routes, "resolve_artist_mbid", AsyncMock(return_value=None))
    _, name = run(routes._resolve_artist(request, LIBRARY_ARTISTS))
    assert name == "Radiohead"


def test_name_only_match_uses_user_spelling(monkeypatch):
    request = make_request(artist_name="  beatles  ")
    monkeypatch.setattr(routes, "resolve_artist_mbid", AsyncMock(return_value=None))
    _, name = run(routes._resolve_artist(request, LIBRARY_ARTISTS))
    assert name == "beatles"


def test_raises_404_with_actionable_message_when_unresolvable(monkeypatch):
    from fastapi import HTTPException

    request = make_request(artist_name="Zzzz Nonexistent Band")
    monkeypatch.setattr(routes, "resolve_artist_mbid", AsyncMock(return_value=None))
    with pytest.raises(HTTPException) as exc:
        run(routes._resolve_artist(request, LIBRARY_ARTISTS))
    assert exc.value.status_code == 404
    assert "Zzzz Nonexistent Band" in exc.value.detail
    assert "not found in your library" in exc.value.detail


def test_create_playlist_backfills_resolved_artist(monkeypatch):
    """A fallback request must end up with artist_ids set so refreshes work."""
    request = make_request(artist_name="Björk")
    captured = {}

    async def fake_build(config, db, **kwargs):
        captured["request"] = kwargs.get("request")
        captured["artist_name"] = kwargs.get("artist_name")
        return {"id": 1}

    client = MagicMock()
    client.get_artists = AsyncMock(return_value=LIBRARY_ARTISTS)

    monkeypatch.setattr(routes, "get_server_client", lambda: client)
    monkeypatch.setattr(routes, "build_playlist", fake_build)
    monkeypatch.setattr(routes, "resolve_artist_mbid", AsyncMock(return_value=None))

    result = run(routes.create_playlist(request, db=MagicMock()))

    assert result == {"id": 1}
    assert captured["request"].artist_ids == ["a3"]
    assert captured["artist_name"] == "Björk"


def test_schema_allows_missing_artist_ids():
    """artist_ids is optional so the fallback can be used without an id."""
    request = CreatePlaylistRequest(artist_name="Radiohead")
    assert request.artist_ids == []
    assert request.artist_name == "Radiohead"