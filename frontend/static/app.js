// Global state for artist selection
let selectedArtistId = null;
let selectedGenres = [];
let editSelectedGenres = [];
let allArtists = [];
let allGenres = [];
let currentToast = null;
let editGenreSettings = null;
let editBlacklistArtistsLoaded = false;

// Global state for library selection
let selectedLibraryIds = [];
let allLibraries = [];

// AI model information cache
let aiModelInfo = null;

// Expose certain functions through the App namespace for new modules
window.App = window.App || {};
window.App.modals = window.App.modals || {};
window.App.playlists = window.App.playlists || {};
window.App.nav = window.App.nav || {};
window.App.system = window.App.system || {};

window.App.modals.openEditModal = window.App.modals.openEditModal || function () { if (typeof openEditModal === 'function') return openEditModal(); };
window.App.modals.closeEditModal = window.App.modals.closeEditModal || function () { if (typeof closeEditModal === 'function') return closeEditModal(); };
window.App.playlists.savePlaylistSettings = window.App.playlists.savePlaylistSettings || function (regenerate) { if (typeof savePlaylistSettings === 'function') return savePlaylistSettings(regenerate); };
window.App.playlists.generateRediscoverWeekly = window.App.playlists.generateRediscoverWeekly || function () { if (typeof generateRediscoverWeekly === 'function') return generateRediscoverWeekly(); };
window.App.system.runChecks = window.App.system.runChecks || function () { if (typeof runSystemChecks === 'function') return runSystemChecks(); };
window.App.nav.navigateToHome = window.App.nav.navigateToHome || function () { if (typeof navigateToHome === 'function') return navigateToHome(); };
window.App.help = window.App.help || {};
window.App.help.showSettingsHelp = window.App.help.showSettingsHelp || function () { if (typeof showSettingsHelp === 'function') return showSettingsHelp(); };

// Handle window resize to ensure proper state
window.addEventListener('resize', function () {
    if (window.innerWidth >= 768) {
        mobileSidebar.classList.add('-translate-x-full'); // Hide mobile sidebar on large screens
        sidebarOverlay.classList.add('hidden'); // Hide overlay on large screens
    } else {
        // On mobile, ensure sidebar is hidden when switching from desktop view
        mobileSidebar.classList.add('-translate-x-full');
        sidebarOverlay.classList.add('hidden');
    }
});

async function checkDatabaseConnectivity() {
    const alertDiv = document.getElementById('database-error-alert');

    try {
        const response = await fetch('/api/playlists');
        if (response.ok) {
            // Database is accessible, hide alert
            alertDiv.classList.add('hidden');
        } else {
            // Database error, show alert
            alertDiv.classList.remove('hidden');
        }
    } catch (error) {
        // Network/database error, show alert
        alertDiv.classList.remove('hidden');
        console.error('Database connectivity check failed:', error);
    }
}

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', function () {
    // Initialize Preline components
    if (window.HSStaticMethods) {
        window.HSStaticMethods.autoInit();
        console.log('Preline initialized');
    } else {
        console.error('Preline not loaded');
    }

    // Setup artist selection change handler
    const artistSelect = document.getElementById('artist-search-select');
    if (artistSelect) {
        artistSelect.addEventListener('change', handleArtistSelection);
        // Add validation on click - highlight library selector if no libraries selected
        artistSelect.addEventListener('click', function () {
            if (selectedLibraryIds.length === 0) {
                // Apply validation styling to library selectors
                const libraryMulti = document.getElementById('library-multi');
                const mobileLibraryMulti = document.getElementById('mobile-library-multi');
                if (libraryMulti) {
                    libraryMulti.classList.add('ring-2', 'ring-red-500', 'ring-opacity-50');
                    setTimeout(() => libraryMulti.classList.remove('ring-2', 'ring-red-500', 'ring-opacity-50'), 3000);
                }
                if (mobileLibraryMulti) {
                    mobileLibraryMulti.classList.add('ring-2', 'ring-red-500', 'ring-opacity-50');
                    setTimeout(() => mobileLibraryMulti.classList.remove('ring-2', 'ring-red-500', 'ring-opacity-50'), 3000);
                }
                showToast('warning', 'Please select a music library first.');
            }
        });
    }

    // Load libraries on page load
    loadLibraries();

    // Load playlist count on page load
    updatePlaylistCount();

    // Handle initial page routing (with small delay to ensure DOM is ready)
    setTimeout(() => {
        const currentPage = getPageFromURL(window.location.pathname);
        handlePageNavigation(currentPage);
    }, 100);

    // Check database connectivity
    checkDatabaseConnectivity();
});

