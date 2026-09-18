import httpx
from typing import List, Dict, Any, Union, Optional


class _TracksMixin:
    async def get_track_by_id(self, track_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single track by its ID using Subsonic API

        Args:
            track_id: The track ID

        Returns:
            Track object with format: {id, title, artist, album, year, play_count}
        """
        try:
            await self._ensure_authenticated()

            params = self._get_subsonic_params()
            params["id"] = track_id

            response = await self.client.get(
                f"{self.base_url}/rest/getSong.view",
                params=params
            )
            response.raise_for_status()

            data = await response.json()

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            song_data = subsonic_response.get("song", {})
            if not song_data:
                print(f"⚠️ No song found for ID: {track_id}")
                return None

            track = {
                "id": song_data.get("id"),
                "title": song_data.get("title"),
                "artist": song_data.get("artist"),
                "album": song_data.get("album"),
                "year": song_data.get("year"),
                "play_count": song_data.get("playCount", 0),
                "starred": song_data.get("starred") is not None,
                "rating": song_data.get("userRating", 0),
                "format": song_data.get("suffix"),
                "bit_rate": song_data.get("bitRate", 0),
                "bit_depth": song_data.get("bitDepth"),
                "duration": song_data.get("duration"),
                "track_number": song_data.get("track")
            }

            print(f"✅ Fetched track: {track['title']} by {track['artist']}")
            return track

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching track by ID {track_id}: {e}")


    async def get_tracks_by_artist(self, artist_id: str, library_ids: Union[List[str], None] = None) -> List[Dict[str, Any]]:
        """Fetch tracks for a specific artist using Subsonic API

        Args:
            artist_id: The artist ID
            library_ids: Optional list of library IDs to filter tracks

        Returns:
            List of tracks with format: {id, title, album, year, play_count}
        """
        try:
            await self._ensure_authenticated()

            params = self._get_subsonic_params()
            params["id"] = artist_id

            # Add library filter if specified (use first library if multiple provided)
            if library_ids and len(library_ids) > 0:
                params["musicFolderId"] = library_ids[0]
        
            response = await self.client.get(
                f"{self.base_url}/rest/getArtist.view",
                params=params
            )
            response.raise_for_status()
        
            data = response.json()
        
            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")
        
            artist_data = subsonic_response.get("artist", {})
            tracks_list = []
        
            # Get artist name for track metadata
            artist_name = artist_data.get("name", "Unknown Artist")
        
            # Get tracks from albums
            for album in artist_data.get("album", []):
                album_id = album.get("id")
                album_name = album.get("name", "")
                album_year = album.get("year", 0)
            
                # Get songs from each album
                album_params = self._get_subsonic_params()
                album_params["id"] = album_id
            
                album_response = await self.client.get(
                    f"{self.base_url}/rest/getAlbum.view",
                    params=album_params
                )
                album_response.raise_for_status()
                album_data = album_response.json()
            
                album_subsonic = album_data.get("subsonic-response", {})
                if album_subsonic.get("status") == "ok":
                    album_info = album_subsonic.get("album", {})
                    for song in album_info.get("song", []):
                        tracks_list.append({
                            "id": song.get("id"),
                            "title": song.get("title"),
                            "artist": artist_name,  # Include artist name for AI processing
                            "album": album_name,
                            "year": album_year,
                            "play_count": song.get("playCount", 0),
                            "starred": song.get("starred") is not None,
                            "rating": song.get("userRating", 0),
                            "format": song.get("suffix"),
                            "bit_rate": song.get("bitRate", 0),
                            "bit_depth": song.get("bitDepth")
                        })
        
            return self._deduplicate_tracks(tracks_list)
            
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching tracks for artist {artist_id}: {e}")


    async def get_tracks_by_genres(self, genres: List[str], library_ids: List[str] = None) -> List[Dict[str, Any]]:
        """Fetch tracks for multiple genres using Subsonic getSongsByGenre API with pagination

        Args:
            genres: List of genre names
            library_ids: Optional list of library IDs to filter tracks

        Returns:
            List of tracks with format: {id, title, album, year, play_count}
        """
        try:
            await self._ensure_authenticated()

            all_tracks = []
            total_fetched = 0
            offset = 0
            batch_size = 500  # Max allowed by API

            library_filter = library_ids[0] if library_ids and len(library_ids) > 0 else None
            print(f"🎵 Starting multi-genre track collection for {len(genres)} genres{' in library ' + library_filter if library_filter else ''}")

            for genre in genres:
                offset = 0
                while True:
                    params = self._get_subsonic_params()
                    params["genre"] = genre
                    params["count"] = batch_size
                    params["offset"] = offset

                    # Add library filter if specified (use first library if multiple provided)
                    if library_ids and len(library_ids) > 0:
                        params["musicFolderId"] = library_ids[0]

                    response = await self.client.get(
                        f"{self.base_url}/rest/getSongsByGenre.view",
                        params=params
                    )
                    response.raise_for_status()

                    data = response.json()

                    # Handle Subsonic API response format
                    subsonic_response = data.get("subsonic-response", {})
                    if subsonic_response.get("status") != "ok":
                        error = subsonic_response.get("error", {})
                        error_msg = error.get('message', 'Unknown error')
                        error_code = error.get('code', 0)

                        # If getSongsByGenre is not supported, fall back to search approach
                        if "not implemented" in error_msg.lower() or error_code == 0:
                            print(f"⚠️ getSongsByGenre not supported, falling back to search method")
                            genre_tracks = await self._get_tracks_by_genre_fallback(genre)
                            all_tracks.extend(genre_tracks)
                            break
                        else:
                            raise Exception(f"Subsonic API error: {error_msg}")

                    songs_by_genre = subsonic_response.get("songsByGenre", {})
                    songs = songs_by_genre.get("song", [])

                    # If no songs returned, we've reached the end
                    if not songs:
                        break

                    # Convert songs to our track format
                    for song in songs:
                        track = {
                            "id": song.get("id"),
                            "title": song.get("title"),
                            "artist": song.get("artist"),
                            "album": song.get("album"),
                            "year": song.get("year"),
                            "genre": song.get("genre"),
                            "play_count": song.get("playCount", 0),
                            "starred": song.get("starred") is not None,
                            "rating": song.get("userRating", 0),
                            "format": song.get("suffix"),
                            "bit_rate": song.get("bitRate", 0),
                            "bit_depth": song.get("bitDepth"),
                            "duration": song.get("duration"),
                            "track_number": song.get("track")
                        }
                        all_tracks.append(track)

                    batch_count = len(songs)
                    total_fetched += batch_count
                    offset += batch_size

                    print(f"📦 Fetched batch for genre '{genre}': {batch_count} tracks (total: {total_fetched})")

                    # Safety check: prevent infinite loops
                    if batch_count < batch_size:
                        break

                    # Safety check: prevent too many API calls (max 100 batches = 50k tracks)
                    if offset >= 50000:
                        print(f"⚠️ Reached safety limit of 50k tracks for genre '{genre}'")
                        break

            deduped = self._deduplicate_tracks(all_tracks)
            print(f"✅ Completed multi-genre collection: {len(deduped)} tracks for {len(genres)} genres")
            return deduped

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching tracks for genres {genres}: {e}")


    async def get_tracks_by_genre(self, genre: str, library_ids: List[str] = None) -> List[Dict[str, Any]]:
        """Fetch tracks for a specific genre using Subsonic getSongsByGenre API with pagination

        Args:
            genre: The genre name
            library_ids: Optional list of library IDs to filter tracks

        Returns:
            List of tracks with format: {id, title, album, year, play_count}
        """
        try:
            await self._ensure_authenticated()

            all_tracks = []
            total_fetched = 0
            offset = 0
            batch_size = 500  # Max allowed by API

            library_filter = library_ids[0] if library_ids and len(library_ids) > 0 else None
            print(f"🎵 Starting genre track collection for '{genre}'{' in library ' + library_filter if library_filter else ''}")

            while True:
                params = self._get_subsonic_params()
                params["genre"] = genre
                params["count"] = batch_size
                params["offset"] = offset

                # Add library filter if specified (use first library if multiple provided)
                if library_ids and len(library_ids) > 0:
                    params["musicFolderId"] = library_ids[0]

                response = await self.client.get(
                    f"{self.base_url}/rest/getSongsByGenre.view",
                    params=params
                )
                response.raise_for_status()

                data = response.json()

                # Handle Subsonic API response format
                subsonic_response = data.get("subsonic-response", {})
                if subsonic_response.get("status") != "ok":
                    error = subsonic_response.get("error", {})
                    error_msg = error.get('message', 'Unknown error')
                    error_code = error.get('code', 0)

                    # If getSongsByGenre is not supported, fall back to search approach
                    if "not implemented" in error_msg.lower() or error_code == 0:
                        print(f"⚠️ getSongsByGenre not supported, falling back to search method")
                        return await self._get_tracks_by_genre_fallback(genre)
                    else:
                        raise Exception(f"Subsonic API error: {error_msg}")

                songs_by_genre = subsonic_response.get("songsByGenre", {})
                songs = songs_by_genre.get("song", [])

                # If no songs returned, we've reached the end
                if not songs:
                    break

                # Convert songs to our track format
                for song in songs:
                    track = {
                        "id": song.get("id"),
                        "title": song.get("title"),
                        "artist": song.get("artist"),
                        "album": song.get("album"),
                        "year": song.get("year"),
                        "genre": song.get("genre"),
                        "play_count": song.get("playCount", 0),
                        "starred": song.get("starred") is not None,
                        "rating": song.get("userRating", 0),
                        "format": song.get("suffix"),
                        "bit_rate": song.get("bitRate", 0),
                        "bit_depth": song.get("bitDepth"),
                        "duration": song.get("duration"),
                        "track_number": song.get("track")
                    }
                    all_tracks.append(track)

                batch_count = len(songs)
                total_fetched += batch_count
                offset += batch_size

                print(f"📦 Fetched batch: {batch_count} tracks (total: {total_fetched})")

                # Safety check: prevent infinite loops
                if batch_count < batch_size:
                    break

                # Safety check: prevent too many API calls (max 100 batches = 50k tracks)
                if offset >= 50000:
                    print(f"⚠️ Reached safety limit of 50k tracks for genre '{genre}'")
                    break

            deduped = self._deduplicate_tracks(all_tracks)
            print(f"✅ Completed genre collection: {len(deduped)} tracks for '{genre}'")
            return deduped

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching tracks for genre {genre}: {e}")


    async def _get_tracks_by_genre_fallback(self, genre: str) -> List[Dict[str, Any]]:
        """Fallback method using search3 when getSongsByGenre is not available

        Args:
            genre: The genre name

        Returns:
            List of tracks with format: {id, title, album, year, play_count}
        """
        print(f"🔄 Using fallback search method for genre '{genre}'")

        try:
            await self._ensure_authenticated()

            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query to get all tracks
            params["artistCount"] = 0
            params["albumCount"] = 0
            params["songCount"] = 5000  # Get large sample to find genre tracks

            response = await self.client.get(
                f"{self.base_url}/rest/search3.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            search_result = subsonic_response.get("searchResult3", {})
            songs = search_result.get("song", [])

            tracks_list = []
            for song in songs:
                # Filter songs that match the genre exactly
                if song.get("genre") == genre:
                    track = {
                        "id": song.get("id"),
                        "title": song.get("title"),
                        "artist": song.get("artist"),
                        "album": song.get("album"),
                        "year": song.get("year"),
                        "genre": song.get("genre"),
                        "play_count": song.get("playCount", 0),
                        "starred": song.get("starred") is not None,
                        "rating": song.get("userRating", 0),
                        "format": song.get("suffix"),
                        "bit_rate": song.get("bitRate", 0),
                        "bit_depth": song.get("bitDepth"),
                        "duration": song.get("duration"),
                        "track_number": song.get("track")
                    }
                    tracks_list.append(track)

            deduped = self._deduplicate_tracks(tracks_list)
            print(f"✅ Fallback method found {len(deduped)} tracks for '{genre}'")
            return deduped

        except Exception as e:
            print(f"❌ Fallback method also failed: {e}")
            return []


    async def get_starred(self, library_ids: Union[List[str], str, None] = None) -> List[Dict[str, Any]]:
        """Fetch starred tracks from Navidrome using getStarred API

        Args:
            library_ids: Optional library ID(s) to filter starred tracks

        Returns:
            List of starred track metadata
        """
        try:
            await self._ensure_authenticated()

            # Normalize library_ids to a single string for musicFolderId parameter
            library_id = None
            if isinstance(library_ids, list) and library_ids:
                library_id = library_ids[0]  # Use first library ID
            elif isinstance(library_ids, str):
                library_id = library_ids

            params = self._get_subsonic_params()
            if library_id:
                params["musicFolderId"] = library_id

            response = await self.client.get(
                f"{self.base_url}/rest/getStarred.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            starred_data = subsonic_response.get("starred", {})
            songs = starred_data.get("song", [])

            # Convert to consistent format
            tracks = []
            for song in songs:
                tracks.append({
                    "id": song.get("id"),
                    "title": song.get("title"),
                    "artist": song.get("artist"),
                    "album": song.get("album"),
                    "genre": song.get("genre"),
                    "year": song.get("year"),
                    "duration": song.get("duration"),
                    "play_count": song.get("playCount", 0),
                    "played": song.get("played"),
                    "starred": song.get("starred") is not None,
                    "rating": song.get("userRating", 0),
                    "format": song.get("suffix"),
                    "bit_rate": song.get("bitRate", 0),
                    "bit_depth": song.get("bitDepth"),
                    "genres": song.get("genres", []),
                    "path": song.get("path")
                })

            deduped = self._deduplicate_tracks(tracks)
            print(f"⭐ Retrieved {len(deduped)} starred tracks")
            return deduped

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching starred tracks: {e}")


    async def get_genre_stats(self) -> List[Dict[str, Any]]:
        """Get genre statistics with track counts

        Returns:
            List of dicts with genre name and track count, sorted by count descending
        """
        try:
            await self._ensure_authenticated()

            # Get a larger sample of tracks to count genres
            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query to get all
            params["artistCount"] = 0
            params["albumCount"] = 0
            params["songCount"] = 5000  # Get large sample for genre stats

            response = await self.client.get(
                f"{self.base_url}/rest/search3.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            search_result = subsonic_response.get("searchResult3", {})
            songs = search_result.get("song", [])

            # Count tracks per genre
            genre_counts = {}
            for song in songs:
                genre = song.get("genre")
                if genre:
                    genre_counts[genre] = genre_counts.get(genre, 0) + 1

            # Convert to list of dicts, sorted by count descending
            genre_stats = [
                {"genre": genre, "track_count": count}
                for genre, count in genre_counts.items()
            ]
            genre_stats.sort(key=lambda x: x["track_count"], reverse=True)

            return genre_stats

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching genre stats: {e}")


    async def get_total_song_count(self) -> int:
        """Get the total number of songs in the library using startScan API
    
        Returns:
            int: Total number of songs in the library
        """
        try:
            await self._ensure_authenticated()
        
            # Use startScan API to get accurate song count
            params = self._get_subsonic_params()
        
            response = await self.client.get(
                f"{self.base_url}/rest/startScan.view",
                params=params
            )
            response.raise_for_status()
        
            data = response.json()
        
            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")
        
            scan_status = subsonic_response.get("scanStatus", {})
            count = scan_status.get("count", 0)
        
            print(f"📊 Total song count in library (via startScan): {count}")
            return count
            
        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error getting song count: {e}")
    

    async def get_library_stats(self) -> dict:
        """
        Calculate statistics needed for track scoring normalization.

        Returns:
            dict: Library statistics including max_play_count and max_playlist_appearances
        """
        try:
            await self._ensure_authenticated()

            # Try to get total song count from scan status
            total_tracks = await self.get_total_song_count()

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
    


