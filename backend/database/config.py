import aiosqlite
from typing import List, Optional, Dict
from datetime import datetime, timedelta


class _ConfigMixin:
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


