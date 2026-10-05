from typing import List, Dict, Any, Union, Optional
from .utils import _get_quality_score
from ..services.lastfm_service import (
    artists_match,
    normalize_artist,
    resolve_top_tracks,
)


class _TracksMixin:
    """Methods for fetching tracks from Jellyfin."""
    
    async def get_library_stats(self) -> dict:
        """
        Calculate statistics needed for track scoring normalization.

        Returns:
            dict: Library statistics including max_play_count and max_playlist_appearances
        """
        try:
            await self._ensure_authenticated()
            
            headers = self._get_auth_headers()
            
            # Ask Jellyfin for a single item so the response still includes
            # TotalRecordCount without downloading the whole library.
            response = await self.client.get(
                f"{self.base_url}/Items",
                headers=headers,
                params=self._items_params(
                    IncludeItemTypes="Audio",
                    Limit=1
                )
            )
            response.raise_for_status()
            total_tracks = response.json().get("TotalRecordCount", 0)
            
            # For max_play_count, we'll estimate based on total tracks
            # Assuming most popular tracks might have 10-20% of total plays
            # This is a rough estimate since we can't get actual max play count easily
            estimated_max_plays = max(100, int(total_tracks * 0.1))
            
            stats = {
                'max_play_count': estimated_max_plays,
                'max_playlist_appearances': 10,  # Default reasonable max
                'total_tracks': total_tracks
            }
            
            print(f"📊 Calculated library stats: {stats}")
            return stats
            
        except Exception as e:
            print(f"⚠️ Error getting library stats, using defaults: {e}")
            # Return safe defaults if we can't get stats
            return {
                'max_play_count': 100,
                'max_playlist_appearances': 10,
                'total_tracks': 0
            }
    
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

    async def find_artist_by_name(
        self,
        artist_name: str,
        library_ids: Union[List[str], str, None] = None,
    ) -> Optional[Dict[str, Any]]:
        """Look up a library artist by (fuzzy) name.

        Jellyfin's Subsonic-compatible API is not used here because it has no
        top-songs endpoint; this helper exists so top-track resolution can turn the
        artist *name* used by Last.fm back into a Jellyfin artist id.

        Returns:
            The matching artist dict ({id, name, mbid, ...}), or None if not found.
        """
        if not artist_name:
            return None

        artists = await self.get_artists(library_ids) or []
        target = normalize_artist(artist_name)
        if not target:
            return None

        for artist in artists:
            if normalize_artist(artist.get("name")) == target:
                return artist

        # Fall back to a case-insensitive substring match for partial user input.
        for artist in artists:
            name = normalize_artist(artist.get("name"))
            if name and (target in name or name in target):
                return artist

        return None

    async def get_top_songs_by_artist(
        self,
        artist_name: str,
        count: int,
        library_ids: Union[List[str], None] = None,
        artist_mbid: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Fetch an artist's most popular songs, resolved via Last.fm.

        Jellyfin exposes no equivalent of Subsonic's ``getTopSongs``. Last.fm's
        ``artist.getTopTracks`` is used instead, and each returned title is matched
        against the artist's local tracks so results carry real Jellyfin item ids.

        Args:
            artist_name: Artist name used to locate the library artist.
            count: Max number of top tracks to return.
            library_ids: Optional library scope.
            artist_mbid: MBID override for the Last.fm request. Takes precedence over
                the library's own MBID, which is often missing from Jellyfin metadata.

        Degrades gracefully to an empty list when Last.fm is unconfigured, the
        artist is unknown, or the API is unreachable.
        """
        if count <= 0 or not artist_name:
            return []

        artist = await self.find_artist_by_name(artist_name, library_ids)
        if not artist:
            print(f"⚠️ Jellyfin top tracks skipped: no library artist matching '{artist_name}'")
            return []

        local_tracks = await self.get_tracks_by_artist(artist["id"], library_ids) or []
        if not local_tracks:
            print(f"⚠️ Jellyfin top tracks skipped: '{artist['name']}' has no local tracks")
            return []

        # A user-supplied MBID wins; otherwise fall back to the library's, if any.
        effective_mbid = artist_mbid or artist.get("mbid")
        top_tracks = await resolve_top_tracks(
            artist.get("name") or artist_name,
            local_tracks,
            artist_mbid=effective_mbid,
            limit=count,
        )

        # resolve_top_tracks already stamps is_top_track; keep the guarantee local so
        # this method honours its contract regardless of the resolver's internals.
        for track in top_tracks:
            track["is_top_track"] = True

        resolved_name = top_tracks[0].get("artist") if top_tracks else None
        if resolved_name and not artists_match(resolved_name, artist.get("name")):
            print(f"⚠️ Last.fm returned tracks by '{resolved_name}' for '{artist['name']}'")

        return top_tracks[:count]
    
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
        """Fetch recently played tracks (Jellyfin alternative to smart playlists)."""
        await self._ensure_authenticated()
        
        headers = self._get_auth_headers()
        all_tracks = []
        target_count = min(limit, 2000)
        start_index = 0
        page_size = min(500, target_count)
        
        while len(all_tracks) < target_count:
            response = await self.client.get(
                f"{self.base_url}/Items",
                headers=headers,
                params=self._items_params(
                    IncludeItemTypes="Audio",
                    ParentId=library_ids[0] if library_ids else None,
                    SortBy="DateLastPlayed",
                    SortOrder="Descending",
                    StartIndex=start_index,
                    Limit=page_size,
                    Fields="Genres,Path,DateLastPlayed,UserData"
                )
            )
            response.raise_for_status()
            data = response.json()
            items = data.get("Items", [])
            if not items:
                break
            
            for track in items:
                normalized = self._normalize_track(track)
                normalized["played"] = track.get("DateLastPlayed")
                all_tracks.append(normalized)
            
            start_index += len(items)
            if len(items) < page_size:
                break
        
        return all_tracks[:target_count]
    
    async def get_tracks_by_year_range(
        self,
        start_year: int,
        end_year: int,
        library_ids: Union[List[str], None] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Fetch tracks whose production year is within an inclusive range."""
        await self._ensure_authenticated()
        
        response = await self.client.get(
            f"{self.base_url}/Items",
            headers=self._get_auth_headers(),
            params=self._items_params(
                IncludeItemTypes="Audio",
                ParentId=library_ids[0] if library_ids else None,
                Years=list(range(start_year, end_year + 1)),
                Limit=min(limit, 500),
                Fields="Genres,DateLastPlayed,UserData",
            )
        )
        response.raise_for_status()
        tracks = []
        for track in response.json().get("Items", []):
            normalized = self._normalize_track(track)
            normalized["played"] = track.get("DateLastPlayed")
            tracks.append(normalized)
        return tracks
    
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

        # Jellyfin returns Artists as a list of strings (e.g. ["Artist Name"]),
        # unlike Emby which uses a list of dicts. Handle both shapes.
        raw_artists = jellyfin_track.get("Artists") or []
        if raw_artists and isinstance(raw_artists[0], dict):
            artist_name = raw_artists[0].get("Name", "")
        else:
            artist_name = raw_artists[0] if raw_artists else ""

        return {
            "id": jellyfin_track.get("Id"),
            "title": jellyfin_track.get("Name"),
            "artist": artist_name or jellyfin_track.get("ArtistName", ""),
            "album": jellyfin_track.get("Album", ""),
            "year": jellyfin_track.get("ProductionYear", 0),
            "genres": genres,
            "played": jellyfin_track.get("DateLastPlayed"),
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