from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.video_insights import analyze_video
from app.core.config import get_settings
from app.ingest.youtube import run_ingestion
from app.models import Coach, UserProfile, Video, VideoAnalysis, VideoCoach
from app.ranking.score import compute_personalized_scores, today_str
from app.vision.pipeline import match_video_coaches

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


_LLM_QUOTA_EXC_NAMES = {"ResourceExhausted", "RateLimitError", "TooManyRequests"}


def _is_llm_quota_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in _LLM_QUOTA_EXC_NAMES:
        return True
    msg = str(exc).lower()
    return "429" in msg and ("quota" in msg or "rate limit" in msg)


def _resolve_preferred_coach_ids(db: Session) -> set[int]:
    profile = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if not profile or not profile.preferred_coaches:
        return set()
    out: set[int] = set()
    for token in profile.preferred_coaches or []:
        if isinstance(token, int):
            out.add(token)
        else:
            c = db.query(Coach).filter(Coach.display_name == str(token)).first()
            if c:
                out.add(c.id)
    return out


def _video_passes_admission(
    db: Session,
    video: Video,
    preferred_coach_ids: set[int],
    min_confidence: float,
) -> bool:
    if not preferred_coach_ids:
        return False
    link = (
        db.query(VideoCoach)
        .filter(
            VideoCoach.video_id == video.id,
            VideoCoach.coach_id.in_(preferred_coach_ids),
            VideoCoach.confidence >= min_confidence,
        )
        .first()
    )
    return link is not None


def gate_admission(db: Session) -> dict[str, int]:
    """Run face matching on every un-evaluated video and flip is_admitted.

    A video is admitted iff it has a VideoCoach row whose coach_id is in the
    user's preferred_coaches and whose confidence meets the configured
    threshold. Runs face matching first (cheap) before any LLM/transcribe step
    so we don't pay for analysis on rejected candidates.
    """
    settings = get_settings()
    counts = {"matched": 0, "admitted": 0, "rejected": 0, "skipped": 0}

    preferred_coach_ids = _resolve_preferred_coach_ids(db)
    if not preferred_coach_ids:
        logger.warning(
            "admission_gate_no_preferred_coaches — no videos will be admitted; "
            "set preferred coaches in /profile to enable the feed",
        )

    pending = (
        db.query(Video)
        .filter(Video.is_admitted.is_(False))
        .order_by(Video.published_at.desc().nullslast(), Video.id.desc())
        .limit(settings.max_pipeline_videos * 4)
        .all()
    )

    for v in pending:
        try:
            match_video_coaches(db, v, threshold=settings.preferred_coach_min_confidence)
            counts["matched"] += 1
        except Exception as e:
            logger.warning(
                "match_video_coaches_failed vid=%s err=%s",
                v.external_id,
                type(e).__name__,
            )
            counts["skipped"] += 1
            continue

        if _video_passes_admission(
            db, v, preferred_coach_ids, settings.preferred_coach_min_confidence
        ):
            v.is_admitted = True
            counts["admitted"] += 1
        else:
            v.is_admitted = False
            counts["rejected"] += 1

    db.commit()
    logger.info(
        "admission_gate matched=%s admitted=%s rejected=%s skipped=%s",
        counts["matched"],
        counts["admitted"],
        counts["rejected"],
        counts["skipped"],
    )
    return counts


async def _analyze_batch(db: Session, videos: list[Video]) -> None:
    quota_exhausted = False
    for v in videos:
        if quota_exhausted:
            logger.warning("analyze_skipped_quota vid=%s", v.external_id)
            continue
        try:
            await analyze_video(db, v)
        except Exception as e:
            try:
                db.rollback()
            except Exception:
                pass
            if _is_llm_quota_error(e):
                quota_exhausted = True
                logger.warning(
                    "llm_quota_exhausted task=insights vid=%s provider_err=%s; "
                    "remaining videos in batch will be skipped",
                    v.external_id,
                    type(e).__name__,
                )
            else:
                logger.warning(
                    "analyze_failed vid=%s err=%s msg=%s",
                    v.external_id,
                    type(e).__name__,
                    str(e)[:200].replace("\n", " "),
                )


def daily_refresh_job(SessionLocal: sessionmaker) -> None:
    settings = get_settings()
    db: Session = SessionLocal()
    try:
        ingest_counts = run_ingestion(db, days=7)
        logger.info("daily_ingest %s", ingest_counts)

        gate_counts = gate_admission(db)
        logger.info("daily_admission %s", gate_counts)

        pending = (
            db.query(Video)
            .filter(Video.is_admitted.is_(True))
            .outerjoin(VideoAnalysis, VideoAnalysis.video_id == Video.id)
            .filter(VideoAnalysis.id.is_(None))
            .order_by(Video.published_at.desc().nullslast(), Video.id.desc())
            .limit(settings.max_pipeline_videos)
            .all()
        )

        if pending:
            asyncio.run(_analyze_batch(db, pending))

        nrec = compute_personalized_scores(db, today_str())
        logger.info("daily_rank recommendations=%s", nrec)
    finally:
        db.close()


def setup_scheduler(SessionLocal: sessionmaker) -> None:
    global _scheduler
    settings = get_settings()
    if _scheduler is not None:
        return

    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(
        lambda: daily_refresh_job(SessionLocal),
        trigger="cron",
        hour=settings.scheduler_refresh_hour,
        minute=settings.scheduler_refresh_minute,
        id="daily_refresh",
        replace_existing=True,
    )
    sched.start()
    _scheduler = sched
    logger.info(
        "scheduler_started hour=%s minute=%s",
        settings.scheduler_refresh_hour,
        settings.scheduler_refresh_minute,
    )


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
