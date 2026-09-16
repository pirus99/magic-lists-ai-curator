(function (window) {
    const selects = {
        initHSSelect() {
            if (window.HSSelect) {
                try { window.HSSelect.autoInit(); } catch (e) { console.warn('HSSelect.autoInit failed', e); }
            }
        }
    };

    window.App = window.App || {};
    window.App.selects = selects;
})(window);

// ── Shared helpers ──────────────────────────────────────────────────────────

// Destroy and re-initialise an HSSelect component for the given <select>.
function reinitHSSelect(select) {
    if (!window.HSSelect || !select) return;
    const instance = window.HSSelect.getInstance(select);
    if (instance) instance.destroy();
    window.HSSelect.autoInit();
}

// Destroy an HSSelect component without re-initialising (e.g. before updating
// its data-hs-select attribute).
function destroyHSSelect(select) {
    if (!window.HSSelect || !select) return;
    const instance = window.HSSelect.getInstance(select);
    if (instance) instance.destroy();
}

// Enable/disable the artist/album diversity caps inputs based on the toggle.
function syncCapsInputs(capsToggle, capsInputs) {
    const disabled = !capsToggle.checked;
    capsInputs.querySelectorAll('input').forEach(input => { input.disabled = disabled; });
    capsInputs.style.opacity = disabled ? '0.5' : '1';
}

// Show the bit-depth select for FLAC, otherwise the bitrate select.
function syncQualityInputs(formatSelect, bitrateWrap, bitdepthWrap, bitrateSelect, bitdepthSelect) {
    const isFlac = formatSelect.value === 'flac';
    bitrateWrap.classList.toggle('hidden', isFlac);
    bitdepthWrap.classList.toggle('hidden', !isFlac);
    if (bitrateSelect) bitrateSelect.disabled = isFlac;
    if (bitdepthSelect) bitdepthSelect.disabled = !isFlac;
}

// Build the library checkbox list for a given container.
function createLibraryCheckboxes(container, libraries, selectedIds, idPrefix) {
    if (!container) return;
    container.innerHTML = '';
    libraries.forEach(library => {
        const checkboxId = `${idPrefix}-lib-${library.id}`;
        const checkboxDiv = document.createElement('div');
        checkboxDiv.className = 'flex items-center px-3 py-2 hover:bg-gray-50 rounded';
        checkboxDiv.innerHTML = `
            <input type="checkbox"
                   id="${checkboxId}"
                   value="${library.id}"
                   class="shrink-0 mt-0.5 border-gray-200 rounded text-blue-600 focus:ring-blue-500"
                   ${selectedIds.includes(library.id) ? 'checked' : ''}>
            <label for="${checkboxId}" class="ml-2 text-sm text-gray-800 cursor-pointer">
                ${library.name}
            </label>
        `;
        container.appendChild(checkboxDiv);
    });
}

// Briefly highlight a library selector to signal that a selection is required.
function highlightLibrarySelector(el) {
    if (!el) return;
    el.classList.add('ring-2', 'ring-red-500', 'ring-opacity-50');
    setTimeout(() => el.classList.remove('ring-2', 'ring-red-500', 'ring-opacity-50'), 3000);
}

// Load artists and populate the select (from original working code)
async function loadArtists() {
    try {
        let url = '/api/artists';
        if (selectedLibraryIds.length > 0) {
            const libraryIdsParam = selectedLibraryIds.map(id => `library_id=${encodeURIComponent(id)}`).join('&');
            url = `/api/artists?${libraryIdsParam}`;
        }
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch artists');
        }
        allArtists = await response.json();

        // Clear any previous selection
        selectedArtistId = null;

        // Populate the select dropdown
        const artistSelect = document.getElementById('artist-search-select');
        if (artistSelect) {
            // Clear existing options except the first one
            while (artistSelect.options.length > 1) {
                artistSelect.remove(1);
            }

            // Add artist options
            allArtists.forEach(artist => {
                const option = document.createElement('option');
                option.value = artist.id;
                option.textContent = artist.name;
                artistSelect.appendChild(option);
            });

            reinitHSSelect(artistSelect);
        }
    } catch (error) {
        console.error('Error loading artists:', error);
        showToast('error', 'Failed to load artists from your library');
    }
}

