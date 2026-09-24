"""SQLite database manager, split into focused submodules.

The public ``DatabaseManager`` class is reassembled here by composing the mixin
classes defined in ``connection``, ``playlists``, ``schedules``, ``cache``,
``config`` and ``analytics``. Import ``from .database import DatabaseManager``
(the old ``database.py`` module path is gone).
"""
from .connection import _ConnectionMixin, get_database_path
from .playlists import _DatabasePlaylistsMixin
from .schedules import _SchedulesMixin
from .cache import _CacheMixin
from .config import _ConfigMixin
from .analytics import _AnalyticsMixin


class DatabaseManager(
    _ConnectionMixin,
    _DatabasePlaylistsMixin,
    _SchedulesMixin,
    _CacheMixin,
    _ConfigMixin,
    _AnalyticsMixin,
):
    """SQLite database manager for storing playlists and related data."""


async def get_db() -> DatabaseManager:
    """FastAPI dependency to get the server-specific database manager."""
    return DatabaseManager(get_database_path())


__all__ = ["DatabaseManager", "get_database_path", "get_db"]
