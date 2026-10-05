"""Shared track-score calculation for playlist AI curation."""
from typing import Any, Dict

TOP_TRACK_BONUS = 150


def calculate_track_score(track: Dict[str, Any]) -> float:
    """Calculate the score supplied to AI curation candidates.

    Play count forms the base score, local likes add a small bonus, and tracks
    supplied by Navidrome's artist top-songs endpoint receive a larger bonus.
    """
    play_count_score = round(track.get("play_count", 0) or 0) * 1.5
    local_likes_bonus = 15 if track.get("local_library_likes", False) else 0
    top_track_bonus = TOP_TRACK_BONUS if track.get("is_top_track", False) else 0
    return play_count_score + local_likes_bonus + top_track_bonus
