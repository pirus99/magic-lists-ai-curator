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

# The ``similar-recordings`` Labs endpoint accepts a different set of algorithms
# than ``similar-artists``. Passing an artist algorithm to the recordings
# endpoint makes ListenBrainz reject the request with HTTP 400.
RECORDING_ALGORITHMS: Dict[str, str] = {
    "5Y Balanced": "session_based_days_1500_session_300_contribution_5_threshold_15_limit_50_skip_30_top_n_listeners_1000",
    "20Y+": "session_based_days_7500_session_300_contribution_5_threshold_15_limit_50_skip_30_top_n_listeners_1000",
    "25Y Deep": "session_based_days_9000_session_300_contribution_5_threshold_15_limit_50_skip_30",
    "3M Recent": "session_based_days_180_session_300_contribution_5_threshold_15_limit_50_skip_30",
    "20Y Broad": "session_based_days_7500_session_300_contribution_5_threshold_15_limit_50_skip_30",
    "5Y Light": "session_based_listens_session_300_contribution_5_threshold_15_limit_50_skip_30",
}

# The complete set of algorithm values the ``similar-recordings`` endpoint
# accepts. Any other value makes ListenBrainz reject the request with HTTP 400.
VALID_RECORDING_ALGORITHMS = frozenset(RECORDING_ALGORITHMS.values())

MAX_RECOMMENDATIONS = 20

# Recording similarity scores are much smaller than artist similarity scores.
MIN_RECORDING_SCORE = 1
MAX_RECORDING_SCORE = 100


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

    async def get_similar_recordings(
        self,
        recording_mbid: str,
        algorithm_key: str,
        minimum_score: int,
    ) -> List[Dict[str, Any]]:
        """Fetch similar recordings for a MusicBrainz recording MBID.

        Mirrors :meth:`get_recommendations` but targets the Labs
        ``similar-recordings`` endpoint, which returns recordings instead of
        artists and uses its own algorithm catalog and score range. Invalid
        entries are dropped before the score filter so the caller never has to
        handle malformed rows.
        """
        if algorithm_key not in RECORDING_ALGORITHMS:
            raise ValueError(f"Unsupported ListenBrainz algorithm: {algorithm_key}")
        if minimum_score < MIN_RECORDING_SCORE or minimum_score > MAX_RECORDING_SCORE:
            raise ValueError(
                f"Minimum score must be between {MIN_RECORDING_SCORE} and {MAX_RECORDING_SCORE}"
            )
        recordings = await self.client.get_similar_recordings(
            recording_mbid, RECORDING_ALGORITHMS[algorithm_key]
        )
        matching = [
            recording
            for recording in recordings
            if recording.get("mbid")
            and isinstance(recording.get("score"), (int, float))
            and recording["score"] > minimum_score
        ]
        matching.sort(key=lambda recording: recording["score"], reverse=True)
        return matching[:MAX_RECOMMENDATIONS]
