# TT Coach — AI Table Tennis Curator

Modular monolith: FastAPI + HTMX + SQLite. Discovers YouTube coaching videos, admits only those that face-match a *preferred coach* you've enrolled, transcribes locally (`faster-whisper`), analyzes them via pluggable LLMs (Ollama / Gemini / OpenAI) with insights tailored to your player profile.

## Discovery & admission model

A video reaches the feed if and only if a preferred coach (one you've enrolled with face samples on `/coaches`) is detected by face similarity at or above `PREFERRED_COACH_MIN_CONFIDENCE` (default 0.55) on at least `FACE_MATCH_FRAME_HIT_QUORUM` sampled frames (default 1). Raise both in `.env` if you need stricter precision and have good enrollment samples.

Discovery surfaces (each one is just a candidate pool — admission still requires a face match):

1. **Seed channels** — channel IDs in `seeds/youtube_channels.txt`. Their recent uploads form the primary candidate pool.
2. **Preferred-coach sample channels** — for each coach you've enrolled in `/coaches`, the YouTube channels hosting their `CoachSample` URLs are auto-derived and their recent uploads added to the pool.
3. **Related videos (1 hop)** — for each candidate above, YouTube's "related videos" sidebar is scraped via `yt-dlp`, bounded by `RELATED_PER_SEED` and `RELATED_TOTAL_CAP`. (The official Data API endpoint for related videos was removed in 2023; `yt-dlp --dump-single-json` is the practical substitute.)

If `preferred_coaches` on `/profile` is empty, no videos will be admitted. Set them up first.

The player profile (`level`, `play_style`, `goals`, `weaknesses`) is used **only** to shape the LLM analyst's framing — emphasizing tips and mistakes relevant to your weaknesses, aligning `try_next_session` with your goals. It does not influence which videos are admitted, nor any ranking weight.

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

APScheduler runs a daily job at `SCHEDULER_REFRESH_HOUR`/`SCHEDULER_REFRESH_MINUTE` in **UTC** (default 06:00 UTC). Order of operations within a single run:

1. **Discover** candidate videos from seed channels + preferred-coach sample channels + 1-hop related-video expansion.
2. **Face match** every un-admitted candidate (cheap: 16 frames + FAISS). Flip `Video.is_admitted` based on whether any preferred coach matches at `PREFERRED_COACH_MIN_CONFIDENCE` on at least `FACE_MATCH_FRAME_HIT_QUORUM` frames (configurable).
3. **Analyze** only admitted videos (transcribe + LLM). Skipped candidates never incur LLM/Whisper cost.
4. **Rank** with `compute_personalized_scores` and rebuild `Recommendation` rows for the day.

Trigger manually:

```bash
python -m app.scheduler.run_once
# or: uv run python -m app.scheduler.run_once
```

### Historical backfill (e.g. last 90 days)

The scheduler ingests roughly the last **7 days** each run (`run_ingestion(..., days=7)`). For a one-time deeper window, run the ingestion CLI with a larger `--since-days` and a higher `--max-per-channel` (playlist pagination uses 50 IDs per API page; active channels need a higher cap than the default **50**):

```bash
python -m app.ingest.cli --since-days 90 --max-per-channel 500
```

Then run `python -m app.scheduler.run_once` (or **Run pipeline** in the UI) so admission, analysis, and ranking catch up.

## Phase 7 (deferred)

Instagram/Reels ingestion is not implemented; see `app/ingest/instagram_deferred.py`.
