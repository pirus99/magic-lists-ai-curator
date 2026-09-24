(function (window) {
    const playlists = {
        async updatePlaylistCount() {
            if (typeof updatePlaylistCount === 'function') return updatePlaylistCount();
            if (window.App && window.App.playlists && typeof window.App.playlists.updatePlaylistCount === 'function') return window.App.playlists.updatePlaylistCount();
            console.warn('updatePlaylistCount() not available');
        },
        async loadPlaylists() {
            if (typeof loadPlaylists === 'function') return loadPlaylists();
            console.warn('loadPlaylists() not available');
        },
        async refreshPlaylist(playlistId) {
            if (typeof refreshPlaylist === 'function') return refreshPlaylist(playlistId);
            console.warn('refreshPlaylist() not available');
        },
        async deletePlaylist(playlistId, playlistName) {
            if (typeof deletePlaylist === 'function') return deletePlaylist(playlistId, playlistName);
            console.warn('deletePlaylist() not available');
        },
        async savePlaylistSettings(regenerate) {
            if (typeof savePlaylistSettings === 'function') return savePlaylistSettings(regenerate);
            console.warn('savePlaylistSettings() not available');
        },
        async generateRediscoverWeekly() {
            if (typeof generateRediscoverWeekly === 'function') return generateRediscoverWeekly();
            console.warn('generateRediscoverWeekly() not available');
        }
    };

    window.App = window.App || {};
    window.App.playlists = playlists;
})(window);

