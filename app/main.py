import logging
import subprocess
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import router as api_router
from app.core.config import get_settings
from app.core.db import get_engine, init_engine
from app.core.logging import correlation_id_ctx, setup_logging
from app.models import UserProfile
from app.scheduler.jobs import setup_scheduler, shutdown_scheduler
from app.web.routes import router as web_router

logger = logging.getLogger(__name__)


class CorrelationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        token = correlation_id_ctx.set(cid)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = cid
            return response
        finally:
            correlation_id_ctx.reset(token)


def seed_singleton_profile(session_factory) -> None:
    from sqlalchemy.orm import Session

    db: Session = session_factory()
    try:
        row = db.query(UserProfile).filter(UserProfile.id == 1).first()
        if row is None:
            db.add(
                UserProfile(
                    id=1,
                    level="intermediate",
                    preferred_languages=["en"],
                    goals=[],
                    weaknesses=[],
                    preferred_coaches=[],
                )
            )
            db.commit()
            logger.info("Created default user_profile id=1")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine()
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    seed_singleton_profile(SessionLocal)
    setup_scheduler(SessionLocal)
    yield
    shutdown_scheduler()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="TT Coach", version="0.1.0", lifespan=lifespan)

    app.add_middleware(CorrelationMiddleware)

    static_dir = settings.data_dir / "static"
    static_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    app.mount("/media", StaticFiles(directory=str(settings.data_dir.resolve())), name="media")

    app.include_router(web_router)
    app.include_router(api_router, prefix="/api")

    return app


app = create_app()


def main():
    """Verify ffmpeg available for vision/transcribe."""
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        logger.warning("ffmpeg not found on PATH; transcription and frame extraction will fail")


if __name__ == "__main__":
    main()
