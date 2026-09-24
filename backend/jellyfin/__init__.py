from .base import _JellyfinBase
from .artists import _ArtistsMixin
from .tracks import _TracksMixin
from .genres import _GenresMixin
from .playlists import _PlaylistsMixin
from .utils import _deduplicate_tracks, _get_quality_score, _parse_genre_string, _normalize_genres


class JellyfinClient(
    _JellyfinBase,
    _ArtistsMixin,
    _TracksMixin,
    _GenresMixin,
    _PlaylistsMixin,
):
    """Jellyfin API client compatible with Navidrome interface"""
    
    # Expose utilities as static methods
    get_quality_score = staticmethod(_get_quality_score)
    deduplicate_tracks = staticmethod(_deduplicate_tracks)
    _deduplicate_tracks = staticmethod(_deduplicate_tracks)
    parse_genre_string = staticmethod(_parse_genre_string)
    normalize_genres = staticmethod(_normalize_genres)

__all__ = ["JellyfinClient"]