import aiosqlite
from typing import Optional


class _AnalyticsMixin:
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