function syncEditBlacklistToggleColor() {
    const blacklistSelect = document.getElementById('edit-genre-blacklist-select');
    if (!blacklistSelect) return;
    const hasSelection = Array.from(blacklistSelect.options).some(opt => opt.selected);
    const toggle = blacklistSelect.closest('.hs-select')?.querySelector('.blacklist-toggle');
    if (toggle) toggle.classList.toggle('has-value', hasSelection);
}

// Toggle the blacklist filter's toggle text color (gray -> black) based on
// whether any artist is currently selected. The HSSelect toggle is rebuilt on
// every re-init, so we re-apply the class each time it changes.
function syncBlacklistToggleColor() {
    const blacklistSelect = document.getElementById('genre-blacklist-select');
    if (!blacklistSelect) return;
    const hasSelection = Array.from(blacklistSelect.options).some(opt => opt.selected);
    const toggle = blacklistSelect.closest('.hs-select')?.querySelector('.blacklist-toggle');
    if (toggle) toggle.classList.toggle('has-value', hasSelection);
}

function getStatusIcon(status) {
    switch (status) {
        case 'success':
            return `<svg class="w-5 h-5 text-green-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"></path>
            </svg>`;
        case 'warning':
            return `<svg class="w-5 h-5 text-yellow-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>
            </svg>`;
        case 'info':
            return `<svg class="w-5 h-5 text-blue-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>
            </svg>`;
        case 'error':
            return `<svg class="w-5 h-5 text-red-400" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>
            </svg>`;
        default:
            return `<svg class="w-5 h-5 text-gray-400 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="m12 2v4l4-4h-4z"></path>
            </svg>`;
    }
}

function getStatusColor(status) {
    switch (status) {
        case 'success':
            return 'text-green-600';
        case 'warning':
            return 'text-yellow-600';
        case 'info':
            return 'text-blue-600';
        case 'error':
            return 'text-red-600';
        default:
            return 'text-gray-500';
    }
}

function getStatusText(status) {
    switch (status) {
        case 'success':
            return 'Success';
        case 'warning':
            return 'Warning';
        case 'info':
            return '';
        case 'error':
            return 'Failed';
        default:
            return 'Checking...';
    }
}

// URL management function
function updateURL(page) {
    let url = '/';

    // Map pages to URL paths
    switch (page) {
        case 'home':
            url = '/';
            break;
        case 'this-is-artist':
            url = '/this-is';
            break;
        case 'artist-radio':
            url = '/artist-radio';
            break;
        case 're-discover':
            url = '/re-discover';
            break;
        case 'genre-mix':
            url = '/genre-mix';
            break;
        case 'playlists':
            url = '/playlists';
            break;
        case 'system-check':
            url = '/system-check';
            break;
        case 'terms':
            url = '/terms';
            break;
        default:
            url = '/';
    }

    // Update browser URL without page reload
    if (window.location.pathname !== url) {
        window.history.pushState({ page: page }, '', url);
    }
}

function showSettingsHelp() {
    alert('To update your settings:\n\n1. Edit your .env file with the correct values\n2. Restart the application\n3. Run the system check again\n\nRefer to the SETUP.md file for detailed configuration instructions.');
}

// Auto-run system checks when the system-check page loads
function initSystemCheckPage() {
    runSystemChecks();
}

// Get page from URL path
function getPageFromURL(pathname) {
    let page;
    switch (pathname) {
        case '/':
            page = 'home';
            break;
        case '/this-is':
            page = 'this-is-artist';
            break;
        case '/artist-radio':
            page = 'artist-radio';
            break;
        case '/re-discover':
            page = 're-discover';
            break;
        case '/genre-mix':
            page = 'genre-mix';
            break;
        case '/playlists':
            page = 'playlists';
            break;
        case '/system-check':
            page = 'system-check';
            break;
        case '/terms':
            page = 'terms';
            break;
        default:
            page = 'home';
            break;
    }
    return page;
}


