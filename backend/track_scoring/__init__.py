"""Smart track scoring & filtering for "This Is" / "Genre Mix" playlists.

The public entry point ``filter_tracks_for_genre_mix_playlist`` is re-exported here so
existing ``from .track_scoring import filter_tracks_for_genre_mix_playlist`` imports keep
working. The implementation is split into ``engagement`` (scoring/threshold) and
``diversity`` (artist/album caps) helper modules.
"""
from .filtering import filter_tracks_for_genre_mix_playlist
from .engagement import (
    score_tracks_by_user_engagement,
    calculate_filter_threshold,
    should_apply_smart_filtering,
    filter_tracks_by_engagement,
)
from .diversity import (
    _split_artists,
    select_diverse_tracks,
    select_diverse_tracks_with_caps,
)


__all__ = [
    "filter_tracks_for_genre_mix_playlist",
    "score_tracks_by_user_engagement",
    "calculate_filter_threshold",
    "should_apply_smart_filtering",
    "filter_tracks_by_engagement",
    "select_diverse_tracks",
    "select_diverse_tracks_with_caps",
]
