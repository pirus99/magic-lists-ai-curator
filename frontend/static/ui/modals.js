(function (window) {
    const modals = {
        openEditModal() {
            const overlay = document.getElementById('edit-modal-overlay');
            const modal = document.getElementById('edit-modal');
            if (overlay) overlay.classList.remove('hidden');
            if (modal) modal.classList.remove('hidden');
        },
        closeEditModal() {
            const overlay = document.getElementById('edit-modal-overlay');
            const modal = document.getElementById('edit-modal');
            if (overlay) overlay.classList.add('hidden');
            if (modal) modal.classList.add('hidden');
        }
    };

    window.App = window.App || {};
    window.App.modals = modals;
})(window);

// Edit modal overlay click-to-close
const editModalOverlay = document.getElementById('edit-modal-overlay');
const editModal = document.getElementById('edit-modal');
if (editModalOverlay) {
    editModalOverlay.addEventListener('click', function () {
        closeEditModal();
    });
}
if (editModal) {
    editModal.addEventListener('click', function (event) {
        // Close only when clicking the backdrop, not the inner panel
        if (event.target === editModal) {
            closeEditModal();
        }
    });
}

// Open the Edit modal for a playlist, prefilling its saved curation settings
let currentEditPlaylistId = null;
async function openEditModal(playlistId) {
    try {
        const response = await fetch(`/api/playlists/${playlistId}`);
        if (!response.ok) {
            throw new Error('Failed to load playlist settings');
        }
        const playlist = await response.json();
        currentEditPlaylistId = playlistId;

        const type = playlist.playlist_type || 'this_is';
        const settings = playlist.curation_settings || {};

        // Header
        document.getElementById('edit-modal-title').textContent = playlist.playlist_name || 'Edit Playlist';
        document.getElementById('edit-modal-type').textContent = typeLabel(type);
        document.getElementById('edit-modal-type-value').value = type;

        // Common: playlist metadata
        document.getElementById('edit-playlist-name').value = playlist.playlist_name || '';
        document.getElementById('edit-playlist-description').value = playlist.description || '';
        document.getElementById('edit-playlist-public').checked = Boolean(playlist.is_public ?? playlist.public ?? false);

        // Common: playlist length
        const length = settings.playlist_length || playlist.playlist_length || 25;
        document.querySelectorAll('input[name="edit-playlist-length"]').forEach(r => {
            r.checked = (parseInt(r.value, 10) === parseInt(length, 10));
        });

        // Common: refresh frequency
        const freq = settings.refresh_frequency || playlist.refresh_frequency || 'none';
        document.querySelectorAll('input[name="edit-refresh-frequency"]').forEach(r => {
            r.checked = (r.value === freq);
        });

        // Type-specific sections
        const thisIsSection = document.getElementById('edit-this-is-section');
        const genreSection = document.getElementById('edit-genre-section');
        const rediscoverSection = document.getElementById('edit-rediscover-section');
        const artistRadioSection = document.getElementById('edit-artist-radio-section');
        const artistRadioSource = document.getElementById('edit-artist-radio-source');

        if (thisIsSection) thisIsSection.classList.add('hidden');
        if (genreSection) genreSection.classList.add('hidden');
        if (rediscoverSection) rediscoverSection.classList.add('hidden');
        if (artistRadioSection) artistRadioSection.classList.add('hidden');
        if (artistRadioSource) artistRadioSource.classList.add('hidden');

        if (type === 'genre_mix') {
            if (genreSection) genreSection.classList.remove('hidden');
            editGenreSettings = settings || {};
            if (allGenres.length === 0) {
                await loadGenres();
            }
            await populateEditGenreModal(settings);
        } else if (type === 'this_is') {
            if (thisIsSection) thisIsSection.classList.remove('hidden');
            editGenreSettings = null;
            const thisIsArtist = document.getElementById('edit-this-is-artist');
            const thisIsArtistId = document.getElementById('edit-this-is-artist-id');
            const thisIsLibraryIds = document.getElementById('edit-this-is-library-ids');
            if (thisIsArtist) thisIsArtist.textContent = settings.artist_name || settings.artist_id || 'Unknown';
            if (thisIsArtistId) thisIsArtistId.value = settings.artist_id || '';
            if (thisIsLibraryIds) thisIsLibraryIds.value = JSON.stringify(settings.library_ids || []);
        } else if (type === 'artist_radio') {
            if (artistRadioSection) artistRadioSection.classList.remove('hidden');
            if (artistRadioSource) artistRadioSource.classList.remove('hidden');
            editGenreSettings = null;
            await populateEditArtistRadioModal(settings);
        } else {
            // rediscover / rediscover_weekly_v2
            if (rediscoverSection) rediscoverSection.classList.remove('hidden');
            const rediscoverLibraryIds = document.getElementById('edit-rediscover-library-ids');
            if (rediscoverLibraryIds) rediscoverLibraryIds.value = JSON.stringify(settings.library_ids || []);
        }

        // Show modal
        const modalOverlay = document.getElementById('edit-modal-overlay');
        const editModal = document.getElementById('edit-modal');
        if (modalOverlay) modalOverlay.classList.remove('hidden');
        if (editModal) editModal.classList.remove('hidden');
    } catch (error) {
        console.error('Error opening edit modal:', error);
        showToast('error', error.message);
    }
}

