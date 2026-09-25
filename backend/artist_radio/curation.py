"""Artist Radio candidate filtering and curation."""
import json
import random
from typing import Any, Dict, List, Optional, Tuple

from ..ai_client import MAX_OVER_RETURN_FACTOR, parse_ai_track_response
from ..output_sorting import space_id_track_list_by_artist_and_album
from ..recipe_manager import recipe_manager
from ..services.candidate_limiter import limit_candidates_for_ai
from ..services.track_scoring_service import calculate_track_score


def filter_radio_tracks(
    tracks: List[Dict[str, Any]],
    year_start: Optional[int],
    year_end: Optional[int],
    max_tracks_per_album: int,
    max_tracks_per_artist: int,
    min_bitrate: Optional[int] = None,
    min_format: Optional[str] = None,
    min_bit_depth: Optional[int] = None,
    protected_track_ids: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter, score, and cap Artist Radio candidates in preference order."""
    eligible_tracks = [
        track
        for track in tracks
        if _passes_radio_filters(
            track,
            year_start,
            year_end,
            min_bitrate,
            min_format,
            min_bit_depth,
        )
    ]

    score_ordered = sorted(
        eligible_tracks,
        key=calculate_track_score,
        reverse=True,
    )
    return _apply_radio_diversity_caps(
        score_ordered,
        max_tracks_per_album,
        max_tracks_per_artist,
        protected_track_ids or set(),
    )


def _passes_radio_filters(
    track: Dict[str, Any],
    year_start: Optional[int],
    year_end: Optional[int],
    min_bitrate: Optional[int],
    min_format: Optional[str],
    min_bit_depth: Optional[int],
) -> bool:
    """Return whether a track passes Artist Radio year and quality rules."""
    year = track.get("year")
    if year_start is not None or year_end is not None:
        if not isinstance(year, (int, float)):
            return False
        if year_start is not None and year < year_start:
            return False
        if year_end is not None and year > year_end:
            return False

    track_format = str(track.get("format") or "").strip().lower()
    track_bitrate = track.get("bit_rate") or 0
    track_bit_depth = track.get("bit_depth")
    if min_format:
        lossless = track_format in {"flac", "alac", "wav", "aiff", "aif", "dsf", "dff", "ape", "wv"}
        if min_format.lower() == "flac" and not lossless:
            return False
        if min_format.lower() == "mp3" and track_format not in {"mp3"}:
            return False
        if min_format.lower() == "flac" and min_bit_depth is not None:
            if track_format != "flac" or track_bit_depth is None or track_bit_depth < min_bit_depth:
                return False
    if min_bitrate is not None and track_bitrate > 0 and track_bitrate < min_bitrate:
        return False
    return True


def _apply_radio_diversity_caps(
    tracks: List[Dict[str, Any]],
    max_tracks_per_album: int,
    max_tracks_per_artist: int,
    protected_track_ids: set[str],
) -> List[Dict[str, Any]]:
    """Apply diversity caps to already score-ordered tracks."""
    result: List[Dict[str, Any]] = []
    album_counts: Dict[str, int] = {}
    artist_counts: Dict[str, int] = {}
    for track in tracks:
        if track.get("id") in protected_track_ids:
            result.append(track)
            continue
        album = str(track.get("album") or "").strip()
        artist = str(track.get("artist") or "").strip()
        if max_tracks_per_album > 0 and album and album_counts.get(album, 0) >= max_tracks_per_album:
            continue
        if max_tracks_per_artist > 0 and artist and artist_counts.get(artist, 0) >= max_tracks_per_artist:
            continue
        result.append(track)
        if album:
            album_counts[album] = album_counts.get(album, 0) + 1
        if artist:
            artist_counts[artist] = artist_counts.get(artist, 0) + 1
    return result


async def curate_radio(
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int,
    ai_client=None,
    artist_name: str = "Artist Radio",
) -> Tuple[List[str], str]:
    """Curate the radio candidate pool, falling back to a stable local order."""
    if not candidate_tracks:
        return [], "No candidate tracks available for Artist Radio."

    recipe = recipe_manager.apply_recipe(
        "artist_radio",
        {"artists": artist_name, "num_tracks": num_tracks},
        True,
    )
    sorting_settings = recipe.get("output_sorting", {})
    artist_spacing = int(sorting_settings.get("space_between_same_artist", 0))
    album_spacing = int(sorting_settings.get("space_between_same_album", 0))
    limited_candidates = limit_candidates_for_ai(
        candidate_tracks,
        recipe,
        ai_client,
    )
    ai_candidates = _build_ai_candidate_order(limited_candidates)
    indexed_tracks = [
        (
            index,
            f"{track.get('title', 'Unknown')} - {track.get('artist', 'Unknown')}",
            track.get("album", "Unknown"),
            track.get("year", "Unknown"),
            calculate_track_score(track),
        )
        for index, track in enumerate(ai_candidates)
    ]
    try:
        if ai_client is not None and getattr(ai_client, "provider", None) is not None:
            content = await ai_client.provider.generate(
                system_prompt=recipe.get("model_instructions", "You are a music curator."),
                user_prompt=(
                    f"Select up to {num_tracks} tracks for Artist Radio.\n"
                    f"Tracks: {indexed_tracks}\n"
                    'Return JSON: {"track_ids": [indices]}'
                ),
                max_tokens=recipe.get("llm_config", {}).get("max_output_tokens", 4000),
                temperature=recipe.get("llm_config", {}).get("temperature", 0.6),
            )
            indices, description = parse_ai_track_response(content)
            if len(indices) > int(num_tracks * MAX_OVER_RETURN_FACTOR):
                raise ValueError("AI returned too many tracks")
            selected = [ai_candidates[index]["id"] for index in indices if 0 <= index < len(ai_candidates)]
            if selected:
                sorted_selection = space_id_track_list_by_artist_and_album(
                    selected,
                    ai_candidates,
                    artist_spacing=artist_spacing,
                    album_spacing=album_spacing,
                )
                return sorted_selection[:num_tracks], description or f"Artist Radio curated from {artist_name}."
    except Exception:
        pass

    ordered = sorted(
        candidate_tracks,
        key=calculate_track_score,
        reverse=True,
    )
    selected_tracks = ordered[:num_tracks]
    sorted_fallback = space_id_track_list_by_artist_and_album(
        [track["id"] for track in selected_tracks],
        selected_tracks,
        artist_spacing=artist_spacing,
        album_spacing=album_spacing,
    )
    return (
        sorted_fallback[:num_tracks],
        "Artist Radio fallback selection based on local track scores.",
    )


def _build_ai_candidate_order(candidate_tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Create score-aware AI ordering with limited order bias."""
    score_ordered = sorted(
        candidate_tracks,
        key=calculate_track_score,
        reverse=True,
    )
    if len(score_ordered) < 2:
        return score_ordered

    groups: List[List[Dict[str, Any]]] = []
    previous_score: Optional[float] = None
    for track in score_ordered:
        score = calculate_track_score(track)
        if previous_score is None or abs(score - previous_score) > 10:
            groups.append([track])
        else:
            groups[-1].append(track)
        previous_score = score

    for group in groups:
        random.shuffle(group)

    varied: List[Dict[str, Any]] = []
    while any(groups):
        for group in groups:
            if group:
                varied.append(group.pop(0))
    return varied
