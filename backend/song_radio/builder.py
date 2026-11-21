"""Song Radio playlist builder and persistence settings."""
import logging
from typing import Any, Dict, List, Optional, Tuple

from ..database import DatabaseManager
from ..core.playlist_builder import PlaylistTypeConfig
from ..core.server_router import get_server_client
from ..services.listenbrainz_service import ListenBrainzService
from .curation import curate_song_radio, filter_song_radio_tracks


logger = logging.getLogger(__name__)


def as_track_dict(source_track: Any) -> Optional[Dict[str, Any]]:
    """Normalize a source track into a plain dict.

    The source track may arrive as a Pydantic model (when creating a playlist
    from an API request) or as a plain dict (when refreshing a stored playlist).
    Pydantic models do not implement ``.get()``, so every consumer must convert
    first.
    """
    if source_track is None:
        return None
    if hasattr(source_track, "model_dump"):
        return source_track.model_dump()
    if hasattr(source_track, "dict"):
        return source_track.dict()
    if isinstance(source_track, dict):
        return source_track
    return None


async def build_song_radio_pool(
    source_mbid: str,
    source_track: Optional[Dict[str, Any]],
    algorithm: str,
    minimum_score: int,
    repeat_limit: int,
    library_ids: Optional[List[str]] = None,
    listenbrainz_enabled: bool = True,
    use_subsonic_similar: bool = False,
    include_source_track: bool = True,
) -> List[Dict[str, Any]]:
    """Build the raw Song Radio candidate pool from a source recording MBID.

    The pool starts from the source track's MusicBrainz recording MBID, fetches
    similar recordings from ListenBrainz, and matches them against the local
    library. Matching happens by recording MBID first and falls back to a
    title+artist lookup, because most music servers do not expose MusicBrainz
    recording IDs for every track.

    When ListenBrainz is disabled, returns no similar recordings, or the user
    opts in via ``use_subsonic_similar``, the pool is extended with tracks from
    the media server's native similarity engine (Navidrome's ``getSimilarSongs2``
    Subsonic endpoint). This requires no MusicBrainz IDs and works entirely
    against the local library, so it is a robust fallback and an easy way to
    widen the candidate pool.

    The returned pool is unfiltered so callers can report how many tracks were
    found before the user decides whether to create a playlist.
    """
    if not source_mbid and not use_subsonic_similar:
        return []

    client = get_server_client()
    service = ListenBrainzService()

    seen_mbids: set[str] = set()
    seen_title_artist: set[str] = set()
    pool: List[Dict[str, Any]] = []
    local_by_mbid: Dict[str, Dict[str, Any]] = {}
    local_by_title_artist: Dict[str, Dict[str, Any]] = {}
    artist_cache: Dict[str, List[Dict[str, Any]]] = {}

    def _title_artist_key(title: str, artist: str) -> str:
        return f"{title.strip().lower()}|||{artist.strip().lower()}"

    def _index_tracks(tracks: List[Dict[str, Any]]) -> None:
        """Add tracks to the local lookup indexes."""
        for track in tracks:
            if not isinstance(track, dict):
                continue
            mbid = track.get("recording_mbid")
            if mbid and mbid not in local_by_mbid:
                local_by_mbid[mbid] = track
            title = track.get("title") or ""
            artist = track.get("artist") or ""
            if title and artist:
                key = _title_artist_key(title, artist)
                if key not in local_by_title_artist:
                    local_by_title_artist[key] = track

    async def _lookup_artist(artist_name: str) -> List[Dict[str, Any]]:
        """Fetch and cache the library tracks for a given artist name."""
        key = artist_name.strip().lower()
        if not key:
            return []
        if key in artist_cache:
            return artist_cache[key]
        try:
            tracks = await client.search_tracks(artist_name, library_ids, limit=100)
        except Exception:
            tracks = []
        artist_cache[key] = tracks
        _index_tracks(tracks)
        return tracks

    # Seed the pool with the source track itself so the playlist always has
    # at least one candidate even if ListenBrainz returns nothing.
    # Some preview flows only want to know how many related tracks were found,
    # so callers can opt out of counting the anchor track as a match.
    if source_track and source_track.get("id") and include_source_track:
        pool.append(source_track)
        _index_tracks([source_track])
        if source_track.get("recording_mbid"):
            seen_mbids.add(source_track["recording_mbid"])
        if source_track.get("title") and source_track.get("artist"):
            seen_title_artist.add(_title_artist_key(source_track["title"], source_track["artist"]))

    for _ in range(max(1, int(repeat_limit))):
        if not source_mbid:
            break
        try:
            similar = await service.get_similar_recordings(source_mbid, algorithm, minimum_score)
        except Exception as exc:
            logger.warning(f"⚠️ ListenBrainz similar-recordings failed: {exc}")
            break

        if not similar:
            break

        added_this_round = 0
        for recording in similar:
            mbid = recording.get("mbid")
            title = recording.get("title") or ""
            artist = recording.get("artist") or ""
            ta_key = _title_artist_key(title, artist) if title and artist else None

            # Skip if we've already seen this recording by MBID or title+artist.
            if mbid and mbid in seen_mbids:
                continue
            if ta_key and ta_key in seen_title_artist:
                continue

            # Try MBID match first, then fall back to title+artist match.
            local = local_by_mbid.get(mbid) if mbid else None
            if not local and ta_key:
                local = local_by_title_artist.get(ta_key)

            # No match yet: pull the recording's artist into the local index so
            # tracks from other artists can be matched as well.
            if not local and artist:
                await _lookup_artist(artist)
                if ta_key:
                    local = local_by_title_artist.get(ta_key)
                if not local and mbid:
                    local = local_by_mbid.get(mbid)

            if local and local.get("id") not in {t.get("id") for t in pool}:
                pool.append(local)
                if mbid:
                    seen_mbids.add(mbid)
                if ta_key:
                    seen_title_artist.add(ta_key)
                added_this_round += 1
            else:
                # Mark as seen even if no local match, so we don't retry.
                if mbid:
                    seen_mbids.add(mbid)
                if ta_key:
                    seen_title_artist.add(ta_key)

        if added_this_round == 0:
            # No new local matches; keep expanding from the last similar set.
            source_mbid = similar[-1].get("mbid") or source_mbid
        else:
            # Advance the expansion source so the next round explores a
            # different branch of the similarity graph instead of re-fetching
            # the same results.
            next_mbid = similar[-1].get("mbid")
            if next_mbid and next_mbid != source_mbid:
                source_mbid = next_mbid

    # Subsonic-native similarity fallback / extension. When ListenBrainz is
    # disabled, returns nothing, or the user explicitly opts in, pull similar
    # tracks straight from the media server (Navidrome getSimilarSongs2). This
    # works without any MusicBrainz IDs and is matched against the local library.
    if use_subsonic_similar and source_track and source_track.get("id"):
        try:
            similar_tracks = await client.get_similar_tracks(
                source_track["id"],
                count=max(25, int(repeat_limit) * 10),
                library_ids=library_ids,
            )
        except Exception as exc:
            logger.warning(f"⚠️ Subsonic similar-tracks failed: {exc}")
            similar_tracks = []

        existing_ids = {t.get("id") for t in pool}
        for track in similar_tracks:
            track_id = track.get("id")
            if not track_id or track_id in existing_ids:
                continue
            pool.append(track)
            existing_ids.add(track_id)
            if track.get("recording_mbid"):
                seen_mbids.add(track["recording_mbid"])
            if track.get("title") and track.get("artist"):
                seen_title_artist.add(_title_artist_key(track["title"], track["artist"]))

    return pool