function closeEditModal() {
    const modalOverlay = document.getElementById('edit-modal-overlay');
    const editModal = document.getElementById('edit-modal');
    if (modalOverlay) modalOverlay.classList.add('hidden');
    if (editModal) editModal.classList.add('hidden');
    currentEditPlaylistId = null;
}

function typeLabel(type) {
    switch (type) {
        case 'genre_mix': return 'Genre Mix';
        case 'this_is': return 'This Is';
        case 'artist_radio': return 'Artist Radio';
        case 'rediscover_weekly_v2': return 'Re-Discover';
        case 'rediscover': return 'Re-Discover';
        default: return type;
    }
}

// Populate the genre-specific fields in the edit modal
async function populateEditGenreModal(settings) {
    const genres = settings.genres || [];
    const genreSelect = document.getElementById('edit-genre-select');

    if (genreSelect) {
        if (window.HSSelect) {
            const existingInstance = window.HSSelect.getInstance(genreSelect);
            if (existingInstance) {
                existingInstance.destroy();
            }
        }

        while (genreSelect.options.length > 1) {
            genreSelect.remove(genreSelect.options.length - 1);
        }

        allGenres.forEach(genre => {
            const option = document.createElement('option');
            option.value = genre.name;
            option.textContent = `${genre.name} (${genre.songCount})`;
            if (genres.includes(genre.name)) {
                option.selected = true;
            }
            genreSelect.appendChild(option);
        });

        genreSelect.removeEventListener('change', editHandleGenreSelection);
        genreSelect.addEventListener('change', editHandleGenreSelection);
    }

    editSelectedGenres = genres.slice();

    document.getElementById('edit-genre-year-start').value = settings.year_start || '';
    document.getElementById('edit-genre-year-end').value = settings.year_end || '';

    document.getElementById('edit-genre-min-bitrate').value = settings.min_bitrate || '';
    document.getElementById('edit-genre-min-format').value = settings.min_format || '';
    document.getElementById('edit-genre-min-bitdepth').value = settings.min_bit_depth || '';

    const capsEnabled = (settings.max_tracks_per_album !== null && settings.max_tracks_per_album !== undefined)
        || (settings.max_tracks_per_artist !== null && settings.max_tracks_per_artist !== undefined);
    document.getElementById('edit-genre-caps-enabled').checked = capsEnabled;
    document.getElementById('edit-genre-max-tracks-per-album').value = settings.max_tracks_per_album != null ? settings.max_tracks_per_album : 2;
    document.getElementById('edit-genre-max-tracks-per-artist').value = settings.max_tracks_per_artist != null ? settings.max_tracks_per_artist : 3;

    const blacklist = settings.blacklisted_artists || [];
    const blacklistSelect = document.getElementById('edit-genre-blacklist-select');
    if (blacklistSelect) {
        while (blacklistSelect.options.length > 0) {
            blacklistSelect.remove(0);
        }
        blacklist.forEach(name => {
            const option = document.createElement('option');
            option.value = name;
            option.textContent = name;
            option.selected = true;
            blacklistSelect.appendChild(option);
        });

        reinitHSSelect(blacklistSelect);

        editBlacklistArtistsLoaded = blacklist.length > 0;
        if (!editBlacklistArtistsLoaded) {
            showEditBlacklistPlaceholder();
        }
    }

    const blacklistSelectElement = document.getElementById('edit-genre-blacklist-select');
    if (blacklistSelectElement && !blacklistSelectElement.dataset.colorSyncAttached) {
        blacklistSelectElement.dataset.colorSyncAttached = 'true';
        blacklistSelectElement.addEventListener('change', syncEditBlacklistToggleColor);
    }
    syncEditBlacklistToggleColor();

    const capsToggle = document.getElementById('edit-genre-caps-enabled');
    const capsInputs = document.getElementById('edit-genre-caps-inputs');
    if (capsToggle && capsInputs) {
        capsToggle.addEventListener('change', () => syncCapsInputs(capsToggle, capsInputs));
        syncCapsInputs(capsToggle, capsInputs);
    }

    const formatSelect = document.getElementById('edit-genre-min-format');
    const bitrateWrap = document.getElementById('edit-genre-bitrate-wrap');
    const bitdepthWrap = document.getElementById('edit-genre-bitdepth-wrap');
    const bitrateSelect = document.getElementById('edit-genre-min-bitrate');
    const bitdepthSelect = document.getElementById('edit-genre-min-bitdepth');
    if (formatSelect && bitrateWrap && bitdepthWrap) {
        const onFormatChange = () =>
            syncQualityInputs(formatSelect, bitrateWrap, bitdepthWrap, bitrateSelect, bitdepthSelect);
        formatSelect.addEventListener('change', onFormatChange);
        onFormatChange();
    }

    if (window.HSSelect) {
        window.HSSelect.autoInit();
    }

    const fetchArtistsBtn = document.getElementById('edit-genre-fetch-artists-btn');
    if (fetchArtistsBtn) {
        fetchArtistsBtn.addEventListener('click', () => loadEditBlacklistArtists(true));
    }
}

