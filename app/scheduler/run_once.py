"""Run daily pipeline once (manual trigger)."""

import logging

from app.core.config import get_settings
from app.core.db import get_engine, init_engine
from app.core.logging import setup_logging
from app.scheduler.jobs import daily_refresh_job
from sqlalchemy.orm import sessionmaker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine()
    SessionLocal = sessionmaker(bind=get_engine())
    daily_refresh_job(SessionLocal)
    logger.info("run_once_complete")


if __name__ == "__main__":
    main()
