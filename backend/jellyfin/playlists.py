import httpx
from typing import List


class _PlaylistsMixin:
    """Methods for managing playlists in Jellyfin."""
    
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
        """Replace all tracks in playlist."""
        await self._ensure_authenticated()
        user_id = await self._resolve_user_id()
        
        headers = self._get_auth_headers()
        
        params = {}
        if user_id:
            params["userId"] = user_id
        
        # Update playlist with new tracks
        response = await self.client.post(
            f"{self.base_url}/Playlists/{playlist_id}/Items",
            headers=headers,
            params=params,
            json={
                "Ids": track_ids
            }
        )
        response.raise_for_status()
        
        # Update comment if provided
        if comment:
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
        user_id = await self._resolve_user_id()
        
        headers = self._get_auth_headers()
        params = {}
        if user_id:
            params["userId"] = user_id
        
        # Name / IsPublic go through the dedicated playlist update endpoint.
        playlist_update = {}
        if name:
            playlist_update["Name"] = name
        if is_public is not None:
            playlist_update["IsPublic"] = is_public
        
        if playlist_update:
            response = await self.client.post(
                f"{self.base_url}/Playlists/{playlist_id}",
                headers=headers,
                params=params,
                json=playlist_update
            )
            response.raise_for_status()
        
        # Comment/description is stored as the item Overview.
        if comment:
            response = await self.client.post(
                f"{self.base_url}/Items/{playlist_id}",
                headers=headers,
                params=params,
                json={"Overview": comment}
            )
            response.raise_for_status()
        
        return True
    
    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete playlist."""
        await self._ensure_authenticated()
        user_id = await self._resolve_user_id()
        
        headers = self._get_auth_headers()
        
        params = {}
        if user_id:
            params["userId"] = user_id
        
        response = await self.client.delete(
            f"{self.base_url}/Playlists/{playlist_id}",
            headers=headers,
            params=params
        )
        response.raise_for_status()
        
        return True