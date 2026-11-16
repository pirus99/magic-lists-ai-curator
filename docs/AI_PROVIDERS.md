# AI Providers

MagicLists uses an LLM to select and order tracks. You can run it fully locally or hand the job to a cloud provider.

> ## ⭐ Recommendation: Google AI Studio
>
> Use **`AI_PROVIDER=google`**. It has a **generous free tier, requires no credit card**, and needs nothing but a single API key. The models below are the sweet spot for this workload:
>
> | Setting | Recommended value |
> |---|---|
> | `AI_PROVIDER` | `google` |
> | `AI_MODEL` | **`gemini-3.1-flash-lite`** — fast, cheap, plenty of context for large track lists |
> | `DESCRIPTION_AI_MODEL` | **`gemma-4-26b-a4b-it`** — small and quick, only writes playlist descriptions |
>
> Get a key at [Google AI Studio](https://ai.google.dev/).
>
> Use `gemini-3.1-pro` instead of the flash-lite model if you want deeper reasoning and don't mind the extra latency.

---

## Options at a glance

| # | Option | Cost | API key | Best for |
|---|---|---|---|---|
| 1 | **Fallback only** (no AI) | Free | No | Trying MagicLists out; play-count sorting |
| 2 | **Ollama** (local) | Free | No | Full privacy, no rate limits, offline |
| 3 | **Google AI** ⭐ | Free tier | Yes | **Best default — free, fast, no card** |
| 4 | **OpenRouter** | Free/Paid | Yes | Access to a huge model catalogue |
| 5 | **Groq** | Free/Paid | Yes | Very fast cloud inference |

---

## Option 1 — Fallback only (no AI)

Leave `AI_PROVIDER` unset. MagicLists falls back to play-count and metadata based sorting. No API key needed. Useful for a quick smoke test or for very large libraries where an LLM round-trip is impractical.

---

## Option 2 — Local LLM (Ollama)

Run models entirely on your own hardware. Nothing about your library leaves the machine — the strongest privacy option and immune to rate limits.

[Install Ollama](https://ollama.com), then:

```bash
ollama pull llamusic
ollama serve
```

Configure:

```ini
AI_PROVIDER=ollama
AI_MODEL=llamusic
OLLAMA_BASE_URL=http://localhost:11434/v1/chat/completions
OLLAMA_MAX_TRACKS=180
OLLAMA_TIMEOUT=300
```

| Variable | Notes |
|---|---|
| `OLLAMA_BASE_URL` | Inside Docker use `http://host.docker.internal:11434/v1/chat/completions` |
| `OLLAMA_MAX_TRACKS` | Cap on tracks sent to the model. **Lower this** (e.g. `120`) if responses break or the model returns its reasoning |
| `OLLAMA_TIMEOUT` | Raise for slow CPUs (default `180` seconds) |

**Running Ollama in the same compose file** is often cleaner than `host.docker.internal`:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    volumes:
      - ollama_data:/root/.ollama

  magiclists:
    image: pirus999/magic-lists-ai-curator:latest
    container_name: magiclists
    ports:
      - "4545:8000"
    environment:
      - SERVER_TYPE=navidrome
      - NAVIDROME_URL=http://navidrome:4533
      - NAVIDROME_USERNAME=your_username
      - NAVIDROME_PASSWORD=your_password
      - DATABASE_PATH=/app/data/magiclists.db
      - AI_PROVIDER=ollama
      - AI_MODEL=llamusic
      - OLLAMA_BASE_URL=http://ollama:11434/v1/chat/completions
      - OLLAMA_MAX_TRACKS=180
    depends_on:
      - ollama
    volumes:
      - ./magiclists-data:/app/data

volumes:
  ollama_data:
```

> **Hardware note:** a decent local model needs roughly 8 GB RAM or more. If responses are truncated, empty, or the model echoes its reasoning, reduce `OLLAMA_MAX_TRACKS` and raise `OLLAMA_TIMEOUT`.

---

## Option 3 — Google AI ⭐ (recommended)

Free tier with a generous quota and no credit card required.

1. Get a key from [Google AI Studio](https://ai.google.dev/).
2. Configure:

```ini
AI_PROVIDER=google
AI_API_KEY=AIzaSy_your-key-here
AI_MODEL=gemini-3.1-flash-lite
DESCRIPTION_AI_MODEL=gemma-4-26b-a4b-it
```

Alternatives:

```ini
# Deeper reasoning, slower
AI_MODEL=gemini-3.1-pro
```

Only track metadata (title, artist, album) is sent — never audio files.

---

## Option 4 — OpenRouter

A single key for a large catalogue of hosted models. Get a key from [OpenRouter](https://openrouter.ai) ($5 minimum deposit).

```ini
AI_PROVIDER=openrouter
AI_API_KEY=sk-or-v1-your-key-here
AI_MODEL=dots-studio/dots-3-note-preview:free
# AI_MODEL=tencent/hy3
DESCRIPTION_AI_MODEL=google/gemma-4-26b-a4b-it:free
```

---

## Option 5 — Groq

Very fast cloud inference. Get a key from [Groq](https://console.groq.com/) — no credit card required.

```ini
AI_PROVIDER=groq
AI_API_KEY=gsk_your-key-here
AI_MODEL=openai/gpt-oss-20b
# AI_MODEL=llama-3.3-70b-versatile
DESCRIPTION_AI_MODEL=llama-3.1-8b-instant
```

---

## The two model variables

| Variable | Role | Recommended |
|---|---|---|
| `AI_MODEL` | The **heavy** model that performs the actual selection and ordering of tracks | `gemini-3.1-flash-lite` |
| `DESCRIPTION_AI_MODEL` | A **cheap, fast** model that only writes short playlist descriptions. Falls back to `AI_MODEL` if unset | `gemma-4-26b-a4b-it` |

Splitting these saves significant cost and latency, because most requests are short descriptions.

---

## Improving results

If the AI returns its reasoning instead of a result, returns empty output, or ignores your filters:

1. **Try a different model.**
2. **Shorten the playlist** — fewer tracks means a smaller prompt and fewer formatting mistakes.
3. **Tune the recipe.** Mount your own `recipes/` folder:
   ```yaml
   volumes:
     - ./recipes:/app/recipes:ro
   ```
   Then edit `max_tokens` and `temperature` for the recipe. See [`recipes/README.md`](../recipes/README.md).
4. **Lower `OLLAMA_MAX_TRACKS`** if you're on Ollama.

## Privacy

Music files are never uploaded. Only metadata — title, artist, album — is sent to whichever provider you configure, and only if you configure one. Running Ollama keeps everything on your machine.