async def fetch_song_radio_tracks(
    request: Any = None,
    library_ids: Optional[List[str]] = None,
    playlist: Optional[Dict[str, Any]] = None,
    settings: Optional[Dict[str, Any]] = None,
    playlist_length: int = 25,
    **kwargs,
) -> List[Dict[str, Any]]:
    """Build and filter the Song Radio candidate pool from a source recording MBID."""
    if request is not None:
        source_mbid = request.source_mbid
        algorithm = request.algorithm
        minimum_score = request.minimum_score
        repeat_limit = request.repeat_limit
        year_start, year_end = request.year_start, request.year_end
        album_cap, artist_cap = request.max_tracks_per_album, request.max_tracks_per_artist
        min_bitrate = request.min_bitrate
        min_format = request.min_format
        min_bit_depth = request.min_bit_depth
        source_track = as_track_dict(getattr(request, "source_track", None))
        listenbrainz_enabled = getattr(request, "listenbrainz_enabled", True)
        use_subsonic_similar = getattr(request, "use_subsonic_similar", False)
    else:
        saved = settings or {}
        source_mbid = saved.get("source_mbid")
        algorithm = saved.get("algorithm", "5Y Balanced")
        minimum_score = saved.get("minimum_score", 20)
        repeat_limit = saved.get("repeat_limit", 6)
        year_start, year_end = saved.get("year_start"), saved.get("year_end")
        album_cap, artist_cap = saved.get("max_tracks_per_album", 4), saved.get("max_tracks_per_artist", 8)
        min_bitrate = saved.get("min_bitrate")
        min_format = saved.get("min_format")
        min_bit_depth = saved.get("min_bit_depth")
        source_track = saved.get("source_track")
        listenbrainz_enabled = saved.get("listenbrainz_enabled", True)
        use_subsonic_similar = saved.get("use_subsonic_similar", False)

    # When ListenBrainz is disabled there is nothing to expand from, so the
    # Subsonic similarity engine becomes the primary source instead of a
    # supplement.
    if not listenbrainz_enabled:
        use_subsonic_similar = True

    pool = await build_song_radio_pool(
        source_mbid=source_mbid,
        source_track=source_track,
        algorithm=algorithm,
        minimum_score=minimum_score,
        repeat_limit=repeat_limit,
        library_ids=library_ids,
        listenbrainz_enabled=listenbrainz_enabled,
        use_subsonic_similar=use_subsonic_similar,
    )

    if not pool:
        return []

    # The source track is the anchor of the playlist and must survive the
    # year/quality filters and the diversity caps.
    protected_ids = set()
    if source_track and source_track.get("id"):
        protected_ids.add(source_track["id"])

    return filter_song_radio_tracks(
        pool,
        year_start,
        year_end,
        album_cap,
        artist_cap,
        min_bitrate,
        min_format,
        min_bit_depth,
        protected_track_ids=protected_ids,
    )


