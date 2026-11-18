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
import time
from typing import List, Optional, Dict, Any

from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from pydantic import BaseModel

# Load environment variables first
load_dotenv()

# Configure logging before anything else logs. The policy (DEBUG / INFO / ERROR)
# lives in backend.logging_config so every module and the HTTP access log share
# one definition of what each level means.
from .logging_config import (
    access_level,
    active_policy_name,
    configure_logging,
    log_startup,
)

LOG_LEVEL = configure_logging()

logger = logging.getLogger(__name__)

# Kept as an alias: the scheduler modules and the startup sequence below use it.
scheduler_logger = logger

# ---------------------------------------------------------------------------
# Core / type package imports
# ---------------------------------------------------------------------------
from .database import DatabaseManager, get_db, get_database_path
from .core.dependencies import get_ai_client
from .core.server_router import get_server_client
import backend.core.scheduler as scheduler_module
from .core.scheduler import (
    build_schedule_payload,
    enqueue_all_due,
    enqueue_manual_refresh,
    get_job_info,
    get_next_run_times,
    register_refresh_handler,
    rehydrate_jobs,
    sync_playlist_job,
)
from .core.refresh_queue import get_refresh_queue
from .core.schedule_spec import ScheduleSpec, describe_schedule, spec_from_frequency
from .this_is.routes import router as this_is_router
from .genre_mix.routes import router as genre_mix_router
from .rediscover.routes import router as rediscover_router
from .artist_radio.routes import router as artist_radio_router
from .song_radio.routes import router as song_radio_router
from .this_is.builder import refresh_this_is_playlist
from .genre_mix.builder import refresh_genre_playlist
from .rediscover.builder import refresh_rediscover_playlist
from .artist_radio.builder import refresh_artist_radio_playlist
from .song_radio.builder import refresh_song_radio_playlist
from .recipe_manager import recipe_manager
from .services.top_tracks_service import (
    STRATEGY_LABELS,
    top_tracks_configured,
    top_tracks_settings,
    top_tracks_strategy,
    top_tracks_supported,
)
from .services.playlist_sync_service import reconcile_playlists_with_server
# SYSTEM CHECK FEATURE - START
from .services.health_check_service import HealthCheckService
# SYSTEM CHECK FEATURE - END

app = FastAPI(title="MagicLists Navidrome MVP")


