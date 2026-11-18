# ✨ Features

Everything MagicLists can do. For setup instructions see the
[documentation index](../README.md#-documentation-index).

---

## 🎵 Playlist types

MagicLists builds five different kinds of playlist. Each one has its own page in the app
where you pick your options and hit generate.

### This Is (Artist)

A definitive playlist for one artist. MagicLists gathers everything it can find — album
tracks, singles, and guest appearances — removes duplicate versions of the same song, and
then asks the AI to balance the hits against the deeper cuts so the result feels like a
proper introduction rather than a shuffle.

You can also ask it to include the artist's most popular tracks. On Navidrome this comes
from the server itself; on Jellyfin it comes from Last.fm (see
[Artist top tracks](#-artist-top-tracks)).

### Artist Radio

Pick one artist, and MagicLists looks up similar artists for you. You choose which of those
suggestions to include, and it builds a mixed radio playlist from all of them. This is the
tool for "I like this band, what else sounds like them?" — without having to know the names
yourself.

Similar artists come from ListenBrainz, and on Navidrome you can also use the server's own
similar-artist data instead.

### Song Radio

Pick a single song and MagicLists builds a radio around it. It finds tracks that sound
similar, matches them against your own library, and the AI arranges them into a mix. The
song you started from is always first.

You can preview the candidate pool before committing, so you can see how many matches exist
before anything is created. On Navidrome there is a built-in fallback that needs no external
service at all.

### Genre Mix

Choose one or more genres and MagicLists builds a playlist from your whole collection in
those genres. This is the most tunable playlist type — you can filter by year range, audio
quality, and limit how many tracks come from the same album or artist so the result stays
varied.

### Re-Discover

Surfaces music you haven't played in a while. Instead of showing you the same favourites,
it digs through your library for tracks that have gone quiet and builds a playlist that
helps you fall back in love with your collection.

---

## ⏰ Refresh scheduling

Any playlist can refresh itself automatically, so your mixes stay alive instead of going
stale.

### Simple schedules

When you create a playlist you get four simple choices: **Don't refresh**, **Daily**,
**Weekly**, or **Monthly**. That is enough for most people.

### Detailed schedules

If you want more control, open a playlist's **Edit** dialog. There you can set the exact
time of day, choose specific weekdays, pick a day of the month, refresh every N hours, or
even write a custom cron expression. A live preview tells you in plain English what the
schedule will do.

### The Refresh Schedule page

**Manage → Refresh Schedule** shows one row per scheduled playlist with its name, type, and
when it will run next. A red exclamation mark appears next to a playlist only if its last
refresh failed — so problems are visible at a glance without digging through logs.

Click any playlist to open a detail view with:

- **Recent refreshes** — when each one ran, whether it succeeded, how long it took, how many
  tracks it produced, and the error message if it failed.
- **Upcoming refreshes** — the next few scheduled runs.
- **Refresh now** — run it immediately.
- **Edit schedule** — jump straight to the scheduler settings.

By default only playlists with an active schedule are listed. **Show all playlists** also
reveals the ones set to manual-only or paused. **Clear history** wipes the recorded log
without touching your playlists or their schedules.

### One refresh at a time

MagicLists never refreshes two playlists simultaneously. Refreshes are queued and spaced
out, which keeps you well clear of AI provider rate limits — a common cause of failed
refreshes in tools that fire everything at once. Manual refreshes join the same queue, so
clicking "Refresh now" can never collide with a scheduled run.

If the app was switched off when a refresh was due, it catches up on startup — but only for
refreshes missed within the last day, so you never get a flood of stale work.

---

## 🎧 Artist top tracks

The **Top Tracks per Artist** slider on the This Is and Artist Radio pages pulls an artist's
most popular songs from a different source depending on your server. The app always shows
which source is active.

| Server | Source | Label | Requires |
|---|---|---|---|
| Navidrome | The server's own top-songs data | `Native` | Nothing |
| Jellyfin | [Last.fm](https://www.last.fm/api) | `Last.fm` | A free `LASTFM_API_KEY` |

Jellyfin has no equivalent of Navidrome's top-songs feature, so set `LASTFM_API_KEY` to a
free key from [last.fm/api/account/create](https://www.last.fm/api/account/create) to enable
it. Last.fm returns song titles rather than server IDs, so MagicLists matches them against
the artist's tracks already in your library — only real matches are used.

The slider is **always visible** on both server types. Without a key it still reads
*Source: Last.fm* but shows a setup prompt, and playlists fall back to play-count ordering.
A missing key never blocks you, and the feature stays discoverable.

Last.fm identifies artists by MusicBrainz ID, and Jellyfin metadata often has none. When
that happens the This Is page shows a **MusicBrainz ID** field so you can paste one in from
[musicbrainz.org](https://musicbrainz.org). It is used for the Last.fm lookup only and never
changes which tracks are chosen.

See [JELLYFIN.md](JELLYFIN.md) for details.

---

## 🖥 Works with Navidrome and Jellyfin

MagicLists talks to either server. Set `SERVER_TYPE=navidrome` or `SERVER_TYPE=jellyfin` and
the app adapts — including the playlist pages, the top-tracks source, and the system check.

Each server type keeps its own database file, so you can run both side by side without them
interfering.

---

## 📚 Multiple libraries

If your server has more than one music library, MagicLists lets you pick which one to work
with. Your choice is remembered, and every playlist is built from the library you selected.

---

## ✏ Playlist editing

Every playlist you create can be changed later — you don't have to delete it and start over.
Open a playlist from the **Playlists** page or from the **Refresh Schedule** page and choose
**Edit**.

In one dialog you can change:

- **Name and description** — rename the playlist and rewrite its comment. Both are pushed to
  your media server, so the change shows up in Navidrome or Jellyfin too.
- **Visibility** — make the playlist public or private on your server.
- **Length** — switch between 25, 50, or 100 tracks.
- **Refresh schedule** — the full scheduler, with a live preview of what it will do.
- **Type-specific settings** — the same options you had when creating it. For a Genre Mix
  that means genres, year range, audio quality, and per-album/per-artist limits; for This Is
  and Artist Radio it means the top-tracks slider; for Artist Radio and Song Radio it means
  the artist or source-track selection.

Two buttons finish the job:

- **Save Changes** — stores your settings and updates the playlist's metadata. The current
  track list is left alone.
- **Save & Refresh** — does the same, then immediately rebuilds the playlist with the new
  settings, so you see the result straight away.

---

## 🌙 Dark mode

The whole interface has a light and dark theme. Toggle it from the sidebar — the choice is
remembered between visits, and it follows the app theme rather than your operating system,
so it never changes under you.

---

## 🩺 System check

MagicLists validates its configuration on startup. If something is misconfigured you are
taken to a system check page that verifies:

- **Environment variables** — that required settings are present
- **Server URL** — that Navidrome or Jellyfin is reachable
- **Authentication** — that your credentials work
- **Artists API** — that API access returns results
- **AI provider** — that AI features are configured
- **Library configuration** — multiple-library setup status

Every failed check comes with a suggested fix. You can revisit the page at any time by
opening `/system-check`.

---

## 🔒 Private by design

MagicLists runs entirely on your own hardware. There is no account, no subscription, and no
usage tracking. Your library stays where it is; only the track lists needed for curation are
sent to the AI provider you choose — and you can run a local model with Ollama if you want
nothing to leave your network at all.

---

## ⚡ No library scans

MagicLists does not require you to run a full library scan for playlist generation. It uses the
track, artist, album, genre, year, and play-information data that Navidrome or Jellyfin already
exposes through its API, so generation does not re-read or analyze every audio file on your server.

This means:

- **No extra waiting** — there is no separate scan phase before a playlist can be built.
- **Existing metadata is enough** — tracks and related library information are queried directly from your media server.
- **Lower server load** — MagicLists works with targeted API requests instead of rescanning the entire library or filesystem.
- **No audio analysis required** — playlist curation and matching depend on library metadata and the configured AI or similarity services, not on fingerprinting every track.
- **Normal server indexing still matters** — your Navidrome or Jellyfin library should already be populated and updated by your media server. MagicLists does not replace that server-side scanning or indexing process.

A playlist can be created as soon as MagicLists is connected to your media server. 

---

## 🆕 What's new since the original version

This project started as a fork of
[magic-lists-for-navidrome](https://github.com/rsynnot/magic-lists-for-navidrome). Here is
what has been added or substantially reworked since then.

### New playlist types

- **Artist Radio** — build a mix from an artist plus similar artists, with ListenBrainz
  suggestions and manual picks.
- **Song Radio** — build a radio around a single track, with a preview of the candidate pool
  before anything is created.
- **Genre Mix** — build from multiple genres, with year, quality, and per-album/per-artist
  filters.

### New scheduling

- **Per-playlist schedules** — every playlist has its own schedule instead of sharing one
  global refresh window. Set the exact time, weekday, day of the month, an hourly interval,
  or a cron expression.
- **Refresh Schedule page** — see every scheduled playlist, its next run, and whether its
  last refresh succeeded, all in one place.
- **Refresh history** — a per-playlist log of recent refreshes with status, duration, track
  count, and error messages.
- **One refresh at a time** — refreshes are queued and spaced out so AI providers never get
  rate limited.
- **Automatic retry** — temporary AI provider errors (rate limits, server hiccups) are
  retried with increasing delays instead of failing the whole refresh.

### New server support

- **Jellyfin** — full support alongside Navidrome, including a Last.fm fallback for artist
  top tracks.

### New interface

- **Dark mode** — a proper light and dark theme across the whole app.
- **Redesigned playlist management** — a cleaner playlist list with inline refresh, edit, and
  delete actions.
- **Themed dialogs** — delete, clear-history, and help dialogs match the app theme instead of
  using the browser's default popups.
- **Detailed edit dialog** — change a playlist's length, filters, metadata, and schedule in
  one place, with a live preview of the schedule.

### Fixes and improvements

- **No usage tracking** — this fork sends no analytics anywhere.
- **Reliable scheduled refreshes** — fixed a long-standing issue where some playlist types
  silently stopped refreshing after the first run.
- **Better error reporting** — failed refreshes now record why they failed instead of
  disappearing into the logs.
- **Playlist cleanup** — playlists deleted directly in Navidrome or Jellyfin are removed from
  MagicLists automatically instead of lingering as broken entries.
- **Predictable logging** — a single `LOG_LEVEL` now controls both application logs and the
  HTTP access log, so successful requests can be hidden without hiding real failures.
- **Runs on current FastAPI and Starlette** — the app no longer breaks on newer releases of
  its web stack, so dependency updates and security patches can be applied.

#### AI responses are handled properly

In the original version, a malformed AI reply often caused an unhandled error and the whole
playlist build failed. These errors have been fixed and now can be handled gracefully, means a malformed response can often be used anyways resulting in a better playlist generation performance.

#### Recipes are cleaner and actually validated

The prompt recipes that drive curation used to contain options that were never read by any
code — they looked configurable but did nothing, which was confusing when tuning them.

- **Unused recipe options were removed**, so every setting you see in a recipe has an effect.
- **Recipes are validated** — a recipe file is checked for the required fields and for
  sensible model settings before it is used, and problems are reported instead of silently
  producing odd results.
- **Placeholders are verified** — if a prompt still contains an unfilled placeholder after
  preparation, that is logged, so a broken recipe is visible rather than quietly sending a
  half-finished prompt to the AI.
- **Old and new recipe formats both work**, so existing customised recipes keep functioning.

#### Track ordering and spacing

A playlist that puts three songs by the same artist back to back does not feel curated, no
matter how good the selection is. MagicLists now actively spaces the result for Genre Mix Playlists:

- **Artist spacing** — the same artist is kept apart by a configurable number of tracks.
- **Album spacing** — tracks from the same album are spread out rather than clustered.
- **Applied after curation**, so the AI's selection is preserved while the running order is
  improved.
- **Graceful when it cannot be satisfied** — if a playlist is too small or too dominated by
  one artist to space perfectly, it still produces a playlist rather than failing.

#### Re-Discover actually runs

The Re-Discover flow in the original version never really executed its intended
analysis-and-curation path — it always fell back to a simple generation strategy,
so the feature suggested the user there were not enough listening history found even when there was.

That flow has been rebuilt so the analysis and AI curation steps genuinely run, with the
fallback reserved for the cases it was meant for: when there is not enough listening history
to analyse.
