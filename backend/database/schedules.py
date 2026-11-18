import aiosqlite
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from ..schemas import ScheduledPlaylist


class _SchedulesMixin:
    async def create_scheduled_playlist(self, playlist_type: str, navidrome_playlist_id: str,
                                      refresh_frequency: str, next_refresh: datetime,
                                      schedule_json: Optional[str] = None) -> ScheduledPlaylist:
        """Create a new scheduled playlist

        Args:
            schedule_json: Serialized ``ScheduleSpec``. When omitted, the caller
                is expected to have derived it from ``refresh_frequency``.
        """
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO scheduled_playlists (playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh, schedule_json)
                VALUES (?, ?, ?, ?, ?)
            """, (playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh.isoformat(), schedule_json))

            scheduled_id = cursor.lastrowid
            await db.commit()

            # Fetch the created scheduled playlist
            async with db.execute("""
                SELECT id, playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh, created_at, updated_at
                FROM scheduled_playlists WHERE id = ?
            """, (scheduled_id,)) as cursor:
                row = await cursor.fetchone()

                if row:
                    return ScheduledPlaylist(
                        id=row[0],
                        playlist_type=row[1],
                        navidrome_playlist_id=row[2],
                        refresh_frequency=row[3],
                        next_refresh=row[4],
                        created_at=row[5],
                        updated_at=row[6]
                    )

        # This should never happen, but handle it gracefully
        raise Exception("Failed to create scheduled playlist")
    

    async def get_scheduled_playlists_due(self, current_time: datetime, grace_hours: int = 168) -> List[ScheduledPlaylist]:
        """Get all scheduled playlists that are due for refresh, including overdue ones within grace period
    
        Args:
            current_time: Current timestamp to check against
            grace_hours: Hours to look back for missed refreshes (default 7 days = 168 hours)
        """
        await self.init_db()
    
        # Calculate grace period cutoff (7 days ago by default)
        grace_cutoff = current_time - timedelta(hours=grace_hours)
    
        scheduled_playlists = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh, created_at, updated_at
                FROM scheduled_playlists 
                WHERE next_refresh <= ? AND next_refresh >= ?
                ORDER BY next_refresh ASC
            """, (current_time.isoformat(), grace_cutoff.isoformat())) as cursor:
                rows = await cursor.fetchall()
            
                for row in rows:
                    scheduled_playlist = ScheduledPlaylist(
                        id=row[0],
                        playlist_type=row[1],
                        navidrome_playlist_id=row[2],
                        refresh_frequency=row[3],
                        next_refresh=row[4],
                        created_at=row[5],
                        updated_at=row[6]
                    )
                    scheduled_playlists.append(scheduled_playlist)
    
        return scheduled_playlists
    

    async def update_scheduled_playlist_next_refresh(self, scheduled_id: int, next_refresh: datetime) -> bool:
        """Update the next refresh time for a scheduled playlist"""
        await self.init_db()
    
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE scheduled_playlists 
                SET next_refresh = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (next_refresh.isoformat(), scheduled_id))
        
            await db.commit()
            return cursor.rowcount > 0


    async def get_scheduled_playlist_by_navidrome_id(self, navidrome_playlist_id: str) -> Optional[ScheduledPlaylist]:
        """Get a scheduled playlist record by Navidrome playlist ID"""
        await self.init_db()
    
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh, created_at, updated_at
                FROM scheduled_playlists 
                WHERE navidrome_playlist_id = ?
            """, (navidrome_playlist_id,)) as cursor:
                row = await cursor.fetchone()
            
                if row:
                    return ScheduledPlaylist(
                        id=row[0],
                        playlist_type=row[1],
                        navidrome_playlist_id=row[2],
                        refresh_frequency=row[3],
                        next_refresh=row[4],
                        created_at=row[5],
                        updated_at=row[6]
                    )
        return None


    async def update_scheduled_playlist_frequency(self, scheduled_id: int, refresh_frequency: str, next_refresh: datetime,
                                                  schedule_json: Optional[str] = None) -> bool:
        """Update the refresh frequency and next refresh time for a scheduled playlist"""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            if schedule_json is None:
                cursor = await db.execute("""
                    UPDATE scheduled_playlists 
                    SET refresh_frequency = ?, next_refresh = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (refresh_frequency, next_refresh.isoformat(), scheduled_id))
            else:
                cursor = await db.execute("""
                    UPDATE scheduled_playlists 
                    SET refresh_frequency = ?, next_refresh = ?, schedule_json = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (refresh_frequency, next_refresh.isoformat(), schedule_json, scheduled_id))

            await db.commit()
            return cursor.rowcount > 0


    async def get_all_schedules(self) -> List[Dict]:
        """Return every scheduled playlist row as a dict (used to rehydrate jobs).

        The owning playlist's name and last refresh time are joined in so callers
        can log a human-readable label and detect schedules that are already
        satisfied (refreshed after they became due).
        """
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT sp.id, sp.playlist_type, sp.navidrome_playlist_id, sp.refresh_frequency,
                       sp.next_refresh, sp.schedule_json, sp.enabled, sp.created_at, sp.updated_at,
                       p.playlist_name, p.last_refreshed
                FROM scheduled_playlists sp
                LEFT JOIN playlists p ON p.navidrome_playlist_id = sp.navidrome_playlist_id
                ORDER BY sp.id ASC
            """) as cursor:
                rows = await cursor.fetchall()

        return [dict(row) for row in rows]


    async def get_schedule_by_navidrome_id(self, navidrome_playlist_id: str) -> Optional[Dict]:
        """Return the schedule row for a playlist as a dict, or ``None``."""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT sp.id, sp.playlist_type, sp.navidrome_playlist_id, sp.refresh_frequency,
                       sp.next_refresh, sp.schedule_json, sp.enabled, sp.created_at, sp.updated_at,
                       p.playlist_name
                FROM scheduled_playlists sp
                LEFT JOIN playlists p ON p.navidrome_playlist_id = sp.navidrome_playlist_id
                WHERE sp.navidrome_playlist_id = ?
                LIMIT 1
            """, (navidrome_playlist_id,)) as cursor:
                row = await cursor.fetchone()

        return dict(row) if row else None


    async def upsert_schedule(self, playlist_type: str, navidrome_playlist_id: str,
                              refresh_frequency: str, next_refresh: datetime,
                              schedule_json: Optional[str] = None,
                              enabled: bool = True) -> Dict:
        """Create or update the schedule for a playlist and return the stored row.

        This is the single write path used by the settings API so a playlist can
        never end up with two competing schedule rows.
        """
        await self.init_db()

        existing = await self.get_schedule_by_navidrome_id(navidrome_playlist_id)
        if existing:
            await self.update_scheduled_playlist_frequency(
                existing["id"], refresh_frequency, next_refresh, schedule_json
            )
            await self.set_schedule_enabled(existing["id"], enabled)
        else:
            await self.create_scheduled_playlist(
                playlist_type=playlist_type,
                navidrome_playlist_id=navidrome_playlist_id,
                refresh_frequency=refresh_frequency,
                next_refresh=next_refresh,
                schedule_json=schedule_json,
            )
            created = await self.get_schedule_by_navidrome_id(navidrome_playlist_id)
            if created:
                await self.set_schedule_enabled(created["id"], enabled)

        return await self.get_schedule_by_navidrome_id(navidrome_playlist_id) or {}


    async def set_schedule_enabled(self, scheduled_id: int, enabled: bool) -> bool:
        """Enable or disable a schedule without deleting it."""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE scheduled_playlists
                SET enabled = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (1 if enabled else 0, scheduled_id))

            await db.commit()
            return cursor.rowcount > 0


    async def delete_scheduled_playlist_by_navidrome_id(self, navidrome_playlist_id: str) -> bool:
        """Delete a scheduled playlist by Navidrome playlist ID"""
        await self.init_db()
    
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM scheduled_playlists WHERE navidrome_playlist_id = ?
            """, (navidrome_playlist_id,))
        
            await db.commit()
            return cursor.rowcount > 0
    

