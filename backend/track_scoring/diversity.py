"""Diversity selection and per-artist/per-album cap enforcement."""
import re
import random
from typing import List, Dict, Tuple, Any, Optional


def _split_artists(artist_field: str) -> List[str]:
    """Split a combined artist string into individual artist names."""
    if not artist_field:
        return []
    normalized = re.sub(
        r"\s*(?:&|feat\.?|ft\.?|featuring|x|and|,)\s*",
        "|",
        artist_field,
        flags=re.IGNORECASE,
    )
    parts = [p.strip().lower() for p in normalized.split("|") if p.strip()]
    seen = set()
    result = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            result.append(p)
    return result


def select_diverse_tracks(
    scored_tracks: List[Tuple[float, Dict]],
    threshold_count: int,
    exploration_ratio: float = 0.0,
    high_tier_ratio: float = 0.4,
    high_tier_multiplier: float = 3.0,
    rng: Optional[random.Random] = None,
) -> Tuple[List[Tuple[float, Dict]], Dict[str, Any]]:
    """Build a diversified, partially-randomized selection from score-sorted tracks."""
    if rng is None:
        rng = random.Random()

    core_fraction = high_tier_ratio if high_tier_ratio > 0 else (1.0 - exploration_ratio)
    core_count = max(0, int(round(threshold_count * core_fraction)))
    explore_count = max(0, threshold_count - core_count)

    high_tier_size = max(core_count, int(round(core_count * high_tier_multiplier)))
    high_tier_size = min(high_tier_size, len(scored_tracks))

    core: List[Tuple[float, Dict]] = []
    if core_count > 0 and high_tier_size > 0:
        pool = scored_tracks[:high_tier_size]
        sample_n = min(core_count, len(pool))
        core = rng.sample(pool, sample_n)

    core_ids = {id(track) for _, track in core}

    start_offset = 0
    if explore_count > 0 and len(scored_tracks) > core_count:
        start_offset = rng.randint(core_count, len(scored_tracks) - 1)

    explore: List[Tuple[float, Dict]] = []
    exhausted = False
    if explore_count > 0:
        n = len(scored_tracks)
        i = 0
        while len(explore) < explore_count and i < n:
            idx = (start_offset + i) % n
            i += 1
            score, track = scored_tracks[idx]
            if id(track) in core_ids:
                continue
            explore.append((score, track))
        exhausted = len(explore) < explore_count

    selected = core + explore
    selection_meta = {
        "core_count": len(core),
        "explore_count": len(explore),
        "high_tier_size": high_tier_size,
        "start_offset": start_offset,
        "exhausted": exhausted,
        "core_fraction": core_fraction,
    }
    return selected, selection_meta


def _track_passes_caps(
    track: Dict,
    artist_state: Dict[str, Dict[str, Any]],
    album_state: Dict[str, int],
    max_tracks_per_album: int,
    max_tracks_per_artist: int,
) -> bool:
    """Check whether a track passes the diversity caps given current state."""
    artist_field = track.get("artist", "Unknown Artist")
    album = (track.get("album") or "").strip()

    artists = _split_artists(artist_field)
    if not artists:
        artists = [artist_field.strip().lower() or "unknown artist"]

    states = []
    for a in artists:
        st = artist_state.get(a)
        if st is None:
            st = {"track_count": 0, "albums": set()}
            artist_state[a] = st
        states.append(st)

    if max_tracks_per_artist > 0 and any(st["track_count"] >= max_tracks_per_artist for st in states):
        return False
    if max_tracks_per_album > 0 and album and album_state.get(album, 0) >= max_tracks_per_album:
        return False
    return True


def _apply_caps_to_track(
    track: Dict,
    artist_state: Dict[str, Dict[str, Any]],
    album_state: Dict[str, int],
) -> None:
    """Update per-artist and per-album state to count a kept track."""
    artist_field = track.get("artist", "Unknown Artist")
    album = (track.get("album") or "").strip()

    artists = _split_artists(artist_field)
    if not artists:
        artists = [artist_field.strip().lower() or "unknown artist"]

    states = [artist_state[a] for a in artists]
    if album:
        for st in states:
            st["albums"].add(album)
        album_state[album] = album_state.get(album, 0) + 1
    for st in states:
        st["track_count"] += 1


