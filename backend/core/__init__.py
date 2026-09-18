"""Shared orchestration layer for the Magic Lists backend.

This package holds code that is common across all playlist types:
- `dependencies`: FastAPI dependency singletons for the Navidrome / AI clients.
- `scheduler`: refresh scheduling and dispatch logic.
- `playlist_builder`: a generic build/refresh pipeline shared by every type.
"""
