import sqlite3
import aiosqlite
import os
from typing import List, Optional, Dict
from datetime import datetime
import json

from .schemas import Playlist, ScheduledPlaylist

class DatabaseManager:
    """SQLite database manager for storing playlists"""
    
    def __init__(self, db_path: str = "magiclists.db"):
        self.db_path = db_path
    
    async def init_db(self):
        """Initialize the database with required tables"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist_id TEXT NOT NULL,
                    playlist_name TEXT NOT NULL,
                    songs TEXT, -- JSON array of song titles
                    description TEXT, -- AI description/description
                    navidrome_playlist_id TEXT, -- Link to Navidrome playlist
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Add description column if it doesn't exist (for existing databases)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN description TEXT")
            except:
                # Column already exists or other error - ignore
                pass
            
            # Add navidrome_playlist_id column if it doesn't exist (for existing databases)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN navidrome_playlist_id TEXT")
            except:
                # Column already exists or other error - ignore
                pass

            # Add library_ids column if it doesn't exist (for existing databases)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN library_ids TEXT")  # JSON array of library IDs
            except:
                # Column already exists or other error - ignore
                pass
            
            # Add last_refreshed column if it doesn't exist (for tracking refreshes)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN last_refreshed TIMESTAMP")
            except:
                # Column already exists or other error - ignore
                pass
            
            # Add playlist_length column if it doesn't exist (for storing original length)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN playlist_length INTEGER")
            except:
                # Column already exists or other error - ignore
                pass

            # Add playlist_type column if it doesn't exist (authoritative type marker)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN playlist_type TEXT")
            except:
                # Column already exists or other error - ignore
                pass

            # Add curation_settings column if it doesn't exist (JSON blob of saved curation settings)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN curation_settings TEXT")
            except:
                # Column already exists or other error - ignore
                pass

            # Add is_public column if it doesn't exist (for Navidrome visibility)
            try:
                await db.execute("ALTER TABLE playlists ADD COLUMN is_public INTEGER DEFAULT 0")
            except:
                # Column already exists or other error - ignore
                pass

            await db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_type TEXT NOT NULL,
                    navidrome_playlist_id TEXT NOT NULL,
                    refresh_frequency TEXT NOT NULL,
                    next_refresh TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_playlists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_type TEXT NOT NULL,
                    navidrome_playlist_id TEXT NOT NULL,
                    refresh_frequency TEXT NOT NULL,
                    next_refresh TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create the app_config table for storing application configuration
            await db.execute("""
                CREATE TABLE IF NOT EXISTS app_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            # Create the library_analytics table for tracking library size
            await db.execute("""
                CREATE TABLE IF NOT EXISTS library_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    song_count INTEGER NOT NULL,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create the user_preferences table for storing user settings like selected library
            await db.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,  -- For future multi-user support
                    selected_library_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create the playlist_history_v2 table for Re-Discover Weekly v2.0 logging
            await db.execute("""
                CREATE TABLE IF NOT EXISTS playlist_history_v2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    playlist_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    navidrome_server_id TEXT NOT NULL,
                    mode_used TEXT NOT NULL,
                    primary_theme TEXT,
                    tracks_analyzed_count INTEGER NOT NULL,
                    track_ids_json TEXT NOT NULL,  -- JSON array of track IDs
                    track_count INTEGER NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create the api_cache table for caching API responses
            await db.execute("""
                CREATE TABLE IF NOT EXISTS api_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cache_key TEXT NOT NULL UNIQUE,
                    cache_value TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create index on cache_key for faster lookups
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_cache_key ON api_cache(cache_key)
            """)

            # Create index on expires_at for cleanup
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_cache_expires ON api_cache(expires_at)
            """)

            await db.commit()

            # Backfill the authoritative playlist_type column for existing rows
            await self._backfill_playlist_types()

    async def _backfill_playlist_types(self):
        """Idempotently populate playlists.playlist_type for rows that lack it.

        Priority:
          1. Copy from a matching scheduled_playlists row (most reliable).
          2. Infer from curation_settings.genres (genre_mix).
          3. Infer from the synthetic artist_id used for rediscover playlists.
          4. Fall back to 'this_is'.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 1. Copy from scheduled_playlists where the playlists row is missing a type
                await db.execute("""
                    UPDATE playlists
                    SET playlist_type = (
                        SELECT sp.playlist_type
                        FROM scheduled_playlists sp
                        WHERE sp.navidrome_playlist_id = playlists.navidrome_playlist_id
                        LIMIT 1
                    )
                    WHERE (playlist_type IS NULL OR playlist_type = '')
                      AND navidrome_playlist_id IN (
                          SELECT navidrome_playlist_id FROM scheduled_playlists
                      )
                """)

                # 2 & 3 & 4. Infer for remaining rows without a type
                async with db.execute("""
                    SELECT id, artist_id, curation_settings
                    FROM playlists
                    WHERE playlist_type IS NULL OR playlist_type = ''
                """) as cursor:
                    rows = await cursor.fetchall()

                for row in rows:
                    playlist_id = row[0]
                    artist_id = row[1] or ""
                    curation_settings = json.loads(row[2]) if row[2] else {}

                    if curation_settings.get("genres"):
                        inferred = "genre_mix"
                    elif artist_id in ("rediscover", "rediscover_v2"):
                        inferred = "rediscover_weekly_v2" if artist_id == "rediscover_v2" else "rediscover"
                    else:
                        inferred = "this_is"

                    await db.execute("""
                        UPDATE playlists SET playlist_type = ? WHERE id = ?
                    """, (inferred, playlist_id))

                await db.commit()
        except Exception:
            # Backfill is best-effort; never block startup on it
            pass
    
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
                        songs=json.loads(row[3]),
                        description=row[4],
                        navidrome_playlist_id=row[5],
                        playlist_length=row[8],
                        created_at=row[6],
                        updated_at=row[7],
                        library_ids=json.loads(row[9]) if row[9] else [],
                        curation_settings=json.loads(row[10]) if row[10] else {},
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
                        songs=json.loads(row[3]),
                        description=row[4],
                        navidrome_playlist_id=row[5],
                        created_at=row[6],
                        updated_at=row[7],
                        library_ids=json.loads(row[9]) if row[9] else [],
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
                        songs=json.loads(row[3]),
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
                        "songs": json.loads(row[3]),
                        "description": row[4],
                        "navidrome_playlist_id": row[5],
                        "is_public": bool(row[6]),
                        "created_at": row[7],
                        "updated_at": row[8],
                        "last_refreshed": row[9],
                        "playlist_length": row[10],
                        "curation_settings": json.loads(row[11]) if row[11] else {},
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
                        "songs": json.loads(row[3]),
                        "description": row[4],
                        "is_public": bool(row[5]),
                        "created_at": row[6],
                        "updated_at": row[7],
                        "navidrome_playlist_id": row[8],
                        "curation_settings": json.loads(row[9]) if row[9] else {},
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
    
    async def delete_scheduled_playlist_by_navidrome_id(self, navidrome_playlist_id: str) -> bool:
        """Delete a scheduled playlist by Navidrome playlist ID"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM scheduled_playlists WHERE navidrome_playlist_id = ?
            """, (navidrome_playlist_id,))
            
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
    
    async def get_config(self, key: str) -> Optional[str]:
        """Get a configuration value by key"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT value FROM app_config WHERE key = ?
            """, (key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None
    
    async def set_config(self, key: str, value: str) -> bool:
        """Set a configuration value"""
        await self.init_db()
        
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)
            """, (key, value))
            await db.commit()
            return True
    
    async def get_or_create_user_id(self) -> str:
        """Get or create a unique user ID for analytics tracking"""
        import uuid
        
        user_id = await self.get_config("user_id")
        if not user_id:
            # Generate a new unique user ID
            user_id = str(uuid.uuid4())
            await self.set_config("user_id", user_id)
        
        return user_id
    
    async def should_track_library_size(self) -> bool:
        """Check if we should track library size (90+ days since last tracking)"""
        await self.init_db()
        
        from datetime import datetime, timedelta
        
        # Get the last tracking timestamp
        last_tracked = await self.get_config("last_library_tracking")
        if not last_tracked:
            return True  # Never tracked before
        
        try:
            last_tracked_date = datetime.fromisoformat(last_tracked)
            cutoff_date = datetime.now() - timedelta(days=90)
            return last_tracked_date < cutoff_date
        except:
            return True  # Invalid timestamp, track again
    
    async def record_library_size(self, song_count: int) -> bool:
        """Record library size for analytics"""
        await self.init_db()
        
        user_id = await self.get_or_create_user_id()
        current_time = datetime.now()
        
        async with aiosqlite.connect(self.db_path) as db:
            # Insert the library analytics record
            await db.execute("""
                INSERT INTO library_analytics (user_id, song_count, recorded_at)
                VALUES (?, ?, ?)
            """, (user_id, song_count, current_time.isoformat()))
            
            # Update the last tracking timestamp
            await db.execute("""
                INSERT OR REPLACE INTO app_config (key, value) VALUES (?, ?)
            """, ("last_library_tracking", current_time.isoformat()))
            
            await db.commit()
            return True

    async def get_user_preference(self, user_id: str, key: str) -> Optional[str]:
        """Get a user preference value"""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT value FROM user_preferences WHERE user_id = ? AND key = ?
            """, (user_id, key)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_user_preference(self, user_id: str, key: str, value: str) -> bool:
        """Set a user preference value"""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO user_preferences (user_id, key, value, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (user_id, key, value))
            await db.commit()
            return True

    async def get_selected_library_id(self, user_id: str) -> Optional[str]:
        """Get the user's selected library ID"""
        return await self.get_user_preference(user_id, "selected_library_id")

    async def set_selected_library_id(self, user_id: str, library_id: str) -> bool:
        """Set the user's selected library ID"""
        return await self.set_user_preference(user_id, "selected_library_id", library_id)

    async def get_cache(self, cache_key: str) -> Optional[str]:
        """Get a cached value by key, checking expiration"""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT cache_value FROM api_cache
                WHERE cache_key = ? AND expires_at > datetime('now')
            """, (cache_key,)) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

    async def set_cache(self, cache_key: str, cache_value: str, ttl_seconds: int) -> bool:
        """Set a cached value with TTL (time to live in seconds)"""
        await self.init_db()

        from datetime import datetime, timedelta
        expires_at = datetime.now() + timedelta(seconds=ttl_seconds)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT OR REPLACE INTO api_cache (cache_key, cache_value, expires_at)
                VALUES (?, ?, ?)
            """, (cache_key, cache_value, expires_at.isoformat()))
            await db.commit()
            return True

    async def cleanup_expired_cache(self) -> int:
        """Clean up expired cache entries. Returns number of entries deleted."""
        await self.init_db()

        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                DELETE FROM api_cache WHERE expires_at <= datetime('now')
            """)
            deleted_count = cursor.rowcount
            await db.commit()
            return deleted_count

# Dependency for FastAPI
async def get_db() -> DatabaseManager:
    """FastAPI dependency to get database manager"""
    # Get database path from environment variable with smart defaults
    # Docker: /app/data/magiclists.db (set in docker-compose.yml)
    # Standalone: ./magiclists.db (current directory)
    default_path = "/app/data/magiclists.db" if os.path.exists("/app/data") else "./magiclists.db"
    db_path = os.getenv("DATABASE_PATH", default_path)
    return DatabaseManager(db_path)