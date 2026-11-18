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

// Short labels for the top-track strategy, mirroring TOP_TRACK_STRATEGY_LABELS in
// backend/services/lastfm_service.py. Rendered next to the count slider so the user
// knows where their top tracks come from.
const TOP_TRACK_STRATEGY_LABELS = {
    native: 'Native',
    lastfm: 'Last.fm',
    hybrid: 'Hybrid',
    off: 'Off',
};

function topTracksStrategy() {
    const strategy = document.body?.dataset.topTracksStrategy || '';
    if (strategy) return strategy;
    // Fallback for pages rendered without the strategy in the template context.
    return document.body?.dataset.serverType === 'navidrome' ? 'native' : 'off';
}

function topTracksSourceLabel() {
    const strategy = topTracksStrategy();
    return TOP_TRACK_STRATEGY_LABELS[strategy] || strategy;
}

// True when the source can actually service a request right now. Jellyfin without
// LASTFM_API_KEY is *supported* (the slider stays visible so the feature is
// discoverable) but not *configured*, so we prompt for setup instead of hiding it.
function topTracksConfigured() {
    return document.body?.dataset.lastfmConfigured === 'true'
        || topTracksStrategy() === 'native';
}

function setupTopTracksControls(prefix) {
    const input = document.getElementById(`${prefix}-top-tracks-count`);
    const output = document.getElementById(`${prefix}-top-tracks-count-value`);
    const controls = input?.closest('.top-tracks-controls');
    const supported = topTracksStrategy() !== 'off';
    const configured = topTracksConfigured();
    if (!input || !controls) return;

    // Never hide the control just because a key is missing: show it, explain what is
    // needed, and disable the slider so a stored preference is not silently ignored.
    controls.classList.remove('hidden');
    controls.dataset.topTracksSupported = String(supported);
    controls.dataset.topTracksConfigured = String(configured);
    controls.classList.toggle('top-tracks-unconfigured', !configured);

    const label = controls.querySelector('[data-top-tracks-source-label]');
    if (label) label.textContent = topTracksSourceLabel();

    const hint = controls.querySelector('[data-top-tracks-source-hint]');
    if (hint) {
        if (!configured) {
            hint.textContent = 'Add LASTFM_API_KEY to your .env file and restart to enable top tracks. '
                + 'Playlists fall back to play-count ordering until then.';
            hint.classList.add('text-amber-600', 'dark:text-amber-400', 'font-medium');
        } else {
            hint.textContent = `Popularity source: ${topTracksSourceLabel()}. Fetches up to this many popular songs. Set to 0 to disable.`;
            hint.classList.remove('text-amber-600', 'dark:text-amber-400', 'font-medium');
        }
    }

    const sync = () => {
        const maxCount = Number(input.max) || 10;
        const count = Math.max(0, Math.min(maxCount, Number(input.value) || 0));
        input.value = String(count);
        if (output) output.textContent = String(count);
        // Only a genuinely unavailable source disables the slider. An unconfigured
        // Last.fm keeps the stored value visible so the setting is not silently lost.
        input.disabled = !supported;
        // The MBID override only matters while top tracks are switched on.
        updateThisIsMbidFallback();
    };
    if (!supported) input.value = '0';
    input.addEventListener('input', sync);
    sync();
}

// Back-compat alias: the old helper name is referenced by inline page scripts.
const setupNavidromeTopTracksControls = setupTopTracksControls;

