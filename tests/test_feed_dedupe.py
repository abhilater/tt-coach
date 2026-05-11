"""Feed shows one row per video (latest feed_date snapshot only)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import router as api_router
from app.core.db import get_db
from app.models import Base, Recommendation, Video


def _session_factory(engine):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_api_feed_dedupes_same_video_across_feed_dates():
    engine = _engine()
    SessionLocal = _session_factory(engine)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_db] = override_db

    db = SessionLocal()
    db.add(
        Video(
            source="youtube",
            external_id="dupvid______",
            url="https://youtu.be/dup",
            title="Duplicate feed test",
        )
    )
    db.commit()
    v = db.query(Video).one()
    db.add(
        Recommendation(
            video_id=v.id,
            score=1.0,
            reasons=["old"],
            feed_date="2026-01-01",
        )
    )
    db.add(
        Recommendation(
            video_id=v.id,
            score=9.0,
            reasons=["new"],
            feed_date="2026-01-15",
        )
    )
    db.commit()
    video_id = v.id
    db.close()

    with TestClient(app) as client:
        r = client.get("/api/feed")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["score"] == 9.0
        assert data["items"][0]["reasons"] == ["new"]
        assert data["items"][0]["video"]["id"] == video_id
