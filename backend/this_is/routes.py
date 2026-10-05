"""FastAPI routes for 'This Is' (single-artist) playlists."""
from fastapi import APIRouter, Depends, HTTPException

from ..schemas import CreatePlaylistRequest, Playlist
from ..database import DatabaseManager, get_db
from ..core.playlist_builder import build_playlist
from ..core.server_router import get_server_client
from ..services.lastfm_service import normalize_artist, resolve_artist_mbid
from .builder import THIS_IS_CONFIG


router = APIRouter(prefix="/api", tags=["this_is"])


async def _resolve_artist(
    request: CreatePlaylistRequest,
    all_artists: list,
):
    """Resolve the target artist for a 'This Is' request.

    Artist ids take precedence. When none are supplied, the manual fallback
    (``artist_name`` plus optional ``artist_mbid``) is used: Last.fm resolves the
    name to a MusicBrainz ID, and the library artist is then matched by MBID and
    finally by normalized name.

    Returns:
        Tuple of ``(artist_dict, display_name)``.

    Raises:
        HTTPException: 400 when neither an artist id nor a name is supplied, or 404
            when the artist cannot be found in the library.
    """
    if not getattr(request, "artist_ids", None):
        typed_name = (request.artist_name or "").strip()
        typed_mbid = (request.artist_mbid or "").strip()
        if not typed_name and not typed_mbid:
            raise HTTPException(
                status_code=400,
                detail="At least one artist must be selected, or an artist name must be provided",
            )

        target_mbid = typed_mbid or await resolve_artist_mbid(typed_name)

        if target_mbid:
            for artist in all_artists:
                if (artist.get("mbid") or "").strip().lower() == target_mbid.lower():
                    return artist, artist["name"]

        if typed_name:
            normalized = normalize_artist(typed_name)
            for artist in all_artists:
                if normalize_artist(artist.get("name")) == normalized:
                    return artist, typed_name
            # Tolerate a partial name match for partial user input.
            for artist in all_artists:
                name = normalize_artist(artist.get("name"))
                if name and (normalized in name or name in normalized):
                    return artist, typed_name

        searched = typed_name or f"MBID {target_mbid}"
        raise HTTPException(
            status_code=404,
            detail=(
                f"Artist '{searched}' was not found in your library. "
                "Last.fm has no matching artist either, so there are no tracks to build from. "
                "Check the spelling, or pick an artist that exists in your library."
            ),
        )

    first_artist_id = request.artist_ids[0]
    selected = [a for a in all_artists if a["id"] == first_artist_id]
    if not selected:
        raise HTTPException(status_code=404, detail="Artist not found")

    return selected[0], selected[0]["name"]


@router.post("/create_playlist", response_model=Playlist)
async def create_playlist(
    request: CreatePlaylistRequest,
    db: DatabaseManager = Depends(get_db),
):
    """Create an AI-curated 'This Is' playlist for a single artist.

    This endpoint supersedes the former ``/api/create_playlist_with_description``
    route: the AI description is always generated and stored, so the separate
    endpoint is no longer needed.

    The artist may be supplied either via ``artist_ids`` or, when the library has no
    usable entry, via the ``artist_name``/``artist_mbid`` fallback fields.
    """
    try:
        nav_client = get_server_client()

        # Validate the requested artist exists (or can be resolved from the fallback).
        all_artists = await nav_client.get_artists()
        artist, display_name = await _resolve_artist(request, all_artists)

        # Backfill the resolved id/name onto the request so the builder, the persisted
        # curation settings and later scheduled refreshes all work for fallback requests.
        request.artist_ids = [artist["id"]]
        request.artist_name = display_name
        if not request.artist_mbid:
            request.artist_mbid = artist.get("mbid")

        return await build_playlist(
            THIS_IS_CONFIG,
            db,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids,
            refresh_frequency=request.refresh_frequency,
            request=request,
            artist_name=display_name,
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create playlist: {str(e)}")
