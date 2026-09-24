"""SQLite database manager, split into focused submodules.

The public ``DatabaseManager`` class is reassembled here by composing the mixin
classes defined in ``connection``, ``playlists``, ``schedules``, ``cache``,
``config`` and ``analytics``. Import ``from .database import DatabaseManager``
(the old ``database.py`` module path is gone).
"""
import os
from typing import Optional

from .connection import _ConnectionMixin
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
    """FastAPI dependency to get database manager."""
    default_path = "/app/data/magiclists.db" if os.path.exists("/app/data") else "./magiclists.db"
    db_path = os.getenv("DATABASE_PATH", default_path)
    # Separate DB per server instance
    server_type = os.getenv("SERVER_TYPE", "navidrome").lower()
    if "." in db_path:
        name, ext = db_path.rsplit(".", 1)
        db_path = f"{name}_{server_type}.{ext}"
    else:
        db_path = f"{db_path}_{server_type}"
    return DatabaseManager(db_path)


__all__ = ["DatabaseManager", "get_db"]