async function populateEditArtistRadioModal(settings) {
    const source = document.getElementById('edit-artist-radio-source');
    if (source) source.textContent = `Source artist: ${settings.artist_name || settings.artist_id || 'Unknown'}`;
    const set = (id, value) => { const element = document.getElementById(id); if (element) element.value = value ?? ''; };
    set('edit-artist-radio-artist-id', settings.artist_id);
    set('edit-artist-radio-artist-name', settings.artist_name);
    set('edit-artist-radio-source-mbid', settings.source_mbid);
    set('edit-artist-radio-library-ids', JSON.stringify(settings.library_ids || []));

    const sourceId = settings.artist_id || '';
    const manualIds = settings.manual_artist_ids || [];
    const recommendationIds = settings.recommendation_ids
        || (settings.selected_artist_ids || []).filter(id => id !== sourceId && !manualIds.includes(id));
    set('edit-artist-radio-selected-artists', JSON.stringify(recommendationIds));
    set('edit-artist-radio-manual-artists', JSON.stringify(manualIds));

    const libraryIds = settings.library_ids || [];
    const query = libraryIds.map(id => `library_id=${encodeURIComponent(id)}`).join('&');
    let artists = [];
    try {
        const response = await fetch(`/api/artists${query ? `?${query}` : ''}`);
        if (response.ok) artists = await response.json();
    } catch (error) {
        console.warn('Could not load Artist Radio artists for edit modal:', error);
    }
    const recommendedSelect = document.getElementById('edit-artist-radio-recommendations');
    const manualSelect = document.getElementById('edit-artist-radio-manual-artists-select');
    if (recommendedSelect) {
        recommendedSelect.innerHTML = '';
        artists.filter(artist => recommendationIds.includes(artist.id)).forEach(artist => {
            const option = new Option(artist.name, artist.id, true, true);
            recommendedSelect.appendChild(option);
        });
        recommendedSelect.disabled = artists.length === 0;
    }
    if (manualSelect) {
        manualSelect.innerHTML = '';
        const blocked = new Set([sourceId, ...recommendationIds]);
        artists.filter(artist => !blocked.has(artist.id)).forEach(artist => {
            const option = new Option(artist.name, artist.id, true, manualIds.includes(artist.id));
            manualSelect.appendChild(option);
        });
        manualSelect.disabled = artists.length === 0;
    }
    if (recommendedSelect) reinitHSSelect(recommendedSelect);
    if (manualSelect) reinitHSSelect(manualSelect);
    set('edit-artist-radio-algorithm', settings.algorithm || '5Y Balanced');
    set('edit-artist-radio-score', settings.minimum_score ?? 142);
    set('edit-artist-radio-year-start', settings.year_start);
    set('edit-artist-radio-year-end', settings.year_end);
    set('edit-artist-radio-min-format', settings.min_format);
    set('edit-artist-radio-min-bitrate', settings.min_bitrate);
    set('edit-artist-radio-min-bitdepth', settings.min_bit_depth);
    set('edit-artist-radio-album-cap', settings.max_tracks_per_album ?? 4);
    set('edit-artist-radio-artist-cap', settings.max_tracks_per_artist ?? 8);
    const enabled = document.getElementById('edit-artist-radio-listenbrainz-enabled');
    const refetch = document.getElementById('edit-artist-radio-refetch');
    const recommendedField = document.getElementById('edit-artist-radio-recommended-artists-field');
    const algorithm = document.getElementById('edit-artist-radio-algorithm');
    const algorithmField = document.getElementById('edit-artist-radio-algorithm-field');
    const similarityScore = document.getElementById('edit-artist-radio-score');
    const scoreField = document.getElementById('edit-artist-radio-score-field');
    if (enabled) enabled.checked = settings.listenbrainz_enabled !== false;
    if (refetch) refetch.checked = settings.refetch_listenbrainz !== false;
    const syncListenbrainzControls = () => {
        const useListenbrainz = enabled?.checked ?? true;
        recommendedField?.classList.toggle('hidden', !useListenbrainz);
        algorithmField?.classList.toggle('hidden', !useListenbrainz);
        scoreField?.classList.toggle('hidden', !useListenbrainz);
        if (algorithm) algorithm.disabled = !useListenbrainz;
        if (similarityScore) similarityScore.disabled = !useListenbrainz;
        if (refetch) refetch.disabled = !useListenbrainz;
    };
    if (enabled && !enabled.dataset.bound) {
        enabled.dataset.bound = 'true';
        enabled.addEventListener('change', syncListenbrainzControls);
    }
    syncListenbrainzControls();
    const caps = document.getElementById('edit-artist-radio-caps-enabled');
    if (caps) caps.checked = settings.diversity_enabled !== false;
    const score = document.getElementById('edit-artist-radio-score');
    const scoreValue = document.getElementById('edit-artist-radio-score-value');
    if (score && scoreValue) {
        score.addEventListener('input', () => { scoreValue.textContent = score.value; });
        scoreValue.textContent = score.value;
    }
    const capsInputs = document.getElementById('edit-artist-radio-caps-inputs');
    if (caps && capsInputs) {
        caps.addEventListener('change', () => syncCapsInputs(caps, capsInputs));
        syncCapsInputs(caps, capsInputs);
    }
    const format = document.getElementById('edit-artist-radio-min-format');
    const bitrate = document.getElementById('edit-artist-radio-min-bitrate');
    const bitrateWrap = document.getElementById('edit-artist-radio-bitrate-wrap');
    const bitdepth = document.getElementById('edit-artist-radio-min-bitdepth');
    const bitdepthWrap = document.getElementById('edit-artist-radio-bitdepth-wrap');
    if (format && bitrate && bitrateWrap && bitdepth && bitdepthWrap) {
        const sync = () => {
            const isFlac = format.value === 'flac';
            bitrateWrap.classList.toggle('hidden', isFlac);
            bitdepthWrap.classList.toggle('hidden', !isFlac);
            bitrate.disabled = isFlac;
            bitdepth.disabled = !isFlac;
        };
        format.addEventListener('change', sync);
        sync();
    }
}

