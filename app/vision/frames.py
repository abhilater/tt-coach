from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_frames_evenly(url: str, out_dir: Path, video_id: str, num_frames: int = 8) -> list[Path]:
    """Extract JPEG frames spread evenly across a video.

    Accepts a local file path or a remote URL (e.g. YouTube). Remote URLs are
    downloaded with the yt-dlp Python API; frames are decoded with OpenCV
    (cv2.VideoCapture). This avoids any external ffmpeg dependency.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    local_path = _resolve_to_local_video(url, out_dir, video_id)
    if local_path is None:
        return []

    try:
        return _extract_frames_with_cv2(local_path, out_dir, video_id, num_frames)
    finally:
        if local_path.exists() and local_path.parent.name == "_downloads":
            try:
                local_path.unlink()
            except OSError:
                pass


def _resolve_to_local_video(url: str, out_dir: Path, video_id: str) -> Path | None:
    """Return a local video file path. Downloads remote URLs with yt-dlp."""
    if url.startswith(("http://", "https://")):
        return _download_with_yt_dlp(url, out_dir, video_id)
    p = Path(url)
    return p if p.is_file() else None


def _download_with_yt_dlp(url: str, out_dir: Path, video_id: str) -> Path | None:
    """Download a remote video to disk via the yt-dlp Python API."""
    try:
        import yt_dlp
    except ImportError:
        logger.warning("yt_dlp_not_installed video_id=%s", video_id)
        return None

    download_dir = out_dir / "_downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(download_dir / f"{video_id}.%(ext)s")
    ydl_opts = {
        "outtmpl": outtmpl,
        # Prefer a single mp4 progressive stream so we don't need ffmpeg to merge.
        "format": "best[ext=mp4][height<=480]/best[height<=480]/best[ext=mp4]/best",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "retries": 2,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = Path(ydl.prepare_filename(info))
        if file_path.exists():
            return file_path
        candidates = sorted(download_dir.glob(f"{video_id}.*"))
        return candidates[0] if candidates else None
    except Exception as e:
        logger.warning(
            "yt_dlp_download_failed video_id=%s err_type=%s",
            video_id,
            type(e).__name__,
        )
        return None


def _extract_frames_with_cv2(
    video_path: Path, out_dir: Path, video_id: str, num_frames: int
) -> list[Path]:
    """Decode `num_frames` evenly spaced JPEG frames using OpenCV."""
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("cv2_open_failed video_id=%s", video_id)
        return []
    try:
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if total <= 0:
            return []
        step = max(total // (num_frames + 1), 1)
        out_paths: list[Path] = []
        for i in range(1, num_frames + 1):
            idx = min(step * i, total - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            out_p = out_dir / f"{video_id}_{i:03d}.jpg"
            if cv2.imwrite(str(out_p), frame):
                out_paths.append(out_p)
        return out_paths
    finally:
        cap.release()