def select_diverse_tracks_with_caps(
    scored_tracks: List[Tuple[float, Dict]],
    threshold_count: int,
    exploration_ratio: float = 0.0,
    high_tier_ratio: float = 0.4,
    high_tier_multiplier: float = 3.0,
    max_tracks_per_album: int = 0,
    max_tracks_per_artist: int = 0,
    rng: Optional[random.Random] = None,
) -> Tuple[List[Tuple[float, Dict]], Dict[str, Any]]:
    """Cap-aware selection over the FULL scored list (single source of truth for genre paths)."""
    if rng is None:
        rng = random.Random()

    caps_enabled = max_tracks_per_album > 0 or max_tracks_per_artist > 0
    diversified = exploration_ratio > 0

    core_fraction = high_tier_ratio if (diversified and high_tier_ratio > 0) else (1.0 - exploration_ratio if diversified else 1.0)
    core_count = max(0, int(round(threshold_count * core_fraction)))

    high_tier_size = max(core_count, int(round(core_count * high_tier_multiplier)))
    high_tier_size = min(high_tier_size, len(scored_tracks))

    artist_state: Dict[str, Dict[str, Any]] = {}
    album_state: Dict[str, int] = {}
    core: List[Tuple[float, Dict]] = []
    caps_dropped = 0

    if core_count > 0 and high_tier_size > 0:
        if diversified:
            pool = scored_tracks[:high_tier_size]
            attempts = 0
            max_attempts = max(len(pool), 1) * 4
            picked_core_ids = set()
            while len(core) < core_count and attempts < max_attempts:
                candidate = rng.choice(pool)
                attempts += 1
                if id(candidate[1]) in picked_core_ids:
                    continue
                if caps_enabled and not _track_passes_caps(candidate[1], artist_state, album_state, max_tracks_per_album, max_tracks_per_artist):
                    caps_dropped += 1
                    continue
                if caps_enabled:
                    _apply_caps_to_track(candidate[1], artist_state, album_state)
                picked_core_ids.add(id(candidate[1]))
                core.append(candidate)
        else:
            for entry in scored_tracks[:core_count]:
                if caps_enabled and not _track_passes_caps(entry[1], artist_state, album_state, max_tracks_per_album, max_tracks_per_artist):
                    caps_dropped += 1
                    continue
                if caps_enabled:
                    _apply_caps_to_track(entry[1], artist_state, album_state)
                core.append(entry)

    core_ids = {id(track) for _, track in core}

    start_offset = 0
    if threshold_count > len(core) and len(scored_tracks) > 0:
        if diversified:
            start_offset = rng.randint(0, len(scored_tracks) - 1)
        else:
            start_offset = min(core_count, len(scored_tracks) - 1)

    explore: List[Tuple[float, Dict]] = []
    exhausted = False
    n = len(scored_tracks)
    if threshold_count > len(core) and n > 0:
        i = 0
        while len(explore) + len(core) < threshold_count and i < n:
            idx = (start_offset + i) % n
            i += 1
            score, track = scored_tracks[idx]
            if id(track) in core_ids:
                continue
            if caps_enabled and not _track_passes_caps(track, artist_state, album_state, max_tracks_per_album, max_tracks_per_artist):
                caps_dropped += 1
                continue
            if caps_enabled:
                _apply_caps_to_track(track, artist_state, album_state)
            explore.append((score, track))
        exhausted = (len(explore) + len(core)) < threshold_count

    selected = core + explore
    selection_meta = {
        "core_count": len(core),
        "explore_count": len(explore),
        "high_tier_size": high_tier_size,
        "start_offset": start_offset,
        "caps_dropped": caps_dropped,
        "exhausted": exhausted,
        "core_fraction": core_fraction,
        "diversified": diversified,
    }
    return selected, selection_meta
