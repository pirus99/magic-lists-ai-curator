# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Song Radio** (`backend/song_radio/`): build a radio playlist around a **single source
  track**. The track's MusicBrainz recording ID is sent to ListenBrainz's
  `similar-recordings` endpoint, results are matched against the local library by recording
  MBID (falling back to normalized title + artist), and the AI curates the final mix. The
  source track is pinned to position 1 and protected from the year/quality filters and
  diversity caps.
  - New endpoints: `POST /api/song-radio/search`, `POST /api/song-radio/recommendations`,
    `POST /api/song-radio/build-pool` (preview the candidate pool without creating a
    playlist) and `POST /api/create_song_radio`.
  - Recording-similarity algorithms (`5Y Balanced`, `20Y+`, `25Y Deep`, `3M Recent`,
    `20Y Broad`, `5Y Light`) with a `1`–`100` minimum score and 1–6 expansion rounds.
  - **Song Radio - Subsonic fallback**: on Navidrome, `getSimilarSongs2` can supplement or replace
    ListenBrainz, requiring no MusicBrainz IDs or external service.
  - New UI page (`frontend/templates/pages/_song_radio.html`) with library search, MBID
    fallback field, pool preview, year/quality filters, diversity caps and refresh
    scheduling; registered with the scheduler as `song_radio`.
  - New recipe `recipes/song_radio_v1.json`, registered in `recipes/registry.json`.
- Documentation for Song Radio: `README.md` feature summary and section, a full
  `docs/API.md` reference, `docs/ENVIRONMENT.md` ListenBrainz notes, server-specific
  sections in `docs/NAVIDROME.md` and `docs/JELLYFIN.md`, and the recipe-type table in
  `recipes/README.md`.

## [1.2.1] - 2026-11-16

### Added

- **Last.fm top tracks for Jellyfin** (`backend/services/lastfm_client.py`,
  `lastfm_service.py`): Jellyfin has no equivalent of Navidrome's `getTopSongs`, so
  **Top Tracks per Artist** on This Is and Artist Radio now resolves through Last.fm's
  `artist.getTopTracks`. Returned titles are matched against the artist's local tracks
  with a normalized, accent- and punctuation-insensitive comparison (ignoring suffixes
  such as `- Remastered`, `(feat. …)`, `- Live`), so only real library tracks with real
  Jellyfin item ids end up in the playlist. New env vars: `LASTFM_API_KEY`,
  `LASTFM_API_URL`, `LASTFM_TIMEOUT`.
  - New endpoint `GET /api/top-tracks/strategies` reports the active source
    (`native` / `lastfm`) plus `supported` (the server type has a source at all) and
    `configured` (it can service a request right now — `lastfm` needs an API key).
    The short labels (`Native`, `Last.fm`, `Hybrid`, `Off`) come from the backend, so
    the UI never hard-codes the wording.
  - The top-tracks control stays **visible on both server types**. Without a key it
    reads *Source: Last.fm*, shows a setup prompt, and playlists fall back to
    play-count ordering — the feature never silently disappears.
- **MusicBrainz ID override for This Is**: Jellyfin artist metadata frequently has no
  MBID, which Last.fm needs to resolve an artist. `POST /api/create_playlist` accepts an
  optional `artist_mbid`, and the This Is page shows a *MusicBrainz ID for Last.fm
  lookup* field when the source is Last.fm, top tracks are enabled and the artist has no
  MBID. It affects the Last.fm request only — never track selection — and is persisted as
  `artist_mbid_override` so scheduled refreshes reuse it. Empty values are ignored rather
  than stored, so they cannot shadow the library's own MBID.
- **Last.fm connectivity check** on the system-check page (Jellyfin only). It probes
  `artist.getTopTracks` — the same endpoint playlist builds use — and reports
  success/warning/error with an actionable suggestion. A missing key is a warning, never
  a startup failure.
- **Help system for playlist types** (`frontend/static/ui/help.js`,
  `frontend/templates/help/`): a *Help* button on each playlist page and in the
  edit-playlist modal opens per-type help content (This Is, Artist Radio, Genre Mix,
  Re-Discover) served by the new `GET /help/{help_type}` route.
- New tests: `test_lastfm_service.py` (title normalization, artist matching, top-track
  resolution) and `test_this_is_artist_fallback.py`.

