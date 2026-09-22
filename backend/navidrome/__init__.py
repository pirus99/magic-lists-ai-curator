"""Navidrome Subsonic API client, split into focused submodules.

The public ``NavidromeClient`` class is reassembled here by composing the method
groups defined in ``base``, ``artists``, ``tracks``, ``genres``, ``playlists`` and
``utils``. Importing ``from .navidrome_client import NavidromeClient`` (the old
path) is no longer valid; use ``from .navidrome import NavidromeClient`` instead.
"""
from .base import _NavidromeBase
from .artists import _ArtistsMixin
from .tracks import _TracksMixin
from .genres import _GenresMixin
from .playlists import _PlaylistsMixin
from .utils import _get_quality_score, _deduplicate_tracks, _parse_genre_string, _normalize_genres


class NavidromeClient(
    _NavidromeBase,
    _ArtistsMixin,
    _TracksMixin,
    _GenresMixin,
    _PlaylistsMixin,
):
    """Simple client for interacting with the Navidrome Subsonic API.

    Behaviour is identical to the previous monolithic implementation; the methods
    now live in mixin classes for maintainability.
    """

    # Expose the module-level helper functions as static utilities.
    get_quality_score = staticmethod(_get_quality_score)
    deduplicate_tracks = staticmethod(_deduplicate_tracks)
    _deduplicate_tracks = staticmethod(_deduplicate_tracks)
    parse_genre_string = staticmethod(_parse_genre_string)
    normalize_genres = staticmethod(_normalize_genres)


__all__ = ["NavidromeClient"]
