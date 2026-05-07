from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.models import Recommendation, Video, VideoAnalysis

router = APIRouter(tags=["api"])


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/feed")
def api_feed(db: Session = Depends(get_db)):
    recs = db.query(Recommendation).order_by(Recommendation.score.desc()).limit(50).all()
    out = []
    for r in recs:
        v = r.video
        out.append(
            {
                "score": r.score,
                "reasons": r.reasons or [],
                "video": {
                    "id": v.id,
                    "title": v.title,
                    "url": v.url,
                    "thumbnail_path": v.thumbnail_path,
                },
            }
        )
    return {"items": out}


@router.get("/videos/{video_id}")
def api_video_detail(video_id: int, db: Session = Depends(get_db)):
    v = db.query(Video).filter(Video.id == video_id).first()
    if not v:
        return {"error": "not_found"}
    ana = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()
    analysis_payload = None
    if ana:
        analysis_payload = {
            "summary": ana.summary,
            "drills": ana.drills,
            "tips": ana.tips,
            "mistakes": ana.mistakes,
            "try_next_session": ana.try_next_session,
            "chapters": ana.chapters,
            "tags": ana.tags,
            "quality_score": ana.quality_score,
            "llm_model": ana.llm_model,
            "prompt_version": ana.prompt_version,
        }
    return {
        "video": {
            "id": v.id,
            "title": v.title,
            "url": v.url,
            "topics": v.topics or [],
        },
        "analysis": analysis_payload,
    }
