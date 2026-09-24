from backend.artist_radio.curation import filter_radio_tracks


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