async function loadGenres() {
    try {
        let url = '/api/genres';
        if (selectedLibraryIds.length > 0) {
            const libraryIdsParam = selectedLibraryIds.map(id => `library_id=${encodeURIComponent(id)}`).join('&');
            url = `/api/genres?${libraryIdsParam}`;
        }
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error('Failed to fetch genres');
        }
        allGenres = await response.json();

        // Get the genre select element
        const genreSelect = document.getElementById('genre-select');

        // Update the placeholder text to show genre count
        if (genreSelect && window.HSSelect) {
            destroyHSSelect(genreSelect);

            // Update the data-hs-select attribute with new placeholder
            const newPlaceholder = `Search ${allGenres.length} genres...`;
            genreSelect.setAttribute('data-hs-select', JSON.stringify({
                "placeholder": newPlaceholder,
                "mode": "tags",
                "toggleTag": "<button type=\"button\" aria-expanded=\"false\"><span class=\"capitalize text-foreground\" data-title></span></button>",
                "toggleClasses": "hs-select-disabled:pointer-events-none hs-select-disabled:opacity-50 relative py-3 ps-4 pe-9 flex items-center gap-x-2 text-nowrap w-full cursor-pointer bg-layer border border-layer-line text-layer-foreground rounded-lg text-start text-sm hover:bg-layer-hover focus:outline-hidden focus:bg-layer-focus",
                "wrapperClasses": "relative pe-9 min-h-11.5 flex items-center flex-wrap w-full bg-layer border border-layer-line hover:bg-layer-hover rounded-lg text-start text-sm focus:bg-layer-focus",
                "tagsItemTemplate": "<div class=\"flex flex-nowrap items-center text-nowrap relative z-10 bg-layer border border-layer-line rounded-full p-1 m-1\"><div class=\"whitespace-nowrap capitalize text-foreground ps-1\" data-title></div><div class=\"inline-flex shrink-0 justify-between items-center size-5 ms-2 rounded-full bg-surface text-surface-foreground hover:bg-surface-hover focus:outline-hidden focus:bg-surface-focus text-sm cursor-pointer\" data-remove><svg class=\"shrink-0 size-3\" xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"M18 6 6 18\"/><path d=\"m6 6 12 12\"/></svg></div></div>",
                "tagsInputClasses": "py-3 px-4 rounded-lg order-1 bg-white border-transparent text-foreground placeholder:text-black focus:ring-0 text-sm outline-hidden",
                "dropdownClasses": "mt-2 z-50 w-full max-h-72 p-1 space-y-0.5 bg-white border border-select-line rounded-lg shadow-xl overflow-hidden overflow-y-auto [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-thumb]:rounded-none [&::-webkit-scrollbar-track]:bg-scrollbar-track [&::-webkit-scrollbar-thumb]:bg-scrollbar-thumb",
                "optionClasses": "py-2 px-4 w-full text-sm text-select-item-foreground cursor-pointer hover:bg-select-item-hover rounded-lg focus:outline-hidden focus:bg-select-item-focus hs-selected:bg-blue-50 hs-selected:text-blue-800",
                "optionTemplate": "<div class=\"flex items-center\"><div class=\"text-sm capitalize text-foreground\" data-title></div><div class=\"text-xs text-muted-foreground-1\" data-description></div><div class=\"ms-auto\"><span class=\"hidden hs-selected:block\"><svg class=\"shrink-0 size-4 text-primary\" xmlns=\"http://www.w3.org/2000/svg\" width=\"16\" height=\"16\" fill=\"currentColor\" viewBox=\"0 0 16 16\"><path d=\"M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425a.247.247 0 0 1 .02-.022Z\"/></svg></span></div></div>",
                "extraMarkup": "<div class=\"absolute top-1/2 end-3 -translate-y-1/2\"><svg class=\"shrink-0 size-3.5 text-muted-foreground-1\" xmlns=\"http://www.w3.org/2000/svg\" width=\"24\" height=\"24\" viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\"><path d=\"m7 15 5 5 5-5\"/><path d=\"m7 9 5-5 5 5\"/></svg></div>",
            }));
        }

        // Clear any previous selection
        selectedGenres = [];

        // Populate the select dropdown
        if (genreSelect) {
            // Clear existing options except the first one
            while (genreSelect.options.length > 1) {
                genreSelect.remove(1);
            }

            // Add genre options
            allGenres.forEach(genre => {
                const option = document.createElement('option');
                option.value = genre.name;
                option.textContent = `${genre.name} (${genre.songCount})`;
                genreSelect.appendChild(option);
            });

            // Setup genre selection change handler
            genreSelect.addEventListener('change', handleGenreSelection);

            // Setup fetch artists button click handler
            const fetchArtistsBtn = document.getElementById('genre-fetch-artists-btn');
            if (fetchArtistsBtn) {
                fetchArtistsBtn.addEventListener('click', () => {
                    loadBlacklistArtists(true);
                });
            }

            // Setup artist/album diversity caps toggle
            const capsToggle = document.getElementById('genre-caps-enabled');
            const capsInputs = document.getElementById('genre-caps-inputs');
            if (capsToggle && capsInputs) {
                capsToggle.addEventListener('change', () => syncCapsInputs(capsToggle, capsInputs));
                syncCapsInputs(capsToggle, capsInputs);
            }

            // Setup format -> bitrate/bit-depth toggle for the Minimum Quality filter.
            // FLAC shows the bit-depth select; MP3/Any shows the bitrate select.
            const formatSelect = document.getElementById('genre-min-format');
            const bitrateWrap = document.getElementById('genre-bitrate-wrap');
            const bitdepthWrap = document.getElementById('genre-bitdepth-wrap');
            const bitrateSelect = document.getElementById('genre-min-bitrate');
            const bitdepthSelect = document.getElementById('genre-min-bitdepth');
            if (formatSelect && bitrateWrap && bitdepthWrap) {
                const onFormatChange = () =>
                    syncQualityInputs(formatSelect, bitrateWrap, bitdepthWrap, bitrateSelect, bitdepthSelect);
                formatSelect.addEventListener('change', onFormatChange);
                onFormatChange();
            }

            // Reinitialize the HSSelect component
            if (window.HSSelect) {
                window.HSSelect.autoInit();
            }

            // Show the default placeholder in the blacklist dropdown (before artists are loaded).
            // Must run after HSSelect autoInit so the dropdown panel exists.
            showBlacklistPlaceholder();

            // Keep the blacklist toggle text color in sync with the current selection.
            // The native select fires 'change' whenever HSSelect updates the selection.
            const blacklistSelect = document.getElementById('genre-blacklist-select');
            if (blacklistSelect && !blacklistSelect.dataset.colorSyncAttached) {
                blacklistSelect.dataset.colorSyncAttached = 'true';
                blacklistSelect.addEventListener('change', syncBlacklistToggleColor);
            }
            syncBlacklistToggleColor();
        }
    } catch (error) {
        console.error('Error loading genres:', error);
        showToast('error', 'Failed to load genres from your library');
    }
}

