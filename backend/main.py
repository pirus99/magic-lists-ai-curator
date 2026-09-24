"""Application entry point for Magic Lists for Navidrome.

This module is intentionally thin. It owns the FastAPI app lifecycle (static /
template mounting, startup/shutdown, scheduler bootstrap, system checks) and the
small set of generic, type-agnostic HTTP endpoints (artists, genres, playlists
CRUD, scheduler status, recipes, health check, library analytics, SPA routing).

All per-type playlist logic (creation, refresh, curation) lives in the type
packages under ``backend/<type>/`` and is exposed through their ``APIRouter``
instances, which are mounted below. The shared build/refresh orchestration lives
in ``core.playlist_builder`` and ``core.scheduler``.
"""
from fastapi import FastAPI, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import Query
import uvicorn
import os
import logging
import logging.handlers
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel

# Load environment variables first
load_dotenv()

# Get log level from environment (ERROR=minimal, INFO=normal, DEBUG=verbose)
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging for scheduler activities with rotation
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.handlers.RotatingFileHandler(
            'scheduler.log',
            maxBytes=5*1024*1024,
            backupCount=2,
            encoding='utf-8'
        ),
        logging.StreamHandler()
    ]
)

# Create a specific logger for scheduler activities
scheduler_logger = logging.getLogger('scheduler')

# Reduce httpx logging verbosity
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Core / type package imports
# ---------------------------------------------------------------------------
from .database import DatabaseManager, get_db
from .schemas import (
    CreatePlaylistRequest,
    CreateGenrePlaylistRequest,
    Playlist,
    RediscoverWeeklyV2Response,
    CreateRediscoverPlaylistRequest,
    PlaylistWithScheduleInfo,
)
from .core.dependencies import get_ai_client
from .core.server_router import get_server_client
import backend.core.scheduler as scheduler_module
from .core.scheduler import (
    schedule_playlist_refresh,
    refresh_scheduled_playlists,
    register_refresh_handler,
)
from .this_is.routes import router as this_is_router
from .genre_mix.routes import router as genre_mix_router
from .rediscover.routes import router as rediscover_router
from .artist_radio.routes import router as artist_radio_router
from .this_is.builder import refresh_this_is_playlist
from .genre_mix.builder import refresh_genre_playlist
from .rediscover.builder import refresh_rediscover_playlist
from .artist_radio.builder import refresh_artist_radio_playlist
from .recipe_manager import recipe_manager
# SYSTEM CHECK FEATURE - START
from .services.health_check_service import HealthCheckService
# SYSTEM CHECK FEATURE - END

app = FastAPI(title="MagicLists Navidrome MVP")

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
scheduler: AsyncIOScheduler = None

# SYSTEM CHECK FEATURE - START
system_check_passed = False
system_check_results = None
# SYSTEM CHECK FEATURE - END


