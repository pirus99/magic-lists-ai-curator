def ensure_artist_spacing(playlist: list[dict], spacing: int = 1) -> list[dict]:
    """
    Ensures that the same artist does not appear within a specified spacing in the playlist.

    Args:
        playlist (list[dict]): A list of dictionaries representing songs, each containing an 'artist' key.
        spacing (int): The minimum number of songs that must separate songs by the same artist.

    Returns:
        list[dict]: A new playlist with the same artist spaced out according to the specified spacing.
    """
    if spacing < 1:
        raise ValueError("Spacing must be at least 1.")

    artist_last_seen = []
    new_playlist = []
    skipped_songs = []
    repositioned_songs_count = 0
    non_spaced_songs_count = 0
    valid = False
    i = 0
    c = 0

    for song in playlist:
        artist = song.get('artist')
        if artist is None:
            print(f"⚠️ Song '{song.get('title', 'Unknown')}' does not have an 'artist' key. Skipping.")
            continue

        # Check if the artist has been seen and if the spacing condition is met
        if artist in artist_last_seen:
            if artist_last_seen.index(artist) < spacing:
                skipped_songs.append(song)
                c = i
                continue

        # If the artist was skipped previously, try to reinsert it
        i += 1
        if i > c + spacing - skipped_songs.__len__() +1:
            if skipped_songs:
                for skipped_song in skipped_songs[:]:
                    skipped_artist = skipped_song.get('artist')
                    if skipped_artist not in artist_last_seen:
                        new_playlist.append(skipped_song)
                        artist_last_seen.insert(0, skipped_artist)
                        artist_last_seen = artist_last_seen[:spacing]
                        skipped_songs.remove(skipped_song)
                        repositioned_songs_count += 1
                    else:
                        skipped_songs.remove(skipped_song)
                        skipped_songs.append(skipped_song)

        # Add the song to the new playlist and update the last seen artists
        new_playlist.append(song)
        artist_last_seen.insert(0, artist)
        artist_last_seen = artist_last_seen[:spacing]

    # After processing all songs, try to reinsert any remaining skipped songs
    for skipped_song in skipped_songs:
        skipped_artist = skipped_song.get('artist')
        if skipped_artist not in artist_last_seen:
            new_playlist.append(skipped_song)
            artist_last_seen.insert(0, skipped_artist)
            artist_last_seen = artist_last_seen[:spacing]
            skipped_songs.remove(skipped_song)
            repositioned_songs_count += 1

    for skipped_song in skipped_songs:
        new_playlist.append(skipped_song)
        non_spaced_songs_count += 1

    if repositioned_songs_count == 0 and non_spaced_songs_count == 0:
        valid = True
        print("✅ (Artist) All songs were spaced already correctly")
        return new_playlist, valid
    if repositioned_songs_count > 0 and non_spaced_songs_count == 0:
        valid = True
        print(f"↕️ (Artist) {repositioned_songs_count} songs repositioned")
        return new_playlist, valid
    if repositioned_songs_count > 0 and non_spaced_songs_count > 0:
        print(f"⚠️ (Album) {repositioned_songs_count} songs repositioned and {non_spaced_songs_count} songs could not be spaced due to spacing constraints")
        return new_playlist, valid
    if non_spaced_songs_count > 0:
        print(f"⚠️ (Artist) {non_spaced_songs_count} songs could not be spaced due to spacing constraints")
        return new_playlist, valid

    return new_playlist, valid

def ensure_album_spacing(playlist: list[dict], spacing: int = 1) -> list[dict]:
    """
    Ensures that the same album does not appear within a specified spacing in the playlist.

    Args:
        playlist (list[dict]): A list of dictionaries representing songs, each containing an 'album' key.
        spacing (int): The minimum number of songs that must separate songs from the same album.

    Returns:
        list[dict]: A new playlist with the same album spaced out according to the specified spacing.
    """
    if spacing < 1:
        raise ValueError("Spacing must be at least 1.")

    album_last_seen = []
    new_playlist = []
    skipped_songs = []
    repositioned_songs_count = 0
    non_spaced_songs_count = 0
    valid = False
    i = 0
    c = 0

    for song in playlist:
        album = song.get('album')
        if album is None:
            print(f"⚠️ Song '{song.get('title', 'Unknown')}' does not have an 'album' key. Skipping.")
            continue

        # Check if the album has been seen and if the spacing condition is met
        if album in album_last_seen:
            if album_last_seen.index(album) < spacing:
                skipped_songs.append(song)
                c = i
                continue

        # If the album was skipped previously, try to reinsert it
        i += 1
        if i > c + spacing - skipped_songs.__len__() +1:
            if skipped_songs:
                for skipped_song in skipped_songs[:]:
                    skipped_album = skipped_song.get('album')
                    if skipped_album not in album_last_seen:
                        new_playlist.append(skipped_song)
                        album_last_seen.insert(0, skipped_album)
                        album_last_seen = album_last_seen[:spacing]
                        skipped_songs.remove(skipped_song)
                        repositioned_songs_count += 1
                    else:
                        skipped_songs.remove(skipped_song)
                        skipped_songs.append(skipped_song)

        # Add the song to the new playlist and update the last seen albums
        new_playlist.append(song)
        album_last_seen.insert(0, album)
        album_last_seen = album_last_seen[:spacing]

    # After processing all songs, try to reinsert any remaining skipped songs
    for skipped_song in skipped_songs:
        skipped_album = skipped_song.get('album')
        if skipped_album not in album_last_seen:
            new_playlist.append(skipped_song)
            album_last_seen.insert(0, skipped_album)
            album_last_seen = album_last_seen[:spacing]
            skipped_songs.remove(skipped_song)
            repositioned_songs_count += 1

    for skipped_song in skipped_songs:
        new_playlist.append(skipped_song)
        non_spaced_songs_count += 1

    if repositioned_songs_count == 0 and non_spaced_songs_count == 0:
        valid = True
        print("✅ (Album) All songs were spaced already correctly")
        return new_playlist, valid
    if repositioned_songs_count > 0 and non_spaced_songs_count == 0:
        valid = True
        print(f"↕️ (Album) {repositioned_songs_count} songs repositioned")
        return new_playlist, valid
    if repositioned_songs_count > 0 and non_spaced_songs_count > 0:
        print(f"⚠️ (Album) {repositioned_songs_count} songs repositioned and {non_spaced_songs_count} songs could not be spaced due to spacing constraints")
        return new_playlist, valid
    if non_spaced_songs_count > 0:
        print(f"⚠️ (Album) {non_spaced_songs_count} songs could not be spaced due to spacing constraints")
        return new_playlist, valid

    return new_playlist, valid

