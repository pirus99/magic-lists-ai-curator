import json
import sqlite3
import aiosqlite
import os
from typing import List, Optional, Dict
from datetime import datetime, timedelta

from ..schemas import Playlist, ScheduledPlaylist


def _safe_json_loads(value, default):
    """Return parsed JSON or a safe fallback for rows that store NULL/empty values."""
    if value is None or value == "":
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


class _DatabasePlaylistsMixin:
    async def create_playlist(self, artist_id: str, playlist_name: str, songs: Optional[List[str]] = None, description: Optional[str] = None, navidrome_playlist_id: Optional[str] = None, playlist_length: Optional[int] = None, library_ids: Optional[List[str]] = None, curation_settings: Optional[Dict] = None, playlist_type: Optional[str] = None) -> Optional[Playlist]:
        """Create a new playlist in the database"""
        await self.init_db()
    
        songs_json = json.dumps(songs or [])
        library_ids_json = json.dumps(library_ids or [])
        curation_settings_json = json.dumps(curation_settings or {})

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO playlists (artist_id, playlist_name, songs, description, navidrome_playlist_id, playlist_length, library_ids, curation_settings, playlist_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (artist_id, playlist_name, songs_json, description, navidrome_playlist_id, playlist_length, library_ids_json, curation_settings_json, playlist_type))
        
            playlist_id = cursor.lastrowid
            await db.commit()
        
            # Fetch the created playlist
            async with db.execute("""
                SELECT id, artist_id, playlist_name, songs, description, navidrome_playlist_id, created_at, updated_at, playlist_length, library_ids, curation_settings, playlist_type, is_public
                FROM playlists WHERE id = ?
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
            
                if row:
                    return Playlist(
                        id=row[0],
                        artist_id=row[1],
                        playlist_name=row[2],
                        songs=_safe_json_loads(row[3], []),
                        description=row[4],
                        navidrome_playlist_id=row[5],
                        playlist_length=row[8],
                        created_at=row[6],
                        updated_at=row[7],
                        library_ids=_safe_json_loads(row[9], []),
                        curation_settings=_safe_json_loads(row[10], {}),
                        playlist_type=row[11],
                        is_public=bool(row[12])
                    )
                return None
    

    async def get_playlist(self, playlist_id: int) -> Optional[Playlist]:
        """Get a playlist by ID"""
        await self.init_db()
    
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, artist_id, playlist_name, songs, description, navidrome_playlist_id, created_at, updated_at, playlist_length, library_ids, is_public
                FROM playlists WHERE id = ?
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
            
                if row:
                    return Playlist(
                        id=row[0],
                        artist_id=row[1],
                        playlist_name=row[2],
                        songs=_safe_json_loads(row[3], []),
                        description=row[4],
                        navidrome_playlist_id=row[5],
                        created_at=row[6],
                        updated_at=row[7],
                        library_ids=_safe_json_loads(row[9], []),
                        is_public=bool(row[10])
                    )
        return None
    

    async def get_playlists_by_artist(self, artist_id: str) -> List[Playlist]:
        """Get all playlists for a specific artist"""
        await self.init_db()
    
        playlists = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT id, artist_id, playlist_name, songs, created_at, updated_at
                FROM playlists WHERE artist_id = ?
                ORDER BY created_at DESC
            """, (artist_id,)) as cursor:
                rows = await cursor.fetchall()
            
                for row in rows:
                    playlist = Playlist(
                        id=row[0],
                        artist_id=row[1],
                        playlist_name=row[2],
                        songs=_safe_json_loads(row[3], []),
                        created_at=row[4],
                        updated_at=row[5]
                    )
                    playlists.append(playlist)
    
        return playlists
    

    async def get_all_playlists_with_schedule_info(self) -> List[Dict]:
        """Get all playlists with their scheduling information"""
        await self.init_db()
    
        playlists = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT 
                    p.id, 
                    p.artist_id, 
                    p.playlist_name, 
                    p.songs, 
                    p.description,
                    p.navidrome_playlist_id,
                    p.is_public,
                    p.created_at, 
                    p.updated_at,
                    p.last_refreshed,
                    p.playlist_length,
                    p.curation_settings,
                    p.playlist_type,
                    sp.refresh_frequency,
                    sp.next_refresh,
                    sp.playlist_type
                FROM playlists p
                LEFT JOIN scheduled_playlists sp ON p.navidrome_playlist_id = sp.navidrome_playlist_id
                ORDER BY p.created_at DESC
            """) as cursor:
                rows = await cursor.fetchall()
            
                for row in rows:
                    # Prefer the authoritative type stored on the playlists row;
                    # fall back to the scheduled_playlists join only if missing.
                    resolved_type = row[12] or row[15] or "this_is"
                    playlist_data = {
                        "id": row[0],
                        "artist_id": row[1],
                        "playlist_name": row[2],
                        "songs": _safe_json_loads(row[3], []),
                        "description": row[4],
                        "navidrome_playlist_id": row[5],
                        "is_public": bool(row[6]),
                        "created_at": row[7],
                        "updated_at": row[8],
                        "last_refreshed": row[9],
                        "playlist_length": row[10],
                        "curation_settings": _safe_json_loads(row[11], {}),
                        "playlist_type": resolved_type,
                        "refresh_frequency": row[13],
                        "next_refresh": row[14]
                    }
                    playlists.append(playlist_data)
    
        return playlists
    

    async def get_playlist_by_id_with_schedule_info(self, playlist_id: int) -> Optional[Dict]:
        """Get a specific playlist with its scheduling information"""
        await self.init_db()
    
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT 
                    p.id, 
                    p.artist_id, 
                    p.playlist_name, 
                    p.songs, 
                    p.description,
                    p.is_public,
                    p.created_at, 
                    p.updated_at,
                    p.navidrome_playlist_id,
                    p.curation_settings,
                    p.playlist_type,
                    sp.refresh_frequency,
                    sp.next_refresh,
                    sp.playlist_type
                FROM playlists p
                LEFT JOIN scheduled_playlists sp ON p.navidrome_playlist_id = sp.navidrome_playlist_id
                WHERE p.id = ?
            """, (playlist_id,)) as cursor:
                row = await cursor.fetchone()
            
                if row:
                    # Prefer the authoritative type stored on the playlists row;
                    # fall back to the scheduled_playlists join only if missing.
                    resolved_type = row[10] or row[13] or "this_is"
                    return {
                        "id": row[0],
                        "artist_id": row[1],
                        "playlist_name": row[2],
                        "songs": _safe_json_loads(row[3], []),
                        "description": row[4],
                        "is_public": bool(row[5]),
                        "created_at": row[6],
                        "updated_at": row[7],
                        "navidrome_playlist_id": row[8],
                        "curation_settings": _safe_json_loads(row[9], {}),
                        "playlist_type": resolved_type,
                        "refresh_frequency": row[11],
                        "next_refresh": row[12]
                    }
    
        return None
    

    async def delete_playlist(self, playlist_id: int) -> bool:
        """Delete a playlist from the database"""
        await self.init_db()
    
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM playlists WHERE id = ?
            """, (playlist_id,))
        
            await db.commit()
            return cursor.rowcount > 0
    

    async def update_playlist_songs(self, playlist_id: int, songs: List[str]) -> bool:
        """Update the songs in a playlist"""
        await self.init_db()
    
        songs_json = json.dumps(songs)
    
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE playlists 
                SET songs = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (songs_json, playlist_id))
        
            await db.commit()
            return cursor.rowcount > 0
    

    async def update_playlist_content(self, navidrome_playlist_id: str, songs: List[str], description: Optional[str] = None) -> bool:
        """Update the songs and description for a playlist during refresh"""
        await self.init_db()
    
        songs_json = json.dumps(songs)
    
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE playlists 
                SET songs = ?, description = ?, last_refreshed = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE navidrome_playlist_id = ?
            """, (songs_json, description, navidrome_playlist_id))
        
            await db.commit()
            return cursor.rowcount > 0


    async def update_playlist_settings(self, playlist_id: int, curation_settings: Dict, playlist_length: Optional[int] = None) -> bool:
        """Update the saved curation settings (and optionally playlist length) for a playlist"""
        await self.init_db()
    
        curation_settings_json = json.dumps(curation_settings or {})
    
        if playlist_length is not None:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    UPDATE playlists 
                    SET curation_settings = ?, playlist_length = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (curation_settings_json, playlist_length, playlist_id))
                await db.commit()
                return cursor.rowcount > 0
        else:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute("""
                    UPDATE playlists 
                    SET curation_settings = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (curation_settings_json, playlist_id))
                await db.commit()
                return cursor.rowcount > 0


    async def update_playlist_metadata(self, playlist_id: int, playlist_name: Optional[str] = None, description: Optional[str] = None, is_public: Optional[bool] = None) -> bool:
        """Update a playlist's editable metadata such as name, description, and public flag."""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            updates = []
            values = []

            if playlist_name is not None:
                updates.append("playlist_name = ?")
                values.append(playlist_name)
            if description is not None:
                updates.append("description = ?")
                values.append(description)
            if is_public is not None:
                updates.append("is_public = ?")
                values.append(1 if is_public else 0)

            if not updates:
                return False

            updates.append("updated_at = CURRENT_TIMESTAMP")
            values.append(playlist_id)

            cursor = await db.execute(
                f"UPDATE playlists SET {', '.join(updates)} WHERE id = ?",
                values,
            )
            await db.commit()
            return cursor.rowcount > 0
    

    async def update_playlist_last_refreshed(self, navidrome_playlist_id: str) -> bool:
        """Update the last_refreshed timestamp for a playlist"""
        await self.init_db()
    
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                UPDATE playlists 
                SET last_refreshed = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE navidrome_playlist_id = ?
            """, (navidrome_playlist_id,))
        
            await db.commit()
            return cursor.rowcount > 0
    

