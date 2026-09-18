"""User-engagement scoring and threshold helpers for track filtering."""
import random
from datetime import datetime
from typing import List, Dict, Tuple, Any, Optional


def score_tracks_by_user_engagement(tracks: List[Dict], library_stats: Dict) -> List[Tuple[float, Dict]]:
    """
    Score tracks based on user's listening behavior.
    Returns list of (score, track) tuples sorted by score descending.
    """
    scored_tracks = []

    engagement_stats = {
        'total_tracks': len(tracks),
        'loved_tracks': 0,
        'rated_tracks': 0,
        'tracks_with_plays': 0,
        'tracks_in_playlists': 0,
        'recent_tracks': 0,
        'total_play_count': 0,
        'total_playlist_appearances': 0,
        'max_score': 0,
        'min_score': float('inf'),
    }

    max_play_count = library_stats.get('max_play_count', 100)
    max_playlist_appearances = library_stats.get('max_playlist_appearances', 10)

    for track in tracks:
        score = 0.0

        # 1. Loved tracks (starred) - highest weight
        if track.get('starred'):
            score += 1000
            engagement_stats['loved_tracks'] += 1

        # 2. User rating (1-5 stars)
        rating = track.get('userRating', 0) or 0
        if rating > 0:
            score += rating * 200
            engagement_stats['rated_tracks'] += 1

        # 3. Play count (normalized)
        play_count = track.get('play_count', 0) or 0
        if play_count > 0:
            normalized_plays = (play_count / max_play_count) * 500 if max_play_count > 0 else 0
            score += normalized_plays
            engagement_stats['tracks_with_plays'] += 1
            engagement_stats['total_play_count'] += play_count

        # 4. Playlist appearances (normalized)
        playlist_appearances = track.get('playlist_appearances', 0) or 0
        if playlist_appearances > 0:
            normalized_appearances = (playlist_appearances / max_playlist_appearances) * 300 if max_playlist_appearances > 0 else 0
            score += normalized_appearances
            engagement_stats['tracks_in_playlists'] += 1
            engagement_stats['total_playlist_appearances'] += playlist_appearances

        # 5. Recency bonus (played within last 90 days)
        last_played = track.get('last_played')
        if last_played:
            try:
                if isinstance(last_played, str):
                    last_played_dt = datetime.fromisoformat(last_played.replace('Z', '+00:00'))
                else:
                    last_played_dt = last_played
                days_ago = (datetime.now() - last_played_dt).days
                if days_ago <= 90:
                    recency_bonus = max(0, 100 - days_ago)
                    score += recency_bonus
                    engagement_stats['recent_tracks'] += 1
            except (ValueError, TypeError):
                pass

        scored_tracks.append((score, track))

        engagement_stats['max_score'] = max(engagement_stats['max_score'], score)
        engagement_stats['min_score'] = min(engagement_stats['min_score'], score)

    scored_tracks.sort(key=lambda x: x[0], reverse=True)

    return scored_tracks


def calculate_filter_threshold(target_playlist_size: int, ollama_max_tracks: Optional[int] = None) -> int:
    """Calculate optimal multiplier for filtering source tracks."""
    if ollama_max_tracks is not None:
        return ollama_max_tracks

    if target_playlist_size <= 25:
        return 10
    elif target_playlist_size <= 50:
        return 8
    elif target_playlist_size <= 100:
        return 5
    else:
        return max(5, int(600 / target_playlist_size * 6))


def should_apply_smart_filtering(source_tracks: List[Dict], target_playlist_size: int, ollama_max_tracks: Optional[int] = None) -> bool:
    """Determine if smart filtering should be applied based on track count and target size."""
    threshold_multiplier = calculate_filter_threshold(target_playlist_size, ollama_max_tracks)
    threshold = ollama_max_tracks if ollama_max_tracks is not None else target_playlist_size * threshold_multiplier
    return len(source_tracks) > threshold


def filter_tracks_by_engagement(
    tracks: List[Dict],
    target_playlist_size: int,
    library_stats: Dict,
    ollama_max_tracks: Optional[int] = None,
) -> List[Dict]:
    """Apply smart filtering to tracks if needed, returning filtered subset."""
    if not should_apply_smart_filtering(tracks, target_playlist_size, ollama_max_tracks):
        return tracks

    threshold_multiplier = calculate_filter_threshold(target_playlist_size, ollama_max_tracks)
    max_tracks_to_keep = ollama_max_tracks if ollama_max_tracks is not None else target_playlist_size * threshold_multiplier

    scored_tracks = score_tracks_by_user_engagement(tracks, library_stats)
    filtered_tracks = [track for score, track in scored_tracks[:max_tracks_to_keep]]
    return filtered_tracks
