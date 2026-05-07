from __future__ import annotations

import logging
from pathlib import Path

from faster_whisper import WhisperModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_model: WhisperModel | None = None


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        s = get_settings()
        _model = WhisperModel(
            s.whisper_model_size,
            device=s.whisper_device,
            compute_type=s.whisper_compute_type,
        )
    return _model


def transcribe_audio_file(path: Path, language: str | None = None) -> tuple[str, list[dict]]:
    """Returns full text and segment dicts with start/end."""
    model = get_model()
    segments_iter, info = model.transcribe(str(path), language=language, vad_filter=True)
    segments: list[dict] = []
    texts: list[str] = []
    for seg in segments_iter:
        segments.append({"start": float(seg.start), "end": float(seg.end), "text": seg.text.strip()})
        texts.append(seg.text.strip())
    text = " ".join(texts).strip()
    detected = getattr(info, "language", None)
    logger.debug("transcribe_done lang=%s segments=%s", detected, len(segments))
    return text, segments


def transcribe_video_audio(video_url_or_path: str, data_dir: Path, video_id: str) -> tuple[str, list[dict]]:
    """Extract audio with ffmpeg then whisper."""
    import subprocess

    audio_path = data_dir / "audio" / f"{video_id}.wav"
    audio_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        video_url_or_path,
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(audio_path),
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=600)
    return transcribe_audio_file(audio_path)
