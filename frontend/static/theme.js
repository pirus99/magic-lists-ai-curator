/**
 * MagicLists Theme Controller
 * Handles dark/light mode persistence and synchronization across tabs.
 * Runs synchronously in <head> to prevent flash of wrong theme.
 */
(function () {
    'use strict';

    const THEME_KEY = 'magiclists-theme';
    const VALID_THEMES = ['dark', 'light'];
    const DEFAULT_THEME = 'light';

    // Get stored theme or default
    function getStoredTheme() {
        try {
            const stored = localStorage.getItem(THEME_KEY);
            if (stored && VALID_THEMES.includes(stored)) {
                return stored;
            }
        } catch (e) {
            // localStorage unavailable (private browsing, etc.)
        }
        return DEFAULT_THEME;
    }

    // Apply theme to document element
    function applyTheme(theme) {
        const root = document.documentElement;
        if (theme === 'dark') {
            root.classList.add('dark');
        } else {
            root.classList.remove('dark');
        }
    }

    // Initialize theme immediately (synchronous, before paint)
    const initialTheme = getStoredTheme();
    applyTheme(initialTheme);

    // Expose for other modules
    window.App = window.App || {};
    window.App.theme = {
        getTheme: function () {
            return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
        },
        setTheme: function (theme) {
            if (!VALID_THEMES.includes(theme)) return;
            applyTheme(theme);
            try {
                localStorage.setItem(THEME_KEY, theme);
            } catch (e) {
                // Ignore storage errors
            }
            updateAllToggles(theme);
        },
        toggleTheme: function () {
            const current = window.App.theme.getTheme();
            const next = current === 'dark' ? 'light' : 'dark';
            window.App.theme.setTheme(next);
        }
    };

    // Update all theme toggle buttons
    function updateAllToggles(theme) {
        const isDark = theme === 'dark';
        const toggles = document.querySelectorAll('[data-theme-toggle]');
        toggles.forEach(function (btn) {
            btn.setAttribute('aria-pressed', isDark);
            btn.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');
            btn.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';

            // Update icon: show sun in dark mode, moon in light mode
            const sunIcon = btn.querySelector('[data-theme-icon="sun"]');
            const moonIcon = btn.querySelector('[data-theme-icon="moon"]');
            if (sunIcon && moonIcon) {
                sunIcon.hidden = !isDark;
                moonIcon.hidden = isDark;
            }
        });
    }

    // Initialize toggles after DOM is ready
    document.addEventListener('DOMContentLoaded', function () {
        const currentTheme = window.App.theme.getTheme();
        updateAllToggles(currentTheme);

        // Attach click handlers to all toggle buttons
        document.querySelectorAll('[data-theme-toggle]').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                window.App.theme.toggleTheme();
            });
        });
    });

    // Sync across tabs when localStorage changes
    window.addEventListener('storage', function (e) {
        if (e.key === THEME_KEY && e.newValue !== e.oldValue) {
            const theme = e.newValue;
            if (VALID_THEMES.includes(theme)) {
                applyTheme(theme);
                updateAllToggles(theme);
            }
        }
    });
})();