### Changed

- `template_context()` now also injects `server_label` (`"Navidrome"` / `"Jellyfin"`) and
  the top-tracks strategy flags into every Jinja render. Templates must use
  `{{ server_label }}` instead of hard-coding a server name — the system-check page
  previously shipped a literal `data-server-type="jellyfin"` and read it back to build its
  own title, so Navidrome users saw "Jellyfin" there.
- `GET /help/{help_type}` renders through `template_context(request)`, so help partials
  have `server_label` available.
- `.env.example` reorganized and commented: `DATABASE_PATH` and `LOG_LEVEL` documented,
  Navidrome/Jellyfin blocks split out, Jellyfin auth options (API key vs. user/password)
  labelled, and the Last.fm block added.
- `POST /api/create_playlist` validates `artist_ids` before fetching the artist list,
  avoiding a needless API call on an empty request.
- Docs updated: `docs/JELLYFIN.md` (top tracks + MBID sections, new limitation),
  `docs/API.md` (top-tracks endpoint, `artist_mbid`, server-dependent health checks),
  `docs/ENVIRONMENT.md` (Last.fm variables), `docs/TROUBLESHOOTING.md`, and `README.md`.

### Notes for users

- **Navidrome**: nothing changes — top tracks keep using the native `getTopSongs` endpoint
  and `LASTFM_API_KEY` is not read.