# ---------------------------------------------------------------------------
# HTTP access logging
# ---------------------------------------------------------------------------
# Uvicorn's own access log is disabled (see the Dockerfile and the __main__
# block) because it always logs at INFO and cannot be filtered by status code.
# This middleware replaces it: successful requests are DEBUG, client errors are
# WARNING and server errors are ERROR, so LOG_LEVEL=INFO hides the noise from
# the UI polling the API while keeping real failures visible.
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log one line per HTTP request at a level derived from the status code."""
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.error(
            "%s %s -> unhandled exception (%.0fms)",
            request.method,
            request.url.path,
            elapsed_ms,
            exc_info=True,
        )
        raise

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.log(
        access_level(response.status_code),
        "%s %s -> %s (%.0fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


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
    log_startup(
        scheduler_logger,
        "MagicLists starting (log level: %s)",
        active_policy_name(),
    )
    scheduler = AsyncIOScheduler()
    scheduler_module.scheduler = scheduler
    scheduler.start()
    log_startup(scheduler_logger, "Scheduler started successfully")

    # Register per-type refresh handlers with the shared scheduler registry so
    # the refresh queue can dispatch without importing the type packages.
    register_refresh_handler("this_is", refresh_this_is_playlist)
    register_refresh_handler("genre_mix", refresh_genre_playlist)
    register_refresh_handler("rediscover", refresh_rediscover_playlist)
    register_refresh_handler("rediscover_weekly_v2", refresh_rediscover_playlist)
    register_refresh_handler("artist_radio", refresh_artist_radio_playlist)
    register_refresh_handler("song_radio", refresh_song_radio_playlist)

    # Start the throttled refresh queue (one refresh at a time by default).
    get_refresh_queue().start()

    # SYSTEM CHECK FEATURE - START
    # Health checks run *before* any refresh job is registered. A broken
    # configuration (unreachable server, bad credentials, missing AI key) would
    # only produce a queue of failing refreshes, so automatic refreshes stay
    # paused until the checks pass.
    try:
        health_service = HealthCheckService()
        system_check_results = await health_service.run_checks()
        system_check_passed = system_check_results.get("all_passed", False)

        if system_check_passed:
            log_startup(scheduler_logger, "System health checks passed on startup")
        else:
            scheduler_logger.warning("System health checks failed on startup")

        for check in system_check_results.get("checks", []):
            status_emoji = "OK" if check["status"] == "success" else "WARN" if check["status"] == "warning" else "INFO" if check["status"] == "info" else "ERR"
            if "AI Provider" in check["name"]:
                ai_provider = os.getenv("AI_PROVIDER", "openrouter")
                if check["status"] == "success":
                    if "model:" in check["message"]:
                        model_part = check["message"].split("model: ")[1].rstrip(")")
                        log_startup(scheduler_logger, "AI Provider: %s with model '%s' - Ready", ai_provider.title(), model_part)
                    else:
                        log_startup(scheduler_logger, "AI Provider: %s - Ready", ai_provider.title())
                elif check["status"] == "warning":
                    if "not set" in check["message"]:
                        log_startup(scheduler_logger, "AI Provider: %s - No API key (using fallback algorithms)", ai_provider.title())
                    else:
                        scheduler_logger.warning(f"AI Provider: {ai_provider.title()} - {check['message']}")
                elif check["status"] == "error":
                    scheduler_logger.error(f"AI Provider: {ai_provider.title()} - {check['message']}")
            else:
                log_startup(scheduler_logger, "%s %s: %s", status_emoji, check["name"], check["status"])
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

    # Only register refresh jobs once the configuration is known to be healthy.
    if not system_check_passed:
        failed = [
            check.get("name", "unknown")
            for check in (system_check_results or {}).get("checks", [])
            if check.get("status") == "error"
        ]
        scheduler_logger.error(
            "Automatic playlist refreshes are PAUSED: the system check did not pass on "
            "startup%s. Fix the reported problem and restart, or run the system check "
            "and use POST /api/scheduler/start to resume.",
            f" (failed: {', '.join(failed)})" if failed else "",
        )
        return

    # Rebuild one APScheduler job per scheduled playlist from the database.
    try:
        startup_db = DatabaseManager(get_database_path())
        await rehydrate_jobs(startup_db)
    except Exception as e:
        scheduler_logger.error(f"Failed to rehydrate playlist refresh jobs: {e}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup scheduler and refresh queue on app shutdown"""
    global scheduler
    try:
        await get_refresh_queue().stop()
    except Exception as e:
        scheduler_logger.warning(f"Refresh queue shutdown failed: {e}")
    if scheduler:
        scheduler.shutdown()
        log_startup(scheduler_logger, "Scheduler shutdown completed")


# Mount static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# Templates
templates = Jinja2Templates(directory="frontend/templates")


def template_context(request: Request):
    """Return shared template context for the active media server."""
    strategy = top_tracks_strategy()
    server_type = os.getenv("SERVER_TYPE", "navidrome").lower()
    return {
        "request": request,
        "server_type": server_type,
        # Display name for user-facing copy; templates must use this instead of
        # hard-coding a server name.
        "server_label": "Jellyfin" if server_type == "jellyfin" else "Navidrome",
        "top_tracks_strategy": strategy,
        "top_tracks_strategy_label": STRATEGY_LABELS.get(strategy, strategy),
        # "supported" = the server type has a source at all (keep the UI visible);
        # "configured" = it can actually service a request right now.
        "top_tracks_supported": top_tracks_supported(),
        "top_tracks_configured": top_tracks_configured(),
        "lastfm_configured": bool(os.getenv("LASTFM_API_KEY")),
    }


