"""FastAPI routes for Song Radio."""
from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from ..database import DatabaseManager, get_db
from ..core.playlist_builder import build_playlist
from ..core.server_router import get_server_client
from ..services.listenbrainz_service import (
    ListenBrainzService,
    MAX_RECORDING_SCORE,
    MIN_RECORDING_SCORE,
)
from ..schemas import SongRadioRequest, SongRadioSearchRequest, SongRadioPoolRequest, Playlist
from .builder import SONG_RADIO_CONFIG, as_track_dict, build_song_radio_pool


router = APIRouter(prefix="/api", tags=["song_radio"])


@router.post("/song-radio/search", tags=["song_radio"])
async def search_song_radio_tracks(
    request: SongRadioSearchRequest,
):
    """Search the library for tracks by title, artist, or album."""
    try:
        client = get_server_client()
        tracks = await client.search_tracks(
            request.query,
            request.library_ids,
            limit=request.limit,
        )
        return tracks
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/song-radio/recommendations", tags=["song_radio"])
async def get_song_recommendations(
    source_mbid: str,
    algorithm: str,
    minimum_score: int = MIN_RECORDING_SCORE,
):
    try:
        UUID(source_mbid)
        return await ListenBrainzService().get_similar_recordings(
            source_mbid, algorithm, minimum_score
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/song-radio/build-pool", tags=["song_radio"])
async def build_song_radio_pool_endpoint(
    request: SongRadioPoolRequest,
):
    """Build the candidate pool for a source track without creating a playlist.

    Returns the matched local tracks plus a count so the user can decide whether
    to proceed with playlist creation or pick a different source track.
    """
    try:
        # A MusicBrainz recording ID is required unless the Subsonic similarity
        # engine is used, which only needs the source track's server ID.
        if not request.source_mbid and not request.use_subsonic_similar:
            raise ValueError("A MusicBrainz recording ID is required")
        if request.source_mbid:
            UUID(request.source_mbid)
        if request.minimum_score < MIN_RECORDING_SCORE or request.minimum_score > MAX_RECORDING_SCORE:
            raise ValueError(
                f"Minimum score must be between {MIN_RECORDING_SCORE} and {MAX_RECORDING_SCORE}"
            )
        if request.repeat_limit < 1 or request.repeat_limit > 6:
            raise ValueError("Repeat limit must be between 1 and 6")

        source_track = as_track_dict(request.source_track)

        pool = await build_song_radio_pool(
            source_mbid=request.source_mbid,
            source_track=source_track,
            algorithm=request.algorithm,
            minimum_score=request.minimum_score,
            repeat_limit=request.repeat_limit,
            library_ids=request.library_ids,
            listenbrainz_enabled=request.listenbrainz_enabled,
            use_subsonic_similar=request.use_subsonic_similar,
            include_source_track=False,
        )
        return {
            "pool_size": len(pool),
            "tracks": pool,
            "source_mbid": request.source_mbid,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build Song Radio pool: {exc}")


@router.post("/create_song_radio", response_model=Playlist)
async def create_song_radio(
    request: SongRadioRequest,
    db: DatabaseManager = Depends(get_db),
):
    try:
        if not request.source_mbid and not request.use_subsonic_similar:
            raise ValueError("A MusicBrainz recording ID is required")
        if request.source_mbid:
            UUID(request.source_mbid)
        if request.minimum_score < MIN_RECORDING_SCORE or request.minimum_score > MAX_RECORDING_SCORE:
            raise ValueError(
                f"Minimum score must be between {MIN_RECORDING_SCORE} and {MAX_RECORDING_SCORE}"
            )
        if request.year_start and request.year_end and request.year_start > request.year_end:
            raise ValueError("Year start must not be after year end")
        if request.max_tracks_per_album < 0 or request.max_tracks_per_artist < 0:
            raise ValueError("Diversity caps cannot be negative")
        if request.repeat_limit < 1 or request.repeat_limit > 6:
            raise ValueError("Repeat limit must be between 1 and 6")

        return await build_playlist(
            SONG_RADIO_CONFIG,
            db,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids,
            refresh_frequency=request.refresh_frequency,
            request=request,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create Song Radio playlist: {exc}")
