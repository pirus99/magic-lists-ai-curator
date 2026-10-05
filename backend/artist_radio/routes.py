"""FastAPI routes for Artist Radio."""
from fastapi import APIRouter, Depends, HTTPException
from uuid import UUID

from ..database import DatabaseManager, get_db
from ..core.playlist_builder import build_playlist
from ..core.server_router import get_server_client
from ..services.listenbrainz_service import ListenBrainzService
from ..schemas import ArtistRadioRecommendationRequest, ArtistRadioRequest, Playlist
from .builder import ARTIST_RADIO_CONFIG


router = APIRouter(prefix="/api", tags=["artist_radio"])


@router.post("/artist-radio/recommendations", tags=["artist_radio"])
async def get_recommendations(
    source_mbid: str,
    algorithm: str,
    minimum_score: int = 50,
):
    try:
        UUID(source_mbid)
        return await ListenBrainzService().get_recommendations(
            source_mbid, algorithm, minimum_score
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/artist-radio/recommendations/local", tags=["artist_radio"])
async def get_local_recommendations(
    request: ArtistRadioRecommendationRequest,
    library_id: str = None,
):
    try:
        UUID(request.source_mbid)
        service = ListenBrainzService()
        recommendations = await service.get_recommendations(
            request.source_mbid, request.algorithm, request.minimum_score
        )
        local_artists = await get_server_client().get_artists(
            [library_id] if library_id else request.library_ids
        )
        by_mbid = {a.get("mbid"): a for a in local_artists if a.get("mbid")}
        by_name = {_normalize_name(a.get("name", "")): a for a in local_artists}
        matched, seen = [], set()
        for recommendation in recommendations:
            local = by_mbid.get(recommendation["mbid"]) or by_name.get(_normalize_name(recommendation["name"]))
            if local and local["id"] not in seen:
                matched.append({**recommendation, "local_artist_id": local["id"], "local_artist_name": local["name"]})
                seen.add(local["id"])
        if not matched:
            raise ValueError("ListenBrainz returned no artists available in the selected libraries")
        return matched[:20]
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.post("/create_artist_radio", response_model=Playlist)
async def create_artist_radio(
    request: ArtistRadioRequest,
    db: DatabaseManager = Depends(get_db),
):
    try:
        if request.listenbrainz_enabled:
            if not request.source_mbid:
                raise ValueError("A MusicBrainz artist ID is required when ListenBrainz is enabled")
            UUID(request.source_mbid)
        if request.minimum_score < 50 or request.minimum_score > 400:
            raise ValueError("Minimum score must be between 50 and 400")
        if request.year_start and request.year_end and request.year_start > request.year_end:
            raise ValueError("Year start must not be after year end")
        if request.max_tracks_per_album < 0 or request.max_tracks_per_artist < 0:
            raise ValueError("Diversity caps cannot be negative")
        artists = await get_server_client().get_artists(request.library_ids)
        selected = {a["id"] for a in artists}
        if request.artist_id not in selected:
            raise ValueError("Source artist is not available in the selected libraries")
        if not set(request.recommendation_ids + request.manual_artist_ids).issubset(selected):
            raise ValueError("One or more selected artists are not available in the selected libraries")
        return await build_playlist(
            ARTIST_RADIO_CONFIG,
            db,
            playlist_length=request.playlist_length,
            library_ids=request.library_ids,
            refresh_frequency=request.refresh_frequency,
            request=request,
            artist_name=request.artist_name or next(a["name"] for a in artists if a["id"] == request.artist_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create Artist Radio playlist: {exc}")


def _normalize_name(name: str) -> str:
    return " ".join(name.casefold().split())