# ---------------------------------------------------------------------------
# Page routes
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    """Serve the main HTML page"""
    if not system_check_passed:
        return RedirectResponse(url="/system-check", status_code=302)
    return templates.TemplateResponse(request, "index.html", template_context(request))


# SYSTEM CHECK FEATURE - START
@app.get("/system-check", response_class=HTMLResponse)
async def system_check_page(request: Request):
    """Serve the system check page"""
    return templates.TemplateResponse(request, "index.html", template_context(request))
# SYSTEM CHECK FEATURE - END


@app.get("/help/{help_type}", response_class=HTMLResponse)
async def get_help_content(help_type: str, request: Request):
    """Serve a help partial for a given playlist type from the Jinja templates folder."""
    allowed_types = {"this_is", "artist_radio", "genre_mix", "rediscover", "song_radio"}
    if help_type not in allowed_types:
        raise HTTPException(status_code=404, detail="Help content not found")

    return templates.TemplateResponse(request, f"help/{help_type}.html", template_context(request))


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


@app.get("/api/top-tracks/strategies")
async def get_top_track_strategies():
    """List available top-track strategies and which one is active.

    Each entry maps a stable strategy key to a short human-readable label so the
    frontend never has to hardcode the wording.
    """
    strategy = top_tracks_strategy()
    return {
        "active": strategy,
        "active_label": STRATEGY_LABELS.get(strategy, strategy),
        # A strategy is "supported" when the server type can use it at all and
        # "configured" when it is usable right now (Last.fm needs an API key).
        "supported": top_tracks_supported(),
        "configured": top_tracks_configured(),
        "strategies": [
            {
                "key": key,
                "label": label,
                "active": key == strategy,
                "available": key != "hybrid" and key != "off",
            }
            for key, label in STRATEGY_LABELS.items()
        ],
    }


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
    """Get all playlists with scheduling information.

    Runs a reconciliation pass first so playlists deleted directly in
    Navidrome/Jellyfin disappear from Magic Lists instead of showing up as
    stale entries that can no longer be deleted.
    """
    try:
        await reconcile_playlists_with_server(db)
        playlists = await db.get_all_playlists_with_schedule_info()
        next_runs = get_next_run_times()
        for playlist in playlists:
            songs = playlist.get("songs", [])
            playlist["track_count"] = len(songs) if isinstance(songs, list) else 0
            # The APScheduler trigger is authoritative; fall back to the stored
            # value only when no job is registered (e.g. paused schedules).
            live_next_run = next_runs.get(str(playlist.get("navidrome_playlist_id")))
            if live_next_run:
                playlist["next_refresh"] = live_next_run.isoformat()
        return playlists
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch playlists: {str(e)}")


@app.post("/api/playlists/reconcile")
async def reconcile_playlists(db: DatabaseManager = Depends(get_db)):
    """Manually reconcile local playlist records against the media server.

    Removes local playlists (and their schedules) whose media-server playlist
    no longer exists. Safe to call repeatedly; it is a no-op when everything
    is in sync.
    """
    try:
        result = await reconcile_playlists_with_server(db)
        return {"message": "Reconciliation complete", **result}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to reconcile playlists: {str(e)}"
        )


