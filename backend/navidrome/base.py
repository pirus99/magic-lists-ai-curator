import os
from typing import List, Dict, Any, Union, Optional

import httpx


class _NavidromeBase:
    def __init__(self):
        self.base_url = os.getenv("NAVIDROME_URL")
        if not self.base_url:
            raise ValueError("NAVIDROME_URL environment variable is required")
        self.api_key = os.getenv("NAVIDROME_API_KEY")
        self.username = os.getenv("NAVIDROME_USERNAME")
        self.password = os.getenv("NAVIDROME_PASSWORD")
        self.client = httpx.AsyncClient()
        self._auth_token = None
        self._subsonic_token = None
        self._subsonic_salt = None
    

    async def _ensure_authenticated(self):
        """Ensure we have valid authentication credentials"""
        if self.api_key:
            # Use provided static API key (future feature)
            self._auth_token = self.api_key
        elif self.username and self.password and not self._subsonic_token:
            # Login with username/password to get Subsonic credentials
            try:
                response = await self.client.post(
                    f"{self.base_url}/auth/login",
                    json={"username": self.username, "password": self.password}
                )
                response.raise_for_status()
                data = response.json()
            
                # Store both JWT token and Subsonic credentials
                self._auth_token = data.get("token")
                self._subsonic_token = data.get("subsonicToken")
                self._subsonic_salt = data.get("subsonicSalt")
            
                if not self._subsonic_token or not self._subsonic_salt:
                    raise Exception("No Subsonic credentials received from login response")
                
            except httpx.RequestError as e:
                raise Exception(f"Network error during login: {e}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    raise Exception("Invalid username or password")
                elif e.response.status_code == 403:
                    raise Exception("Access forbidden - check your credentials")
                else:
                    raise Exception(f"Login failed with status {e.response.status_code}: {e.response.text}")
            except Exception as e:
                raise Exception(f"Unexpected error during login: {e}")
        elif not self.username or not self.password:
            raise Exception("No authentication method available (need NAVIDROME_API_KEY or NAVIDROME_USERNAME/PASSWORD)")
    

    def _get_subsonic_params(self) -> Dict[str, Any]:
        """Get Subsonic API parameters"""
        if self.api_key:
            # Future: use API key authentication if available
            return {
                "u": self.username,
                "t": self.api_key,
                "v": "1.16.1",
                "c": "MagicLists",
                "f": "json"
            }
        else:
            # Use Subsonic token authentication
            return {
                "u": self.username,
                "t": self._subsonic_token,
                "s": self._subsonic_salt,
                "v": "1.16.1",
                "c": "MagicLists",
                "f": "json"
            }
    


