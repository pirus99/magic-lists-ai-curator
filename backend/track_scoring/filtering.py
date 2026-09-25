"""Main entry point: filter source tracks for This Is / Genre Mix playlists."""
import random
from typing import List, Dict, Tuple, Any, Optional

from .engagement import (
    score_tracks_by_user_engagement,
    calculate_filter_threshold,
)
from .diversity import (
    _split_artists,
    select_diverse_tracks,
    select_diverse_tracks_with_caps,
)


# Format quality tiers (higher = better). Used for "minimum quality" filtering.
_FORMAT_TIER = {
    "flac": 100, "flac24": 100, "alac": 100, "wav": 100, "aiff": 100, "aif": 100,
    "dsf": 100, "dff": 100, "ape": 100, "wv": 100,
    "opus": 60, "ogg": 60, "vorbis": 60,
    "aac": 50, "m4a": 50, "mp4": 50,
    "mp3": 40,
    "wma": 30,
}


def _format_tier(fmt: str) -> int:
    """Return the quality tier for a format string (0 = unknown)."""
    return _FORMAT_TIER.get((fmt or "").strip().lower(), 0)


def filter_tracks_for_genre_mix_playlist(
    source_tracks: List[Dict],
    target_playlist_size: int,
    library_stats: Dict,
    playlist_type: str = "artist",
    diversity_config: Optional[Dict] = None,
    exploration_ratio: float = 0.0,
    high_tier_ratio: float = 0.4,
    high_tier_multiplier: float = 3.0,
    random_seed: Optional[int] = None,
    year_start: Optional[int] = None,
    year_end: Optional[int] = None,
    blacklisted_artists: Optional[List[str]] = None,
    min_bitrate: Optional[int] = None,
    min_format: Optional[str] = None,
    min_bit_depth: Optional[int] = None,
    max_tracks_per_album: Optional[int] = None,
    max_tracks_per_artist: Optional[int] = None,
) -> Tuple[List[Dict], Dict[str, Any]]:
    """
    Filter source tracks for "This Is" / "Genre Mix" playlists using engagement scoring.

    For genre playlists, diversity caps (max tracks per album and max tracks per artist)
    are applied on top of the score-based filtering to ensure track diversity in the
    payload sent to the AI model. Artist ("This Is") playlists keep the original
    score-based filtering unchanged.
    """
    threshold_multiplier = calculate_filter_threshold(target_playlist_size)
    threshold_count = target_playlist_size * threshold_multiplier

    pre_filtered_tracks = []
    filter_stats = {"year_filtered": 0, "artist_filtered": 0, "quality_filtered": 0}

    blacklisted_lower = set()
    if blacklisted_artists:
        blacklisted_lower = {a.lower().strip() for a in blacklisted_artists if a}

    for track in source_tracks:
        track_year = track.get("year")
        if year_start is not None and track_year is not None and track_year < year_start:
            filter_stats["year_filtered"] += 1
            continue
        if year_end is not None and track_year is not None and track_year > year_end:
            filter_stats["year_filtered"] += 1
            continue

        track_artist = track.get("artist", "")
        artist_match = False
        if blacklisted_lower:
            track_artists = _split_artists(track_artist)
            for ta in track_artists:
                if ta in blacklisted_lower:
                    artist_match = True
                    break
            if artist_match:
                filter_stats["artist_filtered"] += 1
                continue

        track_bitrate = track.get("bit_rate", 0) or 0
        track_format = track.get("format", "").lower() or ""
        track_bit_depth = track.get("bit_depth")
        min_format_lower = min_format.lower() if min_format else None

        track_tier = _format_tier(track_format)
        is_lossless = track_tier >= 100

        quality_failed = False
        if min_format_lower == "flac":
            if not is_lossless:
                quality_failed = True
            elif track_format == "flac":
                if min_bit_depth is not None and track_bit_depth is not None and track_bit_depth < min_bit_depth:
                    quality_failed = True
            else:
                if min_bit_depth is not None:
                    quality_failed = True
        else:
            if not is_lossless:
                if min_format_lower is not None and track_format:
                    min_tier = _format_tier(min_format_lower)
                    if track_tier < min_tier:
                        quality_failed = True
                if min_bitrate is not None and track_bitrate > 0 and track_bitrate < min_bitrate:
                    quality_failed = True

        if quality_failed:
            filter_stats["quality_filtered"] += 1
            continue

        pre_filtered_tracks.append(track)

    if any(filter_stats.values()):
        print(f"🔍 PRE-FILTERING APPLIED:")
        print(f"   📅 Year filter: {filter_stats['year_filtered']} tracks excluded")
        print(f"   🚫 Artist blacklist: {filter_stats['artist_filtered']} tracks excluded")
        print(f"   🎧 Quality filter: {filter_stats['quality_filtered']} tracks excluded")
        print(f"   📊 Remaining: {len(pre_filtered_tracks)} tracks (from {len(source_tracks)})")

    if max_tracks_per_album is None:
        max_tracks_per_album = int(diversity_config.get("max_tracks_per_album", 0)) if diversity_config else 0
    if max_tracks_per_artist is None:
        max_tracks_per_artist = int(diversity_config.get("max_tracks_per_artist", 0)) if diversity_config else 0

    apply_diversity = (
        playlist_type == "genre"
        and (max_tracks_per_album > 0 or max_tracks_per_artist > 0)
    )
    max_albums = max_tracks_per_album if apply_diversity else 0
    max_tracks = max_tracks_per_artist if apply_diversity else 0

    if len(pre_filtered_tracks) <= threshold_count:
        if apply_diversity:
            scored_tracks = score_tracks_by_user_engagement(pre_filtered_tracks, library_stats)
            rng = random.Random(random_seed)
            selected, selection_meta = select_diverse_tracks_with_caps(
                scored_tracks=scored_tracks,
                threshold_count=len(pre_filtered_tracks),
                exploration_ratio=exploration_ratio,
                high_tier_ratio=high_tier_ratio,
                high_tier_multiplier=high_tier_multiplier,
                max_tracks_per_album=max_albums,
                max_tracks_per_artist=max_tracks,
                rng=rng,
            )
            capped_tracks = [track for score, track in selected]
            diversity_dropped = selection_meta.get("caps_dropped", 0)
            print(f"🎭 DIVERSITY CAPS (below threshold): kept {len(capped_tracks)} of "
                  f"{len(pre_filtered_tracks)} tracks (dropped {diversity_dropped}, "
                  f"max {max_albums} tracks per album / {max_tracks} tracks per artist)")
            return capped_tracks, {
                "filtered": False,
                "reason": "below_threshold_diversity_applied",
                "source_count": len(pre_filtered_tracks),
                "sent_count": len(capped_tracks),
                "diversity_applied": True,
                "diversity_dropped": diversity_dropped,
                "max_tracks_per_album": max_albums,
                "max_tracks_per_artist": max_tracks,
                "pre_filter_stats": filter_stats,
            }
        return pre_filtered_tracks, {
            "filtered": False,
            "reason": "below_threshold",
            "source_count": len(pre_filtered_tracks),
            "sent_count": len(pre_filtered_tracks),
            "diversity_applied": False,
            "pre_filter_stats": filter_stats,
        }

    scored_tracks = score_tracks_by_user_engagement(pre_filtered_tracks, library_stats)
    selection_meta: Dict[str, Any] = {}
    use_diverse_selection = exploration_ratio > 0

    if apply_diversity:
        rng = random.Random(random_seed)
        selected, selection_meta = select_diverse_tracks_with_caps(
            scored_tracks=scored_tracks,
            threshold_count=threshold_count,
            exploration_ratio=exploration_ratio,
            high_tier_ratio=high_tier_ratio,
            high_tier_multiplier=high_tier_multiplier,
            max_tracks_per_album=max_albums,
            max_tracks_per_artist=max_tracks,
            rng=rng,
        )
        filtered_tracks = [track for score, track in selected]
        diversity_dropped = selection_meta.get("caps_dropped", 0)
    elif use_diverse_selection:
        rng = random.Random(random_seed)
        selected, selection_meta = select_diverse_tracks(
            scored_tracks=scored_tracks,
            threshold_count=threshold_count,
            exploration_ratio=exploration_ratio,
            high_tier_ratio=high_tier_ratio,
            high_tier_multiplier=high_tier_multiplier,
            rng=rng,
        )
        filtered_tracks = [track for score, track in selected]
        diversity_dropped = 0
    else:
        filtered_tracks = [track for score, track in scored_tracks[:threshold_count]]
        diversity_dropped = 0

    print(f"🎯 FILTERING DECISION:")
    print(f"   🎯 Threshold: {threshold_count} tracks (target: {target_playlist_size} × {threshold_multiplier}x multiplier)")
    print(f"   ✂️  Filtered {len(pre_filtered_tracks)} → {len(filtered_tracks)} tracks for LLM payload")
    print(f"   📤 Payload reduction: {((len(pre_filtered_tracks) - len(filtered_tracks)) / len(pre_filtered_tracks) * 100):.1f}%")
    if use_diverse_selection:
        print(f"   🎲 Diversified selection: core {selection_meta.get('core_count', 0)} "
              f"(from top {selection_meta.get('high_tier_size', 0)}) + explore "
              f"{selection_meta.get('explore_count', 0)} (offset {selection_meta.get('start_offset', 0)})"
              f"{' [exhausted]' if selection_meta.get('exhausted') else ''}")
    if apply_diversity:
        print(f"   🎭 Diversity caps applied: max {max_albums} tracks per album / {max_tracks} tracks per artist "
              f"(dropped {diversity_dropped} tracks"
              f"{' during selection' if use_diverse_selection else ''})"
              f"{' [exhausted]' if selection_meta.get('exhausted') else ''}")

    if use_diverse_selection:
        sent_scores = [s for s, t in scored_tracks if t in filtered_tracks]
        score_range = {
            "highest": max(sent_scores) if sent_scores else 0,
            "lowest": min(sent_scores) if sent_scores else 0,
            "cutoff": 0,
        }
    else:
        score_range = {
            "highest": scored_tracks[0][0] if scored_tracks else 0,
            "lowest": scored_tracks[threshold_count - 1][0] if len(scored_tracks) >= threshold_count else 0,
            "cutoff": scored_tracks[threshold_count][0] if len(scored_tracks) > threshold_count else 0,
        }
    filter_metadata = {
        "filtered": True,
        "source_count": len(source_tracks),
        "pre_filtered_count": len(pre_filtered_tracks),
        "sent_count": len(filtered_tracks),
        "threshold_multiplier": threshold_multiplier,
        "diversity_applied": apply_diversity,
        "diversity_dropped": diversity_dropped,
        "max_tracks_per_album": max_albums,
        "max_tracks_per_artist": max_tracks,
        "exploration_applied": use_diverse_selection,
        "exploration_ratio": exploration_ratio,
        "high_tier_ratio": high_tier_ratio,
        "high_tier_multiplier": high_tier_multiplier,
        "selection_meta": selection_meta,
        "score_range": score_range,
        "pre_filter_stats": filter_stats,
    }
    return filtered_tracks, filter_metadata
