from typing import List, Dict, Any, Union


class _ArtistsMixin:
    """Methods for fetching artists from Jellyfin."""
    
    async def get_music_libraries(self) -> List[Dict[str, Any]]:
        """Get all music-type libraries from Jellyfin.
        
        Returns:
            List of libraries with structure:
            [
                {"id": "lib_id", "name": "Library Name"},
                ...
            ]
        """
        return await self._get_music_libraries()

    async def get_music_folders(self) -> List[Dict[str, Any]]:
        """Alias for :meth:`get_music_libraries`.

        The shared ``/api/music-folders`` endpoint calls ``get_music_folders()``
        (the Navidrome client exposes that name). Jellyfin exposes the same data
        via ``get_music_libraries()``, so this keeps the interface compatible.
        """
        return await self.get_music_libraries()
    
    async def get_artists(
        self, 
        library_ids: Union[List[str], str, None] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all artists from specified libraries or all libraries.
        
        Args:
            library_ids: Optional library ID(s) to filter artists (string, list of strings, or None)
        
        Returns:
            List of artists: [{"id": "...", "name": "..."}, ...]
        """
        await self._ensure_authenticated()
        
        # Normalize library_ids to a list
        if isinstance(library_ids, str):
            library_ids_list = [library_ids]
        elif isinstance(library_ids, list):
            library_ids_list = library_ids
        else:
            library_ids_list = None
        
        headers = self._get_auth_headers()
        all_artists = []

        # Base params for the dedicated Artists endpoint. The /Artists endpoint
        # is the proper way to list artists; it requires userId when not using
        # an API key, and Recursive ensures nested libraries are included.
        base_params: Dict[str, Any] = {
            "Limit": 5000,
            "Recursive": True,
            "Fields": "ItemCounts",
        }
        if self._user_id:
            base_params["userId"] = self._user_id

        # If specific libraries, query each
        if library_ids_list:
            for lib_id in library_ids_list:
                params = dict(base_params)
                params["parentId"] = lib_id
                response = await self.client.get(
                    f"{self.base_url}/Artists",
                    headers=headers,
                    params=params
                )
                response.raise_for_status()

                for item in response.json().get("Items", []):
                    all_artists.append({
                        "id": item.get("Id"),
                        "name": item.get("Name"),
                        "album_count": item.get("AlbumCount", 0),
                        "song_count": item.get("SongCount", 0)
                    })
        else:
            # Query all libraries
            response = await self.client.get(
                f"{self.base_url}/Artists",
                headers=headers,
                params=base_params
            )
            response.raise_for_status()

            for item in response.json().get("Items", []):
                all_artists.append({
                    "id": item.get("Id"),
                    "name": item.get("Name"),
                    "album_count": item.get("AlbumCount", 0),
                    "song_count": item.get("SongCount", 0)
                })
        
        # Remove duplicates based on artist ID
        unique_artists = []
        seen_ids = set()
        for artist in all_artists:
            if artist['id'] not in seen_ids:
                unique_artists.append(artist)
                seen_ids.add(artist['id'])
        
        return unique_artists
    
    async def get_artists_by_genres(
        self, 
        genres: List[str], 
        library_ids: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch artists that have tracks in specified genres."""
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        all_artists = []

        params: Dict[str, Any] = {
            "IncludeItemTypes": "Audio",
            "Limit": 500,
            "Recursive": True,
        }
        if self._user_id:
            params["userId"] = self._user_id

        # For each genre, find tracks and extract artists
        for genre in genres:
            genre_params = dict(params)
            genre_params["GenreIds"] = genre
            response = await self.client.get(
                f"{self.base_url}/Items",
                headers=headers,
                params=genre_params
            )
            response.raise_for_status()

            for item in response.json().get("Items", []):
                artist_info = item.get("ArtistItems", [{}])[0]
                if artist_info.get("Id"):
                    all_artists.append({
                        "id": artist_info.get("Id"),
                        "name": artist_info.get("Name")
                    })
        
        # Deduplicate
        unique_artists = []
        seen_ids = set()
        for artist in all_artists:
            if artist['id'] not in seen_ids:
                unique_artists.append(artist)
                seen_ids.add(artist['id'])
        
        return unique_artists