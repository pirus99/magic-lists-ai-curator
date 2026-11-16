# Installation & Setup Index

Pick the method that matches your setup. Every path leads to the same result: MagicLists on `http://localhost:4545`.

## Which method should I use?

| I want to… | Use this |
|---|---|
| Add MagicLists next to the Navidrome/Jellyfin I already run | **[Docker Compose (recommended)](DOCKER.md)** |
| Spin up a one-off container without touching my compose file | **[Standalone Docker Run](DOCKER.md#standalone-docker-run)** |
| Install for Navidrome (credentials, libraries, troubleshooting) | **[Navidrome Setup](NAVIDROME.md)** |
| Install for Jellyfin (API key, SSL, known limitations) | **[Jellyfin Setup](JELLYFIN.md)** |
| Develop or hack on the code from source | **[Running Locally](RUNNING_LOCALLY.md)** |
| Pick a brain for curation | **[AI Providers](AI_PROVIDERS.md)** |
| Look up a variable | **[Environment Reference](ENVIRONMENT.md)** |
| Something is broken | **[Troubleshooting](TROUBLESHOOTING.md)** |

## The 60-second version (Docker Compose)

```yaml
services:
  magiclists:
    image: pirus999/magic-lists-ai-curator:latest
    container_name: magiclists
    ports:
      - "4545:8000"
    environment:
      - SERVER_TYPE=navidrome          # or jellyfin
      - NAVIDROME_URL=http://navidrome:4533
      - NAVIDROME_USERNAME=your_username
      - NAVIDROME_PASSWORD=your_password
      - DATABASE_PATH=/app/data/magiclists.db
      - AI_PROVIDER=google
      - AI_API_KEY=your_google_api_key
      - AI_MODEL=gemini-3.1-flash-lite
      - DESCRIPTION_AI_MODEL=gemma-4-26b-a4b-it
    volumes:
      - ./magiclists-data:/app/data
    restart: unless-stopped
```

Then `docker compose up -d` and open <http://localhost:4545>.

> **Start here:** [Docker Compose (recommended)](DOCKER.md) · [Navidrome](NAVIDROME.md) · [Jellyfin](JELLYFIN.md)

## Prerequisites

- **Navidrome** or **Jellyfin** with a scanned music library, or Docker if you're bringing your own server
- Docker Engine 24+ with Compose v2 (`docker compose version`)
- A reachable `DATABASE_PATH` location for the SQLite file
- An AI provider key — we recommend **Google AI Studio** (free tier, no credit card). See [AI Providers](AI_PROVIDERS.md).

## After installing

1. Open <http://localhost:4545> and complete the setup form.
2. Visit <http://localhost:4545/system-check> — every row should be green.
3. Generate your first playlist: pick a tool (**This Is**, **Artist Radio**, **Re-Discover**, **Genre Mix**), choose a track count and refresh interval, and hit generate.

## Next steps

- [API Reference](API.md) — all REST endpoints
- [`recipes/README.md`](../recipes/README.md) — tuning the AI prompt recipes
- [Troubleshooting](TROUBLESHOOTING.md) — for when something looks wrong