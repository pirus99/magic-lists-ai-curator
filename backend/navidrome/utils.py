import os
from typing import List, Dict, Any, Union, Optional

def _get_quality_score(track: Dict[str, Any]) -> int:
    """Return a numeric quality score for a track based on format and bitrate.

    Higher is better. Used to prefer lossless/high-bitrate duplicates.
    """
    fmt = (track.get("format") or track.get("suffix") or "").lower()
    bit_rate = track.get("bit_rate") or 0

    # Lossless formats beat everything
    if fmt in ("flac", "flac24", "alac", "wav", "aiff", "aif", "dsf", "dff", "ape", "wv"):
        return 10000 + bit_rate

    # Lossy: use bitrate as score with small format bonuses
    if fmt in ("opus",):
        return 500 + bit_rate
    if fmt in ("ogg", "vorbis"):
        return 400 + bit_rate
    if fmt in ("aac", "m4a", "mp4"):
        return 300 + bit_rate
    if fmt in ("mp3",):
        return 200 + bit_rate
    if fmt in ("wma",):
        return 150 + bit_rate

    # Unknown format – fall back to bitrate only
    return bit_rate


def _deduplicate_tracks(tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate a list of tracks by track ID.

    When multiple entries share the same ID the one with the highest
    engagement / quality is kept, evaluated in this order:
      1. starred (True beats False)
      2. play_count (higher beats lower)
      3. rating (higher beats lower)
      4. audio quality score (FLAC > high-bitrate MP3 > low-bitrate MP3 …)

    The original insertion order of first-seen IDs is preserved.
    """
    seen: Dict[str, Dict[str, Any]] = {}

    for track in tracks:
        tid = track.get("id")
        if tid is None:
            continue

        if tid not in seen:
            seen[tid] = track
            continue

        existing = seen[tid]

        # Priority 1: starred
        new_loved = bool(track.get("starred"))
        old_loved = bool(existing.get("starred"))
        if new_loved and not old_loved:
            seen[tid] = track
            continue
        if old_loved and not new_loved:
            continue

        # Priority 2: play_count
        new_plays = track.get("play_count") or 0
        old_plays = existing.get("play_count") or 0
        if new_plays > old_plays:
            seen[tid] = track
            continue
        if old_plays > new_plays:
            continue

        # Priority 3: rating
        new_rating = track.get("rating") or 0
        old_rating = existing.get("rating") or 0
        if new_rating > old_rating:
            seen[tid] = track
            continue
        if old_rating > new_rating:
            continue

        # Priority 4: audio quality
        if _get_quality_score(track) > _get_quality_score(existing):
            seen[tid] = track

    result = list(seen.values())

    duplicates_removed = len(tracks) - len(result)
    if duplicates_removed > 0:
        print(f"🔍 Deduplication: removed {duplicates_removed} duplicate track(s) from {len(tracks)} → {len(result)} unique tracks")

    return result


def _parse_genre_string(genre_str: str) -> List[str]:
    """Parse genre strings that may contain multiple genres separated by delimiters"""
    if not genre_str:
        return []

    # Common separators: comma, slash, bullet, tab, pipe
    separators = [",", "/", "•", "\t", "|", ";", "&"]

    # Try each separator
    for sep in separators:
        if sep in genre_str:
            parts = [part.strip() for part in genre_str.split(sep) if part.strip()]
            if len(parts) > 1:
                return parts

    # No separators found, return as single genre
    return [genre_str.strip()]


