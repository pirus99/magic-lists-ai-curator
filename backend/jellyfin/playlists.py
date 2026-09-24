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
        
        headers = self._get_auth_headers()
        
        # Create the playlist
        response = await self.client.post(
            f"{self.base_url}/Playlists",
            headers=headers,
            json={
                "Name": name,
                "Ids": track_ids
            }
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
        
        headers = self._get_auth_headers()
        
        # Update playlist with new tracks
        response = await self.client.post(
            f"{self.base_url}/Playlists/{playlist_id}/Items",
            headers=headers,
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
        """Update playlist metadata."""
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        
        update_data = {}
        if name:
            update_data["Name"] = name
        if comment:
            update_data["Overview"] = comment
        if is_public is not None:
            update_data["IsPublic"] = is_public
        
        response = await self.client.post(
            f"{self.base_url}/Playlists/{playlist_id}",
            headers=headers,
            json=update_data
        )
        response.raise_for_status()
        
        return True
    
    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete playlist."""
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        
        response = await self.client.delete(
            f"{self.base_url}/Playlists/{playlist_id}",
            headers=headers
        )
        response.raise_for_status()
        
        return True