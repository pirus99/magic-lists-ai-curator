# API Reference

Complete reference of every HTTP endpoint exposed by MagicLists AI Curator.

- **Base URL:** `http://<host>:4545` (or `http://localhost:8000` inside the container)
- **Content type:** `application/json` for all request and response bodies unless noted
- **Interactive docs:** `/docs` (Swagger UI) and `/redoc` are served automatically by FastAPI at runtime
- **Authentication:** none — the API is unauthenticated. Do not expose it directly to the public internet.

**Conventions used below**

- All routes are prefixed with `/api` except the page routes and the static mount.
- List-style query parameters use **repeated keys**: `?genres=Rock&genres=Pop`
- Optional list query parameters default to "all libraries" when omitted.
- Errors are returned as `{"detail": "..."}` with an appropriate HTTP status code.

**Common status codes**

| Code | Meaning |
|------|---------|
| `400` | Validation error (missing/invalid field, out-of-range value) |
| `401` | Media server rejected the configured credentials |
| `404` | Entity not found (artist, playlist, insufficient listening history) |
| `422` | Malformed request (e.g. a required query parameter was not supplied) |
| `500` | Unexpected server error |
| `502` | Upstream media server (Navidrome / Jellyfin) rejected the operation |
| `503` | Media server unreachable |

---

## Table of contents

