"""Refresh history storage.

Keeps a small, bounded record of refresh attempts so the scheduler overview
page can show whether the last refresh succeeded and when the next one is due.

History is intentionally minimal: only the last ``MAX_ROWS_PER_PLAYLIST`` rows
per playlist are retained, and everything can be cleared by the user.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

import aiosqlite

logger = logging.getLogger("scheduler")

# How many history rows to keep per playlist. Older rows are pruned on insert.
MAX_ROWS_PER_PLAYLIST = 20


class _HistoryMixin:
    async def record_refresh(
        self,
        navidrome_playlist_id: str,
        status: str,
        started_at: datetime,
        finished_at: Optional[datetime] = None,
        duration_seconds: Optional[float] = None,
        track_count: Optional[int] = None,
        error: Optional[str] = None,
        playlist_name: Optional[str] = None,
        playlist_type: Optional[str] = None,
        trigger: str = "scheduled",
    ) -> None:
        """Record a single refresh attempt and prune old rows for that playlist.

        Args:
            navidrome_playlist_id: Media-server playlist identifier.
            status: ``success`` or ``failed``.
            started_at: When the refresh began.
            finished_at: When it ended (defaults to now).
            duration_seconds: Wall-clock duration of the refresh.
            track_count: Number of tracks written, when known.
            error: Error message for failed refreshes.
            playlist_name: Denormalised name for display without a join.
            playlist_type: Playlist type key (``this_is``, ``genre_mix``, ...).
            trigger: ``scheduled`` or ``manual``.
        """
        await self.init_db()
        finished = finished_at or datetime.now()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO refresh_history (
                    navidrome_playlist_id, playlist_name, playlist_type, trigger,
                    status, started_at, finished_at, duration_seconds, track_count, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                navidrome_playlist_id,
                playlist_name,
                playlist_type,
                trigger,
                status,
                started_at.isoformat(),
                finished.isoformat(),
                duration_seconds,
                track_count,
                error,
            ))

            # Prune everything older than the newest MAX_ROWS_PER_PLAYLIST rows.
            await db.execute("""
                DELETE FROM refresh_history
                WHERE navidrome_playlist_id = ?
                  AND id NOT IN (
                      SELECT id FROM refresh_history
                      WHERE navidrome_playlist_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
            """, (navidrome_playlist_id, navidrome_playlist_id, MAX_ROWS_PER_PLAYLIST))

            await db.commit()

    async def get_recent_refreshes(
        self,
        navidrome_playlist_id: str,
        limit: int = MAX_ROWS_PER_PLAYLIST,
    ) -> List[Dict]:
        """Return the most recent refresh attempts for one playlist, newest first."""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT id, navidrome_playlist_id, playlist_name, playlist_type, trigger,
                       status, started_at, finished_at, duration_seconds, track_count, error
                FROM refresh_history
                WHERE navidrome_playlist_id = ?
                ORDER BY id DESC
                LIMIT ?
            """, (navidrome_playlist_id, max(1, limit))) as cursor:
                rows = await cursor.fetchall()

        return [dict(row) for row in rows]

    async def get_latest_refresh_per_playlist(self) -> Dict[str, Dict]:
        """Return the newest refresh attempt for every playlist, keyed by server ID."""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT h.*
                FROM refresh_history h
                JOIN (
                    SELECT navidrome_playlist_id, MAX(id) AS max_id
                    FROM refresh_history
                    GROUP BY navidrome_playlist_id
                ) latest ON latest.max_id = h.id
            """) as cursor:
                rows = await cursor.fetchall()

        return {row["navidrome_playlist_id"]: dict(row) for row in rows}

    async def clear_refresh_history(self, navidrome_playlist_id: Optional[str] = None) -> int:
        """Delete refresh history, either for one playlist or entirely.

        Returns:
            The number of rows removed.
        """
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            if navidrome_playlist_id:
                cursor = await db.execute(
                    "DELETE FROM refresh_history WHERE navidrome_playlist_id = ?",
                    (navidrome_playlist_id,),
                )
            else:
                cursor = await db.execute("DELETE FROM refresh_history")
            await db.commit()
            return cursor.rowcount or 0
