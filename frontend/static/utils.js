(function (window) {
    const utils = {
        formatFriendlyDate(dateString) {
            if (!dateString) return 'Never';
            const date = new Date(dateString);
            const day = date.getDate();
            const monthNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
            const month = monthNames[date.getMonth()];
            const year = date.getFullYear();
            let hours = date.getHours();
            const minutes = date.getMinutes().toString().padStart(2,'0');
            const ampm = hours >= 12 ? 'pm' : 'am';
            hours = hours % 12;
            hours = hours ? hours : 12;
            return `${day} ${month} ${year} ${hours}:${minutes}${ampm}`;
        }
    };

    window.App = window.App || {};
    window.App.utils = utils;
})(window);

// Util funcrtion for the "Edit Playlist" modal 
(function (root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    root.capturePlaylistRefreshTarget = api.capturePlaylistRefreshTarget;
}(typeof globalThis !== 'undefined' ? globalThis : this, function () {
    function capturePlaylistRefreshTarget(currentEditPlaylistId, closeModal) {
        const playlistId = currentEditPlaylistId;
        if (typeof closeModal === 'function') {
            closeModal();
        }
        return playlistId;
    }

    return {
        capturePlaylistRefreshTarget
    };
}));

function parseIntOrNull(v) {
    if (v === '' || v === null || v === undefined) return null;
    const n = parseInt(v, 10);
    return isNaN(n) ? null : n;
}

// System Check functionality
async function runSystemChecks() {
    const listContainer = document.getElementById('system-checks-list');
    const resultsContainer = document.getElementById('system-check-results');
    const successBanner = document.getElementById('success-banner');
    const errorBanner = document.getElementById('error-banner');
    const updateSettingsBtn = document.getElementById('update-settings-btn');
    const rerunBtn = document.getElementById('rerun-checks-btn');

    // Reset UI
    successBanner.classList.add('hidden');
    errorBanner.classList.add('hidden');
    updateSettingsBtn.classList.add('hidden');
    rerunBtn.disabled = true;
    rerunBtn.innerHTML = `
        <svg class="animate-spin h-4 w-4 text-gray-400 mr-2 inline" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span class="text-gray-400">Running checks...</span>
    `;

    try {
        // Call backend health check endpoint
        const response = await fetch('/api/health-check');
        if (!response.ok) {
            throw new Error('Failed to run system checks');
        }

        const data = await response.json();

        // Display check results
        displaySystemChecks(data.checks);
        displayListenBrainzCard(data.checks);
        displayLastFmCard(data.checks);

        // Show appropriate banner and buttons
        if (data.all_passed) {
            successBanner.classList.remove('hidden');
        } else {
            errorBanner.classList.remove('hidden');
            updateSettingsBtn.classList.remove('hidden');
        }

    } catch (error) {
        console.error('System check error:', error);
        listContainer.innerHTML = `
            <div class="p-4 text-red-600 border border-red-300 rounded-lg bg-red-50">
                <p class="font-medium">Error running system checks</p>
                <p class="text-sm mt-1">${error.message}</p>
            </div>
        `;
        errorBanner.classList.remove('hidden');

        const lbBadge = document.getElementById('listenbrainz-badge');
        if (lbBadge) lbBadge.textContent = 'Not checked';
    } finally {
        rerunBtn.disabled = false;
        rerunBtn.innerHTML = 'Re-run Checks';
    }
}

