import os
from typing import Union

from ..navidrome import NavidromeClient
from ..jellyfin import JellyfinClient


def get_server_client() -> Union[NavidromeClient, JellyfinClient]:
    """Factory that returns appropriate server client based on SERVER_TYPE env."""
    server_type = os.getenv("SERVER_TYPE", "navidrome").lower()

    if server_type == "jellyfin":
        from .dependencies import get_jellyfin_client
        return get_jellyfin_client()
    elif server_type == "navidrome":
        from .dependencies import get_navidrome_client
        return get_navidrome_client()
    else:
        raise ValueError(f"Unknown SERVER_TYPE: {server_type}")
