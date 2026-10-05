# Docker Setup

Docker is the recommended way to run MagicLists. Two flavours are covered:

- [Add to your existing Docker Compose](#add-to-your-existing-docker-compose-recommended) — the recommended path
- [Standalone Docker Run](#standalone-docker-run) — for when you can't edit your compose file

For Navidrome-specific variables see [NAVIDROME.md](NAVIDROME.md); for Jellyfin see [JELLYFIN.md](JELLYFIN.md).

---

## Add to your existing Docker Compose (recommended)

**Why this method?**

- MagicLists lands on the **same Docker network** as Navidrome/Jellyfin, so the connection is simple and reliable (no host ports, no `host.docker.internal`).
- It's the only setup that unlocks **future features that need local file access**, such as audio analysis.
- It's also the easiest way to spin up a standalone MagicLists container: a compose file with a single service.

### Step 1 — Add the service

Open the `docker-compose.yml` that already runs Navidrome or Jellyfin and add this block next to it:

```yaml
services:
  navidrome:
    # ... your existing Navidrome or Jellyfin config ...

  magiclists:
    image: pirus999/magic-lists-ai-curator:latest
    container_name: magiclists
    ports:
      - "4545:8000"
    environment:
      # --- Music server ---
      - SERVER_TYPE=navidrome                  # or: jellyfin
      - NAVIDROME_URL=http://navidrome:4533   # Jellyfin: JELLYFIN_URL=http://jellyfin:8096
      - NAVIDROME_USERNAME=your_username       # Jellyfin: JELLYFIN_USERNAME
      - NAVIDROME_PASSWORD=your_password       # Jellyfin: JELLYFIN_PASSWORD or JELLYFIN_API_KEY

      # --- Database (required) ---
      - DATABASE_PATH=/app/data/magiclists.db

      # --- AI (recommended: Google) ---
      - AI_PROVIDER=google                     # openrouter, groq, google, ollama
      - AI_API_KEY=your_google_api_key
      - AI_MODEL=gemini-3.1-flash-lite
      - DESCRIPTION_AI_MODEL=gemma-4-26b-a4b-it
    volumes:
      - ./magiclists-data:/app/data           # persist database + settings
    restart: unless-stopped
```

> **Hostname matters.** `NAVIDROME_URL` uses the *service name* from your compose file as the hostname (`navidrome` above). If your service is called `music`, use `http://music:4533`.

### Step 2 — Create the data directory

```bash
mkdir -p magiclists-data
```

The container runs as a non-root user (`appuser`, UID 1000) and needs write access to this directory. If you hit permission errors, see [Database Write Errors](TROUBLESHOOTING.md#database-write-errors).

### Step 3 — Fill in your credentials

| Variable | Where to find it |
|---|---|
| `NAVIDROME_URL` | The internal URL of your Navidrome service |
| `NAVIDROME_USERNAME` | Your Navidrome user name |
| `NAVIDROME_PASSWORD` | Your Navidrome password |
| `AI_API_KEY` | [Google AI Studio](https://ai.google.dev/) — free, no credit card |

### Step 4 — Start the stack

```bash
docker compose up -d
```

### Step 5 — Open MagicLists

<http://localhost:4545>

Verify everything with <http://localhost:4545/system-check>.

### Keeping recipes up to date

If you fork/customise the prompt recipes, mount them so your edits survive image updates:

```yaml
    volumes:
      - ./magiclists-data:/app/data
      - ./recipes:/app/recipes:ro
```

See [`recipes/README.md`](../recipes/README.md) for tuning guidance.

### Updating

```bash
docker compose pull magiclists
docker compose up -d
```

Your database lives in the mounted volume, so playlists and settings survive updates.

---

## Standalone Docker Run

Use this when you can't or don't want to modify your existing compose file.

### If Navidrome/Jellyfin is on the same machine but not the same network

```bash
docker run -d \
  --name magiclists \
  -p 4545:8000 \
  --add-host=host.docker.internal:host-gateway \
  -e SERVER_TYPE=navidrome \
  -e NAVIDROME_URL=http://host.docker.internal:4533 \
  -e NAVIDROME_USERNAME=your_username \
  -e NAVIDROME_PASSWORD=your_password \
  -e DATABASE_PATH=/app/data/magiclists.db \
  -e AI_PROVIDER=google \
  -e AI_API_KEY=your_google_api_key \
  -e AI_MODEL=gemini-3.1-flash-lite \
  -e DESCRIPTION_AI_MODEL=gemma-4-26b-a4b-it \
  -v ./magiclists-data:/app/data \
  pirus999/magic-lists-ai-curator:latest
```

> On Docker Desktop (Windows/Mac) `host.docker.internal` works out of the box. On **Linux**, `--add-host=host.docker.internal:host-gateway` above is required.

### If Navidrome/Jellyfin is publicly reachable

Use your public URL:

```bash
docker run -d \
  --name magiclists \
  -p 4545:8000 \
  -e SERVER_TYPE=navidrome \
  -e NAVIDROME_URL=https://music.yourdomain.com \
  -e NAVIDROME_USERNAME=your_username \
  -e NAVIDROME_PASSWORD=your_password \
  -e DATABASE_PATH=/app/data/magiclists.db \
  -e AI_PROVIDER=google \
  -e AI_API_KEY=your_google_api_key \
  -e AI_MODEL=gemini-3.1-flash-lite \
  -e DESCRIPTION_AI_MODEL=gemma-4-26b-a4b-it \
  -v ./magiclists-data:/app/data \
  pirus999/magic-lists-ai-curator:latest
```

### Running Ollama from the container

```bash
docker run -d \
  --name magiclists \
  -p 4545:8000 \
  --add-host=host.docker.internal:host-gateway \
  -e SERVER_TYPE=navidrome \
  -e NAVIDROME_URL=http://host.docker.internal:4533 \
  -e NAVIDROME_USERNAME=your_username \
  -e NAVIDROME_PASSWORD=your_password \
  -e DATABASE_PATH=/app/data/magiclists.db \
  -e AI_PROVIDER=ollama \
  -e AI_MODEL=llamusic \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434/v1/chat/completions \
  -e OLLAMA_MAX_TRACKS=180 \
  -v ./magiclists-data:/app/data \
  pirus999/magic-lists-ai-curator:latest
```

---

## Managing the container

```bash
# Logs (first stop troubleshooting)
docker logs -f magiclists

# Restart
docker restart magiclists

# Stop & remove (your data in ./magiclists-data is kept)
docker rm -f magiclists

# Update to the latest image
docker pull pirus999/magic-lists-ai-curator:latest
```

## Building from source

```bash
git clone https://github.com/pirus99/magic-lists-ai-curator.git
cd magic-lists-ai-curator
docker compose up --build
```

The bundled `docker-compose.yml` builds locally, reads `.env`, and mounts `frontend/` for live editing. Add your `NAVIDROME_*`, `AI_*` and `DATABASE_PATH` values to a `.env` file next to it.

## Troubleshooting

Head to [TROUBLESHOOTING.md](TROUBLESHOOTING.md), or run the built-in check at <http://localhost:4545/system-check>.