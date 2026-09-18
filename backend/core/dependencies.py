"""FastAPI dependency singletons for the Navidrome and AI clients.

These were previously module-level globals in ``main.py``. They are kept here so
that the per-type routers and builders can resolve the same lazily-initialised
client instances without importing the (now thin) application module.
"""
from typing import Optional

from ..navidrome import NavidromeClient
from ..ai_client import AIClient


# Lazily-initialised singletons (mirrors the previous module-level globals).
_navidrome_client: Optional[NavidromeClient] = None
_ai_client: Optional[AIClient] = None


def get_navidrome_client() -> NavidromeClient:
    """Return the shared Navidrome client, creating it on first use."""
    global _navidrome_client
    if _navidrome_client is None:
        _navidrome_client = NavidromeClient()
    return _navidrome_client


def get_ai_client() -> AIClient:
    """Return the shared AI client, creating it on first use."""
    global _ai_client
    if _ai_client is None:
        _ai_client = AIClient()
    return _ai_client
