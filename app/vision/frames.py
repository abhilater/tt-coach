from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_frames_evenly(url: str, out_dir: Path, video_id: str, num_frames: int = 8) -> list[Path]:
    """Extract JPEG frames spread across video using ffmpeg fps sampling."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / f"{video_id}_%03d.jpg")
    vf = f"fps={num_frames}/600"  # ~ num_frames over 10 min span if video long
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        url,
        "-vf",
        vf,
        "-frames:v",
        str(num_frames),
        pattern,
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
    except subprocess.CalledProcessError as e:
        logger.warning("ffmpeg_frames_failed id=%s stderr=%s", video_id, _safe_err(e))
        return []

    paths = sorted(out_dir.glob(f"{video_id}_*.jpg"))
    return paths[:num_frames]


def _safe_err(e: subprocess.CalledProcessError) -> str:
    err = (e.stderr or b"").decode(errors="ignore").replace("\n", " ")
    return err[:500]
