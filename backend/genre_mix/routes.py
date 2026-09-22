"""FastAPI routes for 'Genre Mix' playlists."""
from fastapi import APIRouter, Depends, HTTPException

from ..schemas import CreateGenrePlaylistRequest, Playlist
from ..database import DatabaseManager, get_db
from ..core.playlist_builder import build_playlist
from .builder import GENRE_MIX_CONFIG


router = APIRouter(prefix="/api", tags=["genre_mix"])


@router.post("/create_genre_playlist", response_model=Playlist)
async def create_genre_playlist(
    request: CreateGenrePlaylistRequest,
    db: DatabaseManager = Depends(get_db),
):
    """Create an AI-curated 'Genre Mix' playlist for multiple genres."""
    try:
        if not request.genres:
            raise HTTPException(status_code=400, detail="At least one genre must be selected")
        return await build_playlist(
            GENRE_MIX_CONFIG,
            db,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids,
            refresh_frequency=request.refresh_frequency,
            request=request,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create genre playlist: {str(e)}")
