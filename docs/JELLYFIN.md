# Jellyfin Setup

Guide for running MagicLists against a **Jellyfin** server.

> ⚠️ **Status:** Jellyfin support is the newest part of this project. Playlist generation quality, scheduling, large libraries, and playlist editing are still lightly tested. Please report your experience on the [Issues](https://github.com/pirus99/magic-lists-ai-curator/issues) tab.

## Quick start

1. Set `SERVER_TYPE=jellyfin`
2. Point `JELLYFIN_URL` at your Jellyfin instance
3. Authenticate — either an **API key** (recommended) or **username + password**
4. Start MagicLists and open <http://localhost:4545/system-check>

## Configuration

```yaml
environment:
  - SERVER_TYPE=jellyfin
  - JELLYFIN_URL=http://jellyfin:8096

  # Option A – API key (recommended)
  - JELLYFIN_API_KEY=your_api_key

  # Option B – username / password
  # - JELLYFIN_USERNAME=your_username
  # - JELLYFIN_PASSWORD=your_password

  # Optional: set to false for self-signed certificates
  - JELLYFIN_VERIFY_SSL=true

  - DATABASE_PATH=/app/data/magiclists.db
```

| Variable | Required | Notes |
|---|---|---|
| `SERVER_TYPE` | Yes | Must be `jellyfin` |
| `JELLYFIN_URL` | Yes | Base URL, e.g. `http://jellyfin:8096`. No trailing slash |
| `JELLYFIN_API_KEY` | Yes\* | Preferred. Ignored if username/password are both set |
| `JELLYFIN_USERNAME` | Yes\* | Required when no API key is set |
| `JELLYFIN_PASSWORD` | Yes\* | Required when no API key is set |
| `JELLYFIN_VERIFY_SSL` | No | `true` (default). Set `false` for self-signed certs |

\* One authentication method is required — API key **or** username + password.

## Creating an API key (recommended)

An API key avoids storing your password and is the more reliable option.

1. In Jellyfin, open **Dashboard → Advanced → API Keys**.
2. Click **+** to create a new key.
3. Give it a recognisable name, e.g. `MagicLists`.
4. Copy the generated key — **it is only shown once**.
5. Paste it into `JELLYFIN_API_KEY`.

The account tied to the key must be able to see your music library.

## Self-signed certificates

If your Jellyfin is behind HTTPS with a self-signed certificate, certificate validation fails:

```yaml
  - JELLYFIN_VERIFY_SSL=false
```

Only use this on a trusted network. Prefer mounting your CA certificate if you have one.

## Choosing `JELLYFIN_URL`

| Situation | Value |
|---|---|
| Same Docker network (compose) | `http://jellyfin:8096` (service name) |
| Same host, Docker Desktop | `http://host.docker.internal:8096` |
| Same host, Linux Docker | `http://172.17.0.1:8096` |
| Another machine on your LAN | `http://192.168.1.100:8096` |
| Reverse-proxied with HTTPS | `https://media.yourdomain.com` |

```bash
docker ps --format "table {{.Names}}\t{{.Networks}}"
```

## Music library prerequisites

MagicLists queries Jellyfin's **Artists** endpoint recursively, so:

- Your music must live in a library whose type is **Music**.
- **Collection management** must be enabled for that library, otherwise artists won't be grouped correctly.
- The Jellyfin library must have finished its initial scan.

## Verifying the connection

```bash
curl "http://localhost:4545/system-check"
```

The Jellyfin checks verify URL reachability, authentication, and that the Artists API returns results. Open <http://localhost:4545/system-check> in a browser for a rendered view with suggestions.

## Known limitations

- **Playlist generation quality** — results need more tuning than the Navidrome path.
- **Scheduling** — auto-refresh schedules are less battle-tested on Jellyfin.
- **Large libraries** — very large collections may be slow; expect to raise timeouts.
- **Playlist editing** — playlists created on newer MagicLists versions are editable; older ones need to be recreated.
- **Multi-library** — not supported; the Artists API call isn't scoped per library.

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). Most Jellyfin issues are either a wrong URL, an authentication problem, or TLS verification.