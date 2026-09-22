(function (window) {
    const main = {
        init() {
            // Wire lightweight shims to existing App modules where appropriate
            console.log('App main init');
            if (window.App && window.App.selects) {
                window.App.selects.initHSSelect();
            }
            // Wire template buttons to existing global functions or App shims
            const rediscoverBtn = document.getElementById('rediscover-btn');
            if (rediscoverBtn) {
                rediscoverBtn.addEventListener('click', function () {
                    try { if (window.generateRediscoverWeekly) { window.generateRediscoverWeekly(); } else if (window.App && window.App.playlists && window.App.playlists.generateRediscoverWeekly) { window.App.playlists.generateRediscoverWeekly(); } } catch (e) { console.error(e); }
                });
            }

            const rerunBtn = document.getElementById('rerun-checks-btn');
            if (rerunBtn) {
                rerunBtn.addEventListener('click', function () {
                    try { if (window.runSystemChecks) { window.runSystemChecks(); } else if (window.App && window.App.system && window.App.system.runChecks) { window.App.system.runChecks(); } } catch (e) { console.error(e); }
                });
            }

            const continueBtn = document.getElementById('continue-btn');
            if (continueBtn) {
                continueBtn.addEventListener('click', function () {
                    try { if (window.navigateToHome) { window.navigateToHome(); } else if (window.App && window.App.nav && window.App.nav.navigateToHome) { window.App.nav.navigateToHome(); } } catch (e) { console.error(e); }
                });
            }

            const updateSettingsBtn = document.getElementById('update-settings-btn');
            if (updateSettingsBtn) {
                updateSettingsBtn.addEventListener('click', function () {
                    try { if (window.showSettingsHelp) { window.showSettingsHelp(); } else if (window.App && window.App.help && window.App.help.showSettingsHelp) { window.App.help.showSettingsHelp(); } } catch (e) { console.error(e); }
                });
            }

            // Edit modal wiring
            const editCloseTop = document.getElementById('edit-close-top');
            const editCloseCancel = document.getElementById('edit-close-cancel');
            const editSave = document.getElementById('edit-save-btn');
            const editSaveRefresh = document.getElementById('edit-save-refresh-btn');
            if (editCloseTop) editCloseTop.addEventListener('click', function () { try { if (window.closeEditModal) { window.closeEditModal(); } else if (window.App && window.App.modals && window.App.modals.closeEditModal) { window.App.modals.closeEditModal(); } } catch (e) { console.error(e); } });
            if (editCloseCancel) editCloseCancel.addEventListener('click', function () { try { if (window.closeEditModal) { window.closeEditModal(); } else if (window.App && window.App.modals && window.App.modals.closeEditModal) { window.App.modals.closeEditModal(); } } catch (e) { console.error(e); } });
            if (editSave) editSave.addEventListener('click', function () { try { if (window.savePlaylistSettings) { window.savePlaylistSettings(false); } else if (window.App && window.App.playlists && window.App.playlists.savePlaylistSettings) { window.App.playlists.savePlaylistSettings(false); } } catch (e) { console.error(e); } });
            if (editSaveRefresh) editSaveRefresh.addEventListener('click', function () { try { if (window.savePlaylistSettings) { window.savePlaylistSettings(true); } else if (window.App && window.App.playlists && window.App.playlists.savePlaylistSettings) { window.App.playlists.savePlaylistSettings(true); } } catch (e) { console.error(e); } });

            // Delegate playlist action clicks (refresh, edit, delete)
            const playlistsContainer = document.getElementById('playlists-container');
            if (playlistsContainer) {
                playlistsContainer.addEventListener('click', function (e) {
                    const btn = e.target.closest('[data-action]');
                    if (!btn) return;
                    const action = btn.getAttribute('data-action');
                    const playlistId = btn.getAttribute('data-playlist-id');
                    try {
                        if (action === 'refresh') {
                            if (window.refreshPlaylist) window.refreshPlaylist(playlistId);
                            else if (window.App && window.App.playlists && window.App.playlists.refreshPlaylist) window.App.playlists.refreshPlaylist(playlistId);
                        } else if (action === 'edit') {
                            if (window.openEditModal) window.openEditModal(playlistId);
                            else if (window.App && window.App.modals && window.App.modals.openEditModal) window.App.modals.openEditModal(playlistId);
                        } else if (action === 'delete') {
                            const name = btn.getAttribute('data-playlist-name') || '';
                            if (window.deletePlaylist) window.deletePlaylist(playlistId, name);
                            else if (window.App && window.App.playlists && window.App.playlists.deletePlaylist) window.App.playlists.deletePlaylist(playlistId, name);
                        }
                    } catch (err) { console.error(err); }
                });
            }

            // Delegate system-check toggle clicks
            const systemChecksList = document.getElementById('system-checks-list');
            if (systemChecksList) {
                systemChecksList.addEventListener('click', function (e) {
                    const el = e.target.closest('[data-action="toggle-check"]');
                    if (!el) return;
                    const checkId = el.getAttribute('data-check-id');
                    try { if (window.toggleCheckDetails) window.toggleCheckDetails(checkId); } catch (err) { console.error(err); }
                });
            }
        }
    };

    window.App = window.App || {};
    window.App.main = main;

    // Auto-init on DOMContentLoaded
    document.addEventListener('DOMContentLoaded', function () {
        try { main.init(); } catch (e) { console.error('App main init error', e); }
    });
})(window);
