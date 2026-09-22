"""Smart playlist API for Navidrome native API operations.

Provides methods to create temporary smart playlists with criteria
such as lastPlayed date ranges, then retrieve and clean up those
tracks without fetching the entire library.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import httpx

from ..config import NAVIDROME_URL, NAVIDROME_USERNAME, NAVIDROME_PASSWORD

logger = logging.getLogger(__name__)


class SmartPlaylistAPI:
    """Wrapper for Navidrome Native API smart playlist operations.

    Uses Navidrome's smart playlist criteria system to query tracks
    matching specific conditions (e.g., last played 30-90 days ago)
    without fetching the entire library.
    """

    def __init__(self, client: httpx.AsyncClient, base_url: str):
        self.client = client
        self.base_url = base_url.rstrip("/")
        self._auth_token: Optional[str] = None
        self._subsonic_token: Optional[str] = None
        self._subsonic_salt: Optional[str] = None
        self._jwt_token: Optional[str] = None

    async def _ensure_authenticated(self) -> None:
        """Ensure we have valid JWT token for Native API calls."""
        if not self._jwt_token:
            try:
                response = await self.client.post(
                    f"{self.base_url}/auth/login",
                    json={"username": NAVIDROME_USERNAME, "password": NAVIDROME_PASSWORD},
                )
                response.raise_for_status()
                data = response.json()
                self._jwt_token = data.get("token")
                if not self._jwt_token:
                    raise Exception("No JWT token received from login")
            except httpx.RequestError as e:
                logger.error(f"Network error during login: {e}")
                raise
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise Exception("Invalid username or password")
                elif e.response.status_code == 403:
                    raise Exception("Access forbidden - check your credentials")
                else:
                    raise Exception(f"Login failed with status {e.response.status_code}")

    def _get_native_headers(self) -> Dict[str, str]:
        """Get authentication headers for Native API."""
        return {
            "Authorization": f"Bearer {self._jwt_token}",
            "X-ND-Authorization": f"Bearer {self._jwt_token}",
            "Accept": "application/json",
        }

    async def create_target_playlist(
        self,
        name: str = "magiclists-rediscover-targets",
        days_start: int = 90,
        days_end: int = 30,
        refresh: bool = True,
    ) -> Optional[str]:
        """Create a temporary smart playlist with lastPlayed inTheRange criteria.

        Creates a smart playlist that matches tracks last played between
        days_end and days_start ago (inclusive). The playlist is marked
        public=false and temporary so it can be cleaned up later.

        Args:
            name: Playlist name (will be prefixed with user identifier)
            days_start: Start of target period in days (larger value = older)
            days_end: End of target period in days (smaller value = newer)
            refresh: Whether to immediately refresh the playlist criteria

        Returns:
            Playlist ID if successful, None if failed
        """
        await self._ensure_authenticated()

        # Calculate date strings for the inTheRange criteria
        now = datetime.now(timezone.utc)
        start_date = (now - timedelta(days=days_start)).strftime("%Y-%m-%d")
        end_date = (now - timedelta(days=days_end)).strftime("%Y-%m-%d")

        # Build the smart playlist criteria JSON
        # {"all":[{"inTheRange":{"lastPlayed":["start_date","end_date"]}}]}
        criteria_json = json.dumps(
            {
                "all": [
                    {
                        "inTheRange": {
                            "lastPlayed": [start_date, end_date]
                        }
                    }
                ]
            }
        )

        payload = {
            "name": name,
            "public": False,
            "rules": {
                "all": [
                    {
                        "inTheRange": {
                            "lastPlayed": [start_date, end_date]
                        }
                    }
                ],
                "sort": "lastplayed",
                "order": "desc",
            },
        }

        try:
            response = await self.client.post(
                f"{self.base_url}/api/playlist",
                json=payload,
                headers=self._get_native_headers(),
            )
            response.raise_for_status()
            data = response.json()

            if data.get("id"):
                playlist_id = data["id"]
                logger.info(
                    f"Created target smart playlist '{name}' with ID {playlist_id}"
                )
                return playlist_id
            else:
                logger.warning(f"Playlist created but no ID returned: {data}")
                return None

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                # Playlist already exists - try to get it
                logger.warning("Playlist already exists, attempting to retrieve")
                return await self._get_existing_playlist_id(name)
            logger.error(f"Failed to create playlist: {e}")
            return None
        except Exception as e:
            logger.error(f"Error creating target playlist: {e}")
            return None

    async def _get_existing_playlist_id(self, name: str) -> Optional[str]:
        """Try to get existing playlist ID by name."""
        try:
            response = await self.client.get(
                f"{self.base_url}/api/playlist",
                params={"name": name},
                headers=self._get_native_headers(),
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list) and len(data) > 0:
                # Find playlist by name
                for pl in data:
                    if pl.get("name") == name:
                        return pl.get("id")

            logger.warning(f"Could not find existing playlist '{name}'")
            return None
        except Exception as e:
            logger.debug(f"Error retrieving existing playlist: {e}")
            return None

    async def get_playlist_tracks(
        self, playlist_id: str, limit: int = 1000, offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Retrieve tracks from a smart playlist with pagination.

        Args:
            playlist_id: The playlist ID to fetch tracks from
            limit: Maximum tracks to return per page
            offset: Track offset for pagination

        Returns:
            List of track dictionaries
        """
        await self._ensure_authenticated()

        try:
            response = await self.client.get(
                f"{self.base_url}/api/playlist/{playlist_id}/tracks",
                params={"_start": str(offset), "_limit": str(limit)},
                headers=self._get_native_headers(),
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, dict) and "tracks" in data:
                return data["tracks"]
            elif isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # Try common response formats
                for key in ["tracks", "media_files", "songs", "items"]:
                    if key in data:
                        return data[key]

            logger.warning(f"Unexpected playlist tracks response format: {data}")
            return []

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.error(f"Playlist {playlist_id} not found (may have been deleted)")
                return []
            logger.error(f"Failed to get playlist tracks: {e}")
            return []
        except Exception as e:
            logger.error(f"Error getting playlist tracks: {e}")
            return []

    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete a temporary smart playlist.

        Args:
            playlist_id: The playlist ID to delete

        Returns:
            True if deletion succeeded, False otherwise
        """
        await self._ensure_authenticated()

        try:
            response = await self.client.delete(
                f"{self.base_url}/api/playlist/{playlist_id}",
                headers=self._get_native_headers(),
            )
            response.raise_for_status()
            logger.info(f"Deleted temporary playlist {playlist_id}")
            return True
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning(f"Playlist {playlist_id} already deleted or not found")
                return True  # Consider success if already gone
            logger.error(f"Failed to delete playlist: {e}")
            return False
        except Exception as e:
            logger.error(f"Error deleting playlist: {e}")
            return False

    async def get_target_tracks_direct(
        self,
        days_start: int = 90,
        days_end: int = 30,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Convenience method: create target playlist and retrieve tracks in one call.

        Args:
            days_start: Start of target period in days
            days_end: End of target period in days
            limit: Maximum tracks to retrieve

        Returns:
            List of tracks last played in the target period
        """
        # Create the playlist
        playlist_id = await self.create_target_playlist(
            days_start=days_start, days_end=days_end
        )

        if not playlist_id:
            logger.warning("Failed to create target playlist, returning empty list")
            return []

        try:
            # Retrieve tracks
            tracks = await self.get_playlist_tracks(playlist_id, limit=limit)

            # Clean up the temporary playlist
            await self.delete_playlist(playlist_id)

            logger.info(
                f"Retrieved {len(tracks)} target tracks (30-90 days) and cleaned up playlist"
            )
            return tracks

        except Exception as e:
            # Attempt cleanup even on error
            try:
                await self.delete_playlist(playlist_id)
            except Exception:
                pass
            logger.error(f"Error retrieving target tracks: {e}")
            return []


# Convenience function for quick usage
async def get_tracks_last_played_range(
    client: httpx.AsyncClient,
    base_url: str,
    days_start: int = 90,
    days_end: int = 30,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Quick function to get tracks last played in a date range.

    Args:
        client: httpx async client (already configured)
        base_url: Navidrome base URL
        days_start: Start of target period in days (e.g., 90)
        days_end: End of target period in days (e.g., 30)
        limit: Maximum tracks to return

    Returns:
        List of tracks last played between days_end and days_start ago
    """
    api = SmartPlaylistAPI(client, base_url)
    return await api.get_target_tracks_direct(
        days_start=days_start, days_end=days_end, limit=limit
    )