- [Page routes](#page-routes)
- [Library & metadata](#library--metadata)
- [This Is (artist)](#this-is-artist)
- [Artist Radio & ListenBrainz](#artist-radio--listenbrainz)
- [Genre Mix](#genre-mix)
- [Re-Discover](#re-discover)
- [Playlist management](#playlist-management)
- [Recipes](#recipes)
- [Scheduler](#scheduler)
- [Diagnostics & system info](#diagnostics--system-info)
- [Removed / superseded endpoints](#removed--superseded-endpoints)

---

## Page routes

These return HTML, not JSON.

### `GET /`

Main web interface. Redirects (302) to `/system-check` if the startup health checks have not passed.

### `GET /system-check`

System check / health diagnostics page. Rendered by the same SPA shell as `/`.

### `GET /{path:path}` (SPA fallback)

Catch-all route, **must remain last**. For the known SPA paths `this-is`, `artist-radio`, `re-discover`, `playlists`, and `terms` it serves the app shell (redirecting to `/system-check` if checks failed). Any other path is redirected to `/`.

### `GET /static/*`

Static assets (JS, CSS, images) mounted from `frontend/static`.

---

## Library & metadata

### `GET /api/artists`

List all artists known to the configured media server.

| Query param | Type | Required | Default | Description |
|-------------|------|----------|---------|-------------|
| `library_id` | list of strings | No | all libraries | Restrict the result to the given library IDs. Repeat the key for multiple libraries. |

**Response:** array of artist objects

```json
[{ "id": "abc123", "name": "Radiohead", "album_count": 9, "song_count": 154, "mbid": "a74b1b7f-71a5-4011-9441-d0b5e4122711" }]
```

**Errors:** `401`, `503`, `500`

---

### `GET /api/genres`

List all genres known to the configured media server.

| Query param | Type | Required | Default | Description |
|-------------|------|----------|---------|-------------|
| `library_id` | list of strings | No | all libraries | Restrict the result to the given library IDs. |

**Errors:** `401`, `503`, `500`

---

### `GET /api/artists-by-genre`

List artists that have at least one track in the given genres. Used by the Genre Mix UI to populate the artist-blacklist selector.

| Query param | Type | Required | Default | Description |
|-------------|------|----------|---------|-------------|
| `genres` | list of strings | **Yes** | — | Genre names to match. Omitting it returns `422`. |
| `library_id` | list of strings | No | all libraries | Restrict the result to the given library IDs. |

**Example**

```
GET /api/artists-by-genre?genres=Rock&genres=Indie&library_id=1&library_id=2
```

**Response:** array of objects

```json
[{ "id": "123456", "name": "Radiohead" }]
```

> **Server differences:** the Navidrome backend resolves artists by track artist *name* and synthesises the `id` (`abs(hash(name)) % 10**12`), so it is not a real Navidrome artist ID and is not stable across restarts. The Jellyfin backend returns real `ArtistItems[0].Id` values but caps each genre query at 500 items. The UI keys off `name`, so both behave identically in practice.

**Errors:** `401`, `422`, `503`, `500`

---

### `GET /api/music-folders`

List the available music libraries / folders on the media server. No parameters. Feed the returned IDs into the `library_id` parameters of the other endpoints.

**Errors:** `401`, `503`, `500`

---

## This Is (artist)

### `POST /api/create_playlist`

Create an AI-curated "This Is" playlist for a single artist. The AI description is **always** generated and stored, so there is no separate description endpoint.

**Request body** (`CreatePlaylistRequest`)

| Field | Type | Required | Default | Constraints / description |
|-------|------|----------|---------|--------------------------|
| `artist_ids` | list of strings | **Yes** | — | Non-empty. Only `artist_ids[0]` is used as the source artist. |
| `playlist_name` | string | No | auto-generated | Playlist title. |
| `refresh_frequency` | string | No | `"none"` | One of `none`, `daily`, `weekly`, `monthly`. |
| `playlist_length` | int | No | `25` | Number of tracks. |
| `library_ids` | list of strings | No | `[]` (all) | Libraries to source tracks from. |
| `top_tracks_enabled` | bool | No | `false` | Bias selection toward the artist's most-played tracks. |
| `top_tracks_count` | int | No | `0` | `0`–`20`. Max number of top tracks to include. |

**Example**

```bash
curl -X POST http://localhost:4545/api/create_playlist \
  -H "Content-Type: application/json" \
  -d '{"artist_ids": ["abc123"], "playlist_length": 30, "refresh_frequency": "weekly"}'
```

**Response:** the created `Playlist` object

```json
{
  "id": 12,
  "artist_id": "abc123",
  "playlist_name": "This Is Radiohead",
  "songs": ["1", "2", "…"],
  "description": "…",
  "navidrome_playlist_id": "pl-987",
  "is_public": false,
  "library_ids": [],
  "playlist_length": 25,
  "playlist_type": "this_is",
  "created_at": "2026-01-01 12:00:00",
  "updated_at": "2026-01-01 12:00:00"
}
```

**Errors:** `400` (no artist selected), `404` (artist not found), `500`

---

## Artist Radio & ListenBrainz

Artist Radio discovers similar artists through the [ListenBrainz Labs](https://labs.api.listenbrainz.org) API, then intersects those recommendations with artists actually present in your library. Requires a MusicBrainz artist ID (MBID) for the source artist.

### `POST /api/artist-radio/recommendations`

Fetch raw similar-artist recommendations from ListenBrainz Labs.

**Query parameters**

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source_mbid` | string | **Yes** | — | MusicBrainz ID of the source artist. Must parse as a UUID. |
| `algorithm` | string | **Yes** | — | ListenBrainz Labs algorithm, e.g. `5Y Balanced`, `5Y Similar`, `All Time Similar`. |
| `minimum_score` | int | No | `50` | Lower bound on the ListenBrainz match score. |

**Example**

```bash
curl -X POST "http://localhost:4545/api/artist-radio/recommendations?source_mbid=a74b1b7f-71a5-4011-9441-d0b5e4122711&algorithm=5Y%20Balanced&minimum_score=50"
```

**Errors:** `400` (missing/invalid MBID), `502` (ListenBrainz unreachable or returned an error)

---

### `POST /api/artist-radio/recommendations/local`

Same as above, but the results are filtered down to artists that are actually available in the selected libraries, and annotated with their local artist IDs. This is what the Artist Radio UI calls.

**Query parameters**

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `library_id` | list of strings | No | all libraries | Restrict matching to these libraries. Takes precedence over `library_ids` in the body. |

**Request body** (`ArtistRadioRecommendationRequest`)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source_mbid` | string | **Yes** | — | MusicBrainz ID of the source artist. Must parse as a UUID. |
| `algorithm` | string | No | `"5Y Balanced"` | ListenBrainz Labs algorithm. |
| `minimum_score` | int | No | `50` | Lower bound on the match score. |
| `artist_id` | string | No | `null` | Local artist ID, if known. |
| `library_ids` | list of strings | No | `[]` (all) | Libraries to match against. |

**Response:** array of at most 20 matched recommendations, each annotated with its local artist

```json
[
  {
    "mbid": "…",
    "name": "Boards of Canada",
    "score": 210,
    "local_artist_id": "xyz789",
    "local_artist_name": "Boards of Canada"
  }
]
```

**Errors:** `400` (invalid MBID), `502` — including `400` with *"ListenBrainz returned no artists available in the selected libraries"* when nothing matches.

---

### `POST /api/create_artist_radio`

Create an Artist Radio playlist. The artist pool is the union of your ListenBrainz selections and any manually picked artists.

**Request body** (`ArtistRadioRequest`)

| Field | Type | Required | Default | Constraints / description |
|-------|------|----------|---------|--------------------------|
| `artist_id` | string | **Yes** | — | The source artist. Must exist in the selected libraries. |
| `source_mbid` | string | Conditional | `null` | **Required** when `listenbrainz_enabled` is `true`. Must be a valid UUID. |
| `listenbrainz_enabled` | bool | No | `true` | Use ListenBrainz discovery. Set `false` for a purely manual artist pool. |
| `algorithm` | string | No | `"5Y Balanced"` | ListenBrainz Labs algorithm. |
| `minimum_score` | int | No | `142` | `50`–`400`. |
| `recommendation_ids` | list of strings | No | `[]` | MBIDs chosen from the recommendations list. |
| `manual_artist_ids` | list of strings | No | `[]` | Local artist IDs added by hand. |
| `refetch_listenbrainz` | bool | No | `false` | Re-query ListenBrainz instead of trusting the stored recommendations. |
| `artist_name` | string | No | resolved from `artist_id` | Display name for the source artist. |
| `playlist_name` | string | No | auto-generated | Playlist title. |
| `refresh_frequency` | string | No | `"none"` | `none`, `daily`, `weekly`, `monthly`. |
| `playlist_length` | int | No | `25` | Number of tracks. |
| `library_ids` | list of strings | No | `[]` (all) | Libraries to source tracks from. |
| `year_start` | int | No | `null` | Minimum release year. Must be ≤ `year_end`. |
| `year_end` | int | No | `null` | Maximum release year. |
| `diversity_enabled` | bool | No | `true` | Apply the per-album / per-artist caps below. |
| `max_tracks_per_album` | int | No | `4` | Must be ≥ 0. |
| `max_tracks_per_artist` | int | No | `8` | Must be ≥ 0. |
| `min_bitrate` | int | No | `null` | Minimum bitrate in kbps. |
| `min_format` | string | No | `null` | Minimum format, e.g. `flac`. |
| `min_bit_depth` | int | No | `null` | Minimum FLAC bit depth (16, 24). |
| `top_tracks_enabled` | bool | No | `false` | Bias toward most-played tracks. |
| `top_tracks_count` | int | No | `0` | `0`–`10`. |

**Response:** the created `Playlist` object (same shape as [`POST /api/create_playlist`](#post-apicreate_playlist))

**Validation errors (`400`)**

- `A MusicBrainz artist ID is required when ListenBrainz is enabled`
- `Minimum score must be between 50 and 400`
- `Year start must not be after year end`
- `Diversity caps cannot be negative`
- `Source artist is not available in the selected libraries`
- `One or more selected artists are not available in the selected libraries`

---

## Genre Mix

### `POST /api/create_genre_playlist`

Create an AI-curated "Genre Mix" playlist from one or more genres, with optional filtering.

**Request body** (`CreateGenrePlaylistRequest`)

| Field | Type | Required | Default | Constraints / description |
|-------|------|----------|---------|--------------------------|
| `genres` | list of strings | **Yes** | — | Non-empty list of genre names. |
| `playlist_name` | string | No | auto-generated | Playlist title. |
| `refresh_frequency` | string | No | `"none"` | `none`, `daily`, `weekly`, `monthly`. |
| `playlist_length` | int | No | `25` | Number of tracks. |
| `library_ids` | list of strings | No | `[]` (all) | Libraries to source tracks from. |
| `year_start` | int | No | `null` | Minimum release year (1950–2026). |
| `year_end` | int | No | `null` | Maximum release year (1950–2026). |
| `blacklisted_artists` | list of strings | No | `[]` | Artist **names** to exclude. Populated via [`GET /api/artists-by-genre`](#get-apiartists-by-genre). |
| `min_bitrate` | int | No | `null` | Minimum bitrate in kbps (128, 192, 256, 320). |
| `min_format` | string | No | `null` | Minimum format (`mp3`, `flac`, `aac`, …). |
| `min_bit_depth` | int | No | `null` | Minimum FLAC bit depth (16, 24). FLAC-only filter; `null` = any. |
| `max_tracks_per_album` | int | No | `null` | Global cap per album. `0` or `null` disables. |
| `max_tracks_per_artist` | int | No | `null` | Cap per artist. `0` or `null` disables. |

**Response:** the created `Playlist` object

**Errors:** `400` (no genre selected), `500`

---

## Re-Discover

### `GET /api/rediscover-weekly-v2`

Generate Re-Discover Weekly (v2) recommendations using temporal analysis and a two-phase AI pass. This is a *preview* — nothing is written to the media server.

**Query parameters**

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `library_ids` | list of strings | No | all libraries | Restrict the analysis to these libraries. |

**Response** (`RediscoverWeeklyV2Response`)

```json
{
  "name": "Re-Discover Weekly",
  "tracks": [],
  "theme": "…",
  "mode": "…",
  "description": "…",
  "user_id": "…",
  "server_id": "…",
  "generated_at": "2026-01-01T12:00:00Z",
  "is_fallback": false
}
```

**Errors:** `404` — returned when there is insufficient listening history (*"Insufficient listening history. Star favorites and listen regularly. Check back in 2-3 weeks!"*); also `401`, `503`, `500`.

---

### `POST /api/create-rediscover-playlist-v2`

Create the Re-Discover Weekly (v2) playlist in the media server and store it locally.

**Request body** (`CreateRediscoverPlaylistRequest`)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `refresh_frequency` | string | No | `"weekly"` | `daily`, `weekly`, `monthly`. |
| `playlist_length` | int | No | `25` | Number of tracks. |
| `library_ids` | list of strings | No | `[]` (all) | Libraries to source tracks from. |

**Errors:** `404` (insufficient listening history), `500`

---

## Playlist management

All of these operate on MagicLists' internal playlist IDs (the `id` field returned by `GET /api/playlists`), **not** the media server's playlist ID.

### `GET /api/playlists`

List all managed playlists, enriched with scheduling info and a `track_count`. No parameters.

Runs a reconciliation pass first (see `POST /api/playlists/reconcile`), so playlists that were deleted directly in Navidrome/Jellyfin are omitted instead of appearing as stale entries.

---

### `POST /api/playlists/reconcile`

Reconcile locally tracked playlists against the media server. Removes local playlist and schedule records whose media-server playlist no longer exists. No parameters.

This is safe to call repeatedly and is a no-op when everything is in sync. It also runs automatically on `GET /api/playlists` and before each scheduled refresh sweep.

If the media server is unreachable, **nothing is deleted** — a network failure must not drop tracking data for playlists that still exist. The response reports this via `orphaned: true`.

**Response**

```json
{
  "message": "Reconciliation complete",
  "checked": 12,
  "removed_ids": [41, 42],
  "removed_names": ["Daily Mix", "This Is Radiohead"],
  "orphaned": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `checked` | int | Number of locally tracked playlists that were inspected. |
| `removed_ids` | int[] | MagicLists playlist IDs that were removed. |
| `removed_names` | string[] | Names of the removed playlists. |
| `orphaned` | bool | `true` when the media server was unreachable and nothing was reconciled. |

**Errors:** `500`

---

### `GET /api/playlists/{playlist_id}`

Fetch a single playlist with its schedule info and saved curation settings.

| Path param | Type | Required | Description |
|------------|------|----------|-------------|
| `playlist_id` | int | **Yes** | The MagicLists playlist ID. |

**Errors:** `404` (not found), `500`

---

### `DELETE /api/playlists/{playlist_id}`

Delete a playlist from both the media server and the local database.

| Path param | Type | Required | Description |
|------------|------|----------|-------------|
| `playlist_id` | int | **Yes** | The MagicLists playlist ID. |

**Idempotent:** if the playlist was already deleted directly in Navidrome/Jellyfin, the server-side delete is treated as successful and the local records (playlist + schedule) are still removed. This endpoint no longer fails with a "playlist not found" error in that situation.

**Response**

```json
{ "message": "Playlist deleted successfully" }
```

**Errors:** `404` (no such MagicLists playlist), `502` (media server refused the delete for a reason other than "already gone" — the local record is left intact), `500`

---

### `PUT /api/playlists/{playlist_id}/settings`

Update a playlist's saved curation settings, metadata, and refresh schedule. Any of `playlist_name`, `description`, or `is_public` that is present are synced to the media server; `refresh_frequency` reconciles the schedule entry.

**Path params**

| Path param | Type | Required | Description |
|------------|------|----------|-------------|
| `playlist_id` | int | **Yes** | The MagicLists playlist ID. |

**Request body** (`UpdatePlaylistSettingsRequest`)

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `curation_settings` | object | **Yes** | — | Free-form settings blob. Must at least support `playlist_length`, `top_tracks_enabled`, and `top_tracks_count`. `top_tracks_count` is clamped to 20 for `this_is` and 10 for `artist_radio` playlists; for other playlist types the top-tracks keys are stripped. |
| `refresh_frequency` | string | No | `null` | `none`/`never` removes the schedule; otherwise the schedule is created or updated. |
| `playlist_name` | string | No | `null` | New playlist title. |
| `description` | string | No | `null` | New playlist comment/description. |
| `is_public` | bool | No | `null` | Public visibility on the media server. |

**Response:** the updated playlist object, including `track_count`

**Errors:** `400` (playlist has no media server ID), `404` (not found), `502` (media server rejected the metadata update), `500`

---

### `POST /api/playlists/{playlist_id}/refresh`

Manually regenerate a playlist from its saved curation settings, dispatching to the correct builder based on `playlist_type` (`genre_mix`, `artist_radio`, `rediscover` / `rediscover_weekly_v2`, or `this_is`).

| Path param | Type | Required | Description |
|------------|------|----------|-------------|
| `playlist_id` | int | **Yes** | The MagicLists playlist ID. |

**Response**

```json
{ "message": "Playlist refreshed successfully", "playlist_id": "pl-987" }
```

> `playlist_id` in the response is the **media server** playlist ID.

**Errors:** `400` (playlist has no media server ID), `404`, `500`

---

## Recipes

Recipes are the per-playlist-type JSON prompts that drive AI curation. See [`recipes/README.md`](../recipes/README.md) for the format.

### `GET /api/recipes`

List all available recipe versions and their metadata. No parameters.

### `GET /api/recipes/validate`

Validate every recipe in the registry and report errors. Checks required fields
(`recipe_id`, `name`, `llm_config`, and a selection prompt), `user_parameters` token syntax,
prompt placeholder resolvability, `{{MATH:…}}` expressions, and the optional
`description_llm_config` / `output_sorting` / `source_filtering` / `max_candidate_tracks`
blocks. Recipes using the parameterized `inputs` format are validated against that shape instead.
No parameters.

**Response**

```json
{
  "this_is":       { "recipe_file": "this_is_v2.json", "valid": true,  "errors": [] },
  "genre_mix":     { "recipe_file": "genre_mix_v2.json", "valid": true, "errors": [] },
  "artist_radio":  { "recipe_file": "artist_radio_v1.json", "valid": true,  "errors": [] },
  "re_discover":   { "recipe_file": "re_discover_phase2_v2.json", "valid": true, "errors": [] },
  "re_discover_phase1_v2": { "recipe_file": "re_discover_phase1_v2.json", "valid": true, "errors": [] }
}
```

**Errors:** `500`

---

## Scheduler

### `GET /api/scheduler/status`

Report whether the background scheduler is running, its state, and its active jobs.

**Response**

```json
{
  "scheduler_running": true,
  "active_jobs": 1,
  "jobs": [{ "id": "playlist_refresh", "next_run_time": "2026-01-02T03:00:00+00:00", "func": "refresh_scheduled_playlists" }],
  "scheduler_state": "running"
}
```

If the scheduler is not initialised the response is `{"scheduler_running": false, "error": "Scheduler not initialized"}`.

**Errors:** `500`

---

### `POST /api/scheduler/trigger`

Run a scheduler pass immediately: refresh every playlist that is due, then return. No parameters.

**Response:** `{"message": "Scheduler check completed successfully"}`

**Errors:** `500`

---

### `POST /api/scheduler/start`

Register/start the recurring scheduler job. No parameters.

**Response**

```json
{ "message": "Scheduler job started", "active_jobs": 1, "jobs": [{ "id": "…", "next_run": "…"}] }
```

**Errors:** `500`

---

## Diagnostics & system info

### `GET /api/health-check`

Run the full system health check suite (environment variables, media server URL, authentication, artists API, AI provider, library configuration) and return the results. Also updates the state used by the `/` redirect.

**Response**

```json
{
  "all_passed": true,
  "checks": [
    { "name": "Navidrome URL", "status": "pass", "message": "…", "suggestion": "" }
  ]
}
```

Never returns an error status for a failed *check* — failures are reported inside the payload. Only an internal failure produces a single check with `"status": "error"`.

---

### `GET /api/ai-model-info`

Report the configured AI provider and model. Useful for confirming which model the instance is actually using.

**Response**

```json
{ "provider": "google", "model": "gemini-3.5-flash", "has_api_key": true }
```

Never errors — on failure it returns `{"provider": "unknown", "model": "unknown", "has_api_key": false}`.

---

### `POST /api/track-library-size`

Record the current total song count for local analytics. The database decides whether tracking is due; if it is not, nothing is written.

**Response**

```json
{ "message": "Library size tracked successfully", "tracked": true, "song_count": 42123, "user_id": "…" }
```

or, when no tracking is due:

```json
{ "message": "Library size tracking not needed yet", "tracked": false }
```

**Errors:** `500`

---

## Removed / superseded endpoints

These paths are **not** routed any more. They are listed so you can update existing integrations.

| Endpoint | Status | Replacement |
|----------|--------|-------------|
| `POST /api/create_playlist_with_description` | Removed | `POST /api/create_playlist` — the AI description is now always generated and stored. |
| `GET /api/rediscover-weekly` | Removed (v1) | `GET /api/rediscover-weekly-v2` |
| `POST /api/create-rediscover-playlist` | Removed (v1) | `POST /api/create-rediscover-playlist-v2` |