// Collect the modal fields into a curation_settings object
function collectEditSettings() {
    const type = document.getElementById('edit-modal-type-value').value || document.getElementById('edit-modal-type').textContent;
    const lengthEl = document.querySelector('input[name="edit-playlist-length"]:checked');
    const freqEl = document.querySelector('input[name="edit-refresh-frequency"]:checked');
    const playlist_length = lengthEl ? parseInt(lengthEl.value, 10) : 25;
    const refresh_frequency = freqEl ? freqEl.value : 'none';
    const playlist_name = document.getElementById('edit-playlist-name').value.trim();
    const description = document.getElementById('edit-playlist-description').value.trim();
    const is_public = document.getElementById('edit-playlist-public').checked;

    let curation_settings = { playlist_length, refresh_frequency };

    if (type === 'genre_mix') {
        const capsEnabled = document.getElementById('edit-genre-caps-enabled').checked;
        const genreSelect = document.getElementById('edit-genre-select');
        const selectedGenres = genreSelect
            ? Array.from(genreSelect.selectedOptions).map(o => o.value)
            : [];

        const blacklistSelect = document.getElementById('edit-genre-blacklist-select');
        curation_settings = {
            ...curation_settings,
            genres: selectedGenres,
            year_start: parseIntOrNull(document.getElementById('edit-genre-year-start').value),
            year_end: parseIntOrNull(document.getElementById('edit-genre-year-end').value),
            min_bitrate: parseIntOrNull(document.getElementById('edit-genre-min-bitrate').value),
            min_format: document.getElementById('edit-genre-min-format').value || null,
            min_bit_depth: parseIntOrNull(document.getElementById('edit-genre-min-bitdepth').value),
            max_tracks_per_album: capsEnabled ? parseInt(document.getElementById('edit-genre-max-tracks-per-album').value, 10) : null,
            max_tracks_per_artist: capsEnabled ? parseInt(document.getElementById('edit-genre-max-tracks-per-artist').value, 10) : null,
            blacklisted_artists: blacklistSelect
                ? Array.from(blacklistSelect.options).filter(o => o.selected).map(o => o.value)
                : []
        };

        if (editGenreSettings && Array.isArray(editGenreSettings.library_ids)) {
            curation_settings.library_ids = editGenreSettings.library_ids;
        }
    } else if (type === 'this_is') {
        curation_settings.artist_id = document.getElementById('edit-this-is-artist-id').value;
        curation_settings.artist_name = document.getElementById('edit-this-is-artist').textContent;
        curation_settings.library_ids = JSON.parse(document.getElementById('edit-this-is-library-ids').value || '[]');
    } else if (type === 'artist_radio') {
        curation_settings = {
            ...curation_settings,
            artist_id: document.getElementById('edit-artist-radio-artist-id').value,
            artist_name: document.getElementById('edit-artist-radio-artist-name').value,
            source_mbid: document.getElementById('edit-artist-radio-source-mbid').value || null,
            listenbrainz_enabled: document.getElementById('edit-artist-radio-listenbrainz-enabled').checked,
            algorithm: document.getElementById('edit-artist-radio-algorithm').value,
            minimum_score: Number(document.getElementById('edit-artist-radio-score').value),
            recommendation_ids: Array.from(document.getElementById('edit-artist-radio-recommendations')?.selectedOptions || []).map(option => option.value),
            manual_artist_ids: Array.from(document.getElementById('edit-artist-radio-manual-artists-select')?.selectedOptions || []).map(option => option.value),
            selected_artist_ids: [...new Set([
                document.getElementById('edit-artist-radio-artist-id').value,
                ...Array.from(document.getElementById('edit-artist-radio-recommendations')?.selectedOptions || []).map(option => option.value),
                ...Array.from(document.getElementById('edit-artist-radio-manual-artists-select')?.selectedOptions || []).map(option => option.value),
            ].filter(Boolean))],
            refetch_listenbrainz: document.getElementById('edit-artist-radio-refetch').checked,
            year_start: parseIntOrNull(document.getElementById('edit-artist-radio-year-start').value),
            year_end: parseIntOrNull(document.getElementById('edit-artist-radio-year-end').value),
            diversity_enabled: document.getElementById('edit-artist-radio-caps-enabled').checked,
            max_tracks_per_album: document.getElementById('edit-artist-radio-caps-enabled').checked ? Number(document.getElementById('edit-artist-radio-album-cap').value) : 0,
            max_tracks_per_artist: document.getElementById('edit-artist-radio-caps-enabled').checked ? Number(document.getElementById('edit-artist-radio-artist-cap').value) : 0,
            min_format: document.getElementById('edit-artist-radio-min-format').value || null,
            min_bitrate: document.getElementById('edit-artist-radio-min-format').value === 'flac' ? null : parseIntOrNull(document.getElementById('edit-artist-radio-min-bitrate').value),
            min_bit_depth: document.getElementById('edit-artist-radio-min-format').value === 'flac' ? parseIntOrNull(document.getElementById('edit-artist-radio-min-bitdepth').value) : null,
            library_ids: JSON.parse(document.getElementById('edit-artist-radio-library-ids').value || '[]')
        };
    } else {
        curation_settings.library_ids = JSON.parse(document.getElementById('edit-rediscover-library-ids').value || '[]');
    }

    return { curation_settings, refresh_frequency, playlist_name, description, is_public };
}