@app.get("/api/playlists/{playlist_id}")
async def get_playlist_detail(playlist_id: int, db: DatabaseManager = Depends(get_db)):
    """Get a single playlist with its scheduling info and saved curation settings"""
    try:
        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        # Attach the structured schedule so the edit modal can prefill its
        # scheduler section without a second request.
        server_id = playlist.get("navidrome_playlist_id")
        if server_id:
            schedule_row = await db.get_schedule_by_navidrome_id(server_id)
            payload = build_schedule_payload(schedule_row)
            playlist["schedule"] = payload.get("schedule")
            playlist["schedule_enabled"] = payload.get("enabled", False)
            playlist["schedule_description"] = payload.get("schedule_description")
            playlist["upcoming"] = payload.get("upcoming", [])
            if payload.get("next_run"):
                playlist["next_refresh"] = payload["next_run"]
        else:
            playlist["schedule"] = None
            playlist["schedule_enabled"] = False

        return playlist
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch playlist: {str(e)}")


@app.delete("/api/playlists/{playlist_id}")
async def delete_playlist(playlist_id: int, db: DatabaseManager = Depends(get_db)):
    """Delete a playlist from the configured server and the local database.

    Deletion is idempotent: if the playlist was already removed in
    Navidrome/Jellyfin, the local records (playlist + schedule) are still
    cleaned up and the request succeeds.
    """
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
                # The clients treat an already-missing playlist as deleted and
                # return True, so an externally deleted playlist no longer
                # blocks removing the local records.
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
    # Structured schedule. When provided it takes precedence over
    # ``refresh_frequency``; ``None`` means "leave the schedule unchanged".
    schedule: Optional[ScheduleSpec] = None
    schedule_enabled: Optional[bool] = None


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

        curation_settings = dict(request.curation_settings)
        if playlist.get("playlist_type") in ("artist_radio", "this_is"):
            max_count = 20 if playlist.get("playlist_type") == "this_is" else 10
            curation_settings.update(top_tracks_settings(
                curation_settings.get("top_tracks_enabled"),
                curation_settings.get("top_tracks_count"),
                max_count=max_count,
            ))
        else:
            curation_settings.pop("top_tracks_enabled", None)
            curation_settings.pop("top_tracks_count", None)

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

        new_length = curation_settings.get("playlist_length")
        await db.update_playlist_settings(
            playlist_id=playlist_id,
            curation_settings=curation_settings,
            playlist_length=new_length if new_length is not None else None
        )

        # Reconcile the refresh schedule. A structured ``schedule`` wins over the
        # legacy ``refresh_frequency`` string; omitting both leaves it unchanged.
        existing = await db.get_schedule_by_navidrome_id(navidrome_playlist_id)
        playlist_type = playlist.get("playlist_type") or "this_is"

        spec: Optional[ScheduleSpec] = request.schedule
        if spec is None and request.refresh_frequency is not None:
            spec = spec_from_frequency(request.refresh_frequency)

        if spec is None:
            # No schedule requested: remove any existing one.
            if existing:
                await db.delete_scheduled_playlist_by_navidrome_id(navidrome_playlist_id)
                scheduler_module.remove_playlist_job(existing["id"])
                scheduler_logger.info(f"Removed schedule for playlist {navidrome_playlist_id}")
        else:
            from .core.scheduler import next_run_for_spec

            enabled = request.schedule_enabled if request.schedule_enabled is not None else True
            next_refresh = next_run_for_spec(spec)
            schedule_row = await db.upsert_schedule(
                playlist_type=playlist_type,
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=request.refresh_frequency or "custom",
                next_refresh=next_refresh,
                schedule_json=spec.model_dump_json(),
                enabled=enabled,
            )
            sync_playlist_job(schedule_row)
            scheduler_logger.info(
                f"Updated schedule for {navidrome_playlist_id} -> {describe_schedule(spec)}"
                f"{'' if enabled else ' (paused)'}"
            )

        updated = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        updated["track_count"] = len(updated.get("songs", []) or [])
        return updated
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update playlist settings: {str(e)}")


