"""Feed list pagination on web HTML and JSON API."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.models import Base, Recommendation, Video
from app.web.routes import router as web_router


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


def test_feed_pagination_slices_scores():
    engine = _engine()
    SessionLocal = _session_factory(engine)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app = FastAPI()
    app.include_router(web_router)
    app.dependency_overrides[get_db] = override_db

    db = SessionLocal()
    for i in range(75):
        db.add(
            Video(
                source="youtube",
                external_id=f"p{i:011d}",
                url=f"https://youtu.be/e{i}",
                title=f"Title {i}",
            )
        )
    db.commit()
    videos = db.query(Video).order_by(Video.id).all()
    for idx, v in enumerate(videos):
        db.add(
            Recommendation(
                video_id=v.id,
                score=float(idx),
                reasons=[],
                feed_date="2099-01-01",
            )
        )
    db.commit()
    db.close()

    with TestClient(app) as client:
        r_default = client.get("/feed?page=1")
        assert r_default.status_code == 200
        assert r_default.text.count('href="/videos/') == 50

        r1 = client.get("/feed?page=1&per_page=20")
        assert r1.status_code == 200
        assert r1.text.count('href="/videos/') == 20

        r4 = client.get("/feed?page=4&per_page=20")
        assert r4.status_code == 200
        assert "page 4 / 4" in r4.text
        assert r4.text.count('href="/videos/') == 15


def test_api_feed_clamps_per_page_and_page():
    engine = _engine()
    SessionLocal = _session_factory(engine)

    def override_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    from app.api.routes import router as api_router

    app = FastAPI()
    app.include_router(api_router, prefix="/api")
    app.dependency_overrides[get_db] = override_db

    db = SessionLocal()
    db.add(
        Video(
            source="youtube",
            external_id="clamped____",
            url="https://youtu.be/x",
            title="Only",
        )
    )
    db.commit()
    v = db.query(Video).one()
    db.add(Recommendation(video_id=v.id, score=1.0, reasons=[], feed_date="2099-01-01"))
    db.commit()
    db.close()

    with TestClient(app) as client:
        r_default = client.get("/api/feed")
        assert r_default.status_code == 200
        assert r_default.json()["per_page"] == 50

        r_big = client.get("/api/feed?per_page=999")
        assert r_big.status_code == 200
        data = r_big.json()
        assert data["per_page"] == 50
        assert len(data["items"]) == 1

        r_zero = client.get("/api/feed?page=0")
        assert r_zero.status_code == 200
        assert r_zero.json()["page"] == 1
