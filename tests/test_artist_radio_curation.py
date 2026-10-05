from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"


from backend.artist_radio import curation
from backend.artist_radio.curation import curate_radio, filter_radio_tracks


def test_filter_radio_tracks_applies_minimum_quality():
    tracks = [
        {"id": "lossless", "format": "flac", "bit_depth": 24, "bit_rate": 900},
        {"id": "lossy", "format": "mp3", "bit_depth": None, "bit_rate": 192},
    ]

    result = filter_radio_tracks(tracks, None, None, 0, 0, min_bitrate=256, min_format="flac", min_bit_depth=16)

    assert [track["id"] for track in result] == ["lossless"]


def test_filter_radio_tracks_uses_known_years_and_caps():
    tracks = [
        {"id": "1", "year": 1990, "album": "A", "artist": "One"},
        {"id": "2", "year": 2000, "album": "A", "artist": "One"},
        {"id": "3", "year": None, "album": "B", "artist": "Two"},
        {"id": "4", "year": 2010, "album": "B", "artist": "Two"},
    ]

    result = filter_radio_tracks(tracks, 1980, 2000, 1, 8)

    assert [track["id"] for track in result] == ["1"]


def test_filter_radio_tracks_keeps_unknown_years_without_range():
    tracks = [{"id": "1", "year": None, "album": "A", "artist": "One"}]

    assert filter_radio_tracks(tracks, None, None, 0, 0) == tracks


def test_filter_radio_tracks_applies_caps_in_score_order():
    tracks = [
        {"id": "low", "play_count": 1, "album": "A", "artist": "One"},
        {"id": "high", "play_count": 20, "album": "A", "artist": "One"},
    ]

    result = filter_radio_tracks(tracks, None, None, 1, 8)

    assert [track["id"] for track in result] == ["high"]


def test_filter_radio_tracks_protects_top_tracks_from_caps():
    tracks = [
        {"id": "normal", "play_count": 1, "year": 2020, "album": "A", "artist": "One"},
        {"id": "top-1", "play_count": 1, "is_top_track": True, "year": 2020, "album": "A", "artist": "One"},
        {"id": "top-2", "play_count": 1, "is_top_track": True, "year": 2020, "album": "A", "artist": "One"},
    ]

    result = filter_radio_tracks(
        tracks,
        None,
        None,
        1,
        2,
        protected_track_ids={"top-1", "top-2"},
    )

    assert {track["id"] for track in result} == {"normal", "top-1", "top-2"}


@pytest.mark.anyio
async def test_curate_radio_uses_recipe_output_sorting(monkeypatch):
    recipe = {
        "model_instructions": "Select tracks",
        "llm_config": {"max_output_tokens": 100, "temperature": 0.6},
        "output_sorting": {
            "space_between_same_artist": 3,
            "space_between_same_album": 2,
        },
    }
    monkeypatch.setattr(curation.recipe_manager, "apply_recipe", lambda *args: recipe)
    ai_client = SimpleNamespace(
        provider=SimpleNamespace(generate=AsyncMock(return_value='{"track_ids": [0, 1, 2, 3]}'))
    )
    candidates = [
        {"id": "a1", "title": "A1", "artist": "Artist A", "album": "Album A", "year": 2020, "play_count": 1},
        {"id": "b1", "title": "B1", "artist": "Artist B", "album": "Album B", "year": 2021, "play_count": 1},
        {"id": "a2", "title": "A2", "artist": "Artist A", "album": "Album C", "year": 2022, "play_count": 1},
        {"id": "b2", "title": "B2", "artist": "Artist B", "album": "Album D", "year": 2023, "play_count": 1},
    ]

    track_ids, _ = await curate_radio(candidates, 4, ai_client=ai_client)

    assert len(track_ids) == 4
    assert len(set(track_ids)) == 4
    by_id = {track["id"]: track for track in candidates}
    assert by_id[track_ids[0]]["artist"] != by_id[track_ids[1]]["artist"]


@pytest.mark.anyio
async def test_curate_radio_fallback_scores_before_recipe_output_sorting(monkeypatch):
    recipe = {
        "output_sorting": {
            "space_between_same_artist": 3,
            "space_between_same_album": 2,
        }
    }
    monkeypatch.setattr(curation.recipe_manager, "apply_recipe", lambda *args: recipe)
    sorting_spy = lambda track_ids, tracks, artist_spacing, album_spacing: ["spaced-a1", "spaced-b1", "spaced-a2", "spaced-c1"]
    monkeypatch.setattr(curation, "space_id_track_list_by_artist_and_album", sorting_spy)
    candidates = [
        {"id": "a1", "title": "A1", "artist": "Artist A", "album": "Album A", "play_count": 1},
        {"id": "b1", "title": "B1", "artist": "Artist B", "album": "Album B", "play_count": 1},
        {"id": "a2", "title": "A2", "artist": "Artist A", "album": "Album C", "play_count": 20},
        {"id": "c1", "title": "C1", "artist": "Artist C", "album": "Album D", "play_count": 1},
    ]

    track_ids, _ = await curate_radio(candidates, 4)

    assert track_ids == ["spaced-a1", "spaced-b1", "spaced-a2", "spaced-c1"]
