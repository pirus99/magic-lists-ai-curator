# 📖 Documentation

Everything you need to install, configure, and troubleshoot **MagicLists AI Curator** lives in this folder. Use the tables below to jump straight to the right guide.

> **New here?** Start with **[INSTALLATION.md](INSTALLATION.md)** — it picks the right path for your setup in under a minute.

---

## 🚀 Getting Started

| I want to… | Guide |
|---|---|
| **Choose an install method** (start here) | **[INSTALLATION.md](INSTALLATION.md)** |
| **Add MagicLists to my existing Docker Compose** (recommended) | **[DOCKER.md](DOCKER.md)** → [Add to your existing Docker Compose](DOCKER.md#add-to-your-existing-docker-compose-recommended) |
| Run a standalone container with `docker run` | **[DOCKER.md](DOCKER.md)** → [Standalone Docker Run](DOCKER.md#standalone-docker-run) |
| Build the image from source | **[DOCKER.md](DOCKER.md)** → [Building from source](DOCKER.md#building-from-source) |
| Develop or contribute without Docker | **[RUNNING_LOCALLY.md](RUNNING_LOCALLY.md)** |

---

## 🎵 Server Setup

| My server | Guide | Covers |
|---|---|---|
| **Navidrome** | **[NAVIDROME.md](NAVIDROME.md)** | Connection settings, `NAVIDROME_URL`, multiple libraries, Song Radio, verification |
| **Jellyfin** | **[JELLYFIN.md](JELLYFIN.md)** | API keys, self-signed certificates, library prerequisites, Last.fm top tracks, MusicBrainz IDs, known limitations |

---

## 🤖 AI Configuration

| I want to… | Guide |
|---|---|
| **Choose an AI provider** (start here) | **[AI_PROVIDERS.md](AI_PROVIDERS.md)** |
| Run fully local & private | [Ollama](AI_PROVIDERS.md#option-2--local-llm-ollama) |
| Use Google AI ⭐ (recommended) | [Google AI](AI_PROVIDERS.md#option-3--google-ai--recommended) |
| Use a different cloud provider | [OpenRouter](AI_PROVIDERS.md#option-4--openrouter) · [Groq](AI_PROVIDERS.md#option-5--groq) |
| Run without any AI at all | [Fallback only](AI_PROVIDERS.md#option-1--fallback-only-no-ai) |
| Understand `AI_MODEL` vs `DESCRIPTION_AI_MODEL` | [The two model variables](AI_PROVIDERS.md#the-two-model-variables) |

---

## 🔧 Reference

| I need… | Guide |
|---|---|
| **See everything the app can do** | **[FEATURES.md](FEATURES.md)** |
| Look up an environment variable | **[ENVIRONMENT.md](ENVIRONMENT.md)** |
| Use the REST API | **[API.md](API.md)** |
| Tune the AI prompt recipes | **[../recipes/README.md](../recipes/README.md)** |

---

## 🩺 Help

| Problem | Guide |
|---|---|
| **Something isn't working** | **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** |
| Quick triage of a failure | [Quick triage](TROUBLESHOOTING.md#quick-triage) |
| Database write errors (500) | [Database Write Errors](TROUBLESHOOTING.md#database-write-errors-500-server-error) |
| Container can't reach Navidrome/Jellyfin | [Connection Issues](TROUBLESHOOTING.md#connection-issues) |
| No artists found | [No artists found](TROUBLESHOOTING.md#no-artists-found) |
| AI returns bad or empty results | [AI Response Issues](TROUBLESHOOTING.md#ai-response-issues) |
| Playlists are too short/long | [Playlist Length Issues](TROUBLESHOOTING.md#playlist-length-issues) |
| Reading container logs | [Container Logs](TROUBLESHOOTING.md#container-logs) |

---

## 📚 File Overview

| File | What it is |
|---|---|
| [AI_PROVIDERS.md](AI_PROVIDERS.md) | Supported AI backends (Google, Ollama, OpenRouter, Groq, none), model variables, privacy notes |
| [API.md](API.md) | Full REST API reference: page routes, library/metadata, playlist types, management, recipes, scheduler, diagnostics |
| [DOCKER.md](DOCKER.md) | Docker Compose and `docker run` setups, container management, building from source |
| [ENVIRONMENT.md](ENVIRONMENT.md) | Every environment variable, grouped by area, plus a minimal working `.env` |
| [FEATURES.md](FEATURES.md) | All playlist types and app features, including what's new over the original version |
| [INSTALLATION.md](INSTALLATION.md) | Entry point for installation — compares methods and links onward |
| [JELLYFIN.md](JELLYFIN.md) | Jellyfin-specific configuration and limitations |
| [NAVIDROME.md](NAVIDROME.md) | Navidrome-specific configuration |
| [RUNNING_LOCALLY.md](RUNNING_LOCALLY.md) | Running from source with a virtual environment, plus running the tests |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Symptom-based fixes for the most common problems |

---

← Back to the [project README](../README.md)