function displaySystemChecks(checks) {
    const container = document.getElementById('system-checks-list');

    container.innerHTML = checks.map(check => {
        const statusIcon = getStatusIcon(check.status);
        const statusColor = getStatusColor(check.status);
        const hasDetails = check.message || check.suggestion;

        const checkId = check.name.replace(/[^a-zA-Z0-9]/g, '');
        return `
            <div class="border border-gray-200 rounded-lg overflow-hidden">
                <div class="p-4 ${hasDetails ? 'cursor-pointer' : ''}" ${hasDetails ? `data-action="toggle-check" data-check-id="${checkId}"` : ''}>
                    <div class="flex items-center justify-between">
                        <div class="flex items-center">
                            <div class="flex-shrink-0">
                                ${statusIcon}
                            </div>
                            <div class="ml-3">
                                <h3 class="text-sm font-medium text-gray-900 dark:text-gray-100">${check.name}</h3>
                                ${check.status !== 'success' ? `<p class="text-sm ${statusColor}">${getStatusText(check.status)}</p>` : ''}
                            </div>
                        </div>
                        ${hasDetails ? `
                            <div class="flex-shrink-0">
                                <svg class="w-5 h-5 text-gray-400 transform transition-transform rotate-90" id="chevron-${checkId}" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                                    <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
                                </svg>
                            </div>
                        ` : ''}
                    </div>
                </div>
                ${hasDetails ? `
                    <div class="hidden px-4 pb-4 pt-4 border-t border-gray-100 bg-gray-50 dark:bg-gray-700" id="details-${checkId}">
                        ${check.message ? `<p class="text-sm text-gray-600 dark:text-gray-300 mb-2">${check.message}</p>` : ''}
                        ${check.suggestion ? `<p class="text-sm text-blue-600 dark:text-blue-400 font-medium">${check.suggestion}</p>` : ''}
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

// ListenBrainz integration card (only rendered when using the Navidrome backend)
function displayListenBrainzCard(checks) {
    const card = document.getElementById('listenbrainz-card');
    if (!card) return;

    const check = (checks || []).find(c => c.name === 'ListenBrainz API');
    const iconEl = document.getElementById('listenbrainz-icon');
    const statusEl = document.getElementById('listenbrainz-status');
    const suggestionEl = document.getElementById('listenbrainz-suggestion');
    const badgeEl = document.getElementById('listenbrainz-badge');

    card.classList.remove('hidden');

    if (!check) {
        // Backend did not run the ListenBrainz check at all
        iconEl.innerHTML = getStatusIcon('warning');
        statusEl.textContent = 'ListenBrainz check was not run.';
        statusEl.className = 'text-sm text-yellow-700 dark:text-yellow-400 mt-1';
        badgeEl.textContent = 'Not checked';
        badgeEl.className = 'flex-shrink-0 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300';
        suggestionEl.classList.add('hidden');
        return;
    }

    const statusIcon = getStatusIcon(check.status);
    const statusColor = getStatusColor(check.status);
    iconEl.innerHTML = statusIcon;

    if (check.status === 'success') {
        statusEl.textContent = check.message || 'ListenBrainz Labs is reachable.';
        statusEl.className = 'text-sm text-gray-600 dark:text-gray-300 mt-1';
        badgeEl.textContent = 'Connected';
        badgeEl.className = 'flex-shrink-0 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300';
    } else {
        statusEl.textContent = check.message || getStatusText(check.status);
        statusEl.className = `text-sm ${statusColor} mt-1`;
        badgeEl.textContent = check.status === 'warning' ? 'Unavailable' : 'Error';
        badgeEl.className = `flex-shrink-0 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
            check.status === 'warning'
                ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300'
                : 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
        }`;
    }

    if (check.suggestion) {
        suggestionEl.textContent = check.suggestion;
        suggestionEl.classList.remove('hidden');
    } else {
        suggestionEl.classList.add('hidden');
    }
}

// Last.fm integration card (only rendered when using the Jellyfin backend)
// Last.fm supplies artist top tracks, which Jellyfin has no native endpoint for.
function displayLastFmCard(checks) {
    const card = document.getElementById('lastfm-card');
    if (!card) return;

    const check = (checks || []).find(c => c.name === 'Last.fm API');
    const iconEl = document.getElementById('lastfm-icon');
    const statusEl = document.getElementById('lastfm-status');
    const suggestionEl = document.getElementById('lastfm-suggestion');
    const badgeEl = document.getElementById('lastfm-badge');

    const strategyLabel = document.body?.dataset.topTracksLabel || 'Off';
    card.classList.remove('hidden');

    if (!check) {
        // Backend did not run the Last.fm check at all
        iconEl.innerHTML = getStatusIcon('warning');
        statusEl.textContent = 'Last.fm check was not run.';
        statusEl.className = 'text-sm text-yellow-700 dark:text-yellow-400 mt-1';
        badgeEl.textContent = 'Not checked';
        badgeEl.className = 'flex-shrink-0 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300';
        suggestionEl.classList.add('hidden');
        return;
    }

    const statusIcon = getStatusIcon(check.status);
    const statusColor = getStatusColor(check.status);
    iconEl.innerHTML = statusIcon;

    if (check.status === 'success') {
        statusEl.textContent = `${check.message || 'Last.fm is reachable.'} Top tracks source: ${strategyLabel}.`;
        statusEl.className = 'text-sm text-gray-600 dark:text-gray-300 mt-1';
        badgeEl.textContent = 'Connected';
        badgeEl.className = 'flex-shrink-0 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300';
    } else {
        statusEl.textContent = `${check.message || getStatusText(check.status)} Top tracks source: ${strategyLabel}.`;
        statusEl.className = `text-sm ${statusColor} mt-1`;
        badgeEl.textContent = check.status === 'warning' ? 'Unavailable' : 'Error';
        badgeEl.className = `flex-shrink-0 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
            check.status === 'warning'
                ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/40 dark:text-yellow-300'
                : 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300'
        }`;
    }

    if (check.suggestion) {
        suggestionEl.textContent = check.suggestion;
        suggestionEl.classList.remove('hidden');
    } else {
        suggestionEl.classList.add('hidden');
    }
}

// Helper function to format dates in friendly format (e.g., "5 Oct 2025 10:12am")
function formatFriendlyDate(dateString) {
    if (!dateString) return 'Never';

    const date = new Date(dateString);
    const day = date.getDate();
    const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    const month = monthNames[date.getMonth()];
    const year = date.getFullYear();

    let hours = date.getHours();
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const ampm = hours >= 12 ? 'pm' : 'am';
    hours = hours % 12;
    hours = hours ? hours : 12; // 0 should be 12

    return `${day} ${month} ${year} ${hours}:${minutes}${ampm}`;
}