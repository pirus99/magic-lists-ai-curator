# Navidrome Setup

Guide for running MagicLists against a **Navidrome** server. (For Jellyfin, see [JELLYFIN.md](JELLYFIN.md).)

## Quick start

1. Set `SERVER_TYPE=navidrome`
2. Point `NAVIDROME_URL` at your Navidrome instance
3. Set `NAVIDROME_USERNAME` and `NAVIDROME_PASSWORD`
4. Start MagicLists and open <http://localhost:4545/system-check>

## Configuration

```yaml
environment:
  - SERVER_TYPE=navidrome
  - NAVIDROME_URL=http://navidrome:4533
  - NAVIDROME_USERNAME=your_username
  - NAVIDROME_PASSWORD=your_password
  - DATABASE_PATH=/app/data/magiclists.db
  # Optional: limit MagicLists to one library
  - NAVIDROME_LIBRARY_ID=
```

| Variable | Required | Notes |
|---|---|---|
| `SERVER_TYPE` | Yes | Must be `navidrome` |
| `NAVIDROME_URL` | Yes | Base URL, **no** trailing `/api` and no trailing slash |
| `NAVIDROME_USERNAME` | Yes | Must be a regular user with permission to see your music |
| `NAVIDROME_PASSWORD` | Yes | Plain text — keep the file permissions tight |
| `NAVIDROME_API_KEY` | No | Alternative to username/password |
| `NAVIDROME_LIBRARY_ID` | No | Restrict MagicLists to a single library (see below) |

## Choosing `NAVIDROME_URL`

This is the single most common source of connection failures. Pick the row that matches your topology:

| Situation | Value |
|---|---|
| Same Docker network (compose) | `http://navidrome:4533` (service name) |
| Same host, Docker Desktop | `http://host.docker.internal:4533` |
| Same host, Linux Docker | `http://172.17.0.1:4533` |
| Another machine on your LAN | `http://192.168.1.100:4533` |
| Public internet | `https://music.yourdomain.com` |

Verify both containers share a network:

```bash
docker ps --format "table {{.Names}}\t{{.Networks}}"
docker network inspect your_network_name
```

## Multiple libraries

If your Navidrome instance hosts more than one music library, either set `NAVIDROME_LIBRARY_ID` to pin MagicLists to one, or leave it empty to search across all of them.

To find the ID, open your Navidrome web UI and look at the library in the URL, or check the Navidrome API:

```bash
curl -u your_username:your_password \
  "http://navidrome:4533/api/library?f=json" | jq '._embedded.subsonicLibrary'
```

## Verifying the connection

```bash
curl "http://localhost:4545/api/artists"
curl "http://localhost:4545/system-check"
```

Or open <http://localhost:4545/system-check> in your browser. The app validates your environment on startup and will point you here if a check fails.

## Nothing found in the artist list?

- Confirm the library has been **scanned** in Navidrome and shows tracks.
- Check Navidrome logs for scan errors.
- Re-check `NAVIDROME_LIBRARY_ID` — a wrong ID silently filters everything out.
- Confirm the user you configured can actually see that library.

## Update to the latest image

```bash
docker compose pull magiclists
docker compose up -d
```

Your database is stored in the mounted volume, so playlists and settings are preserved.