- **Jellyfin**: add `LASTFM_API_KEY` (free key from
  [last.fm/api/account/create](https://www.last.fm/api/account/create)) to `.env` to enable
  top tracks. Last.fm is rate limited to roughly 5 requests/second and responses are not
  cached, so a refresh across many artists costs one request per artist.
- Upgrading is a normal pull + `docker compose up -d --build`; no database migration and no
  need to re-create existing playlists.

## [1.2.0] - 2026-10-05

### Added

- **Artist Radio** (`backend/artist_radio/`): build endless "similar artist" playlists
  from a seed artist, using ListenBrainz Labs recommendations plus manually picked
  artists. Includes its own recipe (`recipes/artist_radio_v1.json`), curator,
  builder, and API routes, and is registered with the scheduler as `artist_radio`.
  - New endpoints: `POST /api/artist-radio/recommendations`,
    `POST /api/artist-radio/recommendations/local`,
    `POST /api/create_artist_radio`.
  - New UI page/section (`frontend/templates/pages/_artist_radio.html`) with
    local-library matching of recommended artists, score threshold filtering
    (50–400), year range filter, and diversity caps per album/artist.
- **Editorial playlist descriptions**: recipes can now define
  `description_instructions` plus a separate `description_llm_config`, so the AI
  writes a short (~120 character) journalistic blurb for the finished playlist.
- **ListenBrainz integration** (`backend/services/listenbrainz_client.py`,
  `listenbrainz_service.py`) with new env vars `LISTENBRAINZ_LABS_URL`,
  `LISTENBRAINZ_TOKEN` (optional, only needed for rate-limited requests) and
  `LISTENBRAINZ_TIMEOUT`.
- **ListenBrainz connectivity check** in the system-check page (Navidrome only),
  reporting success/warning/error with actionable suggestions.
- **Top tracks enrichment** (`backend/services/top_tracks_service.py`): Navidrome's
  artist top-songs endpoint can seed and boost tracks for both **This Is** and
  **Artist Radio** playlists. Configurable per playlist (max 20).
- **Candidate limiting** (`backend/services/candidate_limiter.py`): caps the
  candidate pool sent to the AI app-wide. Precedence is `OLLAMA_MAX_TRACKS`
  (Ollama only) → the recipe's `max_candidate_tracks`; the highest-scoring tracks
  are kept.
- **Playlist reconciliation** (`backend/services/playlist_sync_service.py`):
  local playlists (and their schedules) deleted directly in Navidrome/Jellyfin
  are now cleaned up automatically. Runs on `GET /api/playlists` and before each
  scheduler sweep, plus a manual `POST /api/playlists/reconcile` endpoint. If the
  media server is unreachable nothing is deleted — the run is reported as
  `orphaned` instead, so a network blip cannot destroy tracking data.
- **Recipe validation rework**: recipes are validated against the current
  `user_parameters` + `{{PLACEHOLDER}}` format, with per-format validation
  (`_validate_current_format` / legacy parameterized format), LLM config checks
  (temperature range, positive `max_output_tokens`) and placeholder resolution
  against declared plus runtime placeholders.
- **`{{MATH:...}}` expression support** in recipe prompts, restricted to a safe
  allow-list of functions (`abs`, `round`, `min`, `max`, `ceil`, `floor`, `pow`,
  `sqrt`).
- **Output sorting**: `ensure_artist_spacing` / `ensure_album_spacing` now return a
  validity flag so spacing can be retried, including against the reversed
  playlist, before giving up (`space_album` helper).
- New documentation set under `docs/`: `API.md`, `AI_PROVIDERS.md`, `DOCKER.md`,
  `ENVIRONMENT.md`, `INSTALLATION.md`, `JELLYFIN.md`, `NAVIDROME.md`,
  `RUNNING_LOCALLY.md`, `TROUBLESHOOTING.md`.
- New tests: `test_artist_radio_curation.py`, `test_candidate_limiter.py`,
  `test_listenbrainz_service.py`, `test_navidrome_top_tracks.py`,
  `test_playlist_sync_service.py`.

### Changed

- Playlist deletion is now **idempotent**: if the playlist is already gone from the
  media server, the local records are still removed and the request succeeds.
- Track scoring is centralized in `calculate_track_score`
  (`backend/services/track_scoring_service.py`): play count is the base, local
  library likes add a small bonus, and Navidrome top tracks receive a larger one.
- `filter_tracks_for_this_is_playlist` renamed to
  `filter_tracks_for_genre_mix_playlist`; the removed `ollama_max_tracks` parameter
  is now handled centrally by the candidate limiter.
- All recipes migrated to the v2 format; superseded `this_is` and `re_discover`
  recipes moved to `recipes/archive/`, and all active recipes are registered in
  `recipes/registry.json` (`artist_radio` added).
- Frontend: enhanced edit-playlist modal, improved playlist item layout for mobile,
  reworked home page layout, and shared template context (`server_type`) exposed to
  all templates.
- `README.md` rewritten to be more concise, with setup details split into the new
  `docs/` pages; `OLLAMA_SETUP.md` and `SETUP.md` removed in favour of
  `docs/INSTALLATION.md` / `docs/AI_PROVIDERS.md`.

### Fixed

- Mobile: dark-mode button moved up ~48px so the OS navigation bar no longer covers it.
- Playlists deleted outside Magic Lists no longer raise errors during refresh or deletion.
- Artist/album spacing no longer reports success when tracks could not actually be spaced.

### Notes for users

- **Jellyfin**: Artist Radio's ListenBrainz recommendations and top-tracks
  enrichment are Navidrome-only. On Jellyfin the recommendation step is skipped and
  top-track settings are ignored; manual artist selection still works.
- Upgrading is a normal pull + `docker compose up -d --build`. Add the optional
  ListenBrainz variables to `.env` to enable recommendations; without a token,
  unauthenticated (rate-limited) requests are used.


## [1.1.0]

Upgrade from Ricky Synnot's version. Existing playlists should be re-created once so
they pick up the new curation settings; otherwise the upgrade is a clean update.

### Added

- **Filters and Sorting**: Added support for custom filters and sorting options primarily for Genre Mix playlists.
- **Playlist edit support**: existing playlists can now be re-curated and re-saved
  through the UI, including their saved recipe settings.
- **Dark mode** throughout the UI.
- **Jellyfin Support**: Jellyfin is now Supported for Playlist Creation and as Library Source. (WIP: Top tracks fetching)

### Fixed

- **Re-discover playlist creation** no longer fails.
- Numerous quality-of-life improvements and bug fixes.

### Notes for users

- **Create a Database Backup before updating!**
- Playlists created by earlier versions (Ricky Synnot's build) should be re-created
  once, otherwise their saved curation settings cannot be edited. See 1.1.0 below.
- If you still not able to Edit your playlist, completly delete your Magiclists Database and start from Scratch.


[1.2.0]: https://github.com/pirus99/magic-lists-ai-curator/releases/tag/1.2.0
[1.1.0]: https://github.com/pirus99/magic-lists-ai-curator/releases/tag/1.1.0