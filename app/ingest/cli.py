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
    parser.add_argument(
        "--ingest",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run YouTube ingestion (default: yes). Use --no-ingest to skip and only gate/rank.",
    )
    parser.add_argument(
        "--gate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Run the face-match admission gate on un-admitted videos after ingestion "
            "(default: yes, with the 60-video scheduler cap removed so the full backlog "
            "is processed)."
        ),
    )
    parser.add_argument(
        "--gate-max-videos",
        type=int,
        default=0,
        help=(
            "Per-run cap for the admission gate (default: 0 = no cap, drain the full "
            "backlog). Set to a small positive integer (e.g. 20) to verify the pipeline "
            "before committing to a long full-backlog face-match pass."
        ),
    )
    parser.add_argument(
        "--rank",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Rebuild today's Recommendation rows after ingestion/gating (default: yes).",
    )
    args = parser.parse_args()

    settings = get_settings()
    setup_logging(settings.log_level)
    init_engine()
    from app.core.db import get_engine

    SessionLocal = sessionmaker(bind=get_engine())
    db = SessionLocal()
    try:
        if args.ingest:
            counts = run_ingestion(
                db,
                days=args.since_days,
                max_per_channel=args.max_per_channel,
            )
            logger.info("ingestion_counts %s", counts)
        else:
            logger.info("ingestion_skipped")

        if args.gate:
            from app.scheduler.jobs import gate_admission

            gate_counts = gate_admission(db, max_videos=args.gate_max_videos)
            logger.info("admission_counts %s", gate_counts)
        else:
            logger.info("admission_gate_skipped")

        if args.rank:
            from app.ranking.score import compute_personalized_scores, today_str

            n_recs = compute_personalized_scores(db, today_str())
            logger.info("ranking_recommendations=%s", n_recs)
        else:
            logger.info("ranking_skipped")
    finally:
        db.close()


if __name__ == "__main__":
    main()
