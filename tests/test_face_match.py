"""Face-match hardening: highest-det_score face per frame; det_score gate at enrollment."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


def _fake_face(det_score: float, embedding_seed: float) -> SimpleNamespace:
    rng = np.random.default_rng(int(embedding_seed * 1e6))
    emb = rng.standard_normal(512).astype("float32")
    emb /= np.linalg.norm(emb)
    return SimpleNamespace(det_score=det_score, normed_embedding=emb)


def test_embedding_picks_highest_det_score_face(tmp_path: Path) -> None:
    """Multi-face frame: must select the face with the strongest detection."""
    from app.vision import embeddings as emb_mod

    faces = [
        _fake_face(0.30, 0.1),
        _fake_face(0.92, 0.2),
        _fake_face(0.55, 0.3),
    ]

    fake_app = SimpleNamespace(get=lambda img: faces)
    fake_img = np.zeros((32, 32, 3), dtype="uint8")

    with patch.object(emb_mod, "get_face_app", return_value=fake_app), patch(
        "cv2.imread", return_value=fake_img
    ):
        out = emb_mod.embedding_from_image(tmp_path / "frame.jpg")

    assert out is not None
    np.testing.assert_allclose(out, faces[1].normed_embedding)


def test_embedding_returns_none_when_no_faces(tmp_path: Path) -> None:
    from app.vision import embeddings as emb_mod

    fake_app = SimpleNamespace(get=lambda img: [])
    fake_img = np.zeros((4, 4, 3), dtype="uint8")
    with patch.object(emb_mod, "get_face_app", return_value=fake_app), patch(
        "cv2.imread", return_value=fake_img
    ):
        assert emb_mod.embedding_from_image(tmp_path / "x.jpg") is None


def test_enroll_skips_low_det_score_embeddings(tmp_path: Path, db_session) -> None:
    """Embeddings under face_min_det_score must not be added to the FAISS index."""
    from app.core.config import get_settings
    from app.models import Coach, CoachSample
    from app.vision import pipeline as vp
    from app.vision.index import FaceIndex

    coach = Coach(display_name="Demo")
    db_session.add(coach)
    db_session.commit()
    sample = CoachSample(coach_id=coach.id, image_path=str(tmp_path / "s.jpg"))
    db_session.add(sample)
    db_session.commit()

    settings = get_settings()
    threshold = settings.face_min_det_score
    high_score = max(threshold + 0.2, 0.8)
    low_score = max(threshold - 0.4, 0.05)

    high = _fake_face(high_score, 0.7)
    low = _fake_face(low_score, 0.4)
    fake_meta = [
        (tmp_path / "s.jpg", high.normed_embedding, high_score),
        (tmp_path / "s2.jpg", low.normed_embedding, low_score),
    ]

    with patch.object(vp, "_resolve_existing_sample_image", return_value=tmp_path / "s.jpg"), \
         patch.object(vp, "embeddings_with_meta", return_value=fake_meta), \
         patch.object(vp, "load_or_create_index", return_value=FaceIndex()), \
         patch.object(vp, "persist_index"):
        added = vp.enroll_coach_samples(db_session, coach.id)

    assert added == 1
