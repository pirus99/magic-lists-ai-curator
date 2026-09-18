import httpx
from typing import List


class _PlaylistsMixin:
    async def create_playlist(self, name: str, track_ids: List[str], comment: str = None) -> str:
        """Create a new playlist in Navidrome using Subsonic API
    
        Args:
            name: Name of the playlist
            track_ids: List of track IDs to add to playlist
            comment: Optional comment/description for the playlist
        
        Returns:
            playlist_id: The ID of the created playlist
        """
        try:
            await self._ensure_authenticated()
        
            # Create the playlist using Subsonic API (note: createPlaylist doesn't support comment)
            params = self._get_subsonic_params()
            params["name"] = name
            # Note: comment will be set via updatePlaylist after creation
        
            response = await self.client.get(
                f"{self.base_url}/rest/createPlaylist.view",
                params=params
            )
            response.raise_for_status()
        
            data = response.json()
        
            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")
        
            playlist_data = subsonic_response.get("playlist", {})
            playlist_id = playlist_data.get("id")
        
            if not playlist_id:
                raise Exception("Failed to get playlist ID from response")
        
            # Add tracks to the playlist if provided - PRESERVE ORDER
            if track_ids:
                print(f"🎵 Adding {len(track_ids)} tracks to playlist in AI-curated order using updatePlaylist...")
            
                # Use proper Subsonic API with multiple songIdToAdd parameters in single call
                update_params = self._get_subsonic_params()
                update_params["playlistId"] = playlist_id
                # Set as list - httpx will create multiple parameters: songIdToAdd=id1&songIdToAdd=id2&...
                update_params["songIdToAdd"] = track_ids
            
                response = await self.client.get(
                    f"{self.base_url}/rest/updatePlaylist.view",
                    params=update_params
                )
                response.raise_for_status()
            
                update_data = response.json()
                update_subsonic = update_data.get("subsonic-response", {})
                if update_subsonic.get("status") != "ok":
                    error = update_subsonic.get("error", {})
                    raise Exception(f"Failed to add songs to playlist: {error.get('message', 'Unknown error')}")
            
                print(f"🎯 Successfully added all {len(track_ids)} tracks in single API call")
        
            # Add comment via updatePlaylist if provided (createPlaylist doesn't support comments)
            if comment:
                print(f"💬 Adding comment to playlist via updatePlaylist...")
                comment_params = self._get_subsonic_params()
                comment_params["playlistId"] = playlist_id
                comment_params["comment"] = comment
            
                comment_response = await self.client.get(
                    f"{self.base_url}/rest/updatePlaylist.view",
                    params=comment_params
                )
                comment_response.raise_for_status()
            
                comment_data = comment_response.json()
                comment_subsonic = comment_data.get("subsonic-response", {})
                if comment_subsonic.get("status") != "ok":
                    error = comment_subsonic.get("error", {})
                    print(f"⚠️ Warning: Failed to add comment to playlist: {error.get('message', 'Unknown error')}")
                else:
                    print(f"✅ Successfully added comment to playlist")
            
            return playlist_id
            
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error creating playlist: {e}")
    

    async def update_playlist(self, playlist_id: str, track_ids: List[str], comment: str = None) -> bool:
        """Update an existing playlist by replacing all tracks
    
        Args:
            playlist_id: ID of the playlist to update
            track_ids: List of track IDs to replace current tracks with
            comment: Optional comment/description to update
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            await self._ensure_authenticated()
        
            # First, get current playlist to find all song IDs to remove
            get_params = self._get_subsonic_params()
            get_params["id"] = playlist_id
        
            response = await self.client.get(
                f"{self.base_url}/rest/getPlaylist.view",
                params=get_params
            )
            response.raise_for_status()
        
            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Failed to get playlist for clearing: {error.get('message', 'Unknown error')}")
        
            # Get current song IDs to remove
            current_playlist = subsonic_response.get("playlist", {})
            current_songs = current_playlist.get("entry", [])
            current_song_ids = [song.get("id") for song in current_songs if song.get("id")]
        
            # Remove all existing songs if any exist
            if current_song_ids:
                clear_params = self._get_subsonic_params()
                clear_params["playlistId"] = playlist_id
                clear_params["songIndexToRemove"] = list(range(len(current_song_ids)))  # Remove all by index
                if comment:
                    clear_params["comment"] = comment
            
                response = await self.client.get(
                    f"{self.base_url}/rest/updatePlaylist.view",
                    params=clear_params
                )
                response.raise_for_status()
            
                data = response.json()
                subsonic_response = data.get("subsonic-response", {})
                if subsonic_response.get("status") != "ok":
                    error = subsonic_response.get("error", {})
                    raise Exception(f"Failed to clear playlist: {error.get('message', 'Unknown error')}")
            elif comment:
                # Just update comment if no songs to remove
                clear_params = self._get_subsonic_params()
                clear_params["playlistId"] = playlist_id
                clear_params["comment"] = comment
            
                response = await self.client.get(
                    f"{self.base_url}/rest/updatePlaylist.view",
                    params=clear_params
                )
                response.raise_for_status()
        
            # Then add the new tracks - PRESERVE ORDER
            if track_ids:
                print(f"🎵 Updating playlist with {len(track_ids)} tracks in AI-curated order...")
            
                # Use proper Subsonic API with multiple songIdToAdd parameters in single call
                update_params = self._get_subsonic_params()
                update_params["playlistId"] = playlist_id
                # Set as list - httpx will create multiple parameters: songIdToAdd=id1&songIdToAdd=id2&...
                update_params["songIdToAdd"] = track_ids
            
                response = await self.client.get(
                    f"{self.base_url}/rest/updatePlaylist.view",
                    params=update_params
                )
                response.raise_for_status()
            
                update_data = response.json()
                update_subsonic = update_data.get("subsonic-response", {})
                if update_subsonic.get("status") != "ok":
                    error = update_subsonic.get("error", {})
                    raise Exception(f"Failed to add songs to playlist: {error.get('message', 'Unknown error')}")
            
                print(f"🎯 Successfully updated playlist with all {len(track_ids)} tracks in single API call")
        
            return True
            
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error updating playlist: {e}")
    

    async def update_playlist_metadata(self, playlist_id: str, name: str = None, comment: str = None, is_public: bool = None) -> bool:
        """Update a playlist's name, description/comment, and visibility in Navidrome if supported."""
        try:
            await self._ensure_authenticated()

            params = self._get_subsonic_params()
            params["playlistId"] = playlist_id
            if name is not None:
                params["name"] = name
            if comment is not None:
                params["comment"] = comment
            if is_public is not None:
                params["public"] = "true" if is_public else "false"

            response = await self.client.get(
                f"{self.base_url}/rest/updatePlaylist.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Failed to update playlist metadata: {error.get('message', 'Unknown error')}")

            return True
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error updating playlist metadata: {e}")


    async def delete_playlist(self, playlist_id: str) -> bool:
        """Delete a playlist from Navidrome
    
        Args:
            playlist_id: ID of the playlist to delete
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            await self._ensure_authenticated()
        
            params = self._get_subsonic_params()
            params["id"] = playlist_id  # According to Subsonic API docs, parameter should be "id", not "playlistId"
        
            print(f"🗑️ Attempting to delete playlist with ID: {playlist_id}")
            print(f"🔧 Delete request URL: {self.base_url}/rest/deletePlaylist.view")
            print(f"🔧 Delete request params: {params}")
        
            response = await self.client.get(
                f"{self.base_url}/rest/deletePlaylist.view",
                params=params
            )
            response.raise_for_status()
        
            data = response.json()
            print(f"🔧 Delete response data: {data}")
        
            subsonic_response = data.get("subsonic-response", {})
            print(f"🔧 Subsonic response status: {subsonic_response.get('status')}")
        
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                error_message = error.get('message', 'Unknown error')
                error_code = error.get('code', 'Unknown code')
                print(f"❌ Subsonic API error: {error_message} (code: {error_code})")
                raise Exception(f"Failed to delete playlist: {error_message} (code: {error_code})")
        
            print(f"✅ Successfully deleted playlist {playlist_id} from Navidrome")
            return True
            
        except httpx.RequestError as e:
            print(f"🌐 Network error deleting playlist: {e}")
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            print(f"🚨 HTTP error deleting playlist: {e.response.status_code} - {e.response.text}")
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code} - {e.response.text}")
        except Exception as e:
            print(f"💥 Unexpected error deleting playlist: {e}")
            raise Exception(f"Unexpected error deleting playlist: {e}")
    

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

