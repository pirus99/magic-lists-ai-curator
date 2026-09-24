"""Artist Radio candidate filtering and curation."""
import json
import random
from typing import Any, Dict, List, Optional, Tuple

from ..ai_client import MAX_OVER_RETURN_FACTOR, parse_ai_track_response
from ..recipe_manager import recipe_manager


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
    """Apply Artist Radio year, quality, and diversity rules to local tracks."""
    result: List[Dict[str, Any]] = []
    album_counts: Dict[str, int] = {}
    artist_counts: Dict[str, int] = {}
    for track in tracks:
        year = track.get("year")
        if year_start is not None or year_end is not None:
            if not isinstance(year, (int, float)):
                continue
            if year_start is not None and year < year_start:
                continue
            if year_end is not None and year > year_end:
                continue

        track_format = str(track.get("format") or "").strip().lower()
        track_bitrate = track.get("bit_rate") or 0
        track_bit_depth = track.get("bit_depth")
        if min_format:
            lossless = track_format in {"flac", "alac", "wav", "aiff", "aif", "dsf", "dff", "ape", "wv"}
            if min_format.lower() == "flac" and not lossless:
                continue
            if min_format.lower() == "mp3" and track_format not in {"mp3"}:
                continue
            if min_format.lower() == "flac" and min_bit_depth is not None:
                if track_format != "flac" or track_bit_depth is None or track_bit_depth < min_bit_depth:
                    continue
        if min_bitrate is not None and track_bitrate > 0 and track_bitrate < min_bitrate:
            continue

        album = str(track.get("album") or "").strip()
        artist = str(track.get("artist") or "").strip()
        track_id = track.get("id")
        is_protected = track_id in (protected_track_ids or set())
        if not is_protected:
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

    shuffled = candidate_tracks.copy()
    random.shuffle(shuffled)
    indexed_tracks = [
        (
            index,
            f"{track.get('title', 'Unknown')} - {track.get('artist', 'Unknown')}",
            track.get("album", "Unknown"),
            track.get("year", "Unknown"),
            track.get("play_count", 0),
        )
        for index, track in enumerate(shuffled)
    ]
    recipe = recipe_manager.apply_recipe(
        "artist_radio",
        {"artists": artist_name, "num_tracks": num_tracks},
        True,
    )
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
            selected = [shuffled[index]["id"] for index in indices if 0 <= index < len(shuffled)]
            if selected:
                return selected[:num_tracks], description or f"Artist Radio curated from {artist_name}."
    except Exception:
        pass

    ordered = sorted(candidate_tracks, key=lambda track: track.get("play_count", 0), reverse=True)
    return [track["id"] for track in ordered[:num_tracks]], f"Artist Radio fallback selection based on local play counts."
