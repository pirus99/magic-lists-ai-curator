# Running Locally (No Docker)

Use this if you want to run Python directly, tinker with the code, or contribute a change.

## Prerequisites

- **Python 3.11+**
- **git**
- A running Navidrome or Jellyfin instance
- Optionally a virtual environment tool (`venv` is built in)

## 1. Clone

```bash
git clone https://github.com/pirus99/magic-lists-ai-curator.git
cd magic-lists-ai-curator
```

## 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it:

```bash
# Linux / macOS
source venv/bin/activate

# Windows (PowerShell)
.\venv\Scripts\Activate.ps1
```

## 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure

Create a `.env` file in the project root:

```ini
SERVER_TYPE=navidrome
NAVIDROME_URL=http://localhost:4533
NAVIDROME_USERNAME=your_username
NAVIDROME_PASSWORD=your_password

# Required — where the SQLite database lives
DATABASE_PATH=./magiclists.db

# AI — Google is recommended
AI_PROVIDER=google
AI_API_KEY=your_google_api_key
AI_MODEL=gemini-3.1-flash-lite
DESCRIPTION_AI_MODEL=gemma-4-26b-a4b-it
```

For Jellyfin swap the server block for:

```ini
SERVER_TYPE=jellyfin
JELLYFIN_URL=http://localhost:8096
JELLYFIN_API_KEY=your_api_key
```

See [ENVIRONMENT.md](ENVIRONMENT.md) for every variable.

> The app reads environment variables directly. If your shell doesn't load `.env`, export them before starting, or prefix the run command with your OS's env-loading tool.

## 5. Run

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 4545 --reload
```

`--reload` auto-restarts on code changes — omit it in production.

Open <http://localhost:4545>.

## Verifying

```bash
curl "http://localhost:4545/system-check"
curl "http://localhost:4545/api/artists"
```

Or open <http://localhost:4545/system-check> in your browser.

## Local AI with Ollama

Run a local model instead of a cloud provider — see [AI Providers](AI_PROVIDERS.md#option-2-local-llm-ollama):

```bash
ollama pull llamusic
ollama serve
```

```ini
AI_PROVIDER=ollama
AI_MODEL=llamusic
OLLAMA_BASE_URL=http://localhost:11434/v1/chat/completions
OLLAMA_MAX_TRACKS=180
```

## Updating

```bash
git pull
```

Restart the server. Your data lives in `magiclists.db` at `DATABASE_PATH`, so it survives updates.

## Running the tests

```bash
pip install pytest pytest-asyncio
pytest tests/
```

Individual tests:

```bash
pytest tests/test_artist_radio_curation.py
pytest tests/test_genre_normalization.py
pytest tests/test_candidate_limiter.py
```

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md). For local installs the usual suspects are a missing `DATABASE_PATH`, a stale virtual environment, or port 4545 already being in use.