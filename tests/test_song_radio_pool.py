"""Tests for the Song Radio candidate pool builder."""
import asyncio

from backend.schemas import SongRadioRequest, SongRadioTrack
from backend.song_radio import builder as song_radio_builder
from backend.song_radio.builder import (
    _resolve_song_radio_artist_id,
    as_track_dict,
    build_song_radio_pool,
    build_song_radio_name,
    extra_song_radio_settings,
)


class FakeServerClient:
    """Minimal stand-in for the music server client."""

    def __init__(self, library_tracks):
        self.library_tracks = library_tracks
        self.search_calls = []

    async def search_tracks(self, query, library_ids=None, limit=50):
        self.search_calls.append(query)
        needle = (query or "").strip().lower()
        matches = [
            track
            for track in self.library_tracks
            if needle in (track.get("artist") or "").lower()
            or needle in (track.get("title") or "").lower()
        ]
        return matches[:limit]


class FakeListenBrainzService:
    """Returns a fixed set of similar recordings."""

    def __init__(self, rounds):
        self.rounds = rounds
        self.calls = []

    async def get_similar_recordings(self, recording_mbid, algorithm, minimum_score):
        self.calls.append(recording_mbid)
        index = min(len(self.calls) - 1, len(self.rounds) - 1)
        return self.rounds[index]


def _install(monkeypatch, client, service):
    monkeypatch.setattr(song_radio_builder, "get_server_client", lambda: client)
    monkeypatch.setattr(song_radio_builder, "ListenBrainzService", lambda: service)


def test_pool_matches_tracks_from_multiple_artists(monkeypatch):
    """Similar recordings by other artists must be matched into the pool."""
    library = [
        {"id": "1", "title": "Dancing Queen", "artist": "ABBA"},
        {"id": "2", "title": "Stayin' Alive", "artist": "Bee Gees"},
        {"id": "3", "title": "Blinding Lights", "artist": "The Weeknd"},
    ]
    client = FakeServerClient(library)
    service = FakeListenBrainzService([
        [
            {"mbid": "mbid-2", "title": "Stayin' Alive", "artist": "Bee Gees", "score": 90},
            {"mbid": "mbid-3", "title": "Blinding Lights", "artist": "The Weeknd", "score": 80},
        ]
    ])
    _install(monkeypatch, client, service)

    source = {"id": "1", "title": "Dancing Queen", "artist": "ABBA"}
    pool = asyncio.run(
        build_song_radio_pool(
            source_mbid="mbid-1",
            source_track=source,
            algorithm="5Y Balanced",
            minimum_score=20,
            repeat_limit=1,
        )
    )

    ids = {track["id"] for track in pool}
    assert ids == {"1", "2", "3"}
    # The other artists must have been looked up in the library.
    assert "Bee Gees" in client.search_calls
    assert "The Weeknd" in client.search_calls


def test_pool_contains_only_the_source_track_when_nothing_matches(monkeypatch):
    """Without library matches the pool still holds the source track."""
    client = FakeServerClient([])
    service = FakeListenBrainzService([
        [{"mbid": "mbid-x", "title": "Unknown", "artist": "Nobody", "score": 90}]
    ])
    _install(monkeypatch, client, service)

    source = {"id": "1", "title": "Dancing Queen", "artist": "ABBA"}
    pool = asyncio.run(
        build_song_radio_pool(
            source_mbid="mbid-1",
            source_track=source,
            algorithm="5Y Balanced",
            minimum_score=20,
            repeat_limit=1,
        )
    )

    assert [track["id"] for track in pool] == ["1"]


def test_pool_preview_excludes_source_track_when_no_matches(monkeypatch):
    """The preview count should report zero matches if only the source track exists."""
    client = FakeServerClient([])
    service = FakeListenBrainzService([
        [{"mbid": "mbid-x", "title": "Unknown", "artist": "Nobody", "score": 90}]
    ])
    _install(monkeypatch, client, service)

    source = {"id": "1", "title": "Dancing Queen", "artist": "ABBA"}
    pool = asyncio.run(
        build_song_radio_pool(
            source_mbid="mbid-1",
            source_track=source,
            algorithm="5Y Balanced",
            minimum_score=20,
            repeat_limit=1,
            include_source_track=False,
        )
    )

    assert pool == []


def test_pool_does_not_duplicate_tracks(monkeypatch):
    """The same track must never appear twice in the pool."""
    library = [
        {"id": "1", "title": "Dancing Queen", "artist": "ABBA"},
        {"id": "2", "title": "Stayin' Alive", "artist": "Bee Gees"},
    ]
    client = FakeServerClient(library)
    service = FakeListenBrainzService([
        [
            {"mbid": "mbid-2", "title": "Stayin' Alive", "artist": "Bee Gees", "score": 90},
            {"mbid": "mbid-2b", "title": "Stayin' Alive", "artist": "Bee Gees", "score": 70},
        ]
    ])
    _install(monkeypatch, client, service)

    source = {"id": "1", "title": "Dancing Queen", "artist": "ABBA"}
    pool = asyncio.run(
        build_song_radio_pool(
            source_mbid="mbid-1",
            source_track=source,
            algorithm="5Y Balanced",
            minimum_score=20,
            repeat_limit=1,
        )
    )

    ids = [track["id"] for track in pool]
    assert len(ids) == len(set(ids))
    assert set(ids) == {"1", "2"}


def test_pool_expands_to_new_source_between_rounds(monkeypatch):
    """Each expansion round should explore a different similarity branch."""
    library = [
        {"id": "1", "title": "Dancing Queen", "artist": "ABBA"},
        {"id": "2", "title": "Stayin' Alive", "artist": "Bee Gees"},
        {"id": "3", "title": "Blinding Lights", "artist": "The Weeknd"},
    ]
    client = FakeServerClient(library)
    service = FakeListenBrainzService([
        [{"mbid": "mbid-2", "title": "Stayin' Alive", "artist": "Bee Gees", "score": 90}],
        [{"mbid": "mbid-3", "title": "Blinding Lights", "artist": "The Weeknd", "score": 80}],
    ])
    _install(monkeypatch, client, service)

    source = {"id": "1", "title": "Dancing Queen", "artist": "ABBA"}
    pool = asyncio.run(
        build_song_radio_pool(
            source_mbid="mbid-1",
            source_track=source,
            algorithm="5Y Balanced",
            minimum_score=20,
            repeat_limit=2,
        )
    )

    ids = {track["id"] for track in pool}
    assert ids == {"1", "2", "3"}
    # The second round must query a different source recording.
    assert service.calls[0] != service.calls[1]


def test_as_track_dict_handles_models_and_dicts():
    model = SongRadioTrack(id="1", title="Dancing Queen", artist="ABBA", artist_id="a1")
    assert as_track_dict(model)["artist_id"] == "a1"
    assert as_track_dict({"id": "2"})["id"] == "2"
    assert as_track_dict(None) is None


def test_pydantic_source_track_does_not_break_playlist_metadata():
    """A Pydantic source track must not raise ``AttributeError: no .get``."""
    request = SongRadioRequest(
        source_mbid="mbid-1",
        source_track=SongRadioTrack(
            id="1", title="Dancing Queen", artist="ABBA", artist_id="a1"
        ),
    )

    assert _resolve_song_radio_artist_id(request=request, playlist_name="x") == "a1"
    assert build_song_radio_name(request=request) == "Song Radio: Dancing Queen"

    settings = extra_song_radio_settings(request=request)
    assert settings["source_track"]["artist_id"] == "a1"
    assert isinstance(settings["source_track"], dict)
