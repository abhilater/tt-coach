from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./data/tt_coach.sqlite3"
    log_level: str = "INFO"

    data_dir: Path = Path("./data")
    face_index_path: Path = Path("./data/faces.faiss")
    face_meta_path: Path = Path("./data/faces_meta.json")

    youtube_api_key: str = ""

    whisper_model_size: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    llm_summary: str = "ollama"
    llm_insights: str = "ollama"
    llm_tagging: str = "ollama"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:7b-instruct"

    gemini_api_key: str = ""
    openai_api_key: str = ""

    scheduler_refresh_hour: int = 6
    scheduler_refresh_minute: int = 0

    max_pipeline_videos: int = 15

    # Discovery: yt-dlp related-videos expansion (1 hop) bounds
    related_per_seed: int = 8
    related_total_cap: int = 200

    # Admission gate: minimum cosine similarity for a preferred-coach face match
    preferred_coach_min_confidence: float = 0.55

    # Face-match hardening
    face_min_det_score: float = 0.6
    face_match_frames: int = 16


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    return s
