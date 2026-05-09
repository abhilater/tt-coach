from app.core.db import get_engine
from sqlalchemy.orm import sessionmaker
from app.models.schema import Video
from app.ingest.youtube import fetch_video_details
from app.core.config import get_settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def backfill_view_counts():
    settings = get_settings()
    if not settings.youtube_api_key:
        print("Error: YOUTUBE_API_KEY not set.")
        return

    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    # Find videos with missing view counts
    videos = db.query(Video).filter(Video.source == "youtube").all()
    if not videos:
        print("No YouTube videos found.")
        return

    video_ids = [v.external_id for v in videos]
    print(f"Fetching details for {len(video_ids)} videos...")

    details = fetch_video_details(settings.youtube_api_key, video_ids)
    
    stats_map = {}
    for item in details:
        vid = item["id"]
        stats = item.get("statistics", {})
        v_count = stats.get("viewCount")
        if v_count:
            stats_map[vid] = int(v_count)

    updated_count = 0
    for v in videos:
        if v.external_id in stats_map:
            v.view_count = stats_map[v.external_id]
            updated_count += 1
    
    db.commit()
    print(f"Updated {updated_count} videos with view counts.")
    db.close()

if __name__ == "__main__":
    backfill_view_counts()
