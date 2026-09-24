from typing import List, Dict, Any, Union
from .utils import _get_quality_score


class _TracksMixin:
    """Methods for fetching tracks from Jellyfin."""
    
    async def get_tracks_by_artist(
        self, 
        artist_id: str, 
        library_ids: Union[List[str], None] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all tracks by a specific artist."""
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        all_tracks = []
        
        # Get artist's albums
        albums_response = await self.client.get(
            f"{self.base_url}/Items",
            headers=headers,
            params=self._items_params(
                ArtistIds=artist_id,
                IncludeItemTypes="MusicAlbum",
                Limit=500
            )
        )
        albums_response.raise_for_status()
        
        # Get tracks from each album
        for album in albums_response.json().get("Items", []):
            tracks_response = await self.client.get(
                f"{self.base_url}/Items",
                headers=headers,
                params=self._items_params(
                    ParentId=album.get("Id"),
                    IncludeItemTypes="Audio",
                    Limit=500
                )
            )
            tracks_response.raise_for_status()
            
            for track in tracks_response.json().get("Items", []):
                all_tracks.append(self._normalize_track(track))
        
        return self._deduplicate_tracks(all_tracks)
    
    async def get_tracks_by_genres(
        self, 
        genres: List[str], 
        library_ids: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch all tracks in specified genres."""
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        all_tracks = []
        
        for genre in genres:
            response = await self.client.get(
                f"{self.base_url}/Items",
                headers=headers,
                params=self._items_params(
                    IncludeItemTypes="Audio",
                    GenreIds=genre,
                    Limit=500
                )
            )
            response.raise_for_status()
            
            for track in response.json().get("Items", []):
                all_tracks.append(self._normalize_track(track))
        
        return self._deduplicate_tracks(all_tracks)
    
    async def get_tracks_by_genre(
        self, 
        genre: str, 
        library_ids: List[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch tracks in single genre."""
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        all_tracks = []
        
        response = await self.client.get(
            f"{self.base_url}/Items",
            headers=headers,
            params=self._items_params(
                IncludeItemTypes="Audio",
                GenreIds=genre,
                Limit=500
            )
        )
        response.raise_for_status()
        
        for track in response.json().get("Items", []):
            all_tracks.append(self._normalize_track(track))
        
        return self._deduplicate_tracks(all_tracks)
    
    async def get_recent_tracks(
        self, 
        limit: int = 500, 
        library_ids: Union[List[str], None] = None,
        days_back: int = None
    ) -> List[Dict[str, Any]]:
        """Fetch recently played tracks (Jellyfin alternative to smart playlists).
        
        Args:
            limit: Maximum tracks to return (max 500)
            library_ids: Optional library IDs to filter by
            days_back: Optional filter by days back (not implemented yet)
        
        Returns:
            List of tracks sorted by DateLastPlayed descending
        """
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        all_tracks = []
        
        # Get all audio tracks sorted by last played
        response = await self.client.get(
            f"{self.base_url}/Items",
            headers=headers,
            params=self._items_params(
                IncludeItemTypes="Audio",
                SortBy="DateLastPlayed",
                SortOrder="Descending",
                Limit=min(limit, 500),
                Fields="ItemCounts,Path"
            )
        )
        response.raise_for_status()
        
        for track in response.json().get("Items", []):
            all_tracks.append(self._normalize_track(track))
        
        return all_tracks
    
    async def get_starred(
        self, 
        library_ids: Union[List[str], str, None] = None
    ) -> List[Dict[str, Any]]:
        """Fetch favorite/liked tracks."""
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        all_tracks = []
        
        if library_ids:
            for lib_id in library_ids:
                response = await self.client.get(
                    f"{self.base_url}/Items",
                    headers=headers,
                    params=self._items_params(
                        IncludeItemTypes="Audio",
                        ParentId=lib_id,
                        Fields="ItemCounts"
                    )
                )
                response.raise_for_status()
                
                for item in response.json().get("Items", []):
                    if item.get("UserData", {}).get("IsFavorite", False):
                        all_tracks.append(self._normalize_track(item))
        else:
            response = await self.client.get(
                f"{self.base_url}/Items",
                headers=headers,
                params=self._items_params(
                    IncludeItemTypes="Audio",
                    Fields="ItemCounts"
                )
            )
            response.raise_for_status()
            
            for item in response.json().get("Items", []):
                if item.get("UserData", {}).get("IsFavorite", False):
                    all_tracks.append(self._normalize_track(item))
        
        return self._deduplicate_tracks(all_tracks)
    
    def _normalize_track(self, jellyfin_track: Dict) -> Dict[str, Any]:
        """Convert Jellyfin track format to standard format."""
        # Extract genres from Jellyfin format
        genres = []
        if "Genres" in jellyfin_track:
            genres = jellyfin_track["Genres"]
        elif "GenreIds" in jellyfin_track:
            # Might need separate API call to get genre names
            genres = []
        
        return {
            "id": jellyfin_track.get("Id"),
            "title": jellyfin_track.get("Name"),
            "artist": jellyfin_track.get("Artists", [{}])[0].get("Name") or jellyfin_track.get("ArtistName", ""),
            "album": jellyfin_track.get("Album", ""),
            "year": jellyfin_track.get("ProductionYear", 0),
            "genres": genres,
            "play_count": jellyfin_track.get("UserData", {}).get("PlayCount", 0),
            "starred": jellyfin_track.get("UserData", {}).get("IsFavorite", False),
            "rating": jellyfin_track.get("CommunityRating", 0) * 10,  # Convert 0-10 to 0-100
            "format": jellyfin_track.get("Container", ""),
            "bit_rate": jellyfin_track.get("Bitrate", 0) // 1000,  # Convert to kbps
            "duration": jellyfin_track.get("RunTimeTicks", 0) // 10_000_000,  # Convert ticks to seconds
            "track_number": jellyfin_track.get("IndexNumber", 0)
        }
    
    def _deduplicate_tracks(self, tracks: List[Dict]) -> List[Dict]:
        """Remove duplicate tracks by ID."""
        seen: Dict[str, Dict[str, Any]] = {}
        
        for track in tracks:
            tid = track.get("id")
            if tid is None:
                continue
                
            if tid not in seen:
                seen[tid] = track
            else:
                # Update if new track has better quality
                existing = seen[tid]
                new_loved = bool(track.get("starred"))
                old_loved = bool(existing.get("starred"))
                if new_loved and not old_loved:
                    seen[tid] = track
                    continue
                if old_loved and not new_loved:
                    continue
                    
                new_plays = track.get("play_count", 0)
                old_plays = existing.get("play_count", 0)
                if new_plays > old_plays:
                    seen[tid] = track
                    continue
                    
                new_rating = track.get("rating", 0)
                old_rating = existing.get("rating", 0)
                if new_rating > old_rating:
                    seen[tid] = track
                    continue
                    
                if _get_quality_score(track) > _get_quality_score(existing):
                    seen[tid] = track
        
        result = list(seen.values())
        duplicates_removed = len(tracks) - len(result)
        if duplicates_removed > 0:
            print(f"🔍 Deduplication: removed {duplicates_removed} duplicate track(s) from {len(tracks)} → {len(result)} unique tracks")
        return result