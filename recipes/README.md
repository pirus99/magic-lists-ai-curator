# Recipe System

This directory contains playlist generation recipes that define how different types of
playlists are created. A recipe is a JSON document that drives both the **LLM prompt** used
for curation and the **source-track filtering** applied before the model ever sees the data.

## Structure

- `registry.json` - Maps playlist types to their current default recipe files
- `{type}_v{major}_{minor}.json` - Individual recipe files with versioning
- `archive/` - Superseded recipe versions kept for reference

### `registry.json`

```json
{
  "this_is": "this_is_v2.json",
  "artist_radio": "artist_radio_v1.json",
  "genre_mix": "genre_mix_v2.json",
  "re_discover": "re_discover_phase2_v2.json",
  "re_discover_phase1_v2": "re_discover_phase1_v2.json",
  "re_discover_phase2_v2": "re_discover_phase2_v2.json"
}
```

The key is the playlist type requested by the API; the value is the recipe file used.

## Recipe File Format

Recipes come in two shapes. The **current** format (used by every recipe in this directory) is
described below. A **parameterized** format that declares its parameters via an `inputs` list is
still supported for backward compatibility and is handled automatically by `RecipeManager`.
`/api/recipes/validate` validates both shapes.

### Current recipe fields

| Field | Purpose |
|-------|---------|
| `recipe_id` | Unique identifier for the recipe |
| `name` | Human-readable name |
| `user_parameters` | Placeholders (`{{TARGET_ARTIST}}`, `{{DESIRED_TRACK_COUNT}}`, …) filled from the API request |
| `llm_config` | `max_output_tokens` and `temperature` for the curation call |
| `description_llm_config` | Optional LLM settings for the editorial-description call |
| `model_instructions` | The main prompt sent to the LLM (supports `{{MATH:...}}` expressions). Used by This Is and Re-Discover recipes |
| `selection_instructions` | The main prompt sent to the LLM for track selection (used by Genre Mix; falls back to `model_instructions` when absent) |
| `description_instructions` | Optional prompt for generating a short editorial blurb |
| `source_filtering` | Engagement-scoring config applied before the LLM runs (Genre Mix only) |
| `output_sorting` | Post-curation spacing rules (see below) |
| `max_candidate_tracks` | Hard cap on how many tracks may be sent to the LLM (see Candidate Limit below) |