@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on app startup and register refresh handlers."""
    global scheduler, system_check_passed, system_check_results
    scheduler = AsyncIOScheduler()
    scheduler_module.scheduler = scheduler
    scheduler.start()
    scheduler_logger.info("Scheduler started successfully")

    # Register per-type refresh handlers with the shared scheduler registry so
    # refresh_scheduled_playlists can dispatch without importing the type packages.
    register_refresh_handler("this_is", refresh_this_is_playlist)
    register_refresh_handler("genre_mix", refresh_genre_playlist)
    register_refresh_handler("rediscover", refresh_rediscover_playlist)
    register_refresh_handler("rediscover_weekly_v2", refresh_rediscover_playlist)
    register_refresh_handler("artist_radio", refresh_artist_radio_playlist)

    schedule_playlist_refresh()
    scheduler_logger.info("Cron job auto-started on application startup")

    # SYSTEM CHECK FEATURE - START
    try:
        health_service = HealthCheckService()
        system_check_results = await health_service.run_checks()
        system_check_passed = system_check_results.get("all_passed", False)

        if system_check_passed:
            scheduler_logger.info("System health checks passed on startup")
        else:
            scheduler_logger.warning("System health checks failed on startup")

        for check in system_check_results.get("checks", []):
            status_emoji = "OK" if check["status"] == "success" else "WARN" if check["status"] == "warning" else "INFO" if check["status"] == "info" else "ERR"
            if "AI Provider" in check["name"]:
                ai_provider = os.getenv("AI_PROVIDER", "openrouter")
                if check["status"] == "success":
                    if "model:" in check["message"]:
                        model_part = check["message"].split("model: ")[1].rstrip(")")
                        scheduler_logger.info(f"AI Provider: {ai_provider.title()} with model '{model_part}' - Ready")
                    else:
                        scheduler_logger.info(f"AI Provider: {ai_provider.title()} - Ready")
                elif check["status"] == "warning":
                    if "not set" in check["message"]:
                        scheduler_logger.info(f"AI Provider: {ai_provider.title()} - No API key (using fallback algorithms)")
                    else:
                        scheduler_logger.warning(f"AI Provider: {ai_provider.title()} - {check['message']}")
                elif check["status"] == "error":
                    scheduler_logger.error(f"AI Provider: {ai_provider.title()} - {check['message']}")
            else:
                scheduler_logger.info(f"{status_emoji} {check['name']}: {check['status']}")
    except Exception as e:
        scheduler_logger.error(f"Failed to run system checks on startup: {e}")
        system_check_passed = False
        system_check_results = {
            "all_passed": False,
            "checks": [{
                "name": "System Check Service",
                "status": "error",
                "message": f"Failed to run health checks: {str(e)}",
                "suggestion": "Check application logs and restart the service"
            }]
        }
    # SYSTEM CHECK FEATURE - END


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup scheduler on app shutdown"""
    global scheduler
    if scheduler:
        scheduler.shutdown()
        scheduler_logger.info("Scheduler shutdown completed")


# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Templates
templates = Jinja2Templates(directory="frontend/templates")


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve the main HTML page"""
    if not system_check_passed:
        return RedirectResponse(url="/system-check", status_code=302)
    return templates.TemplateResponse("index.html", {"request": request})


# SYSTEM CHECK FEATURE - START
@app.get("/system-check", response_class=HTMLResponse)
async def system_check_page(request: Request):
    """Serve the system check page"""
    return templates.TemplateResponse("index.html", {"request": request})
# SYSTEM CHECK FEATURE - END


# ---------------------------------------------------------------------------
# Generic Navidrome data endpoints
# ---------------------------------------------------------------------------
@app.get("/api/artists")
async def get_artists(library_id: List[str] = Query(None)):
    """Get list of artists from Navidrome"""
    try:
        client = get_server_client()
        return await client.get_artists(library_id)
    except Exception as e:
        error_msg = str(e)
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch artists: {error_msg}")


@app.get("/api/genres")
async def get_genres(library_id: List[str] = Query(None)):
    """Get list of genres from Navidrome"""
    try:
        client = get_server_client()
        return await client.get_genres(library_id)
    except Exception as e:
        error_msg = str(e)
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch genres: {error_msg}")


@app.get("/api/artists-by-genre")
async def get_artists_by_genre(genres: List[str] = Query(...), library_id: List[str] = Query(None)):
    """Get list of artists that have tracks in the specified genres"""
    try:
        client = get_server_client()
        return await client.get_artists_by_genres(genres, library_id)
    except Exception as e:
        error_msg = str(e)
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch artists by genre: {error_msg}")


@app.get("/api/music-folders")
async def get_music_folders():
    """Get list of music folders/libraries from Navidrome"""
    try:
        client = get_server_client()
        return await client.get_music_folders()
    except Exception as e:
        error_msg = str(e)
        if "Invalid username or password" in error_msg or "No authentication method available" in error_msg:
            raise HTTPException(status_code=401, detail=error_msg)
        elif "Network error" in error_msg or "connecting to Navidrome" in error_msg:
            raise HTTPException(status_code=503, detail=f"Cannot connect to Navidrome server: {error_msg}")
        else:
            raise HTTPException(status_code=500, detail=f"Failed to fetch music folders: {error_msg}")


# SYSTEM CHECK FEATURE - START
@app.get("/api/health-check")
async def get_health_check():
    """Get system health check results"""
    global system_check_passed, system_check_results
    try:
        health_service = HealthCheckService()
        fresh_results = await health_service.run_checks()
        system_check_passed = fresh_results.get("all_passed", False)
        system_check_results = fresh_results
        if system_check_passed:
            scheduler_logger.info("System health checks passed via API")
        else:
            scheduler_logger.warning("System health checks failed via API")
        return fresh_results
    except Exception as e:
        scheduler_logger.error(f"Failed to run health checks via API: {e}")
        return {
            "all_passed": False,
            "checks": [{
                "name": "System Check Service",
                "status": "error",
                "message": f"Failed to run health checks: {str(e)}",
                "suggestion": "Check application logs and restart the service"
            }]
        }
# SYSTEM CHECK FEATURE - END


# ---------------------------------------------------------------------------
# Playlist CRUD + scheduling endpoints (type-agnostic)
# ---------------------------------------------------------------------------
@app.get("/api/playlists")
async def get_all_playlists(db: DatabaseManager = Depends(get_db)):
    """Get all playlists with scheduling information"""
    try:
        playlists = await db.get_all_playlists_with_schedule_info()
        for playlist in playlists:
            songs = playlist.get("songs", [])
            playlist["track_count"] = len(songs) if isinstance(songs, list) else 0
        return playlists
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch playlists: {str(e)}")


@app.get("/api/playlists/{playlist_id}")
async def get_playlist_detail(playlist_id: int, db: DatabaseManager = Depends(get_db)):
    """Get a single playlist with its scheduling info and saved curation settings"""
    try:
        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")
        return playlist
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch playlist: {str(e)}")


@app.delete("/api/playlists/{playlist_id}")
async def delete_playlist(playlist_id: int, db: DatabaseManager = Depends(get_db)):
    """Delete a playlist from the configured server and the local database."""
    try:
        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        navidrome_playlist_id = playlist.get("navidrome_playlist_id")
        if navidrome_playlist_id:
            server_client = get_server_client()
            scheduler_logger.info(
                f"Deleting playlist {playlist_id} from media server "
                f"(ID: {navidrome_playlist_id})"
            )
            try:
                await server_client.delete_playlist(navidrome_playlist_id)
            except Exception as delete_error:
                scheduler_logger.warning(
                    f"Failed to delete playlist from media server: {delete_error}"
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to delete playlist from media server: {delete_error}",
                ) from delete_error
            await db.delete_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)

        success = await db.delete_playlist(playlist_id)
        if not success:
            raise HTTPException(status_code=404, detail="Playlist not found in database")
        return {"message": "Playlist deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete playlist: {str(e)}")


class UpdatePlaylistSettingsRequest(BaseModel):
    """Request schema for updating a playlist's saved curation settings and metadata"""
    curation_settings: Dict[str, Any]
    refresh_frequency: Optional[str] = None
    playlist_name: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None


@app.put("/api/playlists/{playlist_id}/settings")
async def update_playlist_settings(
    playlist_id: int,
    request: UpdatePlaylistSettingsRequest,
    db: DatabaseManager = Depends(get_db)
):
    """Update a playlist's saved curation settings and reconcile its refresh schedule"""
    try:
        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        navidrome_playlist_id = playlist.get("navidrome_playlist_id")
        if not navidrome_playlist_id:
            raise HTTPException(status_code=400, detail="Playlist has no media server ID")

        server_client = get_server_client()

        if request.playlist_name is not None or request.description is not None or request.is_public is not None:
            try:
                await server_client.update_playlist_metadata(
                    playlist_id=navidrome_playlist_id,
                    name=request.playlist_name,
                    comment=request.description,
                    is_public=request.is_public,
                )
            except Exception as update_error:
                scheduler_logger.warning(
                    f"Failed to sync playlist metadata to media server: {update_error}"
                )
                raise HTTPException(
                    status_code=502,
                    detail=f"Failed to update playlist on media server: {update_error}",
                ) from update_error

            await db.update_playlist_metadata(
                playlist_id=playlist_id,
                playlist_name=request.playlist_name if request.playlist_name is not None else playlist.get("playlist_name"),
                description=request.description if request.description is not None else playlist.get("description"),
                is_public=request.is_public if request.is_public is not None else playlist.get("is_public"),
            )

        new_length = request.curation_settings.get("playlist_length")
        await db.update_playlist_settings(
            playlist_id=playlist_id,
            curation_settings=request.curation_settings,
            playlist_length=new_length if new_length is not None else None
        )

        frequency = request.refresh_frequency if request.refresh_frequency is not None else playlist.get("refresh_frequency")
        frequency = frequency or "none"
        existing = await db.get_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)

        if frequency in ("none", "never"):
            if existing:
                await db.delete_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)
                scheduler_logger.info(f"Removed schedule for playlist {navidrome_playlist_id}")
        else:
            from .core.scheduler import calculate_next_refresh
            next_refresh = calculate_next_refresh(frequency)
            if existing:
                await db.update_scheduled_playlist_frequency(existing.id, frequency, next_refresh)
                scheduler_logger.info(f"Updated schedule for {navidrome_playlist_id} -> {frequency}")
            else:
                await db.create_scheduled_playlist(
                    playlist_type=playlist.get("playlist_type") or "this_is",
                    navidrome_playlist_id=navidrome_playlist_id,
                    refresh_frequency=frequency,
                    next_refresh=next_refresh
                )
                schedule_playlist_refresh()
                scheduler_logger.info(f"Created schedule for {navidrome_playlist_id} -> {frequency}")

        updated = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        updated["track_count"] = len(updated.get("songs", []) or [])
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update playlist settings: {str(e)}")


