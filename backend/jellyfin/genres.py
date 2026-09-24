from typing import List, Dict, Any, Union


class _GenresMixin:
    """Methods for fetching genres from Jellyfin."""
    
    async def get_genres(self, library_ids: Union[List[str], str, None] = None) -> List[Dict[str, Any]]:
        """Extract unique genres from all tracks in libraries.
        
        Returns:
            [
                {"name": "Rock", "songCount": 1250},
                {"name": "Jazz", "songCount": 450},
                ...
            ]
        """
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        
        # Normalize library_ids
        if isinstance(library_ids, str):
            library_ids_list = [library_ids]
        elif isinstance(library_ids, list):
            library_ids_list = library_ids
        else:
            library_ids_list = None
        
        # Get all tracks to extract genres
        all_tracks = []
        
        if library_ids_list:
            # Get tracks from specific libraries
            for lib_id in library_ids_list:
                response = await self.client.get(
                    f"{self.base_url}/Items",
                    headers=headers,
                    params=self._items_params(
                        ParentId=lib_id,
                        IncludeItemTypes="Audio",
                        Limit=5000,
                        Fields="Genres"
                    )
                )
                response.raise_for_status()
                
                for track in response.json().get("Items", []):
                    all_tracks.append(track)
        else:
            # Get tracks from all libraries
            response = await self.client.get(
                f"{self.base_url}/Items",
                headers=headers,
                params=self._items_params(
                    IncludeItemTypes="Audio",
                    Limit=5000,
                    Fields="Genres"
                )
            )
            response.raise_for_status()
            
            for track in response.json().get("Items", []):
                all_tracks.append(track)
        
        # Extract and count genres
        genre_counts = {}
        for track in all_tracks:
            genres = track.get("Genres", [])
            for genre in genres:
                genre_name = genre.strip()
                if genre_name:
                    genre_counts[genre_name] = genre_counts.get(genre_name, 0) + 1
        
        # Convert to list format
        genre_list = [{"name": name, "songCount": count} for name, count in genre_counts.items()]
        
        # Sort by name
        return sorted(genre_list, key=lambda x: x["name"])