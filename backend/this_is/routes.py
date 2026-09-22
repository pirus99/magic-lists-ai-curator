"""FastAPI routes for 'This Is' (single-artist) playlists."""
from fastapi import APIRouter, Depends, HTTPException

from ..schemas import CreatePlaylistRequest, Playlist
from ..database import DatabaseManager, get_db
from ..core.playlist_builder import build_playlist
from ..core.dependencies import get_navidrome_client
from .builder import THIS_IS_CONFIG


router = APIRouter(prefix="/api", tags=["this_is"])


@router.post("/create_playlist", response_model=Playlist)
async def create_playlist(
    request: CreatePlaylistRequest,
    db: DatabaseManager = Depends(get_db),
):
    """Create an AI-curated 'This Is' playlist for a single artist.

    This endpoint supersedes the former ``/api/create_playlist_with_description``
    route: the AI description is always generated and stored, so the separate
    endpoint is no longer needed.
    """
    try:
        nav_client = get_navidrome_client()

        # Validate the requested artist exists.
        all_artists = await nav_client.get_artists()
        if not getattr(request, "artist_ids", None):
            raise HTTPException(status_code=400, detail="At least one artist must be selected")
        first_artist_id = request.artist_ids[0]
        selected = [a for a in all_artists if a["id"] == first_artist_id]
        if not selected:
            raise HTTPException(status_code=404, detail="Artist not found")

        return await build_playlist(
            THIS_IS_CONFIG,
            db,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids,
            refresh_frequency=request.refresh_frequency,
            request=request,
            artist_name=selected[0]["name"],
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create playlist: {str(e)}")
