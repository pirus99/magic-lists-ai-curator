import os
import socket
import uuid
from typing import Dict, Any, Optional

import httpx


# Client identification sent to Jellyfin. Jellyfin 12.0 removed the legacy
# X-Emby-Token / X-Emby-Authorization headers; the only supported scheme is the
# standard `Authorization: MediaBrowser ...` header (see Jellyfin API auth docs).
CLIENT_NAME = "MagicLists"
CLIENT_VERSION = "1.0.0"
# A stable per-process device id so the server can track the session.
_DEVICE_ID = uuid.uuid4().hex


class _JellyfinBase:
    """Base class for Jellyfin API authentication and connection."""
    
    def __init__(self):
        self.base_url = os.getenv("JELLYFIN_URL", "")
        # Only enforce URL if actually using Jellyfin
        server_type = os.getenv("SERVER_TYPE", "navidrome").lower()
        if server_type == "jellyfin" and not self.base_url:
            raise ValueError("JELLYFIN_URL environment variable is required when SERVER_TYPE=jellyfin")
        
        self.api_key = os.getenv("JELLYFIN_API_KEY")
        self.username = os.getenv("JELLYFIN_USERNAME")
        self.password = os.getenv("JELLYFIN_PASSWORD")
        self.verify_ssl = os.getenv("JELLYFIN_VERIFY_SSL", "true").lower() != "false"
        
        if server_type == "jellyfin" and not self.api_key and not (self.username and self.password):
            raise ValueError(
                "Jellyfin requires either JELLYFIN_API_KEY or "
                "both JELLYFIN_USERNAME and JELLYFIN_PASSWORD"
            )
        
        self.client = httpx.AsyncClient(verify=self.verify_ssl)
        self._auth_token: Optional[str] = None
        self._user_id: Optional[str] = None
    
    def _build_auth_header(self, token: Optional[str] = None) -> str:
        """Build the `Authorization: MediaBrowser ...` header value.

        Args:
            token: Access token or API key. When omitted, only client
                identification is included (used for the initial login request
                before a token exists).

        Returns:
            The full header value, e.g.
            `MediaBrowser Token="abc", Client="MagicLists", Device="host",
             DeviceId="...", Version="1.0.0"`.
        """
        parts = [
            f'Client="{CLIENT_NAME}"',
            f'Device="{socket.gethostname()}"',
            f'DeviceId="{_DEVICE_ID}"',
            f'Version="{CLIENT_VERSION}"',
        ]
        if token:
            parts.insert(0, f'Token="{token}"')
        return "MediaBrowser " + ", ".join(parts)
    
    async def _ensure_authenticated(self):
        """Authenticate with Jellyfin using available credentials."""
        if self.api_key:
            # API key-based auth (easiest)
            return
        
        if self.username and self.password and not self._auth_token:
            # Username/password-based auth.
            # The login request carries client identification but no token yet.
            response = await self.client.post(
                f"{self.base_url}/Users/AuthenticateByName",
                json={"Username": self.username, "Pw": self.password},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": self._build_auth_header(),
                }
            )
            response.raise_for_status()
            
            data = response.json()
            self._auth_token = data.get("AccessToken")
            self._user_id = data.get("User", {}).get("Id")
            
            if not self._auth_token:
                raise ValueError("No access token received from Jellyfin")
    
    def _items_params(self, **overrides: Any) -> Dict[str, Any]:
        """Build query parameters for `/Items` (and `/Artists`) requests.

        Jellyfin requires `userId` on item queries when authenticating with a
        user access token (i.e. not an API key), and `Recursive=true` is needed
        to traverse into nested library folders. This helper centralizes both so
        every query is consistent and actually returns data.

        Args:
            **overrides: Extra/override query parameters.

        Returns:
            A dict of query parameters including userId/Recursive when relevant.
        """
        params: Dict[str, Any] = {"Recursive": True}
        if self._user_id:
            params["userId"] = self._user_id
        params.update(overrides)
        return params

    def _get_auth_headers(self) -> Dict[str, str]:
        """Return authorization headers for Jellyfin requests.

        Uses the standard `Authorization: MediaBrowser Token="..."` header,
        which is the only scheme supported by Jellyfin 12.0+ (the legacy
        X-Emby-Token header was removed).
        """
        headers = {}
        
        if self.api_key:
            headers["Authorization"] = self._build_auth_header(token=self.api_key)
        elif self._auth_token:
            headers["Authorization"] = self._build_auth_header(token=self._auth_token)
        
        return headers
    
    async def _get_music_libraries(self) -> list[Dict[str, Any]]:
        """Get all music-type libraries from Jellyfin.

        Uses the dedicated `/Library/VirtualFolders` endpoint, which returns the
        configured libraries (virtual folders) with their collection type. The
        `/Items` endpoint does not expose libraries via `IncludeItemTypes`.

        Returns:
            List of libraries with structure:
            [
                {"id": "lib_id", "name": "Library Name"},
                ...
            ]
        """
        await self._ensure_authenticated()

        headers = self._get_auth_headers()
        response = await self.client.get(
            f"{self.base_url}/Library/VirtualFolders",
            headers=headers
        )
        response.raise_for_status()

        data = response.json()
        libraries = []

        for folder in data:
            # Only include music libraries
            if (folder.get("CollectionType") or "").lower() != "music":
                continue
            libraries.append({
                "id": folder.get("ItemId"),
                "name": folder.get("Name")
            })

        return libraries

    async def _validate_library(self, library_id: str) -> bool:
        """Verify library exists and contains music."""
        await self._ensure_authenticated()

        headers = self._get_auth_headers()
        params: Dict[str, Any] = {
            "IncludeItemTypes": "Audio",
            "ParentId": library_id,
            "Limit": 1,
            "Recursive": True,
        }
        if self._user_id:
            params["userId"] = self._user_id
        response = await self.client.get(
            f"{self.base_url}/Items",
            headers=headers,
            params=params
        )
        response.raise_for_status()

        data = response.json()
        return len(data.get("Items", [])) > 0