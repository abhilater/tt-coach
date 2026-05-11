from __future__ import annotations

from typing import Literal

from sqlalchemy import false, func, select
from sqlalchemy.orm import Query, Session

from app.models import Recommendation, Video, VideoCoach

FeedSort = Literal["recency", "views", "coach_id"]


def latest_feed_date(db: Session) -> str | None:
    return db.query(func.max(Recommendation.feed_date)).scalar()


def feed_recommendations_query(db: Session) -> Query[Recommendation]:
    """Recommendations for the most recent daily snapshot only (one row per video)."""
    latest = latest_feed_date(db)
    q = db.query(Recommendation)
    if latest is None:
        return q.filter(false())
    return q.filter(Recommendation.feed_date == latest)


def apply_feed_sort(base: Query[Recommendation], sort: FeedSort) -> Query[Recommendation]:
    """Apply sort order for the feed query."""
    with_video = base.join(Recommendation.video)
    if sort == "views":
        return with_video.order_by(
            Video.view_count.is_(None),
            Video.view_count.desc(),
            Recommendation.score.desc(),
        )
    if sort == "coach_id":
        primary_coach_id = (
            select(func.min(VideoCoach.coach_id))
            .where(VideoCoach.video_id == Recommendation.video_id)
            .scalar_subquery()
        )
        return with_video.order_by(
            primary_coach_id.is_(None),
            primary_coach_id.asc(),
            Recommendation.score.desc(),
        )
    return with_video.order_by(
        Video.published_at.is_(None),
        Video.published_at.desc(),
        Recommendation.score.desc(),
    )
