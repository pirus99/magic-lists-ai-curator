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
