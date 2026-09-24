"""Builder and refresh logic for 'Re-Discover' (v2) playlists.

Legacy ``"rediscover"`` playlists (stored with that type) are handled here by
mapping them onto the v2 processor, preserving behaviour for existing rows while
the legacy ``RediscoverWeekly`` class has been removed.
"""
import logging
from typing import Any, Dict

from ..database import DatabaseManager
from ..core.dependencies import get_ai_client
from ..core.server_router import get_server_client
from ..core.scheduler import calculate_next_refresh, schedule_playlist_refresh
from .processor import ReDiscoverV2Processor


scheduler_logger = logging.getLogger("scheduler")

FREQUENCY_NAMES = {
    "daily": "Re-Discover Daily ✨",
    "weekly": "Re-Discover Weekly ✨",
    "monthly": "Re-Discover Monthly ✨",
    "never": "Re-Discover ✨",
}


def _playlist_name_for(frequency: str, is_fallback: bool) -> str:
    name = FREQUENCY_NAMES.get(frequency, "Re-Discover Weekly ✨")
    if is_fallback:
        name += " (Fallback)"
    return name


async def create_rediscover_playlist_v2(
    request, db: DatabaseManager
) -> Dict[str, Any]:
    """Create a Re-Discover Weekly v2.0 playlist in Navidrome."""
    scheduler_logger.info(
        f"🎵 Starting Re-Discover v2.0 playlist creation with length {request.playlist_length}, "
        f"library_ids: {request.library_ids}"
    )
    server_client = get_server_client()
    ai_client = get_ai_client()

    user_id = await db.get_or_create_user_id()
    server_id = server_client.base_url or "unknown_server"

    processor = ReDiscoverV2Processor(server_client, ai_client, db)
    playlist_data = await processor.generate_playlist(user_id, server_id, request.library_ids)
    tracks = playlist_data.get("tracks", [])

    if not tracks:
        scheduler_logger.error("❌ No tracks generated for Re-Discover Weekly v2.0")
        raise ValueError("No tracks found for Re-Discover Weekly v2.0")

    scheduler_logger.info(f"✅ Generated {len(tracks)} tracks for Re-Discover Weekly v2.0")

    ai_description = playlist_data.get("description", "")
    ai_curated = any(track.get("ai_curated", False) for track in tracks)
    if ai_curated:
        track_description = next(
            (track.get("ai_description", "") for track in tracks if track.get("ai_curated", False) and track.get("ai_description")),
            "",
        )
        if track_description:
            ai_description = track_description

    scheduler_logger.info(f"🎵 AI curated: {ai_curated}, description length: {len(ai_description)}")

    frequency = request.refresh_frequency
    playlist_name = _playlist_name_for(frequency, playlist_data.get("is_fallback", False))
    scheduler_logger.info(f"📝 Creating playlist: {playlist_name}")

    track_ids = [track["id"] for track in tracks]
    scheduler_logger.info(f"🎵 Track IDs: {track_ids[:5]}... (total: {len(track_ids)})")

    comment_to_use = ai_description if ai_description else f"Theme: {playlist_data.get('theme', 'Mixed')}"
    scheduler_logger.info(f"💬 Creating Re-Discover v2.0 playlist with comment (length: {len(comment_to_use)})")

    navidrome_playlist_id = await server_client.create_playlist(
        name=playlist_name,
        track_ids=track_ids,
        comment=comment_to_use,
    )
    scheduler_logger.info(f"✅ Navidrome playlist created: {navidrome_playlist_id}")

    track_titles = [track.get("title", "Unknown") for track in tracks]
    scheduler_logger.info(f"📊 Storing {len(track_titles)} track titles in database")

    curation_settings = {
        "playlist_length": len(tracks),
        "library_ids": request.library_ids,
        "refresh_frequency": frequency,
    }
    playlist_record = await db.create_playlist(
        artist_id="rediscover_v2",
        playlist_name=playlist_name,
        songs=track_titles,
        description=ai_description,
        navidrome_playlist_id=navidrome_playlist_id,
        playlist_length=len(tracks),
        library_ids=request.library_ids,
        curation_settings=curation_settings,
        playlist_type="rediscover_weekly_v2",
    )
    scheduler_logger.info(f"💾 Database playlist created: {playlist_record}")

    if frequency != "never":
        scheduler_logger.info(f"⏰ Setting up {frequency} refresh schedule")
        await db.create_scheduled_playlist(
            playlist_type="rediscover_weekly_v2",
            navidrome_playlist_id=navidrome_playlist_id,
            refresh_frequency=frequency,
            next_refresh=calculate_next_refresh(frequency),
        )
        schedule_playlist_refresh()
        scheduler_logger.info(f"✅ Scheduled playlist created")

    return {
        "message": f"Re-Discover Weekly v2.0 playlist created successfully with {len(tracks)} tracks",
        "playlist_id": navidrome_playlist_id,
        "track_count": len(tracks),
        "theme": playlist_data.get("theme", "Mixed"),
        "mode": playlist_data.get("mode", "Unknown"),
        "is_fallback": playlist_data.get("is_fallback", False),
    }


