import json
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import os

import aiosqlite


def get_database_path() -> str:
    server_type = os.getenv("SERVER_TYPE", "navidrome").lower()
    base_path = os.getenv("DATABASE_PATH", "magiclists.db")
    if "." in base_path:
        name, ext = base_path.rsplit(".", 1)
        return f"{name}_{server_type}.{ext}"
    return f"{base_path}_{server_type}"


class _ConnectionMixin:
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
          3. Infer from the synthetic artist_id used for rediscover v2 playlists.
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
                    elif artist_id == "rediscover_v2":
                        inferred = "rediscover_weekly_v2"
                    else:
                        inferred = "this_is"

                    await db.execute("""
                        UPDATE playlists SET playlist_type = ? WHERE id = ?
                    """, (inferred, playlist_id))

                await db.commit()
        except Exception:
            # Backfill is best-effort; never block startup on it
            pass


