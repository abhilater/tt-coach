from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session, sessionmaker

from app.analysis.video_insights import analyze_video
from app.core.config import get_settings
from app.ingest.youtube import run_ingestion
from app.models import Video, VideoAnalysis
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


async def _analyze_batch(db: Session, videos: list[Video]) -> None:
    quota_exhausted = False
    for v in videos:
        if quota_exhausted:
            logger.warning("analyze_skipped_quota vid=%s", v.external_id)
            continue
        try:
            await analyze_video(db, v)
            match_video_coaches(db, v)
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

        pending = (
            db.query(Video)
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
