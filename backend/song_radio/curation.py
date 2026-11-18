"""Song Radio candidate filtering and curation."""
from typing import Any, Dict, List, Optional, Tuple

from ..artist_radio.curation import (
    curate_radio,
    filter_radio_tracks,
)


def filter_song_radio_tracks(
    tracks: List[Dict[str, Any]],
    year_start: Optional[int],
    year_end: Optional[int],
    max_tracks_per_album: int,
    max_tracks_per_artist: int,
    min_bitrate: Optional[int],
    min_format: Optional[str],
    min_bit_depth: Optional[int],
    protected_track_ids: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """Filter, score, and cap Song Radio candidates in preference order.

    Reuses the Artist Radio filtering rules because the quality and diversity
    caps are identical; the only difference is the source of the candidate
    pool (similar recordings instead of artist recommendations).
    """
    return filter_radio_tracks(
        tracks,
        year_start,
        year_end,
        max_tracks_per_album,
        max_tracks_per_artist,
        min_bitrate,
        min_format,
        min_bit_depth,
        protected_track_ids=protected_track_ids or set(),
    )


async def curate_song_radio(
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int,
    ai_client=None,
    source_track: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Tuple[List[str], str]:
    """Curate the final Song Radio selection with the shared AI pipeline.

    The source track is pinned to the first position of the playlist so the
    song the radio is based on always comes first.
    """
    source_title = ""
    anchor_track_id = None
    if source_track:
        source_title = source_track.get("title") or ""
        anchor_track_id = source_track.get("id")
    return await curate_radio(
        candidate_tracks,
        num_tracks,
        ai_client,
        f"Song Radio: {source_title}".strip(),
        anchor_track_id=anchor_track_id,
    )