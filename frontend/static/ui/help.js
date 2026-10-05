/**
 * Help / instruction modal for playlist types.
 *
 * A single modal (#help-modal) that is populated at runtime with the data
 * relevant to a specific playlist type. Content is derived from the options
 * that are actually exposed in the frontend UI.
 */

(function (window, document) {

    // -------------------------------------------------------------------------
    // Option value -> human readable label helpers
    // -------------------------------------------------------------------------

    const BITRATE_OPTIONS = [
        { value: '', label: 'Any bitrate' },
        { value: '128', label: '128 kbps' },
        { value: '192', label: '192 kbps' },
        { value: '256', label: '256 kbps' },
        { value: '320', label: '320 kbps' }
    ];

    const BITDEPTH_OPTIONS = [
        { value: '', label: 'Any depth' },
        { value: '16', label: '16 bit' },
        { value: '24', label: '24 bit' }
    ];

    const FORMAT_OPTIONS = [
        { value: '', label: 'Any format' },
        { value: 'mp3', label: 'MP3 (lossy)' },
        { value: 'flac', label: 'FLAC (lossless)' }
    ];

    const LISTENBRAINZ_ALGORITHMS = [
        { value: '', label: '5Y Balanced (default)' },
        { value: '20Y+', label: '20Y+ – long history' },
        { value: '25Y-Deep', label: '25Y Deep – very broad' },
        { value: '3M-Recent', label: '3M Recent – short term only' },
        { value: '20Y-Broad', label: '20Y Broad' },
        { value: '5Y-Light', label: '5Y Light – conservative' }
    ];

    const REFRESH_OPTIONS = [
        { value: 'none', label: "Don't refresh" },
        { value: 'daily', label: 'Daily (1:00 am)' },
        { value: 'weekly', label: 'Weekly (Monday 1:00 am)' },
        { value: 'monthly', label: 'Monthly (1st of month 1:00 am)' }
    ];

    const REDISCOVER_REFRESH_OPTIONS = [
        { value: 'daily', label: 'Daily (1:00 am)' },
        { value: 'weekly', label: 'Weekly (Monday 1:00 am, default)' },
        { value: 'monthly', label: 'Monthly (1st of month 1:00 am)' },
        { value: 'never', label: 'Never' }
    ];

    /**
     * Reads an HTML select/radio group from the DOM and returns the option
     * labels that are currently defined for it.
     *
     * @param {string} selector CSS selector for the select element
     * @param {Array<{value: string, label: string}>} fallbacks
     * @returns {Array<string>} labels in DOM order
     */
    function optionLabels(selector, fallbacks) {
        const el = document.querySelector(selector);
        if (el) {
            const labels = Array.from(el.options)
                .map(function (o) { return (o.textContent || '').trim(); })
                .filter(Boolean);
            if (labels.length) return labels;
        }
        return fallbacks.map(function (o) { return o.label; });
    }

    /**
     * Reads min/max/value of a range input so the help text stays accurate
     * even if the sliders are re-tuned later.
     */
    function rangeInfo(selector, fallbackMin, fallbackMax, fallbackValue) {
        const el = document.getElementById(selector);
        if (!el) {
            return { min: fallbackMin, max: fallbackMax, value: fallbackValue };
        }
        return {
            min: Number(el.min || fallbackMin),
            max: Number(el.max || fallbackMax),
            value: Number(el.value || fallbackValue)
        };
    }

    /**
     * Reads the checked radio of a radio group by name.
     */
    function checkedRadioValue(name, fallback) {
        const el = document.querySelector('input[name="' + name + '"]:checked');
        return el ? el.value : fallback;
    }

    /**
     * Reads the numeric value of a number input.
     */
    function numberOr(inputId, fallback) {
        const el = document.getElementById(inputId);
        if (!el) return fallback;
        const value = Number(el.value);
        return Number.isFinite(value) ? value : fallback;
    }

    // -------------------------------------------------------------------------
    // Content definitions per playlist type
    // -------------------------------------------------------------------------

    const helpContent = {

        this_is: {
            title: 'This Is Artist',
            get subtitle() {
                return 'Single-artist playlist built from your library';
            },
            render() {
                const topTracks = rangeInfo('this-is-top-tracks-count', 0, 20, 15);
                const length = checkedRadioValue('artist-playlist-length', '25');
                const refresh = checkedRadioValue('artist-refresh-frequency', 'none');

                return [
                    section('What data is used', [
                        bullet('All tracks of the <strong>selected artist</strong> that are present in the libraries selected in the sidebar.'),
                        bullet('Navidrome only: Fetch the artist\'s <strong>top tracks</strong> from the <strong>Listenbrainz API</strong>. '),
                        bullet('Optional <strong>MusicBrainz ID</strong> lookup so the artist is matched reliably even if metadata is inconsistent.')
                    ]),
                    section('Available options', [
                        optionRow('Choose an artist', 'The artist used for Playlist curation'),
                        optionRow('Top Tracks per Artist', 'Range ' + topTracks.min + '–' + topTracks.max + ' (default ' + topTracks.value + '). Only shown with Navidrome. Top tracks from the internal Navidrome API are fetched and pre‑scored high to be preferred in AI selection.'),
                        optionRow('Playlist Length', '25 / 50 / 100 tracks (currently ' + length + '). The desired length for the Playlist'),
                        optionRow('Refresh Frequency', ' Rebuilds the playlist on a schedule with the same settings.')
                    ]),
                    section('Notes', [
                        bullet('No year range, quality or diversity filters are available for this playlist type yet – the artist\'s full catalogue is considered.'),
                        bullet('Availability of tracks depends on the libraries selected in the sidebar.')
                    ])
                ];
            }
        },

        artist_radio: {
            title: 'Artist Radio',
            subtitle: 'Similar-artist radio seeded by a source artist',
            render() {
                const lbEnabled = isChecked('artist-radio-listenbrainz-enabled');
                const algorithm = getSelectValue('artist-radio-algorithm', '5Y-Balanced');
                const score = rangeInfo('artist-radio-score', 50, 400, 142);
                const topTracks = rangeInfo('artist-radio-top-tracks-count', 0, 10, 3);
                const albumCap = numberOr('artist-radio-album-cap', 4);
                const artistCap = numberOr('artist-radio-artist-cap', 8);
                const capsEnabled = isChecked('artist-radio-diversity-enabled');
                const length = checkedRadioValue('artist-radio-playlist-length', '25');
                const refresh = checkedRadioValue('artist-radio-refresh-frequency', 'none');

                const parts = [
                    section('What data is used', [
                        bullet('A <strong>source artist</strong> chosen from your library as the seed for the radio mix.'),
                        bullet(lbEnabled
                            ? '<strong>ListenBrainz similar-artist recommendations</strong> for that seed artist, filtered by algorithm and minimum similarity score.'
                            : 'ListenBrainz recommendations are <strong>disabled</strong> – the mix is built purely from artists you pick manually below.'),
                        bullet('All tracks of the selected similar / manual artists inside the selected libraries.'),
                        bullet('Navidrome only: <strong>top tracks</strong> of the selected artists are used as priority tracks.'),
                        bullet('Optional year range and audio-quality filters are applied to the candidate pool.')
                    ]),
                    section('Available options', [
                        optionRow('Source artist', 'The seed. Everything else – the similar artists, the track pool – is derived from it.'),
                        optionRow('Use ListenBrainz similarity', 'When enabled, similar artists are fetched automatically from ListenBrainz. Disable it to build the artist mix entirely by hand.'),
                        optionRow('MusicBrainz artist ID', 'Only shown when the chosen source artist has no MusicBrainz ID in your metadata. Required to query ListenBrainz.'),
                        optionRow('ListenBrainz Algorithm', lbEnabled ? optionLabels('#artist-radio-algorithm', LISTENBRAINZ_ALGORITHMS).join(' · ') + ' (currently ' + algorithm + '). The algorithm decides <em>how</em> similarity is computed: a balanced 5-year window is a good default, broader windows include more distant influences, short windows stay close to current taste.' : 'Disabled – algorithm has no effect.'),
                        optionRow('Minimum Similarity Score', 'Range ' + score.min + '–' + score.max + ' (default ' + score.value + '). Artists with a score below this value are dropped. <strong>Lower</strong> = a larger, more adventurous artist pool; <strong>higher</strong> = only close relatives of the source artist.'),
                        optionRow('Find Similar Artists', 'Fetches the recommendation list from ListenBrainz using the algorithm and score above. The results appear in the two selection fields.'),
                        optionRow('Similar Artists Available in Your Library', 'The recommended artists that actually exist in your library. <strong>This is the decisive field</strong> – only the artists you leave selected here contribute tracks. Deselecting an artist removes them from the pool entirely.'),
                        optionRow('Add Other Library Artists', 'Adds any further artists from your library by hand, so you can steer the mix beyond what ListenBrainz suggests.'),
                        optionRow('Fetch Top Tracks per Selected Artist', 'Range ' + topTracks.min + '–' + topTracks.max + ' (default ' + topTracks.value + '). Navidrome only. Top tracks are always included and <strong>ignore the diversity caps</strong> below. 0 disables this.'),
                        optionRow('Year Range', 'Only tracks released within this range enter the candidate pool. Leave empty for no restriction. A narrow range strongly shapes the era/genre of the station; a wide range keeps it open.'),
                        optionRow('Minimum Quality', optionLabels('#artist-radio-min-bitrate', BITRATE_OPTIONS).join(' · ') + ' Lossy tracks below the chosen bitrate are removed; lossless tracks are always kept.'),
                        optionRow('Format / Bit Depth', 'Selecting <strong>FLAC</strong> switches the quality filter to bit depth (' + optionLabels('#artist-radio-min-bitdepth', BITDEPTH_OPTIONS).join(' · ') + ') and drops all lossy files. <strong>MP3</strong> uses the bitrate list instead.'),
                        optionRow('Use Limits', capsEnabled ? 'Enabled. The two caps below are applied.' : 'Disabled – both caps are set to 0 and no per-album / per-artist restriction is applied.'),
                        optionRow('Tracks per album', capsEnabled ? 'Currently ' + albumCap + '. Maximum tracks taken from a single album. Lower values spread the playlist across more albums; 0 disables the cap.' : 'Inactive while "Use Limits" is off.'),
                        optionRow('Tracks per artist', capsEnabled ? 'Currently ' + artistCap + '. Maximum tracks taken from a single artist. Lower values force a more even spread across the artist mix; 0 disables the cap.' : 'Inactive while "Use Limits" is off.'),
                        optionRow('Playlist Length', '25 / 50 / 100 tracks (currently ' + length + ').'),
                        optionRow('Refresh Frequency', refreshOptionsLabel(REFRESH_OPTIONS, refresh) + ' Re-runs the whole pipeline, including the ListenBrainz lookup, unless the stored recommendations are reused.')
                    ])
                ];

                if (lbEnabled) {
                    parts.push(section('Refreshing', [
                        bullet('When the playlist refreshes, ListenBrainz can either reuse the stored recommendation snapshot or query again for a fresh one (see the edit dialog). Reusing keeps the artist mix stable, re-querying lets it evolve.')
                    ]));
                }

                return parts;
            }
        },

        genre_mix: {
            title: 'Genre Mix',
            subtitle: 'Curated genre playlist with diversity controls',
            render() {
                const albumCap = numberOr('genre-max-tracks-per-album', 2);
                const artistCap = numberOr('genre-max-tracks-per-artist', 3);
                const capsEnabled = isChecked('genre-caps-enabled');
                const length = checkedRadioValue('genre-playlist-length', '25');
                const refresh = checkedRadioValue('genre-refresh-frequency', 'none');

                return [
                    section('What data is used', [
                        bullet('Every track tagged with one of the <strong>selected genres</strong> in the selected libraries.'),
                        bullet('Your <strong>listening behaviour</strong>: play counts and ratings are used to build a "core" of well-loved tracks, blended with a rotating slice of lesser-played but genre-typical tracks, so repeated refreshes do not keep returning the same hits.'),
                        bullet('Optional year range and audio-quality filters narrow the candidate pool before curation.'),
                        bullet('Artists you <strong>exclude</strong> are removed from the pool entirely.')
                    ]),
                    section('Available options', [
                        optionRow('Choose a genre', 'One or more genres. Tracks matching <em>any</em> of the selected genres are eligible. Selecting a single genre makes the playlist a pure deep-dive; selecting several blends them into a mix.'),
                        optionRow('Year Range', 'Only tracks released within this range are considered. Leave empty for no restriction.'),
                        optionRow('Exclude Artists', 'Artists removed from the candidate pool. Use the refresh button to load the artists that actually occur in the selected genres. Useful to avoid over-representing one artist or a genre variant.'),
                        optionRow('Minimum Quality', optionLabels('#genre-min-bitrate', BITRATE_OPTIONS).join(' · ') + ' Lossy tracks below the chosen bitrate are dropped; lossless tracks are always kept.'),
                        optionRow('Format / Bit Depth', 'Selecting <strong>FLAC</strong> switches to bit depth (' + optionLabels('#genre-min-bitdepth', BITDEPTH_OPTIONS).join(' · ') + ') and drops all lossy files. <strong>MP3</strong> uses the bitrate list.'),
                        optionRow('Playlist Length', '25 / 50 / 100 tracks (currently ' + length + ').'),
                        optionRow('Use Limits', capsEnabled ? 'Enabled. The two caps below are applied to keep the mix varied.' : 'Disabled – both caps are set to 0 and no per-album / per-artist restriction is applied.'),
                        optionRow('Tracks per album', capsEnabled ? 'Currently ' + albumCap + '. Lower values force the playlist to draw from more distinct albums.' : 'Inactive while "Use Limits" is off.'),
                        optionRow('Tracks per artist', capsEnabled ? 'Currently ' + artistCap + '. Lower values prevent a single artist from dominating the genre mix.' : 'Inactive while "Use Limits" is off.'),
                        optionRow('Refresh Frequency', refreshOptionsLabel(REFRESH_OPTIONS, refresh) + ' Because the selection blends a fixed "core" with a rotating exploration slice, each refresh returns a partly different selection instead of an identical playlist.')
                    ])
                ];
            }
        },

        rediscover: {
            title: 'Re-Discover Playlist',
            subtitle: 'Forgotten tracks derived from your listening history',
            render() {
                const length = checkedRadioValue('rediscover-playlist-length', '25');
                const refresh = checkedRadioValue('rediscover-refresh-frequency', 'weekly');

                return [
                    section('What data is used', [
                        bullet('Your <strong>complete listening history</strong>: every play count, every "last played" timestamp.'),
                        bullet('Tracks you have played before but <strong>not recently</strong> – the core criterion. Recently played tracks are skipped so the playlist stays a genuine rediscovery.'),
                        bullet('Your <strong>ratings / starred status</strong> as a positive signal: well-rated tracks are prioritised.'),
                        bullet('Aggregated profile of your library: top genres, top artists and top decades are analysed first, then candidate tracks are searched and filtered to match your taste profile.'),
                        bullet('Two AI passes run automatically: a broad, low-cost analysis pass finds candidates, a focused pass ranks and selects the final tracks.')
                    ]),
                    section('Available options', [
                        optionRow('Playlist Length', '25 or 50 tracks (currently ' + length + '). This playlist type intentionally offers no 100-track option.'),
                        optionRow('Refresh Frequency', REDISCOVER_REFRESH_OPTIONS.map(function (o) { return o.label; }).join(' · ') + ' Currently <strong>' + refresh + '</strong>. Running it on a schedule is the intended usage – each run acts on the listening history accumulated since the last run, so a frequent schedule surfaces different forgotten tracks.')
                    ]),
                    section('Notes', [
                        bullet('There are no filters, year ranges or quality options for this type – the outcome depends purely on your listening data. Everything is configured in the navigation settings, which apply to all Re-Discover playlists.'),
                        bullet('The richer your listening history (and any ratings you have set), the better the results.')
                    ])
                ];
            }
        }
    };

    // -------------------------------------------------------------------------
    // Small HTML builders
    // -------------------------------------------------------------------------

    function section(title, rows) {
        return '<div>' +
            '<h4 class="text-sm font-bold text-gray-900 dark:text-gray-100 uppercase tracking-wide mb-3">' + title + '</h4>' +
            '<div class="space-y-3">' + rows.join('') + '</div>' +
            '</div>';
    }

    function bullet(html) {
        return '<p class="text-sm text-gray-600 dark:text-gray-300 flex gap-2">' +
            '<span class="text-blue-500 dark:text-blue-400 mt-0.5 shrink-0">&#8226;</span>' +
            '<span>' + html + '</span>' +
            '</p>';
    }

    function optionRow(name, description) {
        return '<div class="rounded-lg border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 p-3">' +
            '<p class="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">' + name + '</p>' +
            '<p class="text-sm text-gray-600 dark:text-gray-400">' + description + '</p>' +
            '</div>';
    }

    function refreshOptionsLabel(options, current) {
        return options.map(function (o) {
            return o.value === current ? '<strong>' + o.label + '</strong>' : o.label;
        }).join(' · ');
    }

    // -------------------------------------------------------------------------
    // DOM helpers
    // -------------------------------------------------------------------------

    function isChecked(id) {
        const el = document.getElementById(id);
        return !!(el && el.checked);
    }

    function getSelectValue(id, fallback) {
        const el = document.getElementById(id);
        return el && el.value ? el.value : fallback;
    }

    // -------------------------------------------------------------------------
    // Public API
    // -------------------------------------------------------------------------

    /**
     * Opens the help modal for a given playlist type.
     * Unknown types fall back to a generic overview.
     *
     * @param {'this_is'|'artist_radio'|'genre_mix'|'rediscover'} type
     */
    function openHelpModal(type) {
        const config = helpContent[type] || helpContent.this_is;
        const overlay = document.getElementById('help-modal-overlay');
        const modal = document.getElementById('help-modal');
        const title = document.getElementById('help-modal-title');
        const subtitle = document.getElementById('help-modal-subtitle');
        const content = document.getElementById('help-modal-content');

        if (title) title.textContent = 'How ' + config.title + ' works';
        if (subtitle) subtitle.textContent = config.subtitle;
        if (content) content.innerHTML = config.render().join('');

        if (overlay) overlay.classList.remove('hidden');
        if (modal) modal.classList.remove('hidden');
    }

    function closeHelpModal() {
        const overlay = document.getElementById('help-modal-overlay');
        const modal = document.getElementById('help-modal');
        if (overlay) overlay.classList.add('hidden');
        if (modal) modal.classList.add('hidden');
    }

    // Wire close handlers (overlay click, backdrop click, buttons)
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
        types: Object.keys(helpContent)
    });
    // Bare globals so main.js can use its "prefer global" pattern
    window.openHelpModal = openHelpModal;
    window.closeHelpModal = closeHelpModal;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindCloseHandlers);
    } else {
        bindCloseHandlers();
    }
})(window, document);