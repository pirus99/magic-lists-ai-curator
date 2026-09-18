import aiosqlite
from typing import List, Optional, Dict
from datetime import datetime, timedelta


class _CacheMixin:
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