// Handle genre selection change
function handleGenreSelection(e) {
    selectedGenres = Array.from(e.target.selectedOptions).map(option => option.value);
    blacklistArtistsLoaded = false;
    showBlacklistPlaceholder();
    clearBlacklistSelection('genre-blacklist-select');
    syncBlacklistToggleColor();
    const submitBtn = document.getElementById('create-genre-playlist-btn');
    if (submitBtn) submitBtn.disabled = selectedGenres.length === 0;
}

// Clear all selected options in a blacklist <select>.
function clearBlacklistSelection(selectId) {
    const blacklistSelect = document.getElementById(selectId);
    if (blacklistSelect) {
        Array.from(blacklistSelect.options).forEach(opt => { opt.selected = false; });
    }
}

const BLACKLIST_PLACEHOLDER_ID = 'genre-blacklist-placeholder';
const EDIT_BLACKLIST_PLACEHOLDER_ID = 'edit-genre-blacklist-placeholder';

// Insert the "Click Refresh to load Artists" hint into a blacklist dropdown.
function showBlacklistPlaceholder(selectId = 'genre-blacklist-select', placeholderId = BLACKLIST_PLACEHOLDER_ID) {
    const blacklistSelect = document.getElementById(selectId);
    if (!blacklistSelect) return;

    removeBlacklistPlaceholder(placeholderId);

    const panel = window.HSSelect
        ? window.HSSelect.getInstance(blacklistSelect)?.dropdown
        : null;
    if (!panel) return;

    const placeholder = document.createElement('div');
    placeholder.id = placeholderId;
    placeholder.className = 'px-4 py-3 text-sm text-gray-400 italic';
    placeholder.textContent = 'Click Refresh to load Artists for selected Genres';
    panel.appendChild(placeholder);
}

