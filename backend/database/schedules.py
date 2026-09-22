import aiosqlite
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from ..schemas import ScheduledPlaylist


class _SchedulesMixin:
    async def create_scheduled_playlist(self, playlist_type: str, navidrome_playlist_id: str,
                                      refresh_frequency: str, next_refresh: datetime) -> ScheduledPlaylist:
        """Create a new scheduled playlist"""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO scheduled_playlists (playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh)
                VALUES (?, ?, ?, ?)
            """, (playlist_type, navidrome_playlist_id, refresh_frequency, next_refresh.isoformat()))

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
        from datetime import timedelta
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


    async def update_scheduled_playlist_frequency(self, scheduled_id: int, refresh_frequency: str, next_refresh: datetime) -> bool:
        """Update the refresh frequency and next refresh time for a scheduled playlist"""
        await self.init_db()
    
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE scheduled_playlists 
                SET refresh_frequency = ?, next_refresh = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (refresh_frequency, next_refresh.isoformat(), scheduled_id))
        
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
    

