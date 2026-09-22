"""Scheduler and refresh-dispatch logic.

Previously this lived inline in ``main.py``. It now exposes the refresh-time
calculation, the APScheduler job registration, and the due-playlist scan that
dispatches to the correct per-type refresh function via a registry.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Callable, Awaitable, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ..database import DatabaseManager


scheduler_logger = logging.getLogger("scheduler")

# The scheduler instance is owned by the application lifecycle (see main.py).
scheduler: AsyncIOScheduler = None  # type: ignore

# Registry mapping playlist_type -> async refresh callable. Populated by the
# per-type packages on import so this module never imports them directly
# (avoids circular imports with main.py / the type packages).
_REFRESH_REGISTRY: Dict[str, Callable[[Any, DatabaseManager], Awaitable[None]]] = {}


def register_refresh_handler(playlist_type: str, handler) -> None:
    """Register an async refresh handler for a given playlist type."""
    _REFRESH_REGISTRY[playlist_type] = handler


def calculate_next_refresh(frequency: str) -> datetime:
    """Calculate the next refresh time based on frequency."""
    now = datetime.now()
    if frequency == "daily":
        # Next day at 1:00 AM
        next_day = now + timedelta(days=1)
        return next_day.replace(hour=1, minute=0, second=0, microsecond=0)
    elif frequency == "weekly":
        # Next Monday at 1:00 AM
        days_until_monday = (7 - now.weekday()) % 7
        if days_until_monday == 0 and now.hour >= 1:
            days_until_monday = 7  # If it's Monday after 1 AM, go to next Monday
        next_monday = now + timedelta(days=days_until_monday)
        return next_monday.replace(hour=1, minute=0, second=0, microsecond=0)
    elif frequency == "monthly":
        # 1st of next month at 1:00 AM
        if now.month == 12:
            next_month = now.replace(year=now.year + 1, month=1, day=1, hour=1, minute=0, second=0, microsecond=0)
        else:
            next_month = now.replace(month=now.month + 1, day=1, hour=1, minute=0, second=0, microsecond=0)
        return next_month
    else:
        return now  # Fallback


def schedule_playlist_refresh() -> None:
    """Schedule the playlist refresh job to run every 12 hours."""
    if not scheduler.get_job("playlist_refresh"):
        scheduler.add_job(
            refresh_scheduled_playlists,
            "cron",
            hour="1,13",  # Run at 1 AM and 1 PM
            minute=1,     # Run at 1 minute past (1:01 AM and 1:01 PM)
            id="playlist_refresh",
            replace_existing=True,
        )
        scheduler_logger.info("🔄 Playlist refresh job scheduled to run every 12 hours (1:01 AM and 1:01 PM)")


async def refresh_scheduled_playlists() -> None:
    """Check for and refresh scheduled playlists that are due."""
    try:
        current_time = datetime.now()

        if os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG":
            scheduler_logger.debug(f"🔄 Scheduler auto-run initiated at {current_time.strftime('%H:%M:%S')}")
            scheduler_logger.debug("🔍 Checking for playlists due for refresh...")
        else:
            scheduler_logger.info("🔍 Checking for playlists due for refresh...")

        # Get database path from environment variable with smart defaults
        default_path = "/app/data/magiclists.db" if os.path.exists("/app/data") else "./magiclists.db"
        db_path = os.getenv("DATABASE_PATH", default_path)
        db = DatabaseManager(db_path)
        current_time = datetime.now()

        # Get playlists due for refresh (including 7-day catch-up window)
        scheduled_playlists = await db.get_scheduled_playlists_due(current_time, grace_hours=168)

        if not scheduled_playlists:
            if os.getenv("LOG_LEVEL", "INFO").upper() == "DEBUG":
                scheduler_logger.debug("✅ No playlists due for refresh at this time")
            return

        # Group by navidrome_playlist_id to prevent duplicate processing
        unique_playlists: Dict[str, Any] = {}
        for playlist in scheduled_playlists:
            playlist_id = playlist.navidrome_playlist_id
            if playlist_id not in unique_playlists:
                unique_playlists[playlist_id] = playlist
            else:
                # Keep the more recent one (closer to current time)
                existing = datetime.fromisoformat(unique_playlists[playlist_id].next_refresh)
                current = datetime.fromisoformat(playlist.next_refresh)
                if current > existing:
                    unique_playlists[playlist_id] = playlist

        final_playlists = list(unique_playlists.values())

        scheduler_logger.info(
            f"📋 Found {len(final_playlists)} playlist(s) due for refresh "
            f"(deduplicated from {len(scheduled_playlists)} total)"
        )

        for scheduled_playlist in final_playlists:
            scheduled_time = datetime.fromisoformat(scheduled_playlist.next_refresh)
            if scheduled_time < current_time:
                overdue_hours = (current_time - scheduled_time).total_seconds() / 3600
                scheduler_logger.info(
                    f"🕐 Catching up on overdue playlist {scheduled_playlist.navidrome_playlist_id} "
                    f"(missed by {overdue_hours:.1f} hours)"
                )

            handler = _REFRESH_REGISTRY.get(scheduled_playlist.playlist_type)
            if handler is None:
                scheduler_logger.warning(
                    f"⚠️ No refresh handler registered for playlist type "
                    f"'{scheduled_playlist.playlist_type}' (playlist {scheduled_playlist.navidrome_playlist_id})"
                )
                continue
            await handler(scheduled_playlist, db)

    except Exception as e:
        scheduler_logger.error(f"❌ Error checking scheduled playlists: {e}")
