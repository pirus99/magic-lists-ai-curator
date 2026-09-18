import os
from typing import List, Dict, Any, Union

import httpx


class _ArtistsMixin:
    async def get_artists(self, library_ids: Union[List[str], str, None] = None) -> List[Dict[str, Any]]:
        """Fetch all artists from Navidrome using Subsonic API

        Args:
            library_ids: Optional library ID(s) to filter artists (string, list of strings, or None)

        Returns:
            List of artists with format: {id, name}
        """
        try:
            await self._ensure_authenticated()

            # Normalize library_ids to a list
            if isinstance(library_ids, str):
                library_ids_list = [library_ids]
            elif isinstance(library_ids, list):
                library_ids_list = library_ids
            else:
                library_ids_list = []

            # If no specific libraries requested, use env var or fetch from all libraries
            if not library_ids_list:
                env_library_id = os.getenv("NAVIDROME_LIBRARY_ID")
                if env_library_id:
                    library_ids_list = [env_library_id]
                else:
                    # Fetch from all libraries
                    library_ids_list = None

            all_artists = []

            if library_ids_list:
                # Fetch from specific libraries
                for lib_id in library_ids_list:
                    print(f"🎵 Fetching artists from library ID: {lib_id}")
                    artists = await self._get_artists_from_library(lib_id)
                    all_artists.extend(artists)
            else:
                # Fetch from all libraries (no filter)
                print("🎵 Fetching artists from all libraries")
                artists = await self._get_artists_from_library(None)
                all_artists.extend(artists)

            # Remove duplicates based on artist ID
            unique_artists = []
            seen_ids = set()
            for artist in all_artists:
                if artist['id'] not in seen_ids:
                    unique_artists.append(artist)
                    seen_ids.add(artist['id'])

            print(f"✅ Retrieved {len(unique_artists)} unique artists from {len(library_ids_list) if library_ids_list else 'all'} libraries")
            return unique_artists

        except Exception as e:
            print(f"❌ Error in get_artists: {e}")
            raise


    async def _get_artists_from_library(self, library_id: Union[str, None]) -> List[Dict[str, Any]]:
        """Fetch artists from a specific library or all libraries"""
        try:
            params = self._get_subsonic_params()

            # Add library filter if specified
            if library_id:
                params["musicFolderId"] = library_id
                print(f"🎵 Using library ID: {library_id}")

            # Log the full request for debugging (minus auth details)
            log_params = {k: v for k, v in params.items() if k not in ['t', 's']}
            print(f"🌐 getArtists request: GET {self.base_url}/rest/getArtists.view with params: {log_params}")

            response = await self.client.get(
                f"{self.base_url}/rest/getArtists.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()
            print(f"📊 getArtists response status: {response.status_code}")

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                error_message = error.get('message', 'Unknown error')
                error_code = error.get('code', 0)

                print(f"❌ Subsonic API error: {error_message} (code: {error_code})")

                # Handle "Library not found" error
                if "Library not found" in error_message or "empty" in error_message.lower():
                    print("⚠️ Library not found error detected - attempting retry without library filter")

                    # Retry without library filter
                    retry_params = self._get_subsonic_params()
                    # Remove any library-specific parameters
                    retry_params.pop("musicFolderId", None)

                    print(f"🔄 Retry getArtists request: GET {self.base_url}/rest/getArtists.view with params: {retry_params}")

                    retry_response = await self.client.get(
                        f"{self.base_url}/rest/getArtists.view",
                        params=retry_params
                    )
                    retry_response.raise_for_status()

                    retry_data = retry_response.json()
                    retry_subsonic = retry_data.get("subsonic-response", {})

                    print(f"📊 Retry getArtists response status: {retry_response.status_code}")

                    if retry_subsonic.get("status") == "ok":
                        print("✅ Retry successful - multiple libraries detected, using all available libraries")
                        data = retry_data
                        subsonic_response = retry_subsonic
                    else:
                        retry_error = retry_subsonic.get("error", {})
                        raise Exception(f"Multiple libraries error: {retry_error.get('message', 'Unknown error')}")
                else:
                    raise Exception(f"Subsonic API error: {error_message}")

            # Ensure we have valid data to process
            if 'data' not in locals():
                raise Exception("No valid response data available")

            artists_data = subsonic_response.get("artists", {})
            artists_list = []

            # Parse the indexed artist structure
            for index_group in artists_data.get("index", []):
                for artist in index_group.get("artist", []):
                    artists_list.append({
                        "id": artist.get("id"),
                        "name": artist.get("name")
                    })

            print(f"✅ Successfully fetched {len(artists_list)} artists from Navidrome")
            return artists_list

        except httpx.RequestError as e:
            print(f"🌐 Network error in getArtists: {e}")
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            print(f"🚨 HTTP error in getArtists: {e.response.status_code} - {e.response.text}")
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            print(f"💥 Unexpected error in getArtists: {e}")
            raise Exception(f"Unexpected error fetching artists: {e}")


    async def get_music_folders(self) -> List[Dict[str, Any]]:
        """Get all available music folders/libraries using Subsonic API

        Returns:
            List of music folders with format: {id, name}
        """
        try:
            await self._ensure_authenticated()

            params = self._get_subsonic_params()

            print(f"🌐 getMusicFolders request: GET {self.base_url}/rest/getMusicFolders.view")

            response = await self.client.get(
                f"{self.base_url}/rest/getMusicFolders.view",
                params=params
            )
            response.raise_for_status()

            data = response.json()

            # Handle Subsonic API response format
            subsonic_response = data.get("subsonic-response", {})
            if subsonic_response.get("status") != "ok":
                error = subsonic_response.get("error", {})
                raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

            music_folders_data = subsonic_response.get("musicFolders", {})
            folders = music_folders_data.get("musicFolder", [])

            # Ensure folders is a list (API might return single object)
            if isinstance(folders, dict):
                folders = [folders]

            result = []
            for folder in folders:
                result.append({
                    "id": str(folder.get("id", "")),
                    "name": folder.get("name", "Unknown Library")
                })

            print(f"📁 Found {len(result)} music folders: {[f['name'] for f in result]}")
            return result

        except Exception as e:
            print(f"💥 Error fetching music folders: {e}")
            raise Exception(f"Failed to fetch music folders: {e}")
    

    async def get_artists_by_genres(self, genres: List[str], library_ids: List[str] = None) -> List[Dict[str, Any]]:
        """Fetch artists that have tracks in the specified genres

        Args:
            genres: List of genre names to filter artists by
            library_ids: Optional list of library IDs to filter tracks

        Returns:
            List of artists with format: {id, name}
        """
        try:
            await self._ensure_authenticated()

            # Fetch tracks for the specified genres
            tracks = await self.get_tracks_by_genres(genres, library_ids)

            # Extract unique artists from tracks
            artists_map = {}
            for track in tracks:
                artist_name = track.get('artist')
                if artist_name and artist_name not in artists_map:
                    # Generate a stable ID from the artist name (since we don't have artist IDs here)
                    artist_id = str(abs(hash(artist_name)) % (10**12))
                    artists_map[artist_name] = {
                        'id': artist_id,
                        'name': artist_name
                    }

            artists_list = list(artists_map.values())
            # Sort by name
            artists_list.sort(key=lambda x: x['name'].lower())

            print(f"✅ Found {len(artists_list)} unique artists across {len(genres)} genres")
            return artists_list

        except Exception as e:
            print(f"❌ Error in get_artists_by_genres: {e}")
            raise