// Handle artist selection change
function handleArtistSelection(e) {
    selectedArtistId = e.target.value;
    const submitBtn = document.getElementById('create-artist-playlist-btn');

    if (selectedArtistId) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

// This Is Artist form submission
document.getElementById('this-is-form').addEventListener('submit', function (e) {
    e.preventDefault();
    createArtistPlaylist();
});

// Genre Mix form submission
document.getElementById('genre-mix-form').addEventListener('submit', function (e) {
    e.preventDefault();
    createGenrePlaylist();
});

async function createArtistPlaylist() {
    const submitBtn = document.getElementById('create-artist-playlist-btn');

    if (!selectedArtistId) {
        showToast('error', 'Please select an artist first');
        return;
    }

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Creating your playlist...', 0);
    submitBtn.disabled = true;

    try {
        const refreshFrequency = document.querySelector('input[name="artist-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="artist-playlist-length"]:checked').value;

        const response = await fetch('/api/create_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                artist_ids: [selectedArtistId],
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_ids: selectedLibraryIds
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create playlist');
        }

        const data = await response.json();

        // Show success toast
        showToast('success', `Playlist created with ${data.songs ? data.songs.length : 0} tracks`);

        // Update playlist count in sidebar
        updatePlaylistCount();

    } catch (error) {
        console.error('Error creating playlist:', error);
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}

async function createGenrePlaylist() {
    const submitBtn = document.getElementById('create-genre-playlist-btn');

    if (!selectedGenres || selectedGenres.length === 0) {
        showToast('error', 'Please select at least one genre first');
        return;
    }

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Creating your playlist...', 0);
    submitBtn.disabled = true;

    try {
        const refreshFrequency = document.querySelector('input[name="genre-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="genre-playlist-length"]:checked').value;

        // Get filter values
        const yearStart = document.getElementById('genre-year-start').value;
        const yearEnd = document.getElementById('genre-year-end').value;
        const minFormat = document.getElementById('genre-min-format').value;
        // FLAC mode uses bit depth; MP3/Any mode uses bitrate. The hidden select is disabled
        // so its (stale) value is ignored.
        const isFlac = minFormat === 'flac';
        const minBitrateRaw = document.getElementById('genre-min-bitrate').value;
        const minBitDepthRaw = document.getElementById('genre-min-bitdepth').value;
        const minBitrate = isFlac ? null : (minBitrateRaw ? parseInt(minBitrateRaw) : null);
        const minBitDepth = isFlac ? (minBitDepthRaw ? parseInt(minBitDepthRaw) : null) : null;

        // Get blacklisted artists from multi-select
        const blacklistSelect = document.getElementById('genre-blacklist-select');
        const blacklistedArtists = blacklistSelect ? Array.from(blacklistSelect.selectedOptions).map(opt => opt.value) : [];

        // Diversity caps (artist & album). When the checkbox is off, send 0 to disable both.
        const capsEnabled = document.getElementById('genre-caps-enabled').checked;
        const maxTracksPerAlbum = capsEnabled ? parseInt(document.getElementById('genre-max-tracks-per-album').value) || 0 : 0;
        const maxTracksPerArtist = capsEnabled ? parseInt(document.getElementById('genre-max-tracks-per-artist').value) || 0 : 0;

        const response = await fetch('/api/create_genre_playlist', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                genres: selectedGenres,
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_ids: selectedLibraryIds,
                // Filter options
                year_start: yearStart ? parseInt(yearStart) : null,
                year_end: yearEnd ? parseInt(yearEnd) : null,
                blacklisted_artists: blacklistedArtists,
                min_bitrate: minBitrate,
                min_format: minFormat || null,
                min_bit_depth: minBitDepth,
                // Diversity caps (0 disables that cap)
                max_tracks_per_album: maxTracksPerAlbum,
                max_tracks_per_artist: maxTracksPerArtist
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create playlist');
        }

        const data = await response.json();

        // Show success toast
        showToast('success', `Playlist created with ${data.songs ? data.songs.length : 0} tracks`);

        // Update playlist count in sidebar
        updatePlaylistCount();

    } catch (error) {
        console.error('Error creating playlist:', error);
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}

// Re-discover Weekly functionality
async function generateRediscoverWeekly() {
    const button = document.getElementById('rediscover-btn');

    if (!checkLibrarySelection()) {
        return;
    }

    // Show loading toast
    showToast('loading', 'Analyzing your listening history...', 0);
    button.disabled = true;

    try {
        // Use v2.0 create endpoint (generates and creates playlist in one step)
        const refreshFrequency = document.querySelector('input[name="rediscover-refresh-frequency"]:checked').value;
        const playlistLength = document.querySelector('input[name="rediscover-playlist-length"]:checked').value;

        const response = await fetch('/api/create-rediscover-playlist-v2', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_ids: selectedLibraryIds
            })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to create Re-Discover playlist');
        }

        const data = await response.json();

        // Show success message
        const fallbackMsg = data.is_fallback ? ' (using fallback strategy)' : '';
        showToast('success', `Re-Discover playlist created! "${data.theme}" theme with ${data.track_count} tracks${fallbackMsg}`);

    } catch (error) {
        showToast('error', error.message);
    } finally {
        button.disabled = false;
    }
}

// Handle version selection changes (removed - always use v2.0)
function handleVersionChange() {
    const button = document.getElementById('rediscover-btn');
    button.textContent = 'Generate Re-Discover Playlist';
}

// Initialize button text
document.addEventListener('DOMContentLoaded', function () {
    // Set initial button text
    handleVersionChange();
});

// Update playlist count in sidebar
async function updatePlaylistCount() {
    try {
        const response = await fetch('/api/playlists');
        if (response.ok) {
            const playlists = await response.json();
            const count = playlists.length;

            // Update both desktop and mobile sidebar text
            const desktopText = document.getElementById('desktop-playlists-text');
            const mobileText = document.getElementById('mobile-playlists-text');

            if (count > 0) {
                if (desktopText) desktopText.textContent = `Playlists (${count})`;
                if (mobileText) mobileText.textContent = `Playlists (${count})`;
            } else {
                if (desktopText) desktopText.textContent = 'Playlists';
                if (mobileText) mobileText.textContent = 'Playlists';
            }
        }
    } catch (error) {
        console.error('Error fetching playlist count:', error);
        // Keep default text on error
    }
}

// Manage Playlists functionality
// Format next refresh time in a user-friendly way
function formatNextRefresh(nextRefreshTime) {
    const nextRefresh = new Date(nextRefreshTime);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const tomorrow = new Date(today.getTime() + 24 * 60 * 60 * 1000);
    const nextRefreshDate = new Date(nextRefresh.getFullYear(), nextRefresh.getMonth(), nextRefresh.getDate());

    const timeString = nextRefresh.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true });

    if (nextRefreshDate.getTime() === today.getTime()) {
        return `${timeString} today`;
    } else if (nextRefreshDate.getTime() === tomorrow.getTime()) {
        return `${timeString} tomorrow`;
    } else {
        return `${nextRefresh.toLocaleDateString('en-GB')} ${timeString}`;
    }
}