class _RefreshTarget:
    """Lightweight stand-in for a ScheduledPlaylist used by manual refresh dispatch."""
    def __init__(self, navidrome_playlist_id: str, refresh_frequency: str, playlist_type: str, scheduled_id: int = 0):
        self.navidrome_playlist_id = navidrome_playlist_id
        self.refresh_frequency = refresh_frequency
        self.playlist_type = playlist_type
        self.id = scheduled_id


@app.post("/api/playlists/{playlist_id}/refresh")
async def refresh_playlist_endpoint(playlist_id: int, db: DatabaseManager = Depends(get_db)):
    """Manually regenerate a playlist from its saved curation settings"""
    try:
        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        navidrome_playlist_id = playlist.get("navidrome_playlist_id")
        if not navidrome_playlist_id:
            raise HTTPException(status_code=400, detail="Playlist has no Navidrome ID")

        playlist_type = playlist.get("playlist_type") or "this_is"
        frequency = playlist.get("refresh_frequency") or "none"

        scheduled = _RefreshTarget(
            navidrome_playlist_id=navidrome_playlist_id,
            refresh_frequency=frequency,
            playlist_type=playlist_type
        )

        if playlist_type == "genre_mix":
            await refresh_genre_playlist(playlist, db)
        elif playlist_type == "artist_radio":
            await refresh_artist_radio_playlist(playlist, db)
        elif playlist_type in ("rediscover", "rediscover_weekly_v2"):
            await refresh_rediscover_playlist(scheduled, db)
        else:
            await refresh_this_is_playlist(scheduled, db)

        await db.update_playlist_last_refreshed(navidrome_playlist_id)

        existing = await db.get_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)
        if existing and frequency not in ("none", "never"):
            from .core.scheduler import calculate_next_refresh
            await db.update_scheduled_playlist_next_refresh(existing.id, calculate_next_refresh(frequency))

        return {"message": "Playlist refreshed successfully", "playlist_id": navidrome_playlist_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to refresh playlist: {str(e)}")


# ---------------------------------------------------------------------------
# Recipes / scheduler / AI info / analytics endpoints
# ---------------------------------------------------------------------------
@app.get("/api/recipes")
async def get_available_recipes():
    """Get information about available playlist generation recipes"""
    try:
        return recipe_manager.list_available_recipes()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load recipes: {str(e)}")


@app.get("/api/recipes/validate")
async def validate_recipes():
    """Validate all recipe files and return any errors"""
    try:
        registry = recipe_manager._load_registry()
        validation_results = {}
        for playlist_type, recipe_filename in registry.items():
            errors = recipe_manager.validate_recipe(recipe_filename)
            validation_results[playlist_type] = {
                "recipe_file": recipe_filename,
                "valid": len(errors) == 0,
                "errors": errors
            }
        return validation_results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to validate recipes: {str(e)}")


@app.get("/api/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status and active jobs"""
    try:
        if scheduler:
            jobs = list(scheduler.get_jobs())
            job_info = []
            for job in jobs:
                job_info.append({
                    "id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "func": job.func.__name__ if hasattr(job, 'func') else str(job.func)
                })
            return {
                "scheduler_running": scheduler.running,
                "active_jobs": len(jobs),
                "jobs": job_info,
                "scheduler_state": str(scheduler.state)
            }
        return {"scheduler_running": False, "error": "Scheduler not initialized"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")


@app.post("/api/scheduler/trigger")
async def trigger_scheduler_check():
    """Manually trigger the scheduler to check for playlists due for refresh"""
    try:
        scheduler_logger.info("Manual scheduler trigger requested via API")
        await refresh_scheduled_playlists()
        return {"message": "Scheduler check completed successfully"}
    except Exception as e:
        scheduler_logger.error(f"Error in manual scheduler trigger: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger scheduler: {str(e)}")


@app.post("/api/scheduler/start")
async def start_scheduler_job():
    """Manually start the recurring scheduler job"""
    try:
        schedule_playlist_refresh()
        jobs = list(scheduler.get_jobs()) if scheduler else []
        scheduler_logger.info(f"Scheduler job registration requested. Active jobs: {len(jobs)}")
        return {
            "message": "Scheduler job started",
            "active_jobs": len(jobs),
            "jobs": [{"id": job.id, "next_run": job.next_run_time.isoformat() if job.next_run_time else None} for job in jobs]
        }
    except Exception as e:
        scheduler_logger.error(f"Error starting scheduler job: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start scheduler job: {str(e)}")


@app.get("/api/ai-model-info")
async def get_ai_model_info():
    """Get current AI model information for analytics"""
    try:
        ai_client_instance = get_ai_client()
        return {
            "provider": ai_client_instance.provider.provider_type,
            "model": ai_client_instance.model or "unknown",
            "has_api_key": bool(ai_client_instance.api_key)
        }
    except Exception:
        return {"provider": "unknown", "model": "unknown", "has_api_key": False}


@app.post("/api/track-library-size")
async def track_library_size(db: DatabaseManager = Depends(get_db)):
    """Track library size for analytics (called post-launch)"""
    try:
        should_track = await db.should_track_library_size()
        if not should_track:
            return {"message": "Library size tracking not needed yet", "tracked": False}

        nav_client = get_server_client()
        song_count = await nav_client.get_total_song_count()
        user_id = await db.get_or_create_user_id()
        await db.record_library_size(song_count)
        scheduler_logger.info(f"Library size tracked: {song_count} songs for user {user_id}")
        return {
            "message": "Library size tracked successfully",
            "tracked": True,
            "song_count": song_count,
            "user_id": user_id
        }
    except Exception as e:
        scheduler_logger.error(f"Error tracking library size: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to track library size: {str(e)}")


# ---------------------------------------------------------------------------
# Mount per-type routers (creation + type-specific endpoints)
# ---------------------------------------------------------------------------
app.include_router(this_is_router)
app.include_router(genre_mix_router)
app.include_router(rediscover_router)
app.include_router(artist_radio_router)


# ---------------------------------------------------------------------------
# SPA routing (MUST be last route)
# ---------------------------------------------------------------------------
@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_router(request: Request, path: str):
    """Handle SPA routing - serve app for known paths, redirect unknown paths"""
    spa_paths = ["this-is", "artist-radio", "re-discover", "playlists", "terms"]
    if path in spa_paths:
        if not system_check_passed:
            return RedirectResponse(url="/system-check", status_code=302)
        return templates.TemplateResponse("index.html", {"request": request})
    return RedirectResponse(url="/", status_code=302)


if __name__ == "__main__":
    import uvicorn.config

    class FilteredUvicornFormatter(uvicorn.formatters.DefaultFormatter):
        def format(self, record):
            if hasattr(record, 'args') and record.args:
                message = str(record.args[2]) if len(record.args) > 2 else ""
                if 'GET / HTTP' in message:
                    return ""
            return super().format(record)

    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["access"]["()"] = FilteredUvicornFormatter

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=log_config
    )