function showEditBlacklistPlaceholder() {
    showBlacklistPlaceholder('edit-genre-blacklist-select', EDIT_BLACKLIST_PLACEHOLDER_ID);
}

function removeBlacklistPlaceholder(placeholderId = BLACKLIST_PLACEHOLDER_ID) {
    const existing = document.getElementById(placeholderId);
    if (existing) existing.remove();
}

function removeEditBlacklistPlaceholder() {
    removeBlacklistPlaceholder(EDIT_BLACKLIST_PLACEHOLDER_ID);
}

// Load artists for the genre-mix blacklist dropdown.
let blacklistArtistsLoaded = false;
async function loadBlacklistArtists(force = false) {
    if (blacklistArtistsLoaded && !force) return;

    const fetchBtn = document.getElementById('genre-fetch-artists-btn');
    const fetchSpinner = document.getElementById('genre-fetch-artists-spinner');
    if (fetchBtn) fetchBtn.classList.add('hidden');
    if (fetchSpinner) fetchSpinner.classList.remove('hidden');

    try {
        await fetchAndPopulateBlacklist('genre-blacklist-select', selectedGenres);
        blacklistArtistsLoaded = true;
    } catch (error) {
        console.error('Error loading blacklist artists:', error);
        showToast('error', 'Failed to load artists for blacklist');
    } finally {
        if (fetchBtn) fetchBtn.classList.remove('hidden');
        if (fetchSpinner) fetchSpinner.classList.add('hidden');
    }
}

// Fetch artists for the given genres and populate a blacklist <select>.
// `previouslySelected` (optional) keeps existing selections after a refresh.
async function fetchAndPopulateBlacklist(selectId, genres, previouslySelected = []) {
    if (genres.length === 0) {
        showToast('error', 'Please select genres first');
        return;
    }

    let url = `/api/artists-by-genre?${genres.map(g => `genres=${encodeURIComponent(g)}`).join('&')}`;
    if (selectedLibraryIds.length > 0) {
        url += `&${selectedLibraryIds.map(id => `library_id=${encodeURIComponent(id)}`).join('&')}`;
    }

    const response = await fetch(url);
    if (!response.ok) throw new Error('Failed to fetch artists');
    const artists = await response.json();

    const blacklistSelect = document.getElementById(selectId);
    if (!blacklistSelect) return;

    while (blacklistSelect.options.length > 0) blacklistSelect.remove(0);
    removeBlacklistPlaceholder(selectId === 'genre-blacklist-select' ? BLACKLIST_PLACEHOLDER_ID : EDIT_BLACKLIST_PLACEHOLDER_ID);

    artists.forEach(artist => {
        const option = document.createElement('option');
        option.value = artist.name;
        option.textContent = artist.name;
        if (previouslySelected.includes(artist.name)) option.selected = true;
        blacklistSelect.appendChild(option);
    });

    reinitHSSelect(blacklistSelect);
}

