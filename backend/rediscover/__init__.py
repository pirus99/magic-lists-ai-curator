"""Re-Discover (rediscover) playlist type package.

Only the v2 two-phase processor is retained. The legacy ``RediscoverWeekly`` class
has been removed as part of the consolidation; stored playlists with the legacy
``"rediscover"`` type are handled by mapping them onto the v2 processor in
``builder.py``.
"""
