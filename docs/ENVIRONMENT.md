# Environment Variable Reference

Every variable MagicLists reads, where it comes from, and whether it's required.

## Server selection

| Variable | Default | Description | Required |
|---|---|---|---|
| `SERVER_TYPE` | `navidrome` | Which music server to talk to: `navidrome` or `jellyfin` | **Yes** |
| `DATABASE_PATH` | internal path | Location of the SQLite database | **Yes** |
| `LOG_LEVEL` | `INFO` | Log verbosity: `ERROR`, `INFO`, `DEBUG` | No |

## Navidrome

Required when `SERVER_TYPE=navidrome`.

| Variable | Example | Description | Required |
|---|---|---|---|
| `NAVIDROME_URL` | `http://navidrome:4533` | Base URL of the Navidrome instance (no trailing `/api`) | **Yes** |
| `NAVIDROME_USERNAME` | `your_navidrome_username` | Navidrome user name | **Yes**\* |
| `NAVIDROME_PASSWORD` | `your_password` | Navidrome password (plain text) | **Yes**\* |
| `NAVIDROME_API_KEY` | *(empty)* | API key as an alternative to username/password | No |
| `NAVIDROME_LIBRARY_ID` | *(empty)* | Restrict MagicLists to a single library | No |

\* Unless `NAVIDROME_API_KEY` is set.

## Jellyfin

Required when `SERVER_TYPE=jellyfin`.

| Variable | Default | Description | Required |
|---|---|---|---|
| `JELLYFIN_URL` | *(empty)* | Base URL of the Jellyfin instance | **Yes** |
| `JELLYFIN_API_KEY` | *(empty)* | API key for token-based auth — preferred | **Yes**\* |
| `JELLYFIN_USERNAME` | `admin` | Jellyfin user name | **Yes**\* |
| `JELLYFIN_PASSWORD` | `password` | Jellyfin password | **Yes**\* |
| `JELLYFIN_VERIFY_SSL` | `true` | Verify TLS certificates. Set `false` for self-signed certs | No |

\* One authentication method is required — API key **or** username + password.

## AI provider

| Variable | Default | Description | Required |
|---|---|---|---|
| `AI_PROVIDER` | `openrouter` | Provider: `google`, `openrouter`, `groq`, `ollama` | **Yes** |
| `AI_API_KEY` | *(empty)* | Provider API key. Not needed for Ollama | **Yes** for all non-Ollama providers |
| `AI_MODEL` | provider default | The "heavy" model doing playlist selection and reasoning | **Yes** |
| `DESCRIPTION_AI_MODEL` | falls back to `AI_MODEL` | Cheap model used only for short playlist descriptions | No |
| `AI_BASE_URL` | OpenRouter endpoint | Override the inference endpoint | No |

Recommended combination:

```ini
AI_PROVIDER=google
AI_API_KEY=your_google_api_key
AI_MODEL=gemini-3.1-flash-lite
DESCRIPTION_AI_MODEL=gemma-4-26b-a4b-it
```

## Ollama

Only used when `AI_PROVIDER=ollama`.

| Variable | Default | Description | Required |
|---|---|---|---|
| `OLLAMA_BASE_URL` | `http://localhost:11434/v1/chat/completions` | URL of the Ollama server. Use `host.docker.internal` or a compose service name inside Docker | **Yes** |
| `OLLAMA_TIMEOUT` | `180` (seconds) | HTTP request timeout. Raise for slow CPUs or large prompts | No |
| `OLLAMA_MAX_TRACKS` | `150` | Hard cap on tracks sent to the model, preventing context overflow. Lower if responses break. Leave empty for an automatic dynamic limit | No |

## ListenBrainz Labs

Used for **Artist Radio** similar-artist lookups.

| Variable | Default | Description | Required |
|---|---|---|---|
| `LISTENBRAINZ_LABS_URL` | `https://labs.api.listenbrainz.org` | Endpoint for artist suggestions | No |
| `LISTENBRAINZ_TOKEN` | *(empty)* | Personal token — only needed if you hit rate limits | No |
| `LISTENBRAINZ_TIMEOUT` | `15` (seconds) | HTTP timeout for ListenBrainz calls | No |

## Last.fm

Used for **artist top tracks** when `SERVER_TYPE=jellyfin` (Jellyfin has no equivalent of Navidrome's
`getTopSongs`), and to resolve artist names to MusicBrainz IDs for the **This Is** manual artist
fallback. Not used on Navidrome, which has a native top-tracks endpoint.

| Variable | Default | Description | Required |
|---|---|---|---|
| `LASTFM_API_KEY` | *(empty)* | API key from a free Last.fm account. Enables top tracks on Jellyfin. Without it, top tracks are skipped and playlists fall back to play-count ordering | For Jellyfin top tracks |
| `LASTFM_API_URL` | `https://ws.audioscrobbler.com` | API endpoint — override only for testing | No |
| `LASTFM_TIMEOUT` | `15` (seconds) | HTTP timeout for Last.fm calls | No |

Create a key at [last.fm/api/account/create](https://www.last.fm/api/account/create). Last.fm is rate
limited to roughly 5 requests/second, so avoid setting a very high top-tracks count across many artists.

## Minimal working `.env`

Navidrome with Google AI:

```ini
SERVER_TYPE=navidrome
NAVIDROME_URL=http://localhost:4533
NAVIDROME_USERNAME=your_username
NAVIDROME_PASSWORD=your_password
DATABASE_PATH=./magiclists.db
AI_PROVIDER=google
AI_API_KEY=your_google_api_key
AI_MODEL=gemini-3.1-flash-lite
DESCRIPTION_AI_MODEL=gemma-4-26b-a4b-it
```

Jellyfin with a local model:

```ini
SERVER_TYPE=jellyfin
JELLYFIN_URL=http://localhost:8096
JELLYFIN_API_KEY=your_api_key
DATABASE_PATH=./magiclists.db
AI_PROVIDER=ollama
AI_MODEL=llamusic
OLLAMA_BASE_URL=http://localhost:11434/v1/chat/completions
```

## Verifying your configuration

Visit <http://localhost:4545/system-check>. The app validates your environment on startup and, if a check fails, points you there automatically. You can also check it any time:

```bash
curl "http://localhost:4545/system-check"
```