async function loadPlaylists() {
    const loadingDiv = document.getElementById('playlists-loading');
    const containerDiv = document.getElementById('playlists-container');

    loadingDiv.classList.remove('hidden');
    containerDiv.innerHTML = '';

    try {
        const response = await fetch('/api/playlists');
        if (!response.ok) {
            throw new Error('Failed to load playlists');
        }

        let playlists = await response.json();

        loadingDiv.classList.add('hidden');

        // Filter duplicates by navidrome_playlist_id to address backend JOIN issue
        const seenIds = new Set();
        playlists = playlists.filter(playlist => {
            // Use navidrome_playlist_id as unique identifier
            const id = playlist.navidrome_playlist_id || playlist.id; // fallback to id if no navidrome id
            if (seenIds.has(id)) {
                return false; // duplicate, filter out
            }
            seenIds.add(id);
            return true; // unique, keep
        });

        if (playlists.length === 0) {
            containerDiv.innerHTML = `
                <div class="text-center p-8 text-gray-500 dark:text-gray-400">
                    <p class="text-lg mb-2">No playlists yet</p>
                    <p class="text-sm">Create your first playlist using the options in the sidebar!</p>
                </div>
            `;
            return;
        }

        renderPlaylists(playlists);

    } catch (error) {
        console.error('Error loading playlists:', error);
        loadingDiv.classList.add('hidden');
        containerDiv.innerHTML = `
            <div class="text-center p-8 text-red-600 dark:text-red-400">
                <p class="text-lg mb-2">Error loading playlists</p>
                <p class="text-sm">${error.message}</p>
            </div>
        `;
    }
}

function truncateText(text, maxLength) {
    if (!text) return '';
    return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
}

