from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingest.youtube import yt_dlp_transcript
from app.llm.factory import complete_for_task
from app.llm.prompts import format_player_profile, prompt_meta, system_analyst, user_analyst
from app.llm.schemas import VideoInsights
from app.models import Transcript, UserProfile, Video, VideoAnalysis
from app.transcribe.whisper import transcribe_audio_file

logger = logging.getLogger(__name__)

_FFMPEG_WARN_EMITTED = False


def ensure_audio_wav(video: Video, data_dir: Path) -> Path | None:
    """Download/extract WAV via yt-dlp. Requires ffmpeg for postprocessing."""
    dest_base = data_dir / "audio" / video.external_id
    wav_path = Path(str(dest_base) + ".wav")
    if wav_path.exists():
        return wav_path
    if shutil.which("ffmpeg") is None:
        global _FFMPEG_WARN_EMITTED
        if not _FFMPEG_WARN_EMITTED:
            logger.warning(
                "ffmpeg_not_installed: audio extraction & Whisper transcripts disabled; "
                "falling back to YouTube captions only. Install via 'brew install ffmpeg' "
                "(macOS) or your distro's package manager."
            )
            _FFMPEG_WARN_EMITTED = True
        return None
    try:
        subprocess.run(
            [
                "yt-dlp",
                "-x",
                "--audio-format",
                "wav",
                "-o",
                str(dest_base) + ".%(ext)s",
                "--no-playlist",
                video.url,
            ],
            capture_output=True,
            check=True,
            timeout=600,
        )
    except Exception as e:
        logger.warning("yt_dlp_audio_failed vid=%s err=%s", video.external_id, type(e).__name__)
        return None
    return wav_path if wav_path.exists() else None


def ensure_transcript(db: Session, video: Video) -> Transcript | None:
    existing = db.query(Transcript).filter(Transcript.video_id == video.id).first()
    if existing and existing.text:
        return existing

    settings = get_settings()
    text: str | None = None
    segments: list | None = None

    wav = ensure_audio_wav(video, settings.data_dir)
    if wav:
        try:
            text, segments = transcribe_audio_file(wav)
        except Exception as e:
            logger.warning("whisper_failed vid=%s err=%s", video.external_id, type(e).__name__)

    if not text:
        text, segments = yt_dlp_transcript(video.url)

    if not text:
        logger.warning("no_transcript vid=%s", video.external_id)
        return None

    tr = existing or Transcript(video_id=video.id)
    tr.text = text
    tr.segments = segments
    tr.language = video.language or "en"
    if not existing:
        db.add(tr)
    db.commit()
    db.refresh(tr)
    return tr


async def analyze_video(db: Session, video: Video) -> VideoAnalysis | None:
    tr = ensure_transcript(db, video)
    excerpt = (tr.text if tr else "") or ""
    description = video.description or ""

    profile = db.query(UserProfile).filter(UserProfile.id == 1).first()
    profile_block = format_player_profile(profile)

    sys_p = system_analyst()
    usr_p = user_analyst(video.title, description, excerpt, profile_block)

    insights: VideoInsights = await complete_for_task("insights", sys_p, usr_p, VideoInsights)

    analysis = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video.id).first()
    if analysis is None:
        analysis = VideoAnalysis(video_id=video.id)
        db.add(analysis)

    analysis.summary = insights.summary
    analysis.drills = [d.model_dump() for d in insights.drills]
    analysis.tips = insights.coaching_tips
    analysis.try_next_session = insights.try_next_session
    analysis.mistakes = insights.key_mistakes_addressed
    analysis.chapters = [c.model_dump() for c in insights.chapters]
    analysis.tags = insights.skill_tags
    analysis.quality_score = insights.quality_score
    analysis.prompt_version = prompt_meta()
    analysis.llm_model = "multi"

    video.topics = list(set((video.topics or []) + insights.skill_tags))

    db.commit()
    db.refresh(analysis)
    return analysis
