from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Coach, CoachSample, Video, VideoCoach
from app.vision.embeddings import embeddings_from_paths
from app.vision.frames import extract_frames_evenly
from app.vision.index import FaceIndex, merge_scores

logger = logging.getLogger(__name__)


def load_or_create_index() -> FaceIndex:
    s = get_settings()
    return FaceIndex.load(s.face_index_path, s.face_meta_path)


def persist_index(fi: FaceIndex) -> None:
    s = get_settings()
    fi.save(s.face_index_path, s.face_meta_path)


def enroll_coach_samples(db: Session, coach_id: int) -> int:
    """Re-build embeddings for all samples of coach and append to index."""
    coach = db.query(Coach).filter(Coach.id == coach_id).first()
    if not coach:
        return 0
    fi = load_or_create_index()
    added = 0
    samples = db.query(CoachSample).filter(CoachSample.coach_id == coach_id).all()
    data_dir = get_settings().data_dir
    frames_dir = data_dir / "coach_frames"

    for samp in samples:
        paths: list[Path] = []
        if samp.image_path and Path(samp.image_path).exists():
            paths.append(Path(samp.image_path))
        elif samp.source_url:
            paths = extract_frames_evenly(samp.source_url, frames_dir, f"cs{samp.id}", num_frames=8)
            if paths:
                samp.image_path = str(paths[0])
                db.commit()
        embs = embeddings_from_paths(paths)
        for _i, emb in enumerate(embs):
            fid = fi.add(emb, coach_id=coach_id, sample_id=samp.id)
            samp.embedding_id = fid
            added += 1
    persist_index(fi)
    db.commit()
    logger.info("coach_enroll coach_id=%s embeddings_added=%s", coach_id, added)
    return added


def match_video_coaches(db: Session, video: Video, threshold: float = 0.55) -> None:
    fi = load_or_create_index()
    if fi.index.ntotal == 0:
        return

    settings = get_settings()
    frames_dir = settings.data_dir / "video_frames"
    paths = extract_frames_evenly(video.url, frames_dir, video.external_id, num_frames=8)
    from app.vision.embeddings import embedding_from_image

    best_global: dict[int, float] = {}
    evidence: dict[int, list] = {}

    for p in paths:
        emb = embedding_from_image(p)
        if emb is None:
            continue
        matches = fi.search(emb, k=5)
        merged = merge_scores(matches, fi.meta, threshold=threshold)
        for cid, sc in merged.items():
            prev = best_global.get(cid, 0.0)
            if sc > prev:
                best_global[cid] = sc
                evidence[cid] = [{"frame": str(p), "score": sc}]

    for cid, conf in best_global.items():
        link = (
            db.query(VideoCoach)
            .filter(VideoCoach.video_id == video.id, VideoCoach.coach_id == cid)
            .first()
        )
        if link is None:
            link = VideoCoach(video_id=video.id, coach_id=cid, confidence=conf, evidence=evidence.get(cid))
            db.add(link)
        else:
            link.confidence = max(link.confidence or 0.0, conf)
            link.evidence = evidence.get(cid)
    db.commit()
