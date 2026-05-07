# TT Coach — AI Table Tennis Curator

Modular monolith: FastAPI + HTMX + SQLite. Ingests YouTube coaching videos, transcribes locally (`faster-whisper`), analyzes via pluggable LLMs (Ollama / Gemini / OpenAI), optional coach face matching (InsightFace + FAISS).

## Prerequisites

- Python 3.11+
- `ffmpeg` on PATH (for frames/audio)
- `yt-dlp` (PyPI dependency; requires network when fetching audio/transcripts)
- **Local LLM:** Ollama — recommended for reliable local dev (avoids Gemini free-tier quota).

### Local LLM (Ollama on macOS)

1. Download and install from the official macOS disk image: https://ollama.com/download/mac (`Ollama.dmg`). Drag `Ollama.app` into `/Applications`, open it once (menu bar icon = server on `http://127.0.0.1:11434`). If `ollama` is not on `PATH`, restart the shell or run `open -a Ollama`.
2. Pull and warm the model (default in `.env.example`; good fit for ~18GB RAM MacBooks):
   ```bash
   ollama pull qwen2.5:7b-instruct
   printf 'ok\n' | ollama run qwen2.5:7b-instruct
   ```
3. Quick check:
   ```bash
   curl -fsS http://127.0.0.1:11434/api/version
   ```

For local-only routing, keep `LLM_SUMMARY`, `LLM_INSIGHTS`, and `LLM_TAGGING` set to `ollama` in `.env`, and leave `GEMINI_API_KEY` empty so the app does not silently fall through to Gemini when quotas are exhausted. Tune `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, and the HTTP timeout in `app/llm/ollama.py` if needed.

### Package manager: `uv` (optional)

[`uv`](https://docs.astral.sh/uv/) is **not** installed when you `pip install -e ".[dev]"`. It is a separate tool. If you want `uv sync` / `uv run`:

```bash
pip install uv
# or (standalone installer, adds uv to your PATH via ~/.local/bin — restart shell if needed):
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then verify:

```bash
uv --version
```

---

## Setup

### Option A — pip only (no `uv`)

From the repo root, use your existing virtualenv or create one:

```bash
cd tt-coach
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
mkdir -p data
alembic upgrade head
python -m app.ingest.cli --help
```

### Option B — uv

```bash
cd tt-coach
cp .env.example .env
# Add YOUTUBE_API_KEY when using YouTube discovery; for local LLM-only dev keep GEMINI_API_KEY empty
uv sync
mkdir -p data
uv run alembic upgrade head
uv run python -m app.ingest.cli --help
```

## Run

**pip / activated venv:**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**uv:**

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000

## Daily refresh

APScheduler runs a daily job at `SCHEDULER_REFRESH_HOUR`/`SCHEDULER_REFRESH_MINUTE` in **UTC** (default 06:00 UTC). Trigger manually:

```bash
python -m app.scheduler.run_once
# or: uv run python -m app.scheduler.run_once
```

## Phase 7 (deferred)

Instagram/Reels ingestion is not implemented; see `app/ingest/instagram_deferred.py`.