function renderPlaylists(playlists) {
    const container = document.getElementById('playlists-container');

    container.innerHTML = playlists.map(playlist => {
        return `
            <div class="flex items-start justify-between p-4 border border-gray-200 dark:border-gray-700 rounded-lg mb-4">
                <div class="flex-grow">
                    <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-1">${playlist.playlist_name}</h3>
                    <div class="text-sm text-gray-600 dark:text-gray-300 mb-2 space-y-1">
                        <p class="mb-0">
                            ${playlist.track_count || 0} tracks • 
                            Refreshes ${playlist.refresh_frequency || 'manually'} • 
                            ${playlist.next_refresh ? `Next refresh ${formatNextRefresh(playlist.next_refresh)}` : 'No scheduled refresh'}
                        </p>
                        <p class="mb-0">
                            Created ${formatFriendlyDate(playlist.created_at)} • 
                            ${playlist.last_refreshed ? `Refreshed ${formatFriendlyDate(playlist.last_refreshed)}` : 'Not refreshed yet'}
                        </p>
                    </div>
                    ${playlist.description ? `<p class="text-sm text-gray-600 dark:text-gray-400 m-0 mt-2 italic">${truncateText(playlist.description, 140)}</p>` : ''}
                </div>
                <div class="flex-none flex flex-col items-end gap-1">
                    <div class="flex items-center gap-1">
                        <button
                            data-action="refresh"
                            data-playlist-id="${playlist.id}"
                            class="inline-flex items-center gap-1 text-sm font-medium underline cursor-pointer border-none bg-transparent text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 px-2 py-1"
                        >
                            <svg data-refresh-icon="${playlist.id}" class="size-3.5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6M1 19v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0018.49 15"/></svg>
                            <span data-refresh-label="${playlist.id}">Refresh</span>
                        </button>

                        <button
                            data-action="edit"
                            data-playlist-id="${playlist.id}"
                            class="inline-flex items-center gap-1 text-sm font-medium underline cursor-pointer border-none bg-transparent text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 px-2 py-1"
                        >
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 20h9"/>
                                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/>
                            </svg>
                            <span>Edit</span>
                        </button>

                        <button
                            data-action="delete"
                            data-playlist-id="${playlist.id}"
                            data-playlist-name="${playlist.playlist_name.replace(/"/g, '&quot;').replace(/'/g, "\\'")}"
                            class="inline-flex items-center gap-1 text-sm font-medium underline cursor-pointer border-none bg-transparent text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 px-2 py-1"
                        >
                            <svg class="size-3.5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6m3 0V4c0-1 1-2 2-2h6c1 0 2 1 2 2v2M8 10v10M12 10v10M16 10v10"/></svg>
                            <span>Delete</span>
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

async function deletePlaylist(playlistId, playlistName) {
    if (!confirm(`Are you sure you want to delete "${playlistName}"?\n\nThis will permanently remove the playlist from both Magic Lists and your Navidrome library.`)) {
        return;
    }

    try {
        const response = await fetch(`/api/playlists/${playlistId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to delete playlist');
        }

        // Reload the playlists list and update count
        loadPlaylists();
        updatePlaylistCount();

        // Show success toast - note that the backend may only delete locally if Navidrome deletion fails
        showToast('success', 'Playlist deleted from local database (check Navidrome if it still appears there)');

    } catch (error) {
        console.error('Error deleting playlist:', error);
        showToast('error', error.message);
    }
}

// Manually refresh a playlist from its saved curation settings
async function refreshPlaylist(playlistId) {
    if (!playlistId) {
        showToast('error', 'Unable to refresh playlist because no playlist ID was provided.');
        return;
    }

    const btn = document.querySelector(`[data-refresh-btn="${playlistId}"]`);
    const icon = document.querySelector(`[data-refresh-icon="${playlistId}"]`);
    const label = document.querySelector(`[data-refresh-label="${playlistId}"]`);

    // Enter loading state
    if (btn) btn.disabled = true;
    if (icon) icon.classList.add('animate-spin');
    if (label) label.textContent = 'Refreshing...';

    try {
        const response = await fetch(`/api/playlists/${playlistId}/refresh`, {
            method: 'POST'
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to refresh playlist');
        }

        showToast('success', 'Playlist refreshed successfully');
        loadPlaylists();
        updatePlaylistCount();
    } catch (error) {
        console.error('Error refreshing playlist:', error);
        showToast('error', error.message);
    } finally {
        if (btn) btn.disabled = false;
        if (icon) icon.classList.remove('animate-spin');
        if (label) label.textContent = 'Refresh';
    }
}

// Save (and optionally regenerate) the edited playlist settings
async function savePlaylistSettings(regenerate) {
    if (!currentEditPlaylistId) return;

    const { curation_settings, refresh_frequency, playlist_name, description, is_public } = collectEditSettings();

    const saveBtn = document.getElementById('edit-save-btn');
    const refreshBtn = document.getElementById('edit-save-refresh-btn');
    saveBtn.disabled = true;
    refreshBtn.disabled = true;

    try {
        const response = await fetch(`/api/playlists/${currentEditPlaylistId}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ curation_settings, refresh_frequency, playlist_name, description, is_public })
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to save settings');
        }

        showToast('success', 'Settings saved');

        if (regenerate) {
            const playlistIdToRefresh = currentEditPlaylistId;
            const currentPlaylistId = playlistIdToRefresh;
            closeEditModal();
            await refreshPlaylist(currentPlaylistId);
        } else {
            closeEditModal();
            loadPlaylists();
            updatePlaylistCount();
        }
    } catch (error) {
        console.error('Error saving playlist settings:', error);
        showToast('error', error.message);
    } finally {
        saveBtn.disabled = false;
        refreshBtn.disabled = false;
    }
}

// Artist Radio page event handlers
const artistRadioSource = document.getElementById('artist-radio-source');
if (artistRadioSource) artistRadioSource.addEventListener('change', () => {
    updateArtistRadioMbidVisibility();
    if (!document.getElementById('artist-radio-listenbrainz-enabled')?.checked) populateArtistRadioSelects([]);
});
const artistRadioListenbrainzEnabled = document.getElementById('artist-radio-listenbrainz-enabled');
if (artistRadioListenbrainzEnabled) {
    artistRadioListenbrainzEnabled.addEventListener('change', () => {
        const enabled = artistRadioListenbrainzEnabled.checked;
        document.getElementById('artist-radio-listenbrainz-controls')?.classList.toggle('hidden', !enabled);
        document.getElementById('artist-radio-fetch-btn')?.classList.toggle('hidden', !enabled);
        document.getElementById('artist-radio-recommendation-field')?.classList.toggle('hidden', !enabled);
        if (!enabled) populateArtistRadioSelects([]);
    });
}
const artistRadioScore = document.getElementById('artist-radio-score');
if (artistRadioScore) artistRadioScore.addEventListener('input', () => document.getElementById('artist-radio-score-value').textContent = artistRadioScore.value);
const artistRadioFetch = document.getElementById('artist-radio-fetch-btn');
if (artistRadioFetch) artistRadioFetch.addEventListener('click', fetchArtistRadioRecommendations);
const artistRadioForm = document.getElementById('artist-radio-form');
if (artistRadioForm) artistRadioForm.addEventListener('submit', createArtistRadioPlaylist);

async function fetchArtistRadioRecommendations() {
    const source = document.getElementById('artist-radio-source');
    if (!source?.value || !checkLibrarySelection()) return;
    const listenbrainzEnabled = document.getElementById('artist-radio-listenbrainz-enabled').checked;
    if (!listenbrainzEnabled) {
        populateArtistRadioSelects([]);
        showToast('info', 'ListenBrainz is disabled. Choose artists manually below.');
        return;
    }
    const sourceArtist = allArtists.find(artist => artist.id === source.value);
    const mbid = sourceArtist?.mbid || document.getElementById('artist-radio-mbid').value.trim();
    if (!mbid) return showToast('error', 'A MusicBrainz artist ID is required.');
    showToast('loading', 'Fetching similar artists...', 0);
    try {
        const response = await fetch('/api/artist-radio/recommendations/local?' + selectedLibraryIds.map(id => `library_id=${encodeURIComponent(id)}`).join('&'), {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                artist_id: source.value, source_mbid: mbid,
                algorithm: document.getElementById('artist-radio-algorithm').value,
                minimum_score: Number(document.getElementById('artist-radio-score').value), library_ids: selectedLibraryIds
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Failed to fetch recommendations');
        populateArtistRadioSelects(data);
        showToast('success', `Found ${data.length} similar artists in your library`);
    } catch (error) { showToast('error', error.message); }
}

async function createArtistRadioPlaylist(event) {
    if (event) event.preventDefault();
    const submitBtn = document.getElementById('create-artist-radio-btn');
    if (!checkLibrarySelection()) return;
    const source = document.getElementById('artist-radio-source');
    if (!source?.value) return showToast('error', 'Select a source artist.');
    const sourceArtist = allArtists.find(artist => artist.id === source.value);
    const listenbrainzEnabled = document.getElementById('artist-radio-listenbrainz-enabled').checked;
    const sourceMbid = listenbrainzEnabled
        ? (sourceArtist?.mbid || document.getElementById('artist-radio-mbid').value.trim())
        : null;
    if (listenbrainzEnabled && !sourceMbid) return showToast('error', 'A MusicBrainz artist ID is required.');

    const selected = element => Array.from(element.selectedOptions).map(option => option.value);
    const minFormat = document.getElementById('artist-radio-min-format').value;
    const minBitrate = document.getElementById('artist-radio-min-bitrate').value;
    const minBitDepth = document.getElementById('artist-radio-min-bitdepth').value;

    showToast('loading', 'Creating your Artist Radio playlist...', 0);
    submitBtn.disabled = true;
    try {
        const response = await fetch('/api/create_artist_radio', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                artist_id: source.value, artist_name: sourceArtist.name, source_mbid: sourceMbid,
                algorithm: document.getElementById('artist-radio-algorithm').value,
                listenbrainz_enabled: listenbrainzEnabled,
                minimum_score: Number(document.getElementById('artist-radio-score').value),
                recommendation_ids: selected(document.getElementById('artist-radio-recommendations')),
                manual_artist_ids: selected(document.getElementById('artist-radio-manual')),
                refetch_listenbrainz: false,
                year_start: valueOrNull('artist-radio-year-start'), year_end: valueOrNull('artist-radio-year-end'),
                diversity_enabled: document.getElementById('artist-radio-diversity-enabled').checked,
                max_tracks_per_album: Number(document.getElementById('artist-radio-album-cap').value),
                max_tracks_per_artist: Number(document.getElementById('artist-radio-artist-cap').value),
                min_format: minFormat || null,
                min_bitrate: minFormat === 'flac' ? null : (minBitrate ? Number(minBitrate) : null),
                min_bit_depth: minFormat === 'flac' ? (minBitDepth ? Number(minBitDepth) : null) : null,
                playlist_length: Number(document.querySelector('input[name="artist-radio-playlist-length"]:checked').value),
                refresh_frequency: document.querySelector('input[name="artist-radio-refresh-frequency"]:checked').value,
                library_ids: selectedLibraryIds
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Failed to create playlist');
        showToast('success', `Artist Radio playlist created with ${data.songs ? data.songs.length : 0} tracks`);
        updatePlaylistCount();
    } catch (error) {
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}

function valueOrNull(id) { const value = document.getElementById(id).value; return value ? Number(value) : null; }

const artistRadioDiversity = document.getElementById('artist-radio-diversity-enabled');
if (artistRadioDiversity) {
    const inputs = document.getElementById('artist-radio-diversity-inputs');
    const sync = () => {
        inputs.querySelectorAll('input').forEach(input => input.disabled = !artistRadioDiversity.checked);
        inputs.style.opacity = artistRadioDiversity.checked ? '1' : '0.5';
    };
    artistRadioDiversity.addEventListener('change', sync);
    sync();
}
const artistRadioFormat = document.getElementById('artist-radio-min-format');
if (artistRadioFormat) {
    const syncQuality = () => {
        const isFlac = artistRadioFormat.value === 'flac';
        document.getElementById('artist-radio-bitrate-wrap').classList.toggle('hidden', isFlac);
        document.getElementById('artist-radio-bitdepth-wrap').classList.toggle('hidden', !isFlac);
        document.getElementById('artist-radio-min-bitrate').disabled = isFlac;
        document.getElementById('artist-radio-min-bitdepth').disabled = !isFlac;
    };
    artistRadioFormat.addEventListener('change', syncQuality);
    syncQuality();
}