async function loadEditBlacklistArtists(force = false) {
    if (editBlacklistArtistsLoaded && !force) return;

    const fetchBtn = document.getElementById('edit-genre-fetch-artists-btn');
    const fetchSpinner = document.getElementById('edit-genre-fetch-artists-spinner');
    if (fetchBtn) fetchBtn.classList.add('hidden');
    if (fetchSpinner) fetchSpinner.classList.remove('hidden');

    try {
        const blacklistSelect = document.getElementById('edit-genre-blacklist-select');
        const previouslySelected = blacklistSelect
            ? Array.from(blacklistSelect.options).filter(opt => opt.selected).map(opt => opt.value)
            : [];

        await fetchAndPopulateBlacklist('edit-genre-blacklist-select', editSelectedGenres, previouslySelected);

        editBlacklistArtistsLoaded = true;
        syncEditBlacklistToggleColor();
    } catch (error) {
        console.error('Error loading edit blacklist artists:', error);
        showToast('error', 'Failed to load artists for exclude list');
    } finally {
        if (fetchBtn) fetchBtn.classList.remove('hidden');
        if (fetchSpinner) fetchSpinner.classList.add('hidden');
    }
}

function editHandleGenreSelection(e) {
    editSelectedGenres = Array.from(e.target.selectedOptions).map(option => option.value);
    editBlacklistArtistsLoaded = false;
    showEditBlacklistPlaceholder();
    clearBlacklistSelection('edit-genre-blacklist-select');
    syncEditBlacklistToggleColor();
}