Fields that are not relevant to a recipe type may simply be omitted — see
[Recipe Types](#recipe-types) for which fields each type actually uses.

Placeholders use `{{NAME}}` syntax and are substituted from the request. Math expressions
such as `{{MATH:ceil(DESIRED_TRACK_COUNT/5)}}` are evaluated first.

## Validation

`GET /api/recipes/validate` returns, per playlist type, the recipe file, a `valid` flag, and a
list of `errors`. A recipe is valid when:

- `recipe_id` and `name` are present
- `llm_config` is an object, with `temperature` in `[0, 2]` and `max_output_tokens` a positive integer
- `model_instructions` or `selection_instructions` is a non-empty string
- every `user_parameters` value is a single `{{PLACEHOLDER}}` token
- every `{{PLACEHOLDER}}` used in a prompt is either declared in `user_parameters` or filled in
  at request time by `RecipeManager` (`{{TARGET_ARTIST}}`, `{{TARGET_GENRE}}`, `{{ARTISTS}}`,
  `{{DESIRED_TRACK_COUNT}}`, `{{CANDIDATE_TRACKS_JSON}}`, `{{ANALYSIS_SUMMARY}}`)
- every `{{MATH:...}}` expression is evaluable to a number
- optional blocks are well-formed: `description_llm_config`, `max_candidate_tracks` (positive
  integer), `output_sorting` (non-negative integer spacing values), and `source_filtering`
  (`exploration_ratio` / `high_tier_ratio` in `[0, 1]`)

Recipes in the parameterized format are checked instead for `version`, `description`, `inputs`
(a list) and `strategy_notes`; every `{placeholder}` in `prompt_template` must be covered by
`inputs` (with `tracks_data` and `num_tracks` always allowed); and `llm_params` must carry a
`temperature` in `[0, 2]` and a positive `max_tokens`.

Use `GET /api/recipes` to list all available recipes.

## Recipe Types

Recipes fall into three distinct categories. The most important difference is **how many LLM
calls are made and what the model is asked to do**, which in turn determines which recipe
fields are used.

| | **This Is** | **Artist Radio** | **Genre Mix** | **Re-Discover** |
|---|---|---|---|---|
| **Category** | Single-artist curation | Multi-artist curation | Genre curation | Listening-history analysis |
| **LLM calls** | 2 (selection + description) | 2 (selection + description) | 2 (selection + description) | 2 phases |
| **Prompt field** | `model_instructions` | `model_instructions` | `selection_instructions` | `model_instructions` (both phases) |
| **Description** | `description_instructions` | `description_instructions` | `description_instructions` | returned together with tracks in phase 2 |
| **`user_parameters`** | `target_artist`, `desired_track_count` | `artists`, `desired_track_count` | `target_genre`, `desired_track_count` | listening stats (phase 1), analysis + candidates (phase 2) |
| **`source_filtering`** | no | no | yes (engagement-based) | no |
| **Pre-filters (year/quality/blacklist)** | no | yes | yes | no |
| **Diversity caps** | no | yes | yes | prompt-level rule |
| **`output_sorting`** | yes | yes | yes | no |
| **`max_candidate_tracks`** | `150` | `300` | `600` | n/a (pool comes from the analysis) |
| **Recipes** | `this_is_v2.json` | `artist_radio_v1.json` | `genre_mix_v2.json` | `re_discover_phase1_v2.json` + `re_discover_phase2_v2.json` |

### This Is (`this_is`)
- LLM-based curation for a **single artist**
- Balances popular hits with deep cuts, mixing albums and release years
- **No** `source_filtering` block: the candidate pool is narrowed only by
  `max_candidate_tracks`, which keeps the highest-scoring tracks by engagement
- Uses `model_instructions` for track selection and a second `description_instructions`
  call for the editorial blurb
- Recipe: `this_is_v2.json`

### Artist Radio (`artist_radio`)
- LLM-based curation starting from **one or more seed artists**, expanded with similar artists
- Candidates come from server similarity expansion, not from the listening history
- **No** `source_filtering` block: instead the builder applies the year/quality pre-filters and
  the per-album / per-artist diversity caps before scoring, so this recipe type reuses the
  same filter set as Genre Mix while the curation itself is single-shot
- Highest `temperature` (0.8) of all recipe types, since the goal is a free-flowing radio mix
- Uses `model_instructions` for track selection and a second `description_instructions`
  call (via the description model) for the editorial blurb
- Recipe: `artist_radio_v1.json`

### Genre Mix (`genre_mix`)
- LLM-based curation across **one or more genres**
- Selects iconic hits and spreads tracks across decades
- The only recipe type that uses `selection_instructions` instead of `model_instructions`
- Supports the full filter set: year range, artist blacklist, quality floor, and
  per-album / per-artist diversity caps
- Largest candidate budget (`max_candidate_tracks: 600`) because the source pool can be huge
- Recipe: `genre_mix_v2.json`

### Re-Discover Weekly (`re_discover`)
- Two-phase pipeline (no single-shot LLM curation) — the only recipe type split across
  multiple files, where phase 2 consumes the output of phase 1
- **Phase 1** (`re_discover_phase1_v2.json`): analyzes listening history, detects a theme,
  and selects a search strategy (genre/decade/play-count filters). Low `temperature` (0.3)
  because this call must be analytical rather than creative
- **Phase 2** (`re_discover_phase2_v2.json`): an LLM sequences the candidate tracks into a
  cohesive, flowing playlist and writes the editorial description **in the same response**,
  which is why it needs no `description_instructions` call
- No `source_filtering`, `output_sorting`, or `max_candidate_tracks`: the candidate pool is
  produced by the phase 1 search strategy, and its constraints are expressed as prompt rules

## Candidate Limit

`max_candidate_tracks` caps the number of tracks handed to the LLM
(`backend/services/candidate_limiter.py`). It is a safety net for recipes that draw from very
large pools; if omitted, no explicit limit is applied beyond the built-in overshoot factor.

## Filters

Filters reduce the source-track pool sent to the LLM, lowering token cost and improving
curation quality. They are applied in `backend/track_scoring/filtering.py`
(`filter_tracks_for_genre_mix_playlist`, wired up via the `apply_smart_filter` hook on a
playlist type's `PlaylistTypeConfig`) and configured per recipe via `source_filtering` and
per request via the frontend. A type without the hook skips filtering entirely.

### 1. Engagement-based source filtering (`source_filtering`, Genre Mix)
Applied when the source pool is significantly larger than the target playlist size. Tracks are scored by
user engagement (play count, loved/rating, playlist appearances, recency) and the top
`target_playlist_size × multiplier` are kept.

| Key | Default | Meaning |
|-----|---------|---------|
| `exploration_ratio` | `0.6` | Fraction of the kept set filled by a randomized mid-tier "exploration" band |
| `high_tier_ratio` | `0.4` | Fraction of the kept set drawn from a randomized high-scored core |
| `high_tier_multiplier` | `3.0` | Size of the high-tier candidate pool as a multiple of the core count |

When `exploration_ratio > 0` the selection is diversified across runs (different high/mid
tracks each time) while keeping quality high. The threshold multiplier shrinks as the target
playlist grows (e.g. 10× for ≤25 tracks, 5× for ≤100).

### 2. Pre-filters (Genre Mix, Artist Radio)
These narrow the pool **before** scoring and are exposed in the Genre Mix and Artist Radio UIs:

| Filter | Field | Description |
|--------|-------|-------------|
| **Year range** | `year_start`, `year_end` | Keep only tracks released within `[year_start, year_end]` (1950–2026) |
| **Exclude artists** | `blacklisted_artists` | Drop any track whose artist (or featured artist) matches one of the listed names (case-insensitive) |
| **Minimum quality** | `min_bitrate` | Minimum bitrate in kbps (128/192/256/320). Used in MP3/Any mode |
| | `min_format` | Minimum format tier (`mp3`, `flac`, …). Selecting `flac` switches to FLAC mode |
| | `min_bit_depth` | Minimum FLAC bit depth (16/24). FLAC-only filter; drops all lossy and other lossless formats when a depth is set |

In FLAC mode, `min_bitrate` is ignored and only FLAC tracks meeting the requested bit depth
are kept (unknown depth is kept conservatively). In MP3/Any mode, lossless formats are always
kept and lossy formats are filtered by format tier and bitrate floor.

### 3. Diversity caps (Genre Mix, Artist Radio)
Per-album / per-artist caps keep the payload sent to the LLM varied. They are applied **every
time** (even when the source is small), and a value of `0` disables that cap.

| Cap | Field | Default | Description |
|-----|-------|---------|-------------|
| Tracks per album | `max_tracks_per_album` | `2` | Max tracks from the same album (global) |
| Tracks per artist | `max_tracks_per_artist` | `3` | Max tracks per artist |

These caps are sent from the frontend (with the defaults above applied when omitted) and can
also be defined in the recipe's `source_filtering` block.

### 4. Output sorting (`output_sorting`)
Applied **after** the LLM returns the ordered track list, to avoid jarring repetition:

| Key | Default | Meaning |
|-----|---------|---------|
| `space_between_same_artist` | `5` | Minimum tracks separating two songs by the same artist |
| `space_between_same_album` | `4` | Minimum tracks separating two songs from the same album |

> **Note:** The "This Is" playlist applies **no** source filtering, since it targets a single
> artist and needs no year/quality/blacklist/diversity-cap filters — its pool is narrowed only
> by `max_candidate_tracks`. The full filter set above is used by Genre Mix; Artist Radio uses
> the pre-filters and diversity caps; Re-Discover expresses its constraints in the phase 1
> search strategy and the phase 2 prompt instead.

## LLM Instructions & Description Generation

Each recipe drives up to two LLM calls: one to **select/sequence tracks**, and one to write a
short **editorial description** of the finished playlist.

### Selection / curation instructions
The curation prompt tells the model how to pick and order tracks. Recipes use one of:

- `model_instructions` — the curation prompt for This Is and Re-Discover recipes.
- `selection_instructions` — the curation prompt for Genre Mix. If a recipe has neither,
  `model_instructions` is used as a fallback (`backend/ai_client.py`).

Both support `{{PLACEHOLDER}}` substitution and `{{MATH:...}}` expressions. The prompt
typically defines the selection rules (iconic hits, decade spread, artist/album diversity)
and the exact JSON output format the model must return (e.g. `{"track_ids": [...]}`).

### Description instructions
`description_instructions` is an optional prompt used to generate a short, magazine-style
blurb for the already-built playlist. It is given the final ordered track list and must return
a single JSON field, e.g. `{"description": "..."}`. When omitted, no description is generated.

### Description LLM config (`description_llm_config`)
The description call can use its own LLM settings, separate from the curation call. This is
useful because description writing benefits from a higher temperature (more creative phrasing)
and a much smaller token budget than track selection.

| Key | Typical value | Meaning |
|-----|---------------|---------|
| `max_output_tokens` | `2000` | Token budget for the description response (far smaller than the curation call) |
| `temperature` | `0.7` | Sampling temperature — slightly higher than curation for more varied, editorial phrasing |

If `description_llm_config` is absent, the backend falls back to
`{"temperature": 0.7, "max_output_tokens": 500}`.

> **Summary of the two configs:** `llm_config` controls the **track-selection** call
> (e.g. `max_output_tokens: 22000`, `temperature: 0.6` for Genre Mix), while
> `description_llm_config` controls the lighter-weight **description** call.

## Adding New Recipes

1. Create a new recipe file with proper versioning (e.g. `my_type_v1.json`)
2. Update `registry.json` to point the playlist type to the new file
3. Optional: Test with the `/api/recipes/validate` endpoint (see [Validation](#validation))
4. The system will automatically use the new recipe
