from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class Artist(BaseModel):
    """Schema for a music-server artist."""
    id: str
    name: str
    album_count: int = 0
    song_count: int = 0
    mbid: Optional[str] = None

class CreatePlaylistRequest(BaseModel):
    """Request schema for creating a playlist"""
    artist_ids: List[str]
    playlist_name: Optional[str] = None  # Optional, will auto-generate if not provided
    refresh_frequency: str = "none"  # "none", "daily", "weekly", "monthly"
    playlist_length: int = 25  # Number of tracks to include
    library_ids: List[str] = []  # List of library IDs to filter tracks

class ArtistRadioRecommendationRequest(BaseModel):
    """Request schema for fetching ListenBrainz recommendations."""
    source_mbid: str
    algorithm: str = "5Y Balanced"
    minimum_score: int = 50
    artist_id: Optional[str] = None
    library_ids: List[str] = []

class ArtistRadioRequest(BaseModel):
    """Request schema for a ListenBrainz-backed artist radio playlist."""
    artist_id: str
    artist_name: Optional[str] = None
    source_mbid: Optional[str] = None
    listenbrainz_enabled: bool = True
    algorithm: str = "5Y Balanced"
    minimum_score: int = 142
    recommendation_ids: List[str] = []
    manual_artist_ids: List[str] = []
    refetch_listenbrainz: bool = False
    playlist_name: Optional[str] = None
    refresh_frequency: str = "none"
    playlist_length: int = 25
    library_ids: List[str] = []
    year_start: Optional[int] = None
    year_end: Optional[int] = None
    diversity_enabled: bool = True
    max_tracks_per_album: int = 4
    max_tracks_per_artist: int = 8
    min_bitrate: Optional[int] = None
    min_format: Optional[str] = None
    min_bit_depth: Optional[int] = None

class CreateGenrePlaylistRequest(BaseModel):
    """Request schema for creating a genre mix playlist"""
    genres: List[str]
    playlist_name: Optional[str] = None  # Optional, will auto-generate if not provided
    refresh_frequency: str = "none"  # "none", "daily", "weekly", "monthly"
    playlist_length: int = 25  # Number of tracks to include
    library_ids: List[str] = []  # List of library IDs to filter tracks
    # Filter options
    year_start: Optional[int] = None  # Minimum release year (1950-2026)
    year_end: Optional[int] = None  # Maximum release year (1950-2026)
    blacklisted_artists: List[str] = []  # Artist names to exclude from selection
    min_bitrate: Optional[int] = None  # Minimum bitrate in kbps (128, 192, 256, 320)
    min_format: Optional[str] = None  # Minimum format (mp3, flac, aac, etc.)
    min_bit_depth: Optional[int] = None  # Minimum FLAC bit depth (16, 24); None = any. FLAC-only filter.
    # Diversity caps (0 or None disables that cap; defaults applied in the endpoint)
    max_tracks_per_album: Optional[int] = None  # Max tracks from the same album (global)
    max_tracks_per_artist: Optional[int] = None  # Max tracks per artist

class Playlist(BaseModel):
    """Schema for a stored playlist"""
    id: int
    artist_id: str
    playlist_name: str
    songs: List[str] = []
    description: Optional[str] = None
    navidrome_playlist_id: Optional[str] = None
    is_public: Optional[bool] = None
    library_ids: List[str] = []
    playlist_length: Optional[int] = None
    playlist_type: Optional[str] = None
    created_at: str
    updated_at: str

class Song(BaseModel):
    """Schema for a song"""
    id: str
    title: str
    artist: str
    album: str
    duration: Optional[int] = None
    track_number: Optional[int] = None

class PlaylistResponse(BaseModel):
    """Response schema for playlist operations"""
    playlist: Playlist
    message: str

class RediscoverTrack(BaseModel):
    """Schema for a Re-Discover Weekly track"""
    id: str
    title: str
    artist: str
    album: str
    score: float
    historical_plays: int
    days_since_last_play: str

class RediscoverWeeklyV2Response(BaseModel):
    """Response schema for Re-Discover Weekly v2.0"""
    name: str
    tracks: List[Dict[str, Any]]
    theme: str
    mode: str
    description: str
    user_id: str
    server_id: str
    generated_at: str
    is_fallback: Optional[bool] = False

class CreateRediscoverPlaylistRequest(BaseModel):
    """Request schema for creating a Re-Discover Weekly playlist"""
    refresh_frequency: str = "weekly"  # "daily", "weekly", "monthly"
    playlist_length: int = 25  # Number of tracks to include
    library_ids: List[str] = []  # List of library IDs to filter tracks

class ScheduledPlaylist(BaseModel):
    """Schema for a scheduled playlist"""
    id: int
    playlist_type: str  # "rediscover_weekly"
    navidrome_playlist_id: str
    refresh_frequency: str
    next_refresh: str
    created_at: str
    updated_at: str

class PlaylistWithScheduleInfo(BaseModel):
    """Schema for playlist with schedule information"""
    id: int
    artist_id: str
    playlist_name: str
    songs: List[str]
    created_at: str
    updated_at: str
    navidrome_playlist_id: Optional[str] = None
    is_public: Optional[bool] = None
    refresh_frequency: Optional[str] = None
    next_refresh: Optional[str] = None
    playlist_type: Optional[str] = None