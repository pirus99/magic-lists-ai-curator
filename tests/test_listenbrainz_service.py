import asyncio

from backend.services.listenbrainz_service import (
    ALGORITHMS,
    RECORDING_ALGORITHMS,
    VALID_RECORDING_ALGORITHMS,
    ListenBrainzService,
)


class FakeClient:
    def __init__(self, artists, recordings=None):
        self.artists = artists
        self.recordings = recordings or []
        self.calls = []

    async def get_similar_artists(self, mbid, algorithm):
        self.calls.append(("artists", mbid, algorithm))
        return self.artists

    async def get_similar_recordings(self, mbid, algorithm):
        self.calls.append(("recordings", mbid, algorithm))
        return self.recordings

    async def get_similar_artists_raw(self, mbid, algorithm):
        self.calls.append(("artists", mbid, algorithm))
        return self.artists


def test_algorithm_catalog_and_strict_score_cap():
    artists = [{"mbid": str(i), "name": str(i), "score": score} for i, score in enumerate(range(30, 231))]
    client = FakeClient(artists)
    service = ListenBrainzService(client)

    result = asyncio.run(service.get_recommendations("artist", "5Y Balanced", 50))

    assert len(result) == 20
    assert result[0]["score"] == 230
    assert all(item["score"] > 50 for item in result)
    assert client.calls[0][0] == "artists"
    assert client.calls[0][2] == ALGORITHMS["5Y Balanced"]


def test_rejects_unknown_algorithm_and_out_of_range_score():
    service = ListenBrainzService(FakeClient([]))
    try:
        asyncio.run(service.get_recommendations("artist", "unknown", 50))
    except ValueError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("Expected unsupported algorithm to fail")

    try:
        asyncio.run(service.get_recommendations("artist", "5Y Balanced", 49))
    except ValueError as exc:
        assert "between 50 and 400" in str(exc)
    else:
        raise AssertionError("Expected invalid score to fail")


def test_similar_recordings_filters_by_score_and_caps():
    recordings = [
        {"mbid": str(i), "title": f"Track {i}", "artist": f"Artist {i}", "score": score}
        for i, score in enumerate(range(10, 111))
    ]
    client = FakeClient([], recordings=recordings)
    service = ListenBrainzService(client)

    result = asyncio.run(service.get_similar_recordings("rec", "5Y Balanced", 50))

    assert len(result) == 20
    assert result[0]["score"] == 110
    assert all(item["score"] > 50 for item in result)
    assert client.calls[0][0] == "recordings"
    assert client.calls[0][1] == "rec"
    assert client.calls[0][2] == RECORDING_ALGORITHMS["5Y Balanced"]


def test_similar_recordings_rejects_unknown_algorithm():
    service = ListenBrainzService(FakeClient([]))
    try:
        asyncio.run(service.get_similar_recordings("rec", "unknown", 50))
    except ValueError as exc:
        assert "Unsupported" in str(exc)
    else:
        raise AssertionError("Expected unsupported algorithm to fail")


def test_similar_recordings_rejects_out_of_range_score():
    service = ListenBrainzService(FakeClient([]))
    try:
        asyncio.run(service.get_similar_recordings("rec", "5Y Balanced", 0))
    except ValueError as exc:
        assert "between 1 and 100" in str(exc)
    else:
        raise AssertionError("Expected invalid score to fail")


def test_similar_recordings_drops_invalid_entries():
    recordings = [
        {"mbid": "valid", "title": "Track", "artist": "Artist", "score": 100},
        {"mbid": "", "title": "No MBID", "artist": "Artist", "score": 100},
        {"mbid": "bad", "title": "No Score", "artist": "Artist", "score": "x"},
        {"mbid": "low", "title": "Low", "artist": "Artist", "score": 10},
    ]
    service = ListenBrainzService(FakeClient([], recordings=recordings))
    result = asyncio.run(service.get_similar_recordings("rec", "5Y Balanced", 50))

    assert len(result) == 1
    assert result[0]["mbid"] == "valid"


def test_recording_algorithms_differ_from_artist_algorithms():
    """The similar-recordings endpoint rejects artist algorithms with HTTP 400."""
    assert set(RECORDING_ALGORITHMS) == set(ALGORITHMS)
    # Every recording algorithm must be one the endpoint actually accepts.
    for key in ALGORITHMS:
        assert RECORDING_ALGORITHMS[key] in VALID_RECORDING_ALGORITHMS
        assert RECORDING_ALGORITHMS[key].startswith("session_based_")
    # The artist-only algorithms must never leak into the recordings catalog.
    artist_only = {
        "session_based_days_1825_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30",
        "session_based_days_75_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30",
        "session_based_days_1800_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30",
    }
    assert artist_only.isdisjoint(VALID_RECORDING_ALGORITHMS)
