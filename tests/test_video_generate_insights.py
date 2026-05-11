"""POST /videos/{id}/generate-insights web route."""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.web.routes as web_routes
from app.core.db import get_db
from app.models import Base, Video
from app.web.routes import router as web_router


def _engine():
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_video_generate_insights_success_redirect(monkeypatch):
    engine = _engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    db.add(
        Video(
            source="youtube",
            external_id="ext123",
            url="https://youtu.be/abc",
            title="Test",
        )
    )
    db.commit()
    vid = db.query(Video).first().id
    db.close()

    monkeypatch.setattr(web_routes, "get_engine", lambda: engine)
    monkeypatch.setattr(web_routes, "analyze_video", AsyncMock(return_value=None))

    def override_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app = FastAPI()
    app.include_router(web_router)
    app.dependency_overrides[get_db] = override_db

    with TestClient(app) as client:
        r = client.post(f"/videos/{vid}/generate-insights", follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers.get("location", "")
    assert f"/videos/{vid}" in loc
    assert "flash=success" in loc
    assert "Insights+generated" in loc or "Insights%20generated" in loc


def test_video_generate_insights_not_found(monkeypatch):
    engine = _engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(web_routes, "get_engine", lambda: engine)

    app = FastAPI()
    app.include_router(web_router)

    with TestClient(app) as client:
        r = client.post("/videos/999/generate-insights", follow_redirects=False)
    assert r.status_code == 404


def test_video_generate_insights_error_redirect(monkeypatch):
    engine = _engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    db.add(
        Video(
            source="youtube",
            external_id="ext999",
            url="https://youtu.be/xyz",
            title="Err",
        )
    )
    db.commit()
    vid = db.query(Video).first().id
    db.close()

    monkeypatch.setattr(web_routes, "get_engine", lambda: engine)
    monkeypatch.setattr(
        web_routes,
        "analyze_video",
        AsyncMock(side_effect=RuntimeError("llm down")),
    )

    app = FastAPI()
    app.include_router(web_router)

    with TestClient(app) as client:
        r = client.post(f"/videos/{vid}/generate-insights", follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers.get("location", "")
    assert f"/videos/{vid}" in loc
    assert "flash=error" in loc
    assert "RuntimeError" in loc