// Load libraries and populate the multi-select interface
async function loadLibraries() {
    try {
        console.log('📚 Loading libraries from API...');
        console.log(`📚 Current localStorage:`, localStorage.getItem('selectedLibraryIds'));
        const response = await fetch('/api/music-folders');
        if (!response.ok) {
            throw new Error(`Failed to fetch libraries: ${response.status} ${response.statusText}`);
        }
        allLibraries = await response.json();
        console.log(`📚 Loaded ${allLibraries.length} libraries:`, allLibraries);

        // Clear any previous selection
        selectedLibraryIds = [];

        // Get UI elements
        const desktopLoading = document.getElementById('library-loading');
        const desktopSingle = document.getElementById('library-single');
        const desktopSingleName = document.getElementById('library-single-name');
        const desktopMulti = document.getElementById('library-multi');
        const desktopMultiText = document.getElementById('library-multi-text');
        const desktopCheckboxes = document.getElementById('library-checkboxes');

        const mobileLoading = document.getElementById('mobile-library-loading');
        const mobileSingle = document.getElementById('mobile-library-single');
        const mobileSingleName = document.getElementById('mobile-library-single-name');
        const mobileMulti = document.getElementById('mobile-library-multi');
        const mobileMultiText = document.getElementById('mobile-library-multi-text');
        const mobileCheckboxes = document.getElementById('mobile-library-checkboxes');

        // Hide loading states
        if (desktopLoading) desktopLoading.classList.add('hidden');
        if (mobileLoading) mobileLoading.classList.add('hidden');

        // Hide all states initially
        if (desktopSingle) desktopSingle.classList.add('hidden');
        if (mobileSingle) mobileSingle.classList.add('hidden');
        if (desktopMulti) desktopMulti.classList.add('hidden');
        if (mobileMulti) mobileMulti.classList.add('hidden');

        if (allLibraries.length === 1) {
            // Single library - show read-only display (AC1)
            const library = allLibraries[0];
            selectedLibraryIds = [library.id];

            if (desktopSingle && desktopSingleName) {
                desktopSingleName.textContent = library.name;
                desktopSingle.classList.remove('hidden');
            }
            if (mobileSingle && mobileSingleName) {
                mobileSingleName.textContent = library.name;
                mobileSingle.classList.remove('hidden');
            }

            console.log(`📚 Single library detected: ${library.name} (ID: ${library.id}) - showing readonly display`);

            // Save to localStorage
            localStorage.setItem('selectedLibraryIds', JSON.stringify(selectedLibraryIds));
            console.log(`📚 Saved to localStorage:`, selectedLibraryIds);

        } else {
            // Multiple libraries - show multi-select interface (AC2)
            console.log(`📚 Multiple libraries detected: ${allLibraries.length} libraries - showing multi-select`);

            // Load saved library selections from localStorage
            const savedLibraryIds = localStorage.getItem('selectedLibraryIds');
            if (savedLibraryIds) {
                try {
                    const parsedIds = JSON.parse(savedLibraryIds);
                    // Filter to only include libraries that still exist
                    selectedLibraryIds = parsedIds.filter(id => allLibraries.some(lib => lib.id === id));
                    console.log(`📚 Loaded saved library selections:`, selectedLibraryIds);
                } catch (e) {
                    console.warn('📚 Invalid saved library IDs, starting fresh');
                    selectedLibraryIds = [];
                }
            } else {
                console.log('📚 No saved library selections found');
                selectedLibraryIds = [];
            }

            // Create checkboxes for desktop and mobile
            createLibraryCheckboxes(desktopCheckboxes, allLibraries, selectedLibraryIds, 'desktop');
            createLibraryCheckboxes(mobileCheckboxes, allLibraries, selectedLibraryIds, 'mobile');

            // Update display text
            updateLibraryDisplayText();

            // Show multi-select interfaces
            if (desktopMulti) desktopMulti.classList.remove('hidden');
            if (mobileMulti) mobileMulti.classList.remove('hidden');

            // Add event listeners for dropdown toggles
            const desktopToggle = document.getElementById('library-multi-toggle');
            const desktopDropdown = document.getElementById('library-multi-dropdown');
            const mobileToggle = document.getElementById('mobile-library-multi-toggle');
            const mobileDropdown = document.getElementById('mobile-library-multi-dropdown');

            if (desktopToggle && desktopDropdown) {
                desktopToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    desktopDropdown.classList.toggle('hidden');
                });
            }
            if (mobileToggle && mobileDropdown) {
                mobileToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    mobileDropdown.classList.toggle('hidden');
                });
            }

            // Add event listeners for checkboxes
            allLibraries.forEach(library => {
                const desktopCheckbox = document.getElementById(`desktop-lib-${library.id}`);
                const mobileCheckbox = document.getElementById(`mobile-lib-${library.id}`);

                if (desktopCheckbox) {
                    desktopCheckbox.addEventListener('change', handleLibraryCheckboxChange);
                }
                if (mobileCheckbox) {
                    mobileCheckbox.addEventListener('change', handleLibraryCheckboxChange);
                }
            });

            // Close dropdowns when clicking outside
            document.addEventListener('click', (e) => {
                if (desktopDropdown && !desktopMulti.contains(e.target)) {
                    desktopDropdown.classList.add('hidden');
                }
                if (mobileDropdown && !mobileMulti.contains(e.target)) {
                    mobileDropdown.classList.add('hidden');
                }
            });
        }

    } catch (error) {
        console.error('Error loading libraries:', error);
        showToast('error', 'Failed to load music libraries');

        // Hide loading and show error state
        const desktopLoading = document.getElementById('library-loading');
        const mobileLoading = document.getElementById('mobile-library-loading');
        const desktopSingle = document.getElementById('library-single');
        const mobileSingle = document.getElementById('mobile-library-single');
        const desktopMulti = document.getElementById('library-multi');
        const mobileMulti = document.getElementById('mobile-library-multi');

        // Hide all states
        if (desktopLoading) desktopLoading.classList.add('hidden');
        if (mobileLoading) mobileLoading.classList.add('hidden');
        if (desktopSingle) desktopSingle.classList.add('hidden');
        if (mobileSingle) mobileSingle.classList.add('hidden');
        if (desktopMulti) desktopMulti.classList.add('hidden');
        if (mobileMulti) mobileMulti.classList.add('hidden');
    }
}

