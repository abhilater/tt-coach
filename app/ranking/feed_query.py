from __future__ import annotations

from sqlalchemy import false, func
from sqlalchemy.orm import Query, Session

from app.models import Recommendation


def latest_feed_date(db: Session) -> str | None:
    return db.query(func.max(Recommendation.feed_date)).scalar()


def feed_recommendations_query(db: Session) -> Query[Recommendation]:
    """Recommendations for the most recent daily snapshot only (one row per video)."""
    latest = latest_feed_date(db)
    q = db.query(Recommendation)
    if latest is None:
        return q.filter(false())
    return q.filter(Recommendation.feed_date == latest)
