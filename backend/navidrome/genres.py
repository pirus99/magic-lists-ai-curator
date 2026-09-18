import httpx
import os
from typing import List, Dict, Any, Union, Optional


class _GenresMixin:
    async def get_genres(self, library_ids: Union[List[str], str, None] = None) -> List[Dict[str, Any]]:
        """Fetch all available genres from Navidrome with track counts

        Args:
            library_ids: Optional library ID(s) to filter genres (string, list of strings, or None)

        Returns:
            List of genre objects with name and songCount
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

            all_genres = {}

            if library_ids_list:
                # Fetch from specific libraries
                for lib_id in library_ids_list:
                    print(f"🎵 Fetching genres from library ID: {lib_id}")
                    genres = await self._get_genres_from_library(lib_id)
                    for genre in genres:
                        name = genre["name"]
                        count = genre["songCount"]
                        if name in all_genres:
                            all_genres[name] += count
                        else:
                            all_genres[name] = count
            else:
                # Fetch from all libraries (no filter)
                print("🎵 Fetching genres from all libraries")
                genres = await self._get_genres_from_library(None)
                for genre in genres:
                    name = genre["name"]
                    count = genre["songCount"]
                    all_genres[name] = count

            # Convert to list of genre objects
            genre_list = [{"name": name, "songCount": count} for name, count in all_genres.items()]

            print(f"✅ Retrieved {len(genre_list)} unique genres from {len(library_ids_list) if library_ids_list else 'all'} libraries")
            return sorted(genre_list, key=lambda x: x["name"])

        except Exception as e:
            print(f"❌ Error in get_genres: {e}")
            raise


    async def _get_genres_from_library(self, library_id: Union[str, None]) -> List[Dict[str, Any]]:
        """Fetch genres from a specific library or all libraries"""
        try:
            # First try the OpenSubsonic getGenres endpoint (returns ALL genres)
            try:
                params = self._get_subsonic_params()

                # Add library filter if specified (musicFolderId parameter)
                if library_id:
                    params["musicFolderId"] = library_id

                response = await self.client.get(
                    f"{self.base_url}/rest/getGenres.view",
                    params=params
                )
                response.raise_for_status()

                data = response.json()

                # Handle Subsonic API response format
                subsonic_response = data.get("subsonic-response", {})
                if subsonic_response.get("status") != "ok":
                    error = subsonic_response.get("error", {})
                    raise Exception(f"Subsonic API error: {error.get('message', 'Unknown error')}")

                genres_data = subsonic_response.get("genres", {})
                genre_list = genres_data.get("genre", [])

                # Extract genre objects with counts from the structured response
                genres = []
                for genre_item in genre_list:
                    genre_name = genre_item.get("value")
                    song_count = genre_item.get("songCount", 0)
                    if genre_name:
                        genres.append({
                            "name": genre_name,
                            "songCount": song_count
                        })

                if genres:
                    print(f"✅ Retrieved {len(genres)} genres using getGenres endpoint")
                    return genres

            except Exception as e:
                print(f"⚠️ getGenres endpoint failed ({e}), falling back to search-based method")

            # Fallback: Use search-based method with larger sample
            params = self._get_subsonic_params()
            params["query"] = ""  # Empty query to get all
            params["artistCount"] = "0"
            params["albumCount"] = "0"
            params["songCount"] = "10000"  # Increased sample size for better coverage

            # Add library filter if specified
            if library_id:
                params["musicFolderId"] = library_id

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

            # Extract unique genres with improved parsing and counts
            genre_counts = {}
            for song in songs:
                genre = song.get("genre")
                if genre:
                    # Parse multiple genres separated by common delimiters
                    parsed_genres = self._parse_genre_string(genre)
                    for parsed_genre in parsed_genres:
                        genre_counts[parsed_genre] = genre_counts.get(parsed_genre, 0) + 1

            # Convert to list of genre objects
            genres = [{"name": name, "songCount": count} for name, count in genre_counts.items()]

            print(f"📊 Retrieved {len(genres)} genres using search fallback method (sampled {len(songs)} tracks)")
            return genres

        except httpx.RequestError as e:
            raise Exception(f"Network error connecting to Navidrome: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error from Navidrome: {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Unexpected error fetching genres: {e}")


