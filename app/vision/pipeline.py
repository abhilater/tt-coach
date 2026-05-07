from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Coach, CoachSample, Video, VideoCoach
from app.vision.embeddings import embeddings_with_meta
from app.vision.frames import extract_frames_evenly
from app.vision.index import FaceIndex, merge_scores

logger = logging.getLogger(__name__)


def _resolve_existing_sample_image(image_path: str, data_dir: Path) -> Path | None:
    data_resolved = data_dir.resolve()
    p = Path(image_path)
    if p.is_file():
        return p.resolve()
    candidates: list[Path] = []
    if not p.is_absolute() and p.parts and p.parts[0] == data_resolved.name:
        candidates.append((data_resolved / Path(*p.parts[1:])).resolve())
    candidates.append((data_resolved / image_path).resolve())
    for under_data in candidates:
        try:
            under_data.relative_to(data_resolved)
        except ValueError:
            continue
        if under_data.is_file():
            return under_data
    return None


def _image_path_for_db(path: Path, data_dir: Path) -> str:
    data_resolved = data_dir.resolve()
    try:
        rel = path.resolve().relative_to(data_resolved)
    except ValueError:
        return str(path).replace("\\", "/")
    if rel.parts and rel.parts[0] == data_resolved.name:
        rel = Path(*rel.parts[1:])
    return str(rel).replace("\\", "/")


def load_or_create_index() -> FaceIndex:
    s = get_settings()
    return FaceIndex.load(s.face_index_path, s.face_meta_path)


def persist_index(fi: FaceIndex) -> None:
    s = get_settings()
    fi.save(s.face_index_path, s.face_meta_path)


def enroll_coach_samples(db: Session, coach_id: int) -> int:
    """Re-build embeddings for all samples of coach and append to index.

    Embeddings whose detection score is below ``settings.face_min_det_score`` are
    discarded so the FAISS index stays clean of blurry / oblique / mis-detected
    crops, which otherwise drag false-positive rates up at the matching stage.
    """
    coach = db.query(Coach).filter(Coach.id == coach_id).first()
    if not coach:
        return 0
    settings = get_settings()
    fi = load_or_create_index()
    added = 0
    skipped_low_quality = 0
    samples = db.query(CoachSample).filter(CoachSample.coach_id == coach_id).all()
    data_dir = settings.data_dir
    frames_dir = data_dir / "coach_frames"

    for samp in samples:
        paths: list[Path] = []
        if samp.image_path:
            resolved = _resolve_existing_sample_image(samp.image_path, data_dir)
            if resolved:
                paths.append(resolved)
        if not paths and samp.source_url:
            paths = extract_frames_evenly(samp.source_url, frames_dir, f"cs{samp.id}", num_frames=8)
            if paths:
                samp.image_path = _image_path_for_db(paths[0], data_dir)
                db.commit()
        meta = embeddings_with_meta(paths)
        if meta:
            best_p, _, _ = max(meta, key=lambda t: t[2])
            samp.image_path = _image_path_for_db(best_p, data_dir)
            db.commit()
            for _path, emb, score in meta:
                if score < settings.face_min_det_score:
                    skipped_low_quality += 1
                    continue
                fid = fi.add(emb, coach_id=coach_id, sample_id=samp.id)
                samp.embedding_id = fid
                added += 1
        elif paths:
            samp.image_path = _image_path_for_db(paths[0], data_dir)
            db.commit()
            logger.warning(
                "coach_enroll_no_faces coach_id=%s sample_id=%s",
                coach_id,
                samp.id,
            )
    persist_index(fi)
    db.commit()
    logger.info(
        "coach_enroll coach_id=%s embeddings_added=%s skipped_low_quality=%s threshold=%.2f",
        coach_id,
        added,
        skipped_low_quality,
        settings.face_min_det_score,
    )
    return added


def match_video_coaches(db: Session, video: Video, threshold: float | None = None) -> None:
    fi = load_or_create_index()
    if fi.index.ntotal == 0:
        return

    settings = get_settings()
    if threshold is None:
        threshold = settings.preferred_coach_min_confidence
    quorum = max(1, settings.face_match_frame_hit_quorum)

    db.query(VideoCoach).filter(VideoCoach.video_id == video.id).delete()

    frames_dir = settings.data_dir / "video_frames"
    paths = extract_frames_evenly(
        video.url, frames_dir, video.external_id, num_frames=settings.face_match_frames
    )
    from app.vision.embeddings import embedding_from_image

    hits: dict[int, list[dict]] = {}
    best: dict[int, float] = {}

    for p in paths:
        emb = embedding_from_image(p)
        if emb is None:
            continue
        matches = fi.search(emb, k=5)
        merged = merge_scores(matches, fi.meta, threshold=threshold)
        for cid, sc in merged.items():
            prev_best = best.get(cid, 0.0)
            if sc > prev_best:
                best[cid] = sc
            hits.setdefault(cid, []).append({"frame": str(p), "score": sc})

    for cid, conf in best.items():
        if len(hits.get(cid, [])) < quorum:
            continue
        db.add(
            VideoCoach(
                video_id=video.id,
                coach_id=cid,
                confidence=conf,
                evidence=hits[cid],
            )
        )
    db.commit()
