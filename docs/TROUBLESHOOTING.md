# Troubleshooting

**Start here:** open <http://localhost:4545/system-check>. MagicLists validates its configuration on startup and, on failure, redirects you to a system check page that lists exactly what's wrong along with a suggested fix.

## Quick triage

| Symptom | Likely cause | Fix |
|---|---|---|
| *Database Configuration Error* banner | `DATABASE_PATH` missing or unwritable | See [Database Write Errors](#database-write-errors) |
| Cannot reach Navidrome/Jellyfin | Wrong URL / wrong network | See [Connection Issues](#connection-issues) |
| Artist list empty | Library not scanned, or wrong library ID | See [No artists found](#no-artists-found) |
| AI returns reasoning or empty output | Model/limit mismatch | See [AI Response Issues](#ai-response-issues) |
| Playlists too short | Filters dropping candidates | See [Playlist Length Issues](#playlist-length-issues) |

---

## Database Write Errors (500 Server Error)

System checks pass, but playlist creation fails with a 500 about database write permissions.

**`DATABASE_PATH` is required** — without it playlists and settings can't persist.

- **Docker**: `DATABASE_PATH=/app/data/magiclists.db`, with a volume mounted at `/app/data`
- **Standalone**: `DATABASE_PATH=./magiclists.db` in your project directory

### Permission errors on Docker

The container runs as a non-root user (`appuser`, UID 1000). If it can't write to the mounted directory:

```bash
mkdir -p magiclists-data
sudo chown -R 1000:1000 magiclists-data
```

### Other database problems

- Confirm the directory exists and has free disk space.
- If the database looks corrupted, stop the container, move the `.db` file aside, and restart — MagicLists recreates it (your playlists will need regenerating).

---

## Connection Issues

### Wrong `NAVIDROME_URL` / `JELLYFIN_URL`

Pick the value matching your topology:

| Situation | Value |
|---|---|
| Same Docker network | `http://navidrome:4533` (use the service name) |
| Same host, Docker Desktop | `http://host.docker.internal:4533` |
| Same host, Linux Docker | `http://172.17.0.1:4533` |
| Another machine on your LAN | `http://192.168.1.100:4533` |
| Public internet | `https://music.yourdomain.com` |

Remember: no trailing `/api`, no trailing slash.

### Check that containers share a network

```bash
# List Docker networks
docker network ls

# Inspect your network
docker network inspect your_network_name

# See which network each container is on
docker ps --format "table {{.Names}}\t{{.Networks}}"
```

If MagicLists isn't on the same network, add both services to a shared one:

```yaml
services:
  navidrome:
    networks: [media]
  magiclists:
    networks: [media]
networks:
  media:
```

### Jellyfin TLS errors

Self-signed certificates fail validation. Either mount your CA cert, or as a last resort:

```yaml
  - JELLYFIN_VERIFY_SSL=false
```

### Authentication rejected

- Confirm the user exists and can see your music library.
- Jellyfin: prefer `JELLYFIN_API_KEY` over username/password.
- Navidrome: try `NAVIDROME_API_KEY` if password auth fails.
- Restart the container after changing credentials — environment variables are read at startup.

---

## No artists found

- Make sure your music library has been **scanned** in Navidrome/Jellyfin and actually contains tracks.
- Check the Navidrome/Jellyfin logs for scan errors.
- If you use multiple libraries, verify `NAVIDROME_LIBRARY_ID` — a wrong ID silently filters everything out.
- On Jellyfin, confirm the library type is **Music** and that **collection management** is enabled (artists won't group correctly without it).
- Confirm the configured account has permission to view that library.

Quick test:

```bash
curl "http://localhost:4545/api/artists"
curl "http://localhost:4545/system-check"
```

---

## AI Response Issues

Symptoms: the AI returns its reasoning or context instead of a result, or returns nothing.

1. **Try a different model.**
2. **Shorten the playlist** — fewer tracks means a smaller prompt and fewer formatting errors.
3. **Tune the recipe.** Mount your own recipes folder:
   ```yaml
   volumes:
     - ./HOST_PATH_FOR_YOUR_RECIPES:/app/recipes
   ```
   Then adjust `max_tokens` and `temperature` for the recipe until results look right.
4. **On Ollama, lower `OLLAMA_MAX_TRACKS`** (e.g. `120`) and raise `OLLAMA_TIMEOUT` (e.g. `300`) for slow CPUs.

More detail: [`recipes/README.md`](../recipes/README.md) and [AI Providers](AI_PROVIDERS.md).

---

## Playlist Length Issues

- Ensure the artist or genre actually has enough tracks.
- Check your logs — filtering options may be dropping everything before AI curation.
- Relax the filters so enough tracks reach the model.

---

## Issues with Editing Playlists

- Playlists are only editable if created with MagicLists **>= 1.1.0**.
- If you created a playlist with an older version, delete and recreate it with the current version to enable editing.

---

## Container Logs

Always the first thing to check:

```bash
docker logs -f magiclists
```

For more detail, set `LOG_LEVEL=DEBUG`.

---

## Still stuck?

- Re-run <http://localhost:4545/system-check>.
- Review your variables against [ENVIRONMENT.md](ENVIRONMENT.md).
- Open an issue on the [Issues tab](https://github.com/pirus99/magic-lists-ai-curator/issues/new/choose) — include your system check output and relevant log lines.