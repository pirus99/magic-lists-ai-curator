/**
 * Help / instruction modal for playlist types.
 *
 * Modal content is loaded from static help files in frontend/static/help/
 * so each playlist type can manage its own copy independently.
 */

(function (window, document) {
    const helpTypes = {
        this_is: {
            title: 'This Is Artist',
            subtitle: 'Single-artist playlist built from your library'
        },
        artist_radio: {
            title: 'Artist Radio',
            subtitle: 'Similar-artist radio seeded by a source artist'
        },
        genre_mix: {
            title: 'Genre Mix',
            subtitle: 'Curated genre playlist with diversity controls'
        },
        rediscover: {
            title: 'Re-Discover',
            subtitle: 'Forgotten tracks derived from your listening history'
        }
    };

    async function openHelpModal(type) {
        const normalizedType = type && helpTypes[type] ? type : 'this_is';
        const config = helpTypes[normalizedType];
        const overlay = document.getElementById('help-modal-overlay');
        const modal = document.getElementById('help-modal');
        const title = document.getElementById('help-modal-title');
        const subtitle = document.getElementById('help-modal-subtitle');
        const content = document.getElementById('help-modal-content');

        if (title) title.textContent = 'How ' + config.title + ' works';
        if (subtitle) subtitle.textContent = config.subtitle;
        if (content) {
            content.innerHTML = '<div class="space-y-3 animate-pulse">' +
                '<div class="h-4 w-36 rounded bg-gray-200 dark:bg-gray-700"></div>' +
                '<div class="h-3 w-full rounded bg-gray-200 dark:bg-gray-700"></div>' +
                '<div class="h-3 w-5/6 rounded bg-gray-200 dark:bg-gray-700"></div>' +
                '<div class="h-3 w-2/3 rounded bg-gray-200 dark:bg-gray-700"></div>' +
                '</div>';
        }

        if (overlay) overlay.classList.remove('hidden');
        if (modal) modal.classList.remove('hidden');

        try {
            const response = await fetch('/help/' + normalizedType, { cache: 'no-store' });
            if (!response.ok) {
                throw new Error('Help content not found');
            }

            const html = await response.text();
            if (content) {
                content.innerHTML = html;
            }
        } catch (error) {
            console.error('Failed to load help content for ' + normalizedType, error);
            if (content) {
                content.innerHTML = '<div class="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300">' +
                    'Help content is temporarily unavailable. Please try again later.' +
                    '</div>';
            }
        }
    }

    function closeHelpModal() {
        const overlay = document.getElementById('help-modal-overlay');
        const modal = document.getElementById('help-modal');
        if (overlay) overlay.classList.add('hidden');
        if (modal) modal.classList.add('hidden');
    }

    function bindCloseHandlers() {
        const overlay = document.getElementById('help-modal-overlay');
        const modal = document.getElementById('help-modal');
        const closeTop = document.getElementById('help-close-top');
        const closeBottom = document.getElementById('help-close-bottom');

        if (overlay) overlay.addEventListener('click', closeHelpModal);
        if (modal) {
            modal.addEventListener('click', function (event) {
                if (event.target === modal) closeHelpModal();
            });
        }
        if (closeTop) closeTop.addEventListener('click', closeHelpModal);
        if (closeBottom) closeBottom.addEventListener('click', closeHelpModal);

        document.addEventListener('keydown', function (event) {
            if (event.key === 'Escape' && modal && !modal.classList.contains('hidden')) {
                closeHelpModal();
            }
        });
    }

    window.App = window.App || {};
    window.App.help = Object.assign(window.App.help || {}, {
        openHelpModal: openHelpModal,
        closeHelpModal: closeHelpModal,
        types: Object.keys(helpTypes)
    });

    window.openHelpModal = openHelpModal;
    window.closeHelpModal = closeHelpModal;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindCloseHandlers);
    } else {
        bindCloseHandlers();
    }
})(window, document);