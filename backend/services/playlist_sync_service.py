"""Reconciliation between the media server and the local Magic Lists database.

Playlists can be deleted directly in Navidrome/Jellyfin (or by any other
client). Magic Lists keeps its own rows in `playlists` / `scheduled_playlists`,
so those rows become stale and the playlist keeps showing up in the UI — and
deleting it from Magic Lists then fails with "playlist not found" because the
server-side playlist is already gone.

`reconcile_playlists_with_server` performs a single pass of that cleanup: it
asks the media server which playlists still exist and removes the local rows
for any that no longer do.
"""
import logging
from typing import Dict, List, Optional, Set

from ..database import DatabaseManager
from ..core.server_router import get_server_client


logger = logging.getLogger("scheduler")

# Fallback local IDs used when the media server cannot be reached.
_UNKNOWN = "?"


async def reconcile_playlists_with_server(db: DatabaseManager) -> Dict[str, object]:
    """Remove local playlist records whose media-server playlist is gone.

    This is intentionally best-effort: if the media server is unreachable, no
    local rows are touched (deleting them would be wrong, since a network
    failure must not destroy tracking data for playlists that still exist).

    Args:
        db: The database manager to reconcile.

    Returns:
        A summary dict with:
            - `checked`: number of local playlists inspected.
            - `removed_ids`: local playlist IDs that were removed.
            - `removed_names`: names of the removed playlists.
            - `orphaned`: True if the server could not be reached and nothing
              was reconciled.
    """
    try:
        playlists: List[Dict] = await db.get_all_playlists_with_schedule_info()
    except Exception as e:
        logger.warning(f"Could not load local playlists for reconciliation: {e}")
        return {
            "checked": 0,
            "removed_ids": [],
            "removed_names": [],
            "orphaned": False,
        }

    tracked: Dict[str, Dict] = {}
    for playlist in playlists:
        server_id = playlist.get("navidrome_playlist_id")
        if server_id:
            tracked[str(server_id)] = playlist

    if not tracked:
        return {
            "checked": len(playlists),
            "removed_ids": [],
            "removed_names": [],
            "orphaned": False,
        }

    try:
        client = get_server_client()
        existing: Set[str] = await client.get_playlist_ids()
    except Exception as e:
        # Never delete local state just because the server is unreachable.
        logger.warning(
            f"Skipping playlist reconciliation, media server unavailable: {e}"
        )
        return {
            "checked": len(tracked),
            "removed_ids": [],
            "removed_names": [],
            "orphaned": True,
        }

    missing = [server_id for server_id in tracked if server_id not in existing]

    if not missing:
        return {
            "checked": len(tracked),
            "removed_ids": [],
            "removed_names": [],
            "orphaned": False,
        }

    removed_ids = await db.delete_playlists_by_server_ids(missing)
    removed_names = [
        tracked[server_id].get("playlist_name", _UNKNOWN)
        for server_id in missing
    ]

    logger.info(
        f"🧹 Reconciliation removed {len(removed_ids)} playlist(s) that no longer "
        f"exist on the media server: {', '.join(removed_names)}"
    )

    return {
        "checked": len(tracked),
        "removed_ids": removed_ids,
        "removed_names": removed_names,
        "orphaned": False,
    }
