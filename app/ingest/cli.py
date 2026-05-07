import argparse
import logging

from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.db import init_engine
from app.core.logging import setup_logging
from app.ingest.youtube import run_ingestion

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="TT Coach ingestion CLI")
    parser.add_argument("--since-days", type=int, default=7, help="Published-after window")
    parser.add_argument(
        "--max-per-channel",
        type=int,
        default=50,
        help="Max uploads to fetch per channel (use ~500 for a 90-day backfill on active channels)",
    )
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine()
    from app.core.db import get_engine

    SessionLocal = sessionmaker(bind=get_engine())
    db = SessionLocal()
    try:
        counts = run_ingestion(
            db,
            days=args.since_days,
            max_per_channel=args.max_per_channel,
        )
        logger.info("ingestion_counts %s", counts)
    finally:
        db.close()


if __name__ == "__main__":
    main()