async def curate_song_radio_wrapper(
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int,
    request: Any = None,
    ai_client=None,
    source_track: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> Tuple[List[str], str]:
    effective_source = as_track_dict(source_track)
    if effective_source is None and request is not None:
        effective_source = as_track_dict(getattr(request, "source_track", None))
    return await curate_song_radio(
        candidate_tracks,
        num_tracks,
        ai_client,
        effective_source,
    )


def build_song_radio_name(request: Any = None, source_track: Optional[Dict[str, Any]] = None, **kwargs) -> str:
    if request is not None and request.playlist_name:
        return request.playlist_name
    title = "Song Radio"
    if source_track:
        title = f"Song Radio: {source_track.get('title', 'Mix')}"
    elif request is not None:
        st = as_track_dict(getattr(request, "source_track", None))
        if st:
            title = f"Song Radio: {st.get('title', 'Mix')}"
    return title


def extra_song_radio_settings(request: Any = None, source_track: Optional[Dict[str, Any]] = None, **kwargs) -> Dict[str, Any]:
    if request is None:
        return {}
    st = as_track_dict(request.source_track)
    return {
        "source_mbid": request.source_mbid,
        "source_track": st,
        "listenbrainz_enabled": request.listenbrainz_enabled,
        "use_subsonic_similar": request.use_subsonic_similar,
        "algorithm": request.algorithm,
        "minimum_score": request.minimum_score,
        "repeat_limit": request.repeat_limit,
        "year_start": request.year_start,
        "year_end": request.year_end,
        "diversity_enabled": request.diversity_enabled,
        "max_tracks_per_album": request.max_tracks_per_album,
        "max_tracks_per_artist": request.max_tracks_per_artist,
        "min_bitrate": request.min_bitrate,
        "min_format": request.min_format,
        "min_bit_depth": request.min_bit_depth,
    }


async def refresh_song_radio_playlist(playlist: Dict[str, Any], db: DatabaseManager) -> int:
    """Refresh a Song Radio playlist using its stored source recording MBID.

    Args:
        playlist: Playlist row from ``get_playlist_by_navidrome_id_with_schedule_info``.
        db: Database manager.

    Returns:
        The number of tracks written to the playlist.

    Raises:
        ValueError: If no tracks or no curated selection could be produced.
    """
    navidrome_playlist_id = playlist.get("navidrome_playlist_id")
    settings = playlist.get("curation_settings") or {}
    library_ids = settings.get("library_ids") or playlist.get("library_ids") or []
    target_length = settings.get("playlist_length") or playlist.get("playlist_length", 25)

    tracks = await fetch_song_radio_tracks(
        library_ids=library_ids,
        playlist=playlist,
        settings=settings,
        playlist_length=target_length,
    )
    if not tracks:
        raise ValueError("No tracks found for Song Radio refresh")

    selected_ids, description = await curate_song_radio_wrapper(
        candidate_tracks=tracks,
        num_tracks=target_length,
        ai_client=None,
        source_track=settings.get("source_track"),
    )
    if not selected_ids:
        raise ValueError("No curated tracks generated")

    from ..playlist_metadata import description_refresh_enabled, resolve_refresh_description

    comment_to_use = resolve_refresh_description(
        existing_description=playlist.get("description"),
        generated_description=description,
        refresh_description=description_refresh_enabled(settings),
    )

    server_client = get_server_client()
    await server_client.update_playlist(
        playlist_id=navidrome_playlist_id,
        track_ids=selected_ids,
        comment=comment_to_use,
    )

    titles = {track["id"]: track.get("title", "") for track in tracks}
    track_titles = [titles[track_id] for track_id in selected_ids if track_id in titles]
    await db.update_playlist_content(
        navidrome_playlist_id=navidrome_playlist_id,
        songs=track_titles,
        description=comment_to_use,
    )
    return len(track_titles)


def _resolve_song_radio_artist_id(request: Any = None, playlist_name: str = "") -> str:
    """Resolve the stored ``artist_id`` for a Song Radio playlist.

    ``request.source_track`` may be a Pydantic model or a plain dict depending
    on whether the playlist is being created or refreshed, so both are handled.
    """
    if request is None:
        return ""
    source_track = as_track_dict(getattr(request, "source_track", None))
    if source_track is None:
        return ""
    return source_track.get("artist_id") or ""


SONG_RADIO_CONFIG = PlaylistTypeConfig(
    type_key="song_radio",
    fetch_tracks=fetch_song_radio_tracks,
    curate=curate_song_radio_wrapper,
    build_playlist_name=build_song_radio_name,
    default_refresh_frequency="none",
    schedule_on_create=True,
    extra_curation_settings=extra_song_radio_settings,
    artist_id_resolver=_resolve_song_radio_artist_id,
)
