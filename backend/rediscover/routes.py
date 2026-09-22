"""FastAPI routes for the active Re-Discover (v2) playlist flow."""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..core.dependencies import get_ai_client, get_navidrome_client
from ..database import DatabaseManager, get_db
from ..schemas import CreateRediscoverPlaylistRequest, RediscoverWeeklyV2Response
from .builder import create_rediscover_playlist_v2
from .processor import ReDiscoverV2Processor


router = APIRouter(prefix="/api", tags=["rediscover"])


@router.get("/rediscover-weekly-v2", response_model=RediscoverWeeklyV2Response)
async def get_rediscover_weekly_v2(
    library_ids: Optional[List[str]] = None,
    db: DatabaseManager = Depends(get_db),
):
    """Generate Re-Discover Weekly v2.0 playlist using temporal analysis and two-phase AI."""
    try:
        nav_client = get_navidrome_client()
        ai_client = get_ai_client()
        user_id = await db.get_or_create_user_id()
        server_id = nav_client.base_url or "unknown_server"

        processor = ReDiscoverV2Processor(nav_client, ai_client, db)
        result = await processor.generate_playlist(user_id, server_id, library_ids)
        return RediscoverWeeklyV2Response(**result)
    except Exception as e:
        error_msg = str(e)
        if "Insufficient listening history" in error_msg:
            raise HTTPException(status_code=404, detail="Insufficient listening history. Star favorites and listen regularly. Check back in 2-3 weeks!")
        elif "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to generate Re-Discover Weekly v2.0: {error_msg}")


@router.post("/create-rediscover-playlist-v2")
async def create_rediscover_playlist(
    request: CreateRediscoverPlaylistRequest,
    db: DatabaseManager = Depends(get_db),
):
    """Create a Re-Discover Weekly v2.0 playlist in Navidrome."""
    try:
        return await create_rediscover_playlist_v2(request, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logging.getLogger("scheduler").error(f"❌ Failed to create Re-Discover Weekly v2.0 playlist: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create Re-Discover Weekly v2.0 playlist: {str(e)}")
