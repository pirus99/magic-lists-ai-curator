"""Business layer for Last.fm top-track enrichment.

Resolves Last.fm top tracks to real media-server tracks by matching against the
artist's local track list, because Last.fm returns titles and never server item IDs.

All public functions degrade gracefully: on a missing API key or any API failure they
log a warning and return an empty result rather than raising into the playlist build.
"""
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional, Sequence

from .lastfm_client import LastFmClient

logger = logging.getLogger(__name__)

# Suffixes that carry no identity information for matching purposes.
_NOISE_PATTERNS = (
    r"\bremaster(?:ed)?\b.*$",
    r"\breissue\b.*$",
    r"\bradio edit\b.*$",
    r"\bextended(?: mix)?\b.*$",
    r"\(\s*(?:feat|ft|featuring)\b[^)]*\)",
    r"\[\s*(?:feat|ft|featuring)\b[^\]]*\]",
    r"\(\s*live[^)]*\)",
    r"\[\s*live[^\]]*\]",
    r"\(\s*acoustic[^)]*\)",
    r"\[\s*acoustic[^\]]*\]",
    r"\(\s*instrumental[^)]*\)",
    r"\[\s*instrumental[^\]]*\]",
    r"[\(\[\{].*?[\)\]\}]",
)
# Trailing "- <year>", "- 2011 Remaster", "- Live at Wembley", "- Portishead Remix"
# style qualifiers. The separator anchor plus the optional qualifier words keep titles
# that legitimately *are* a year (e.g. "1999") intact.
_TRAILING_NOISE_RE = re.compile(
    r"\s*[-–—]\s*(?:.*\s)?(?:"  # optional qualifier words before the keyword
    r"(?:19|20)\d{2}"
    r"|remaster(?:ed)?|reissue|live|acoustic|instrumental|demo"
    r"|version|edit|mix|remix|unplugged|re-?recorded"
    r")\b.*\s*$",
    re.IGNORECASE,
)
_NOISE_RE = re.compile("|".join(_NOISE_PATTERNS), re.IGNORECASE)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_title(value: Any) -> str:
    """Normalize a track title for fuzzy comparison.

    Lowercases, strips accents and punctuation, removes noise suffixes such as
    ``- Remastered``, ``(feat. Someone)`` or ``- Live at Wembley``, and collapses
    whitespace. Titles that consist only of noise (e.g. ``(Remastered)``) normalize
    to an empty string and are skipped during matching.
    """
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = _NOISE_RE.sub(" ", text)
    text = _TRAILING_NOISE_RE.sub(" ", text)
    text = _NON_ALNUM_RE.sub(" ", text.casefold())
    return " ".join(text.split())


def normalize_artist(value: Any) -> str:
    """Normalize an artist name for comparison (accents, punctuation, case)."""
    if not value:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = _NON_ALNUM_RE.sub(" ", text.casefold())
    return " ".join(text.split())


def artists_match(left: Any, right: Any) -> bool:
    """Return True when two artist names are equivalent after normalization.

    One side may be empty, which is treated as a match so that library tracks with
    missing artist metadata can still be matched by title alone.
    """
    normalized_left = normalize_artist(left)
    normalized_right = normalize_artist(right)
    if not normalized_left or not normalized_right:
        return True
    if normalized_left == normalized_right:
        return True
    # Tolerate a trailing "the ..." or a single-token variance on compound names.
    return normalized_left.replace("the ", "", 1) == normalized_right.replace("the ", "", 1)


def _build_local_index(local_tracks: Sequence[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Index local tracks by normalized title, preserving their relative order."""
    index: Dict[str, List[Dict[str, Any]]] = {}
    for track in local_tracks:
        if not isinstance(track, dict) or not track.get("id"):
            continue
        key = normalize_title(track.get("title"))
        if not key:
            continue
        index.setdefault(key, []).append(track)
    return index


def _match_one(
    entry: Dict[str, Any],
    local_tracks: Sequence[Dict[str, Any]],
    used_ids: set,
) -> Optional[Dict[str, Any]]:
    """Find the local track matching a single Last.fm entry.

    Tries an exact normalized title match first, then a conservative token-subset
    match. Each local track is returned at most once per resolution pass.
    """
    title_key = normalize_title(entry.get("name"))
    if not title_key:
        return None

    entry_artist = entry.get("artist")
    candidates = [track for track in local_tracks if track.get("id") not in used_ids]
    exact = [
        track
        for track in candidates
        if normalize_title(track.get("title")) == title_key
        and artists_match(track.get("artist"), entry_artist)
    ]
    if exact:
        return exact[0]

    # Conservative fallback: the local title must contain every significant token of
    # the Last.fm title. This catches truncated library titles without matching
    # unrelated songs that merely share a common word.
    tokens = title_key.split()
    if len(tokens) < 2:
        return None
    partial = [
        track
        for track in candidates
        if all(token in normalize_title(track.get("title")) for token in tokens)
        and artists_match(track.get("artist"), entry_artist)
    ]
    if len(partial) == 1:
        return partial[0]
    return None


async def resolve_top_tracks(
    artist_name: str,
    local_tracks: Sequence[Dict[str, Any]],
    *,
    artist_mbid: Optional[str] = None,
    limit: int = 20,
    client: Optional[LastFmClient] = None,
) -> List[Dict[str, Any]]:
    """Resolve an artist's Last.fm top tracks to matching local tracks.

    Args:
        artist_name: Artist name used for the Last.fm lookup.
        local_tracks: The artist's tracks already fetched from the media server.
        artist_mbid: Optional MusicBrainz ID, preferred over the name.
        limit: Maximum number of resolved tracks to return.
        client: Optional injected client, for testing.

    Returns:
        Copies of the matching local track dicts, in Last.fm rank order. Empty when
        Last.fm is unconfigured, unreachable, or nothing matched.
    """
    if limit <= 0 or not local_tracks:
        return []

    lastfm = client or LastFmClient()
    if not lastfm.is_configured():
        logger.warning("⚠️ Last.fm top tracks skipped: LASTFM_API_KEY is not configured")
        return []

    try:
        entries = await lastfm.get_top_tracks(artist_name, artist_mbid=artist_mbid, limit=limit)
    except RuntimeError as exc:
        logger.warning(f"⚠️ Last.fm top tracks unavailable for '{artist_name}': {exc}")
        return []

    if not entries:
        logger.info(f"ℹ️ Last.fm returned no top tracks for '{artist_name}'")
        return []

    resolved: List[Dict[str, Any]] = []
    used_ids: set = set()
    for entry in entries:
        match = _match_one(entry, local_tracks, used_ids)
        if match is None:
            continue
        used_ids.add(match["id"])
        track = dict(match)
        track["is_top_track"] = True
        resolved.append(track)
        if len(resolved) >= limit:
            break

    logger.info(
        f"🎯 Last.fm resolved {len(resolved)}/{min(limit, len(entries))} top tracks for '{artist_name}'"
    )
    return resolved


def top_tracks_strategy_label(strategy: str) -> str:
    """Return a short human-readable label for a top-track strategy key."""
    return TOP_TRACK_STRATEGY_LABELS.get(strategy, strategy)


# Single source of truth for top-track strategy short labels, shared by the
# template context, the health-check payload and the frontend.
TOP_TRACK_STRATEGY_LABELS: Dict[str, str] = {
    "native": "Native",
    "lastfm": "Last.fm",
    "hybrid": "Hybrid",
    "off": "Off",
}