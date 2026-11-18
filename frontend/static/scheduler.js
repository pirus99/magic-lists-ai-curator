/**
 * Refresh Schedule page.
 *
 * Renders one tile per playlist showing the last refresh outcome, the next
 * scheduled run, and live queue state. Clicking a tile opens a detail panel
 * with refresh history and upcoming runs, from which the edit modal can be
 * opened.
 */
(function (window) {
    'use strict';

    const TYPE_LABELS = {
        this_is: 'This Is',
        genre_mix: 'Genre Mix',
        artist_radio: 'Artist Radio',
        song_radio: 'Song Radio',
        rediscover: 'Re-Discover',
        rediscover_weekly_v2: 'Re-Discover',
    };

    const TYPE_ICONS = {
        this_is: '<circle cx="12" cy="8" r="4"/><path d="M6 20c0-3.31 2.69-6 6-6s6 2.69 6 6"/>',
        genre_mix: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
        artist_radio: '<path stroke-linecap="round" stroke-linejoin="round" d="m3.75 7.5 16.5-4.125M12 6.75c-2.708 0-5.363.224-7.948.655C2.999 7.58 2.25 8.507 2.25 9.574v9.176A2.25 2.25 0 0 0 4.5 21h15a2.25 2.25 0 0 0 2.25-2.25V9.574c0-1.067-.75-1.994-1.802-2.169A48.329 48.329 0 0 0 12 6.75Zm-1.683 6.443-.005.005-.006-.005.006-.005.005.005Zm-.005 2.127-.005-.006.005-.005.005.005-.005.005Zm-2.116-.006-.005.006-.006-.006.005-.005.006.005Zm-.005-2.116-.006-.005.006-.005.005.005-.005.005ZM9.255 10.5v.008h-.008V10.5h.008Zm3.249 1.88-.007.004-.003-.007.006-.003.004.006Zm-1.38 5.126-.003-.006.006-.004.004.007-.006.003Zm.007-6.501-.003.006-.007-.003.004-.007.006.004Zm1.37 5.129-.007-.004.004-.006.006.003-.004.007Zm.504-1.877h-.008v-.007h.008v.007ZM9.255 18v.008h-.008V18h.008Zm-3.246-1.87-.007.004L6 16.127l.006-.003.004.006Zm1.366-5.119-.004-.006.006-.004.004.007-.006.003ZM7.38 17.5l-.003.006-.007-.003.004-.007.006.004Zm-1.376-5.116L6 12.38l.003-.007.007.004-.004.007Zm-.5 1.873h-.008v-.007h.008v.007ZM17.25 12.75a.75.75 0 1 1 0-1.5.75.75 0 0 1 0 1.5Zm0 4.5a.75.75 0 1 1 0-1.5.75.75 0 0 1 0 1.5Z" />',
        song_radio: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
        rediscover: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
        rediscover_weekly_v2: '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/>',
    };

    let currentTiles = [];
    let pollTimer = null;
    let detailPlaylistId = null;
    // Default view shows only playlists with an active refresh schedule.
    let showAllPlaylists = false;
    // Once the page has rendered once, background refreshes must not re-show
    // the loading placeholder (it causes a visible flicker).
    let hasLoadedOnce = false;

    // ------------------------------------------------------------------
    // Formatting helpers
    // ------------------------------------------------------------------
    function formatDateTime(value) {
        if (!value) return '—';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '—';
        return date.toLocaleString(undefined, {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
        });
    }

    function formatRelative(value) {
        if (!value) return '';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '';
        const diffMs = date.getTime() - Date.now();
        const absMinutes = Math.round(Math.abs(diffMs) / 60000);

        let text;
        if (absMinutes < 1) text = 'less than a minute';
        else if (absMinutes < 60) text = `${absMinutes} min`;
        else if (absMinutes < 1440) text = `${Math.round(absMinutes / 60)} h`;
        else text = `${Math.round(absMinutes / 1440)} d`;

        return diffMs >= 0 ? `in ${text}` : `${text} ago`;
    }

    function formatDuration(seconds) {
        if (seconds === null || seconds === undefined) return '';
        if (seconds < 60) return `${Math.round(seconds)}s`;
        const minutes = Math.floor(seconds / 60);
        const rest = Math.round(seconds % 60);
        return `${minutes}m ${rest}s`;
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function typeLabel(type) {
        return TYPE_LABELS[type] || type || 'Playlist';
    }

    function typeIcon(type) {
        const paths = TYPE_ICONS[type] || TYPE_ICONS.this_is;
        return `<svg class="size-5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
            fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;
    }

    // ------------------------------------------------------------------
    // Tile rendering
    // ------------------------------------------------------------------
    function renderTile(tile) {
        const lastRun = tile.last_run;
        const failed = lastRun && lastRun.status === 'failed';
        const unscheduled = tile.is_scheduled === false;

        const nextRunText = unscheduled
            ? '<span class="text-gray-400 dark:text-gray-500">Manual only</span>'
            : tile.next_run
                ? `${formatDateTime(tile.next_run)} <span class="text-gray-400 dark:text-gray-500">(${formatRelative(tile.next_run)})</span>`
                : 'Not scheduled';

        // Only a failed last run is surfaced on the tile; everything else lives
        // in the detail modal.
        const failIcon = failed
            ? `<span class="flex-none text-red-600 dark:text-red-400" title="Last refresh failed">
                    <svg class="size-5" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
                        fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <circle cx="12" cy="12" r="10" />
                        <line x1="12" y1="8" x2="12" y2="12" />
                        <line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                </span>`
            : '';

        const runningDot = tile.state === 'running'
            ? '<span class="flex-none size-2 rounded-full bg-blue-600 dark:bg-blue-400 animate-pulse" title="Refreshing now"></span>'
            : tile.state === 'queued'
                ? '<span class="flex-none size-2 rounded-full bg-amber-500" title="Queued"></span>'
                : '';

        // Unscheduled playlists are visually de-emphasised so the scheduled ones
        // stay the focus of the page.
        const tileClasses = unscheduled
            ? 'border-dashed opacity-75'
            : 'border-gray-200 dark:border-gray-700 hover:border-blue-400 dark:hover:border-blue-500 hover:bg-gray-50 dark:hover:bg-gray-700/40';

        return `
            <button type="button" data-scheduler-tile="${escapeHtml(tile.navidrome_playlist_id)}"
                class="text-left w-full flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 px-3 py-2.5 border rounded-lg transition-colors bg-white dark:bg-gray-800 ${tileClasses}">
                <div class="flex items-center gap-3 min-w-0 w-full sm:w-auto sm:flex-1">
                    <span class="flex-none flex items-center justify-center size-8 rounded-lg bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300">
                        ${typeIcon(tile.playlist_type)}
                    </span>
                    <div class="min-w-0 flex-1">
                        <h3 class="text-sm font-semibold text-gray-900 dark:text-gray-100 truncate">${escapeHtml(tile.playlist_name || 'Untitled')}</h3>
                        <p class="text-xs text-gray-500 dark:text-gray-400 truncate">${escapeHtml(typeLabel(tile.playlist_type))}</p>
                    </div>
                    <span class="flex-none flex items-center gap-1.5 sm:hidden">
                        ${runningDot}
                        ${failIcon}
                    </span>
                </div>
                <div class="flex items-center justify-between gap-2 w-full sm:w-auto sm:flex-none sm:block sm:text-right">
                    <p class="text-xs text-gray-500 dark:text-gray-400">Next run</p>
                    <p class="text-xs text-gray-900 dark:text-gray-100">${nextRunText}</p>
                </div>
                <span class="hidden sm:flex flex-none items-center gap-1.5">
                    ${runningDot}
                    ${failIcon}
                </span>
            </button>
        `;
    }

    function renderQueueSummary(queue) {
        const summary = document.getElementById('scheduler-queue-summary');
        if (!summary) return;

        const running = queue && queue.running;
        const queued = (queue && queue.queued) || [];

        if (!running && queued.length === 0) {
            summary.classList.add('hidden');
            summary.innerHTML = '';
            return;
        }

        const parts = [];
        if (running) {
            parts.push(`Refreshing <strong>${escapeHtml(running.playlist_name || running.navidrome_playlist_id)}</strong>`);
        }
        if (queued.length) {
            parts.push(`${queued.length} queued`);
        }
        parts.push(`one at a time, ${queue.min_gap_seconds}s apart`);

        summary.innerHTML = parts.join(' • ');
        summary.classList.remove('hidden');
    }

    // ------------------------------------------------------------------
    // Data loading
    // ------------------------------------------------------------------
    async function loadSchedulerOverview(showLoading = false) {
        const loading = document.getElementById('scheduler-loading');
        const container = document.getElementById('scheduler-tiles');
        const empty = document.getElementById('scheduler-empty');
        if (!container) return;

        // Only surface the loading placeholder on the very first load or when
        // the user explicitly reloads. Background polls and view toggles must
        // not make the page flicker.
        const shouldShowLoading = showLoading || !hasLoadedOnce;
        if (loading && shouldShowLoading) loading.classList.remove('hidden');

        try {
            const url = showAllPlaylists
                ? '/api/scheduler/overview?include_unscheduled=true'
                : '/api/scheduler/overview';
            const response = await fetch(url);
            if (!response.ok) throw new Error('Failed to load refresh schedule');

            const data = await response.json();
            currentTiles = data.tiles || [];
            hasLoadedOnce = true;

            if (loading) loading.classList.add('hidden');

            if (currentTiles.length === 0) {
                container.innerHTML = '';
                if (empty) {
                    const title = document.getElementById('scheduler-empty-title');
                    const hint = document.getElementById('scheduler-empty-hint');
                    if (showAllPlaylists) {
                        if (title) title.textContent = 'No playlists yet';
                        if (hint) hint.textContent = 'Create a playlist to see it here.';
                    } else {
                        if (title) title.textContent = 'No scheduled playlists';
                        if (hint) hint.textContent = 'Set a refresh schedule on a playlist, or use "Show all playlists".';
                    }
                    empty.classList.remove('hidden');
                }
                renderQueueSummary(data.queue);
                return;
            }

            if (empty) empty.classList.add('hidden');
            container.innerHTML = currentTiles.map(renderTile).join('');
            renderQueueSummary(data.queue);
        } catch (error) {
            console.error('Error loading scheduler overview:', error);
            if (loading) loading.classList.add('hidden');
            container.innerHTML = `
                <div class="text-center p-8 text-red-600 dark:text-red-400">
                    <p class="text-lg mb-2">Error loading refresh schedule</p>
                    <p class="text-sm">${escapeHtml(error.message)}</p>
                </div>
            `;
        }
    }

    function toggleShowAll() {
        showAllPlaylists = !showAllPlaylists;

        const btn = document.getElementById('scheduler-show-all-btn');
        const label = document.getElementById('scheduler-show-all-label');
        if (btn) {
            btn.setAttribute('aria-pressed', showAllPlaylists ? 'true' : 'false');
            btn.classList.toggle('bg-blue-50', showAllPlaylists);
            btn.classList.toggle('dark:bg-blue-900/30', showAllPlaylists);
            btn.classList.toggle('border-blue-300', showAllPlaylists);
            btn.classList.toggle('dark:border-blue-700', showAllPlaylists);
        }
        if (label) {
            label.textContent = showAllPlaylists ? 'Scheduled only' : 'Show all playlists';
        }

        loadSchedulerOverview();
    }

    // ------------------------------------------------------------------
    // Detail panel
    // ------------------------------------------------------------------
    function openDetailPanel(playlistId) {
        const tile = currentTiles.find(item => item.navidrome_playlist_id === playlistId);
        if (!tile) return;

        detailPlaylistId = playlistId;

        document.getElementById('scheduler-detail-title').textContent = tile.playlist_name || 'Playlist';
        document.getElementById('scheduler-detail-type').textContent = typeLabel(tile.playlist_type);
        document.getElementById('scheduler-detail-schedule').textContent = tile.schedule_description || 'Manual only';

        // Summary block
        const lastRun = tile.last_run;
        document.getElementById('scheduler-detail-tracks').textContent = `${tile.track_count || 0} tracks`;

        const statusEl = document.getElementById('scheduler-detail-status');
        if (tile.state === 'running') {
            statusEl.textContent = 'Refreshing now';
            statusEl.className = 'text-blue-600 dark:text-blue-400 font-medium';
        } else if (tile.state === 'queued') {
            statusEl.textContent = 'Queued';
            statusEl.className = 'text-amber-600 dark:text-amber-400 font-medium';
        } else if (!lastRun) {
            statusEl.textContent = 'Never run';
            statusEl.className = 'text-gray-500 dark:text-gray-400 font-medium';
        } else if (lastRun.status === 'success') {
            statusEl.textContent = 'Last refresh succeeded';
            statusEl.className = 'text-green-600 dark:text-green-400 font-medium';
        } else {
            statusEl.textContent = 'Last refresh failed';
            statusEl.className = 'text-red-600 dark:text-red-400 font-medium';
        }

        document.getElementById('scheduler-detail-last').textContent = lastRun
            ? `${formatDateTime(lastRun.finished_at || lastRun.started_at)}${lastRun.duration_seconds ? ` (${formatDuration(lastRun.duration_seconds)})` : ''}`
            : '—';

        document.getElementById('scheduler-detail-next').textContent = tile.next_run
            ? `${formatDateTime(tile.next_run)} (${formatRelative(tile.next_run)})`
            : 'Not scheduled';

        const upcoming = document.getElementById('scheduler-detail-upcoming');
        const runs = tile.upcoming || [];
        upcoming.innerHTML = runs.length
            ? runs.map(run => `<li class="flex justify-between gap-2">
                    <span>${formatDateTime(run)}</span>
                    <span class="text-gray-400 dark:text-gray-500">${formatRelative(run)}</span>
                </li>`).join('')
            : '<li class="text-gray-500 dark:text-gray-400">No upcoming refreshes scheduled.</li>';

        const history = document.getElementById('scheduler-detail-history');
        history.innerHTML = '<p class="text-sm text-gray-500 dark:text-gray-400">Loading history...</p>';

        document.getElementById('scheduler-detail-overlay').classList.remove('hidden');
        document.getElementById('scheduler-detail-panel').classList.remove('hidden');

        loadDetailHistory(playlistId);
    }

    async function loadDetailHistory(playlistId) {
        const history = document.getElementById('scheduler-detail-history');
        try {
            const response = await fetch(`/api/scheduler/history?playlist_id=${encodeURIComponent(playlistId)}&limit=10`);
            if (!response.ok) throw new Error('Failed to load history');
            const data = await response.json();
            const rows = data.history || [];

            if (rows.length === 0) {
                history.innerHTML = '<p class="text-sm text-gray-500 dark:text-gray-400">No refreshes recorded yet.</p>';
                return;
            }

            history.innerHTML = rows.map(row => {
                const ok = row.status === 'success';
                const badge = ok
                    ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-300">Success</span>'
                    : '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-300">Failed</span>';
                const meta = [
                    formatDateTime(row.finished_at || row.started_at),
                    row.trigger === 'manual' ? 'manual' : 'scheduled',
                    row.duration_seconds ? formatDuration(row.duration_seconds) : null,
                    row.track_count ? `${row.track_count} tracks` : null,
                ].filter(Boolean).join(' • ');

                // A successful run can still carry a note (e.g. a legitimate
                // fallback was used); a failed run carries the reason.
                const note = row.error
                    ? `<p class="mt-1 text-xs break-words ${ok
                        ? 'text-amber-600 dark:text-amber-400'
                        : 'text-red-600 dark:text-red-400'}">${escapeHtml(row.error)}</p>`
                    : '';

                return `<div class="p-2.5 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <div class="flex items-center justify-between gap-2">
                        <span class="text-xs text-gray-600 dark:text-gray-300">${escapeHtml(meta)}</span>
                        ${badge}
                    </div>
                    ${note}
                </div>`;
            }).join('');
        } catch (error) {
            console.error('Error loading refresh history:', error);
            history.innerHTML = `<p class="text-sm text-red-600 dark:text-red-400">${escapeHtml(error.message)}</p>`;
        }
    }

    function closeDetailPanel() {
        document.getElementById('scheduler-detail-overlay').classList.add('hidden');
        document.getElementById('scheduler-detail-panel').classList.add('hidden');
        detailPlaylistId = null;
    }

    // ------------------------------------------------------------------
    // Actions
    // ------------------------------------------------------------------
    async function refreshFromDetail() {
        if (!detailPlaylistId) return;
        const tile = currentTiles.find(item => item.navidrome_playlist_id === detailPlaylistId);
        if (!tile) return;

        try {
            const response = await fetch(`/api/playlists/${tile.id}/refresh`, { method: 'POST' });
            const data = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(data.detail || 'Failed to queue refresh');

            if (data.status === 'already_queued') {
                showToast('info', 'This playlist is already queued or refreshing');
            } else {
                showToast('success', 'Refresh queued');
            }
            closeDetailPanel();
            loadSchedulerOverview();
        } catch (error) {
            console.error('Error queueing refresh:', error);
            showToast('error', error.message);
        }
    }

    function editFromDetail() {
        if (!detailPlaylistId) return;
        const tile = currentTiles.find(item => item.navidrome_playlist_id === detailPlaylistId);
        if (!tile) return;

        closeDetailPanel();
        if (window.openEditModal) window.openEditModal(tile.id);
        else if (window.App && window.App.modals && window.App.modals.openEditModal) {
            window.App.modals.openEditModal(tile.id);
        }
    }

    async function clearHistory() {
        openClearHistoryModal();
    }

    // ------------------------------------------------------------------
    // Clear-history modal
    // ------------------------------------------------------------------
    function setClearHistoryBusy(busy) {
        const confirmBtn = document.getElementById('clear-history-confirm-btn');
        const cancelBtn = document.getElementById('clear-history-cancel-btn');
        const closeBtn = document.getElementById('clear-history-close-top');
        const spinner = document.getElementById('clear-history-confirm-spinner');
        const label = document.getElementById('clear-history-confirm-label');

        if (confirmBtn) confirmBtn.disabled = busy;
        if (cancelBtn) cancelBtn.disabled = busy;
        if (closeBtn) closeBtn.disabled = busy;
        if (spinner) spinner.classList.toggle('hidden', !busy);
        if (label) label.textContent = busy ? 'Clearing...' : 'Clear History';
    }

    function openClearHistoryModal() {
        const overlay = document.getElementById('clear-history-modal-overlay');
        const modal = document.getElementById('clear-history-modal');
        if (!overlay || !modal) {
            // Modal markup missing (e.g. partial render) — fall back to confirm().
            if (confirm('Clear all refresh history? This only removes the log, not the playlists.')) {
                performClearHistory();
            }
            return;
        }

        setClearHistoryBusy(false);
        overlay.classList.remove('hidden');
        modal.classList.remove('hidden');

        const confirmBtn = document.getElementById('clear-history-confirm-btn');
        if (confirmBtn) confirmBtn.focus();
    }

    function closeClearHistoryModal() {
        const overlay = document.getElementById('clear-history-modal-overlay');
        const modal = document.getElementById('clear-history-modal');
        if (overlay) overlay.classList.add('hidden');
        if (modal) modal.classList.add('hidden');
        setClearHistoryBusy(false);
    }

    async function performClearHistory() {
        setClearHistoryBusy(true);
        try {
            const response = await fetch('/api/scheduler/history', { method: 'DELETE' });
            if (!response.ok) throw new Error('Failed to clear history');
            showToast('success', 'Refresh history cleared');
            closeClearHistoryModal();
            loadSchedulerOverview();
        } catch (error) {
            console.error('Error clearing history:', error);
            showToast('error', error.message);
            setClearHistoryBusy(false);
        }
    }

    // ------------------------------------------------------------------
    // Wiring
    // ------------------------------------------------------------------
    function startPolling() {
        stopPolling();
        pollTimer = setInterval(() => {
            const page = document.getElementById('scheduler-content');
            if (page && page.style.display !== 'none') {
                loadSchedulerOverview();
            }
        }, 5000);
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function init() {
        const container = document.getElementById('scheduler-tiles');
        if (container) {
            container.addEventListener('click', function (event) {
                const tile = event.target.closest('[data-scheduler-tile]');
                if (!tile) return;
                openDetailPanel(tile.getAttribute('data-scheduler-tile'));
            });
        }

        const reloadBtn = document.getElementById('scheduler-refresh-btn');
        if (reloadBtn) reloadBtn.addEventListener('click', () => loadSchedulerOverview(true));

        const showAllBtn = document.getElementById('scheduler-show-all-btn');
        if (showAllBtn) showAllBtn.addEventListener('click', toggleShowAll);

        const clearBtn = document.getElementById('scheduler-clear-history-btn');
        if (clearBtn) clearBtn.addEventListener('click', clearHistory);

        // Clear-history modal wiring
        const clearOverlay = document.getElementById('clear-history-modal-overlay');
        if (clearOverlay) clearOverlay.addEventListener('click', closeClearHistoryModal);

        const clearCloseBtn = document.getElementById('clear-history-close-top');
        if (clearCloseBtn) clearCloseBtn.addEventListener('click', closeClearHistoryModal);

        const clearCancelBtn = document.getElementById('clear-history-cancel-btn');
        if (clearCancelBtn) clearCancelBtn.addEventListener('click', closeClearHistoryModal);

        const clearConfirmBtn = document.getElementById('clear-history-confirm-btn');
        if (clearConfirmBtn) clearConfirmBtn.addEventListener('click', performClearHistory);

        const closeBtn = document.getElementById('scheduler-detail-close');
        if (closeBtn) closeBtn.addEventListener('click', closeDetailPanel);

        const overlay = document.getElementById('scheduler-detail-overlay');
        if (overlay) overlay.addEventListener('click', closeDetailPanel);

        const refreshBtn = document.getElementById('scheduler-detail-refresh');
        if (refreshBtn) refreshBtn.addEventListener('click', refreshFromDetail);

        const editBtn = document.getElementById('scheduler-detail-edit');
        if (editBtn) editBtn.addEventListener('click', editFromDetail);

        document.addEventListener('keydown', function (event) {
            if (event.key !== 'Escape') return;

            // Close the topmost open dialog first.
            const clearModal = document.getElementById('clear-history-modal');
            if (clearModal && !clearModal.classList.contains('hidden')) {
                closeClearHistoryModal();
                return;
            }

            const panel = document.getElementById('scheduler-detail-panel');
            if (panel && !panel.classList.contains('hidden')) closeDetailPanel();
        });

        startPolling();
    }

    window.loadSchedulerOverview = loadSchedulerOverview;
    window.App = window.App || {};
    window.App.scheduler = { loadSchedulerOverview, openDetailPanel, closeDetailPanel };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})(window);
