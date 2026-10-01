import httpx
from typing import List, Set


class _PlaylistsMixin:
    """Methods for managing playlists in Jellyfin."""
    
    async def get_playlist_ids(self) -> Set[str]:
        """Return the set of playlist IDs that currently exist on the server.

        Used to reconcile Magic Lists' local database with the media server so
        playlists deleted outside of Magic Lists can be cleaned up.
        """
        await self._ensure_authenticated()

        headers = self._get_auth_headers()
        # GET /Playlists requires a userId; resolve it (API-key auth has none yet).
        user_id = await self._resolve_user_id()
        # GET /Playlists only accepts a userId query parameter (no
        # Recursive/IncludeItemTypes), so _items_params() is not used here.
        params = {}
        if user_id:
            params["userId"] = user_id
        response = await self.client.get(
            f"{self.base_url}/Playlists",
            headers=headers,
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        items = data.get("Items", data) if isinstance(data, dict) else data
        return {
            str(item.get("Id"))
            for item in items
            if item.get("Id")
        }

    async def playlist_exists(self, playlist_id: str) -> bool:
        """Return True if the given playlist still exists on the server."""
        return str(playlist_id) in await self.get_playlist_ids()

    async def create_playlist(
        self, 
        name: str, 
        track_ids: List[str], 
        comment: str = None
    ) -> str:
        """Create a new playlist and populate with tracks.
        
        Args:
            name: Name of the playlist
            track_ids: List of track IDs to add to playlist
            comment: Optional comment/description for the playlist
        
        Returns:
            playlist_id: The ID of the created playlist
        """
        await self._ensure_authenticated()
        # Jellyfin 12.x requires a valid UserId for playlist creation. With an API
        # key the token carries no user, so resolve it from /Users.
        user_id = await self._resolve_user_id()
        
        headers = self._get_auth_headers()
        
        # Create the playlist
        payload = {
            "Name": name,
            "Ids": track_ids,
            "MediaType": "Audio",
        }
        if user_id:
            payload["UserId"] = user_id
        response = await self.client.post(
            f"{self.base_url}/Playlists",
            headers=headers,
            json=payload
        )
        response.raise_for_status()
        
        data = response.json()
        playlist_id = data.get("Id")
        
        if not playlist_id:
            raise Exception("Failed to get playlist ID from response")
        
        # Add comment if provided
        if comment:
            await self.update_playlist_metadata(playlist_id, comment=comment)
        
        return playlist_id
    
    async def update_playlist(
        self, 
        playlist_id: str, 
        track_ids: List[str], 
        comment: str = None
    ) -> bool:
        """Replace all tracks in a Jellyfin playlist."""
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        response = await self.client.post(
            f"{self.base_url}/Playlists/{playlist_id}",
            headers=headers,
            json={"Ids": track_ids}
        )
        response.raise_for_status()
        
        # Update comment if provided
        if comment is not None:
            await self.update_playlist_metadata(playlist_id, comment=comment)
        
        return True
    
    async def update_playlist_metadata(
        self, 
        playlist_id: str,
        name: str = None,
        comment: str = None,
        is_public: bool = None
    ) -> bool:
        """Update playlist metadata.

        Jellyfin's ``UpdatePlaylist`` endpoint (``POST /Playlists/{id}``) only
        accepts ``Name``, ``Ids``, ``Users`` and ``IsPublic`` (its DTO has
        ``additionalProperties: false``), so the description/comment must be set
        via the generic item update endpoint (``POST /Items/{id}``) using the
        ``Overview`` field on ``BaseItemDto``.
        """
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        
        # Name / IsPublic go through the dedicated playlist update endpoint.
        playlist_update = {}
        if name is not None:
            playlist_update["Name"] = name
        if is_public is not None:
            playlist_update["IsPublic"] = is_public
        
        if playlist_update:
            response = await self.client.post(
                f"{self.base_url}/Playlists/{playlist_id}",
                headers=headers,
                json=playlist_update
            )
            response.raise_for_status()
        
        # Comment/description is stored as the item Overview.
        if comment is not None:
            response = await self.client.post(
                f"{self.base_url}/Items/{playlist_id}",
                headers=headers,
                json={"Overview": comment}
            )
            response.raise_for_status()
        
        return True
    
    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete a playlist from Jellyfin.

        Jellyfin 12.1 does not expose ``DELETE /Playlists/{id}``. A playlist is
        an item, so the supported generic deletion endpoint is used instead.

        Deleting an already-deleted playlist is a no-op and returns True, so
        callers can reconcile state after the user removed the playlist
        directly in Jellyfin.
        """
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        response = await self.client.delete(
            f"{self.base_url}/Items/{playlist_id}",
            headers=headers
        )
        
        if response.status_code == 404:
            # Already gone -> treat as successfully deleted.
            return True
        
        response.raise_for_status()
        
        return True