async def refresh_rediscover_playlist(scheduled_playlist, db: DatabaseManager) -> None:
    """Refresh a Re-Discover Weekly playlist (legacy or v2) using the v2 processor."""
    try:
        scheduler_logger.info(
            f"🔄 Starting refresh for playlist ID: {scheduled_playlist.navidrome_playlist_id} "
            f"(frequency: {scheduled_playlist.refresh_frequency})"
        )
        server_client = get_server_client()
        ai_client = get_ai_client()

        playlists = await db.get_all_playlists_with_schedule_info()
        original_playlist = next(
            (p for p in playlists if p.get("navidrome_playlist_id") == scheduled_playlist.navidrome_playlist_id),
            None,
        )
        if not original_playlist:
            scheduler_logger.error(f"❌ Could not find original playlist data for {scheduled_playlist.navidrome_playlist_id}")
            return

        settings = original_playlist.get("curation_settings") or {}
        library_ids = settings.get("library_ids") or []
        original_length = settings.get("playlist_length") or original_playlist.get("playlist_length", 20)
        scheduler_logger.info(f"🎯 Using original playlist length: {original_length}")

        previous_songs = original_playlist.get("songs", [])[:10]
        scheduler_logger.info(f"🔄 Re-Discover v2.0 refresh context - Previous tracks: {len(previous_songs)}, Library IDs: {library_ids}")

        user_id = await db.get_or_create_user_id()
        server_id = server_client.base_url or "unknown_server"

        processor = ReDiscoverV2Processor(server_client, ai_client, db)
        result = await processor.generate_playlist(user_id, server_id, library_ids if library_ids else None)

        tracks = result.get("tracks", [])
        if tracks:
            scheduler_logger.info(f"🎵 Generated {len(tracks)} new tracks for refresh")
            if len(tracks) != original_length:
                scheduler_logger.warning(f"⚠️ Generated {len(tracks)} tracks but user requested {original_length}")
            else:
                scheduler_logger.info(f"✅ Generated exact number of requested tracks: {len(tracks)}")

            ai_description = ""
            ai_curated = False
            if tracks:
                first_track = tracks[0]
                ai_description = first_track.get("ai_description", "")
                ai_curated = first_track.get("ai_curated", False)

            track_ids = [track["id"] for track in tracks]
            comment_to_use = ai_description if (ai_description and ai_curated) else "Re-Discover Weekly v2.0 - Automatically refreshed"
            await server_client.update_playlist(
                playlist_id=scheduled_playlist.navidrome_playlist_id,
                track_ids=track_ids,
                comment=comment_to_use,
            )

            track_titles = [track["title"] for track in tracks]
            description_to_store = ai_description if ai_curated else "Algorithmic selection"
            await db.update_playlist_content(
                navidrome_playlist_id=scheduled_playlist.navidrome_playlist_id,
                songs=track_titles,
                description=description_to_store,
            )

            next_refresh = calculate_next_refresh(scheduled_playlist.refresh_frequency)
            await db.update_scheduled_playlist_next_refresh(scheduled_playlist.id, next_refresh)
            scheduler_logger.info(
                f"✅ Successfully refreshed playlist {scheduled_playlist.navidrome_playlist_id}. "
                f"Next refresh: {next_refresh.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        else:
            scheduler_logger.warning(f"⚠️ No tracks generated for playlist {scheduled_playlist.navidrome_playlist_id}")
    except Exception as e:
        scheduler_logger.error(f"❌ Error refreshing playlist {scheduled_playlist.navidrome_playlist_id}: {e}")