@app.post("/api/playlists/{playlist_id}/refresh", status_code=202)
async def refresh_playlist_endpoint(playlist_id: int, db: DatabaseManager = Depends(get_db)):
    """Queue a manual refresh of a playlist.

    The refresh runs through the shared throttled queue so it can never collide
    with a scheduled refresh (or another manual one) and cannot trip AI-provider
    rate limits. Returns ``202 Accepted`` immediately; poll
    ``/api/scheduler/overview`` for progress.
    """
    try:
        playlist = await db.get_playlist_by_id_with_schedule_info(playlist_id)
        if not playlist:
            raise HTTPException(status_code=404, detail="Playlist not found")

        navidrome_playlist_id = playlist.get("navidrome_playlist_id")
        if not navidrome_playlist_id:
            raise HTTPException(status_code=400, detail="Playlist has no media server ID")

        playlist_type = playlist.get("playlist_type") or "this_is"
        queued = await enqueue_manual_refresh(
            navidrome_playlist_id,
            playlist_type,
            playlist.get("playlist_name"),
        )

        if not queued:
            return {
                "status": "already_queued",
                "message": "This playlist is already queued or refreshing",
                "playlist_id": navidrome_playlist_id,
            }

        return {
            "status": "queued",
            "message": "Playlist refresh queued",
            "playlist_id": navidrome_playlist_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to queue playlist refresh: {str(e)}")


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
    """Get scheduler status, per-playlist jobs, and refresh-queue state"""
    try:
        queue_state = get_refresh_queue().snapshot()
        if scheduler:
            jobs = get_job_info()
            return {
                "scheduler_running": scheduler.running,
                "active_jobs": len(jobs),
                "jobs": jobs,
                "scheduler_state": str(scheduler.state),
                "queue": queue_state,
            }
        return {
            "scheduler_running": False,
            "error": "Scheduler not initialized",
            "queue": queue_state,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {str(e)}")


@app.get("/api/scheduler/overview")
async def get_scheduler_overview(
    include_unscheduled: bool = Query(
        False,
        description="Include playlists that have no active refresh schedule",
    ),
    db: DatabaseManager = Depends(get_db),
):
    """Return one tile per playlist with schedule, last run, and live state.

    This powers the Refresh Schedule page. By default only playlists that
    actually have an enabled refresh schedule are included; pass
    ``include_unscheduled=true`` to also list manual-only and paused playlists.
    Each entry combines:
      * playlist identity (name, type, id),
      * the schedule spec + human-readable description + upcoming runs,
      * the most recent refresh outcome from ``refresh_history``,
      * live queue state (queued / running).
    """
    try:
        playlists = await db.get_all_playlists_with_schedule_info()
        latest = await db.get_latest_refresh_per_playlist()
        queue_state = get_refresh_queue().snapshot()

        running_id = (queue_state.get("running") or {}).get("navidrome_playlist_id")
        queued_ids = {
            job["navidrome_playlist_id"] for job in queue_state.get("queued", [])
        }

        tiles = []
        for playlist in playlists:
            server_id = playlist.get("navidrome_playlist_id")
            if not server_id:
                continue

            schedule_row = await db.get_schedule_by_navidrome_id(server_id)
            schedule_payload = build_schedule_payload(schedule_row)
            is_scheduled = bool(
                schedule_payload.get("enabled") and schedule_payload.get("schedule")
            )

            # Default view lists only playlists with an active schedule.
            if not is_scheduled and not include_unscheduled:
                continue

            last_run = latest.get(server_id)

            if server_id == running_id:
                state = "running"
            elif server_id in queued_ids:
                state = "queued"
            else:
                state = "idle"

            tiles.append({
                "id": playlist.get("id"),
                "navidrome_playlist_id": server_id,
                "playlist_name": playlist.get("playlist_name"),
                "playlist_type": playlist.get("playlist_type"),
                "track_count": len(playlist.get("songs") or []),
                "last_refreshed": playlist.get("last_refreshed"),
                "state": state,
                "is_scheduled": is_scheduled,
                **schedule_payload,
                "last_run": last_run,
            })

        # Soonest upcoming refresh first; unscheduled playlists last.
        tiles.sort(key=lambda tile: (tile.get("next_run") is None, tile.get("next_run") or ""))

        return {
            "tiles": tiles,
            "queue": queue_state,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build scheduler overview: {str(e)}")


@app.get("/api/scheduler/history")
async def get_scheduler_history(
    playlist_id: Optional[str] = Query(None, description="Media-server playlist ID"),
    limit: int = Query(20, ge=1, le=100),
    db: DatabaseManager = Depends(get_db),
):
    """Return refresh history for one playlist, or the latest run per playlist."""
    try:
        if playlist_id:
            return {"history": await db.get_recent_refreshes(playlist_id, limit=limit)}
        return {"latest": await db.get_latest_refresh_per_playlist()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch refresh history: {str(e)}")


@app.delete("/api/scheduler/history")
async def clear_scheduler_history(
    playlist_id: Optional[str] = Query(None, description="Limit clearing to one playlist"),
    db: DatabaseManager = Depends(get_db),
):
    """Clear refresh history, either for one playlist or entirely."""
    try:
        removed = await db.clear_refresh_history(playlist_id)
        return {"message": "Refresh history cleared", "removed": removed}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to clear refresh history: {str(e)}")


@app.post("/api/scheduler/trigger")
async def trigger_scheduler_check(db: DatabaseManager = Depends(get_db)):
    """Queue every playlist whose scheduled refresh time has passed."""
    try:
        scheduler_logger.info("Manual scheduler trigger requested via API")
        queued = await enqueue_all_due(db)
        return {
            "message": "Scheduler check completed",
            "queued": queued,
        }
    except Exception as e:
        scheduler_logger.error(f"Error in manual scheduler trigger: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to trigger scheduler: {str(e)}")


@app.post("/api/scheduler/start")
async def start_scheduler_job(db: DatabaseManager = Depends(get_db)):
    """Re-register all per-playlist refresh jobs from the database.

    Refuses to start when the last system check did not pass, so a broken
    configuration cannot be turned into a queue of failing refreshes.
    """
    try:
        if not system_check_passed:
            failed = [
                check.get("name", "unknown")
                for check in (system_check_results or {}).get("checks", [])
                if check.get("status") == "error"
            ]
            detail = (
                "Automatic refreshes are paused because the system check did not pass"
                + (f" (failed: {', '.join(failed)})" if failed else "")
                + ". Fix the reported problem and run the system check again."
            )
            scheduler_logger.error(f"Refusing to start scheduler: {detail}")
            raise HTTPException(status_code=409, detail=detail)

        registered = await rehydrate_jobs(db)
        scheduler_logger.info(f"Scheduler rehydration requested. Active jobs: {registered}")
        return {
            "message": "Scheduler jobs registered",
            "active_jobs": registered,
            "jobs": get_job_info(),
        }
    except HTTPException:
        raise
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
app.include_router(song_radio_router)


# ---------------------------------------------------------------------------
# SPA routing (MUST be last route)
# ---------------------------------------------------------------------------
@app.get("/{path:path}", response_class=HTMLResponse)
async def spa_router(request: Request, path: str):
    """Handle SPA routing - serve app for known paths, redirect unknown paths"""
    spa_paths = [
        "this-is",
        "artist-radio",
        "song-radio",
        "re-discover",
        "genre-mix",
        "playlists",
        "scheduler",
        "terms",
    ]
    # Normalize trailing slashes so /song-radio/ behaves like /song-radio
    normalized_path = path.strip("/")
    if normalized_path in spa_paths:
        if not system_check_passed:
            return RedirectResponse(url="/system-check", status_code=302)
        return templates.TemplateResponse(request, "index.html", template_context(request))
    return RedirectResponse(url="/", status_code=302)


if __name__ == "__main__":
    # Access logging is handled by the middleware above, so uvicorn's own access
    # log is switched off to avoid a second, unfilterable line per request.
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        access_log=False,
    )
