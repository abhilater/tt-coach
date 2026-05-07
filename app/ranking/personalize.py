from __future__ import annotations

from collections import Counter

from sqlalchemy.orm import Session

from app.models import Recommendation, Video, VideoAnalysis


def tag_overlap_score(tags_a: list[str], tags_b: list[str]) -> float:
    if not tags_a or not tags_b:
        return 0.0
    ca = Counter(t.lower() for t in tags_a)
    cb = Counter(t.lower() for t in tags_b)
    inter = sum((ca & cb).values())
    return inter / max(len(ca), len(cb), 1)


def watch_next(db: Session, video_id: int, limit: int = 5) -> list[Video]:
    base = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()
    if not base or not base.tags:
        recs = (
            db.query(Recommendation).order_by(Recommendation.score.desc()).limit(limit).all()
        )
        return [r.video for r in recs if r.video_id != video_id][:limit]

    candidates = db.query(VideoAnalysis).filter(VideoAnalysis.video_id != video_id).all()
    scored: list[tuple[float, int]] = []
    for ca in candidates:
        if not ca.tags:
            continue
        s = tag_overlap_score(base.tags, ca.tags)
        scored.append((s, ca.video_id))

    scored.sort(reverse=True)
    out: list[Video] = []
    for _, vid in scored[:limit]:
        v = db.query(Video).filter(Video.id == vid).first()
        if v:
            out.append(v)
    return out