// Handle library selection change


// Update the display text for multi-library selector
function updateLibraryDisplayText() {
    const desktopText = document.getElementById('library-multi-text');
    const mobileText = document.getElementById('mobile-library-multi-text');

    if (selectedLibraryIds.length === 0) {
        if (desktopText) desktopText.textContent = 'Select library';
        if (mobileText) mobileText.textContent = 'Select library';
        if (desktopText) desktopText.className = 'text-gray-500 truncate';
        if (mobileText) mobileText.className = 'text-gray-500 truncate';
    } else if (selectedLibraryIds.length === 1) {
        const library = allLibraries.find(lib => lib.id === selectedLibraryIds[0]);
        const libraryName = library ? library.name : '1 library';
        if (desktopText) desktopText.textContent = libraryName;
        if (mobileText) mobileText.textContent = libraryName;
        if (desktopText) desktopText.className = 'text-gray-900 truncate';
        if (mobileText) mobileText.className = 'text-gray-900 truncate';
    } else {
        if (desktopText) desktopText.textContent = `${selectedLibraryIds.length} libraries`;
        if (mobileText) mobileText.textContent = `${selectedLibraryIds.length} libraries`;
        if (desktopText) desktopText.className = 'text-gray-900 truncate';
        if (mobileText) mobileText.className = 'text-gray-900 truncate';
    }
}

// Handle library checkbox changes
function handleLibraryCheckboxChange(e) {
    const libraryId = e.target.value;
    const isChecked = e.target.checked;

    if (isChecked) {
        if (!selectedLibraryIds.includes(libraryId)) {
            selectedLibraryIds.push(libraryId);
        }
    } else {
        selectedLibraryIds = selectedLibraryIds.filter(id => id !== libraryId);
    }

    // Sync checkboxes between desktop and mobile
    const desktopCheckbox = document.getElementById(`desktop-lib-${libraryId}`);
    const mobileCheckbox = document.getElementById(`mobile-lib-${libraryId}`);

    if (desktopCheckbox && desktopCheckbox !== e.target) {
        desktopCheckbox.checked = isChecked;
    }
    if (mobileCheckbox && mobileCheckbox !== e.target) {
        mobileCheckbox.checked = isChecked;
    }

    // Update localStorage
    localStorage.setItem('selectedLibraryIds', JSON.stringify(selectedLibraryIds));

    // Update display text
    updateLibraryDisplayText();

    // Refresh current page content if needed
    const currentPage = getPageFromURL(window.location.pathname);
    if (currentPage === 'this-is-artist') {
        loadArtists();
    } else if (currentPage === 'genre-mix') {
        loadGenres();
    }

    console.log(`📚 Library selection updated:`, selectedLibraryIds);
}

// Check if libraries are selected and show warning if not
function checkLibrarySelection() {
    if (selectedLibraryIds.length === 0) {
        showToast('warning', 'Please select a music library.');
        highlightLibrarySelector(document.getElementById('library-multi'));
        highlightLibrarySelector(document.getElementById('mobile-library-multi'));
        return false;
    }
    return true;
}

function toggleCheckDetails(checkId) {
    const detailsDiv = document.getElementById(`details-${checkId}`);
    const chevron = document.getElementById(`chevron-${checkId}`);

    if (detailsDiv.classList.contains('hidden')) {
        detailsDiv.classList.remove('hidden');
        chevron.classList.remove('rotate-90');
        chevron.classList.add('-rotate-90');
    } else {
        detailsDiv.classList.add('hidden');
        chevron.classList.remove('-rotate-90');
        chevron.classList.add('rotate-90');
    }
}