// This file is loaded *before* app.js, which declares the shared `let` state
// (allArtists, selectedArtistId). Touching those bindings while app.js has not run
// throws a ReferenceError, so every entry point that reads shared state is deferred
// until DOMContentLoaded, after all scripts have executed.
function initTopTracksControls() {
    document.querySelectorAll('.top-tracks-controls').forEach(control => {
        const input = control.querySelector('input[type="range"]');
        if (input) setupTopTracksControls(input.id.replace(/-top-tracks-count$/, ''));
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTopTracksControls);
} else {
    initTopTracksControls();
}

function topTracksPayload(prefix) {
    const input = document.getElementById(`${prefix}-top-tracks-count`);
    const maxCount = Number(input?.max) || 10;
    const count = Math.max(0, Math.min(maxCount, Number(input?.value) || 0));
    return { top_tracks_enabled: count > 0, top_tracks_count: count };
}

// Handle artist selection change
function handleArtistSelection(e) {
    selectedArtistId = e.target.value;
    const submitBtn = document.getElementById('create-artist-playlist-btn');

    updateThisIsMbidFallback();

    if (selectedArtistId) {
        submitBtn.disabled = false;
    } else {
        submitBtn.disabled = true;
    }
}

// Read the user-supplied Last.fm MBID override, if present.
function thisIsMbidOverride() {
    return document.getElementById('this-is-artist-mbid')?.value.trim() || '';
}

// Resolve the currently selected artist's MusicBrainz ID from the artist dropdown.
//
// This deliberately reads the DOM rather than app.js's `allArtists`: playlists.js is
// loaded *before* app.js, so the `let allArtists` binding is in the temporal dead zone
// and touching it throws a ReferenceError (a bare `typeof` guard does not help --
// `typeof` on a not-yet-initialised `let` throws too). The <option> elements are the
// same data app.js renders, so they are the reliable cross-file source.
function selectedArtistMbid() {
    const select = document.getElementById('artist-search-select');
    const selectedId = select?.value;
    if (!select || !selectedId) return { id: null, name: null, mbid: null };

    const option = Array.from(select.options).find(o => o.value === selectedId);
    const name = option?.textContent?.trim() || '';
    // app.js may attach the MBID to the option; otherwise fall back to a data attribute.
    const mbid = (option?.dataset?.mbid || option?.dataset?.mbidValue || '').trim();
    return { id: selectedId, name, mbid };
}

// Last.fm needs a MusicBrainz ID to resolve top tracks, and Jellyfin library metadata
// frequently has none. Show the override input only when all of these hold:
//   - the active source is Last.fm (i.e. Jellyfin + LASTFM_API_KEY),
//   - an artist is selected,
//   - top tracks are actually requested,
//   - that artist has no usable MBID in the library metadata.
function updateThisIsMbidFallback() {
    const block = document.getElementById('this-is-artist-mbid-fallback');
    if (!block) return;

    if (topTracksStrategy() !== 'lastfm') {
        block.classList.add('hidden');
        return;
    }

    const artist = selectedArtistMbid();
    if (!artist.id) {
        block.classList.add('hidden');
        return;
    }

    const needsMbid = !artist.mbid;
    const topTracksOn = topTracksPayload('this-is').top_tracks_enabled;
    const show = needsMbid && topTracksOn;
    block.classList.toggle('hidden', !show);

    const hint = document.getElementById('this-is-artist-mbid-hint');
    if (hint) {
        hint.textContent = topTracksOn
            ? `No MusicBrainz ID in the library metadata for "${artist.name}". Enter one so Last.fm can find their top tracks.`
            : `Set the Top Tracks slider above 0 to fetch top tracks for "${artist.name}".`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    updateThisIsMbidFallback();
});

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
                // Last.fm lookup override only; ignored unless the source is Last.fm.
                artist_mbid: thisIsMbidOverride() || null,
                refresh_frequency: refreshFrequency,
                playlist_length: parseInt(playlistLength),
                library_ids: selectedLibraryIds,
                ...topTracksPayload('this-is')
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
            <div class="flex flex-col md:flex-row md:items-start md:justify-between p-4 border border-gray-200 dark:border-gray-700 rounded-lg mb-4">
                <div class="flex-grow w-full md:w-auto min-w-0">
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
                <div class="flex-none md:flex-none flex flex-row md:flex-col items-start md:items-end gap-1 mt-3 md:mt-0 w-full md:w-auto pt-2 md:pt-0 border-t md:border-t-0 border-gray-200 dark:border-gray-700/60">
                    <div class="flex items-center flex-wrap gap-1 w-full md:w-auto">
                        <button
                            data-action="refresh"
                            data-playlist-id="${playlist.id}"
                            class="inline-flex flex-1 md:flex-none items-center justify-center md:justify-start gap-1 text-sm font-medium underline cursor-pointer border-none bg-transparent text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 px-2 py-2"
                        >
                            <svg data-refresh-icon="${playlist.id}" class="size-3.5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6M1 19v-6h6M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0018.49 15"/></svg>
                            <span data-refresh-label="${playlist.id}">Refresh</span>
                        </button>

                        <button
                            data-action="edit"
                            data-playlist-id="${playlist.id}"
                            class="inline-flex flex-1 md:flex-none items-center justify-center md:justify-start gap-1 text-sm font-medium underline cursor-pointer border-none bg-transparent text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 px-2 py-2"
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
                            class="inline-flex flex-1 md:flex-none items-center justify-center md:justify-start gap-1 text-sm font-medium underline cursor-pointer border-none bg-transparent text-red-600 hover:text-red-800 dark:text-red-400 dark:hover:text-red-300 px-2 py-2"
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

// ---------------------------------------------------------------------------
// Delete playlist confirmation modal
// Replaces the native window.confirm() so the dialog follows the app theme
// (light/dark) and can show a busy state while the request is in flight.
// ---------------------------------------------------------------------------
let pendingDeletePlaylistId = null;

function openDeleteModal(playlistId, playlistName) {
    const overlay = document.getElementById('delete-modal-overlay');
    const modal = document.getElementById('delete-modal');
    const nameEl = document.getElementById('delete-modal-playlist-name');
    if (!overlay || !modal) {
        // Modal markup missing (e.g. partial page render) — fall back to confirm()
        if (confirm(`Are you sure you want to delete "${playlistName}"?\n\nThis will permanently remove the playlist from both Magic Lists and your media server.`)) {
            performDeletePlaylist(playlistId);
        }
        return;
    }

    pendingDeletePlaylistId = playlistId;
    if (nameEl) nameEl.textContent = `"${playlistName || 'this playlist'}"`;
    setDeleteModalBusy(false);

    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');

    const confirmBtn = document.getElementById('delete-confirm-btn');
    if (confirmBtn) confirmBtn.focus();
}

function closeDeleteModal() {
    const overlay = document.getElementById('delete-modal-overlay');
    const modal = document.getElementById('delete-modal');
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
    pendingDeletePlaylistId = null;
    setDeleteModalBusy(false);
}

function setDeleteModalBusy(busy) {
    const confirmBtn = document.getElementById('delete-confirm-btn');
    const cancelBtn = document.getElementById('delete-cancel-btn');
    const closeBtn = document.getElementById('delete-close-top');
    const spinner = document.getElementById('delete-confirm-spinner');
    const label = document.getElementById('delete-confirm-label');

    if (confirmBtn) confirmBtn.disabled = busy;
    if (cancelBtn) cancelBtn.disabled = busy;
    if (closeBtn) closeBtn.disabled = busy;
    if (spinner) spinner.classList.toggle('hidden', !busy);
    if (label) label.textContent = busy ? 'Deleting...' : 'Delete Playlist';
}

// Entry point used by the playlist card "Delete" button
async function deletePlaylist(playlistId, playlistName) {
    openDeleteModal(playlistId, playlistName);
}

async function performDeletePlaylist(playlistId) {
    setDeleteModalBusy(true);

    try {
        const response = await fetch(`/api/playlists/${playlistId}`, {
            method: 'DELETE'
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
            throw new Error(errorData.detail || 'Failed to delete playlist');
        }

        closeDeleteModal();

        // Reload the playlists list and update count
        loadPlaylists();
        updatePlaylistCount();

        // Deletion is idempotent server-side: a playlist already removed in
        // Navidrome/Jellyfin is simply cleaned up locally as well.
        showToast('success', 'Playlist deleted from Magic Lists and your media server');

    } catch (error) {
        console.error('Error deleting playlist:', error);
        setDeleteModalBusy(false);
        showToast('error', error.message);
    }
}

// Wire up the delete modal once the DOM is ready (playlists.js loads before
// main.js, so the markup may still be parsing).
function initDeleteModal() {
    const overlay = document.getElementById('delete-modal-overlay');
    const modal = document.getElementById('delete-modal');
    if (!overlay || !modal) return;

    overlay.addEventListener('click', closeDeleteModal);
    modal.addEventListener('click', function (event) {
        // Close only when clicking the backdrop, not the inner panel
        if (event.target === modal) closeDeleteModal();
    });

    const cancelBtn = document.getElementById('delete-cancel-btn');
    const closeBtn = document.getElementById('delete-close-top');
    const confirmBtn = document.getElementById('delete-confirm-btn');
    if (cancelBtn) cancelBtn.addEventListener('click', closeDeleteModal);
    if (closeBtn) closeBtn.addEventListener('click', closeDeleteModal);
    if (confirmBtn) {
        confirmBtn.addEventListener('click', function () {
            if (pendingDeletePlaylistId) performDeletePlaylist(pendingDeletePlaylistId);
        });
    }

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && !modal.classList.contains('hidden')) {
            closeDeleteModal();
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initDeleteModal);
} else {
    initDeleteModal();
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

        // The endpoint queues the refresh and returns 202 immediately.
        const data = await response.json().catch(() => ({}));
        if (data.status === 'already_queued') {
            showToast('info', 'This playlist is already queued or refreshing');
        } else {
            showToast('success', 'Refresh queued — it will start shortly');
        }
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

    const { curation_settings, refresh_frequency, playlist_name, description, is_public, schedule, schedule_enabled } = collectEditSettings();

    const saveBtn = document.getElementById('edit-save-btn');
    const refreshBtn = document.getElementById('edit-save-refresh-btn');
    saveBtn.disabled = true;
    refreshBtn.disabled = true;

    try {
        const response = await fetch(`/api/playlists/${currentEditPlaylistId}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ curation_settings, refresh_frequency, playlist_name, description, is_public, schedule, schedule_enabled })
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
                library_ids: selectedLibraryIds,
                ...topTracksPayload('artist-radio')
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

// Song Radio page event handlers
const songRadioSearch = document.getElementById('song-radio-search');
const songRadioTrackSelect = document.getElementById('song-radio-track');
let songRadioBuiltPool = null; // holds the last built pool so create can reuse it
if (songRadioSearch && songRadioTrackSelect) {
    const resultsBox = document.getElementById('song-radio-results');
    const mbidFallback = document.getElementById('song-radio-mbid-fallback');
    const mbidInput = document.getElementById('song-radio-mbid');
    const poolBox = document.getElementById('song-radio-pool');
    const poolCount = document.getElementById('song-radio-pool-count');
    const createBtn = document.getElementById('create-song-radio-btn');

    document.getElementById('song-radio-search-btn').addEventListener('click', async () => {
        const query = songRadioSearch.value.trim();
        if (!query || !checkLibrarySelection()) return;
        showToast('loading', 'Searching library...', 0);
        try {
            const response = await fetch('/api/song-radio/search', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ query, library_ids: selectedLibraryIds, limit: 50 })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Search failed');
            songRadioTrackSelect.innerHTML = '<option value="">Choose a track</option>';
            const sortedTracks = [...data].sort((a, b) => {
                const titleA = (a.title || 'Unknown').toLocaleLowerCase();
                const titleB = (b.title || 'Unknown').toLocaleLowerCase();
                return titleA.localeCompare(titleB) || (a.artist || 'Unknown').localeCompare(b.artist || 'Unknown');
            });
            sortedTracks.forEach(track => {
                const option = document.createElement('option');
                option.value = track.id;
                option.textContent = `${track.title || 'Unknown'} — ${track.artist || 'Unknown'} (${track.album || 'Unknown'})`;
                option.dataset.track = JSON.stringify({
                    id: track.id,
                    title: track.title,
                    artist: track.artist,
                    album: track.album,
                    artist_id: track.artist_id,
                    recording_mbid: track.recording_mbid || null
                });
                songRadioTrackSelect.appendChild(option);
            });
            resultsBox.classList.remove('hidden');
            poolBox.classList.add('hidden');
            createBtn.disabled = true;
            songRadioBuiltPool = null;
            showToast('success', `Found ${data.length} track(s)`);
        } catch (error) { showToast('error', error.message); }
    });

    songRadioTrackSelect.addEventListener('change', () => {
        const option = songRadioTrackSelect.selectedOptions[0];
        const track = option && option.dataset.track ? JSON.parse(option.dataset.track) : null;
        if (track && track.recording_mbid) {
            mbidFallback.classList.add('hidden');
            mbidInput.value = track.recording_mbid;
        } else {
            mbidFallback.classList.remove('hidden');
            mbidInput.value = '';
        }
        // Reset any previously built pool when the source track changes.
        poolBox.classList.add('hidden');
        songRadioBuiltPool = null;
        if (songRadioFindBtn) songRadioFindBtn.disabled = !document.getElementById('song-radio-listenbrainz-enabled').checked || !(option && option.value);
        // In Subsonic-only mode (ListenBrainz disabled or "use Navidrome
        // similar-tracks" checked) the pool is built server-side on create, so
        // the "Find Similar Tracks" step is optional and the Create button can
        // be enabled as soon as a source track is selected.
        const subsonicSimilarInput = document.getElementById('song-radio-subsonic-similar');
        const subsonicOnly = !document.getElementById('song-radio-listenbrainz-enabled').checked
            || Boolean(subsonicSimilarInput && subsonicSimilarInput.checked);
        createBtn.disabled = !(option && option.value) || !subsonicOnly;
    });

    const findBtn = document.getElementById('song-radio-find-btn');
    if (findBtn) {
        findBtn.addEventListener('click', async () => {
            const option = songRadioTrackSelect.selectedOptions[0];
            if (!option || !option.value) return showToast('error', 'Select a source track first.');
            const track = option.dataset.track ? JSON.parse(option.dataset.track) : null;
            const subsonicSimilarInput = document.getElementById('song-radio-subsonic-similar');
            const useSubsonic = Boolean(subsonicSimilarInput && subsonicSimilarInput.checked);
            const sourceMbid = track?.recording_mbid || mbidInput.value.trim();
            if (!sourceMbid && !useSubsonic) return showToast('error', 'A MusicBrainz Recording ID is required.');

            showToast('loading', 'Finding similar tracks...', 0);
            findBtn.disabled = true;
            try {
                const response = await fetch('/api/song-radio/build-pool', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        source_mbid: sourceMbid,
                        source_track: track,
                        listenbrainz_enabled: document.getElementById('song-radio-listenbrainz-enabled').checked,
                        use_subsonic_similar: Boolean(subsonicSimilarInput && subsonicSimilarInput.checked),
                        algorithm: document.getElementById('song-radio-algorithm').value,
                        minimum_score: Number(document.getElementById('song-radio-score').value),
                        repeat_limit: Number(document.getElementById('song-radio-repeat').value),
                        library_ids: selectedLibraryIds
                    })
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || 'Failed to build pool');
                songRadioBuiltPool = data;
                const n = data.pool_size;
                const listenbrainzEnabled = document.getElementById('song-radio-listenbrainz-enabled').checked;
                poolCount.textContent = n > 0
                    ? `Found ${n} matching track${n === 1 ? '' : 's'} in your library.`
                    : listenbrainzEnabled && !useSubsonic
                        ? 'ListenBrainz found no matching tracks.'
                        : 'No matching tracks found in your library.';
                poolBox.classList.remove('hidden');
                createBtn.disabled = n === 0;
                if (n > 0) showToast('success', `Built a pool of ${n} track(s).`);
                else if (listenbrainzEnabled && !useSubsonic) showToast('info', 'ListenBrainz found no matching tracks.');
                else showToast('info', 'No matches — try another track or lower the score.');
            } catch (error) {
                showToast('error', error.message);
            } finally {
                findBtn.disabled = false;
            }
        });
    }

    const resetBtn = document.getElementById('song-radio-reset-btn');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            poolBox.classList.add('hidden');
            createBtn.disabled = true;
            songRadioBuiltPool = null;
            songRadioTrackSelect.value = '';
            songRadioTrackSelect.dispatchEvent(new Event('change'));
        });
    }
}
const songRadioScore = document.getElementById('song-radio-score');
if (songRadioScore) songRadioScore.addEventListener('input', () => document.getElementById('song-radio-score-value').textContent = songRadioScore.value);
const songRadioRepeat = document.getElementById('song-radio-repeat');
if (songRadioRepeat) songRadioRepeat.addEventListener('input', () => document.getElementById('song-radio-repeat-value').textContent = songRadioRepeat.value);
const songRadioListenbrainzEnabled = document.getElementById('song-radio-listenbrainz-enabled');
const songRadioListenbrainzControls = document.getElementById('song-radio-listenbrainz-controls');
const songRadioFindBtnWrap = document.getElementById('song-radio-find-btn-wrap');
const songRadioFindBtn = document.getElementById('song-radio-find-btn');
if (songRadioListenbrainzEnabled) {
    const syncListenbrainzUi = () => {
        const enabled = songRadioListenbrainzEnabled.checked;
        songRadioListenbrainzControls?.classList.toggle('hidden', !enabled);
        songRadioFindBtnWrap?.classList.toggle('hidden', !enabled);
        const option = songRadioTrackSelect.selectedOptions[0];
        if (songRadioFindBtn) songRadioFindBtn.disabled = !enabled || !(option && option.value);
        // Re-evaluate whether the Create button can be enabled without the
        // "Find Similar Tracks" step (Subsonic-only mode).
        const subsonicSimilarInput = document.getElementById('song-radio-subsonic-similar');
        const subsonicOnly = !enabled || Boolean(subsonicSimilarInput && subsonicSimilarInput.checked);
        const createBtn = document.getElementById('create-song-radio-btn');
        const poolBox = document.getElementById('song-radio-pool');
        if (subsonicOnly && option && option.value && createBtn) {
            createBtn.disabled = false;
            poolBox?.classList.add('hidden');
            songRadioBuiltPool = null;
        } else if (createBtn) {
            createBtn.disabled = true;
        }
    };
    songRadioListenbrainzEnabled.addEventListener('change', syncListenbrainzUi);
    syncListenbrainzUi();
}
const songRadioSubsonicSimilar = document.getElementById('song-radio-subsonic-similar');
if (songRadioSubsonicSimilar) {
    songRadioSubsonicSimilar.addEventListener('change', () => {
        const subsonicOnly = songRadioSubsonicSimilar.checked
            || !document.getElementById('song-radio-listenbrainz-enabled').checked;
        const option = songRadioTrackSelect.selectedOptions[0];
        const createBtn = document.getElementById('create-song-radio-btn');
        const poolBox = document.getElementById('song-radio-pool');
        if (subsonicOnly && option && option.value && createBtn) {
            createBtn.disabled = false;
            poolBox?.classList.add('hidden');
            songRadioBuiltPool = null;
        } else if (createBtn) {
            createBtn.disabled = true;
        }
    });
}
const songRadioDiversity = document.getElementById('song-radio-diversity-enabled');
if (songRadioDiversity) {
    const inputs = document.getElementById('song-radio-diversity-inputs');
    const sync = () => {
        inputs.querySelectorAll('input').forEach(input => input.disabled = !songRadioDiversity.checked);
        inputs.style.opacity = songRadioDiversity.checked ? '1' : '0.5';
    };
    songRadioDiversity.addEventListener('change', sync);
    sync();
}
const songRadioFormat = document.getElementById('song-radio-min-format');
if (songRadioFormat) {
    const syncQuality = () => {
        const isFlac = songRadioFormat.value === 'flac';
        document.getElementById('song-radio-bitrate-wrap').classList.toggle('hidden', isFlac);
        document.getElementById('song-radio-bitdepth-wrap').classList.toggle('hidden', !isFlac);
        document.getElementById('song-radio-min-bitrate').disabled = isFlac;
        document.getElementById('song-radio-min-bitdepth').disabled = !isFlac;
    };
    songRadioFormat.addEventListener('change', syncQuality);
    syncQuality();
}
const songRadioForm = document.getElementById('song-radio-form');
if (songRadioForm) songRadioForm.addEventListener('submit', createSongRadioPlaylist);

async function createSongRadioPlaylist(event) {
    if (event) event.preventDefault();
    const submitBtn = document.getElementById('create-song-radio-btn');
    if (!checkLibrarySelection()) return;
    const subsonicSimilarInput = document.getElementById('song-radio-subsonic-similar');
    const useSubsonic = Boolean(subsonicSimilarInput && subsonicSimilarInput.checked);
    const listenbrainzEnabled = document.getElementById('song-radio-listenbrainz-enabled').checked;
    // When relying on Navidrome's similarity engine the pool is built server-side
    // on create, so the "Find Similar Tracks" step is not required.
    if (!songRadioBuiltPool && listenbrainzEnabled && !useSubsonic) {
        return showToast('error', 'Find similar tracks first to build the pool.');
    }
    const trackSelect = document.getElementById('song-radio-track');
    const option = trackSelect.selectedOptions[0];
    if (!option || !option.value) return showToast('error', 'Select a source track.');
    const track = option.dataset.track ? JSON.parse(option.dataset.track) : null;
    const sourceMbid = track?.recording_mbid || document.getElementById('song-radio-mbid').value.trim();
    if (!sourceMbid && !useSubsonic) return showToast('error', 'A MusicBrainz Recording ID is required.');

    const minFormat = document.getElementById('song-radio-min-format').value;
    const minBitrate = document.getElementById('song-radio-min-bitrate').value;
    const minBitDepth = document.getElementById('song-radio-min-bitdepth').value;

    showToast('loading', 'Creating your Song Radio playlist...', 0);
    submitBtn.disabled = true;
    try {
        const response = await fetch('/api/create_song_radio', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                source_mbid: sourceMbid,
                source_track: track,
                listenbrainz_enabled: document.getElementById('song-radio-listenbrainz-enabled').checked,
                use_subsonic_similar: Boolean(document.getElementById('song-radio-subsonic-similar') && document.getElementById('song-radio-subsonic-similar').checked),
                algorithm: document.getElementById('song-radio-algorithm').value,
                minimum_score: Number(document.getElementById('song-radio-score').value),
                repeat_limit: Number(document.getElementById('song-radio-repeat').value),
                year_start: valueOrNull('song-radio-year-start'),
                year_end: valueOrNull('song-radio-year-end'),
                diversity_enabled: document.getElementById('song-radio-diversity-enabled').checked,
                max_tracks_per_album: Number(document.getElementById('song-radio-album-cap').value),
                max_tracks_per_artist: Number(document.getElementById('song-radio-artist-cap').value),
                min_format: minFormat || null,
                min_bitrate: minFormat === 'flac' ? null : (minBitrate ? Number(minBitrate) : null),
                min_bit_depth: minFormat === 'flac' ? (minBitDepth ? Number(minBitDepth) : null) : null,
                playlist_length: Number(document.querySelector('input[name="song-radio-playlist-length"]:checked').value),
                refresh_frequency: document.querySelector('input[name="song-radio-refresh-frequency"]:checked').value,
                library_ids: selectedLibraryIds
            })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Failed to create playlist');
        showToast('success', `Song Radio playlist created with ${data.songs ? data.songs.length : 0} tracks`);
        updatePlaylistCount();
    } catch (error) {
        showToast('error', error.message);
    } finally {
        submitBtn.disabled = false;
    }
}