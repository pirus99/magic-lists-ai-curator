"""ListenBrainz recommendation service."""
from typing import Any, Dict, List

from .listenbrainz_client import ListenBrainzClient


ALGORITHMS: Dict[str, str] = {
    "5Y Balanced": "session_based_days_1825_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30",
    "20Y+": "session_based_days_7500_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30",
    "25Y Deep": "session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30",
    "3M Recent": "session_based_days_75_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30",
    "20Y Broad": "session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30",
    "5Y Light": "session_based_days_1800_session_300_contribution_3_threshold_10_limit_100_filter_True_skip_30",
}
MAX_RECOMMENDATIONS = 20


class ListenBrainzService:
    def __init__(self, client: ListenBrainzClient = None) -> None:
        self.client = client or ListenBrainzClient()

    async def get_recommendations(
        self,
        artist_mbid: str,
        algorithm_key: str,
        minimum_score: int,
    ) -> List[Dict[str, Any]]:
        if algorithm_key not in ALGORITHMS:
            raise ValueError(f"Unsupported ListenBrainz algorithm: {algorithm_key}")
        if minimum_score < 50 or minimum_score > 400:
            raise ValueError("Minimum score must be between 50 and 400")
        artists = await self.client.get_similar_artists(artist_mbid, ALGORITHMS[algorithm_key])
        matching = [artist for artist in artists if artist["score"] > minimum_score]
        matching.sort(key=lambda artist: artist["score"], reverse=True)
        return matching[:MAX_RECOMMENDATIONS]
