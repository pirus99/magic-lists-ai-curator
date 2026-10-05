import asyncio

from backend.services.listenbrainz_service import ALGORITHMS, ListenBrainzService


class FakeClient:
    def __init__(self, artists):
        self.artists = artists
        self.calls = []

    async def get_similar_artists(self, mbid, algorithm):
        self.calls.append((mbid, algorithm))
        return self.artists


def test_algorithm_catalog_and_strict_score_cap():
    artists = [{"mbid": str(i), "name": str(i), "score": score} for i, score in enumerate(range(30, 231))]
    client = FakeClient(artists)
    service = ListenBrainzService(client)

    result = asyncio.run(service.get_recommendations("artist", "5Y Balanced", 50))

    assert len(result) == 20
    assert result[0]["score"] == 230
    assert all(item["score"] > 50 for item in result)
    assert client.calls[0][1] == ALGORITHMS["5Y Balanced"]


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