def space_album(spaced_playlist: list[dict], album_spacing, runs):
    # Ensure album spacing
    album_valid = False
    dex = 0
    while not album_valid and dex < runs:
        dex += 1
        spaced_playlist, album_valid = ensure_album_spacing(spaced_playlist, spacing=album_spacing)
        if not album_valid:
            reversed_spaced_playlist, album_valid = ensure_album_spacing(spaced_playlist[::-1], spacing=album_spacing)
            spaced_playlist = reversed_spaced_playlist[::-1]
        if not album_valid:
            spaced_playlist, album_valid = ensure_album_spacing(spaced_playlist, spacing=album_spacing)
    return spaced_playlist, album_valid

def space_artist(spaced_playlist: list[dict], artist_spacing, runs):
    #Ensure artist spacing
    artist_valid = False
    dex = 0
    while not artist_valid and dex < runs:
        dex += 1
        spaced_playlist, artist_valid = ensure_artist_spacing(spaced_playlist, spacing=artist_spacing)
        if not artist_valid:
            reversed_spaced_playlist, artist_valid = ensure_artist_spacing(spaced_playlist[::-1], spacing=artist_spacing)
            spaced_playlist = reversed_spaced_playlist[::-1]
        if not artist_valid:
            spaced_playlist, artist_valid = ensure_artist_spacing(spaced_playlist, spacing=artist_spacing)
    return spaced_playlist, artist_valid

def space_id_track_list_by_artist_and_album(track_ids: list[int], candidate_tracks: list[dict], artist_spacing: int = 0, album_spacing: int = 0) -> list[dict]:
    """
    Sorts a playlist of tracks based on artist and album spacing.

    Args:
        track_ids (list[int]): A list of track IDs to be sorted.
        candidate_tracks (list[dict]): A list of dictionaries representing candidate tracks, each containing 'id', 'artist', and 'album' keys.
        artist_spacing (int): The minimum number of songs that must separate songs by the same artist.
        album_spacing (int): The minimum number of songs that must separate songs from the same album.

    Returns:
        list[dict]: A new playlist sorted according to the specified artist and album spacing.
    """
    playlist = []
    # Filter candidate tracks to only include those in track_ids
    filtered_tracks = []
    added_ids = set()
    duplicate_count = 0
    
    for track in candidate_tracks:
        if track["id"] in track_ids and track["id"] not in added_ids:
            filtered_tracks.append(track)
            added_ids.add(track["id"])
        elif track["id"] in track_ids and track["id"] in added_ids:
            duplicate_count += 1

    if duplicate_count >= 1:
        print(f"⚠️ {duplicate_count} duplicate entries removed from output")

    #Define Spacing Vars
    spaced_playlist = filtered_tracks
    correctly_spaced = False

    if artist_spacing > 0 and album_spacing > 0:
        artist_valid = False
        album_valid = False
        dex = 0
        while not correctly_spaced and dex < 25:
            dex += 1
            spaced_playlist, artist_valid = space_artist(spaced_playlist, artist_spacing, 1)
            spaced_playlist, album_valid = space_album(spaced_playlist, album_spacing, 1)
            correctly_spaced = album_valid and artist_valid

    if album_spacing > 0 and artist_spacing == 0:
        spaced_playlist, correctly_spaced = space_album(spaced_playlist, album_spacing, 10)

    if artist_spacing > 0 and album_spacing == 0:
        spaced_playlist, correctly_spaced = space_artist(spaced_playlist, artist_spacing, 10)

    for track in spaced_playlist:
        playlist.append(track["id"])

    return playlist