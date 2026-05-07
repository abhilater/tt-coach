"""Face match: threshold + frame-hit quorum before persisting VideoCoach rows."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
from sqlalchemy.orm import Session

from app.models import Channel, Coach, Video, VideoCoach
from app.vision import pipeline as vp


def test_match_video_coaches_skips_when_quorum_not_met(db_session: Session, tmp_path, monkeypatch):
    coach = Coach(display_name="CoachQ")
    ch = Channel(source="youtube", external_id="UCq", title="Ch", is_trusted=True)
    db_session.add_all([coach, ch])
    db_session.commit()

    vid = Video(
        source="youtube",
        external_id="vq12______",
        url="https://www.youtube.com/watch?v=VQ12______",
        title="Lesson",
        channel_id=ch.id,
    )
    db_session.add(vid)
    db_session.commit()

    rng = np.random.default_rng(42)
    emb = rng.standard_normal(512).astype("float32")
    emb /= np.linalg.norm(emb)

    fi = MagicMock()
    fi.index.ntotal = 1
    fi.meta = [{"faiss_id": 0, "coach_id": coach.id, "sample_id": 1}]
    fi.search = MagicMock(return_value=[(0, 0.70)])

    settings = MagicMock()
    settings.preferred_coach_min_confidence = 0.65
    settings.face_match_frames = 16
    settings.face_match_frame_hit_quorum = 2
    settings.data_dir = tmp_path

    monkeypatch.setattr(vp, "get_settings", lambda: settings)
    monkeypatch.setattr(vp, "load_or_create_index", lambda: fi)

    frames = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    monkeypatch.setattr(vp, "extract_frames_evenly", lambda *a, **k: frames)

    def emb_one_frame(path):
        if path == frames[0]:
            return emb.astype("float32")
        return None

    monkeypatch.setattr("app.vision.embeddings.embedding_from_image", emb_one_frame)

    vp.match_video_coaches(db_session, vid, threshold=0.65)

    rows = db_session.query(VideoCoach).filter(VideoCoach.video_id == vid.id).all()
    assert rows == []


def test_match_video_coaches_persists_when_quorum_met(db_session: Session, tmp_path, monkeypatch):
    coach = Coach(display_name="CoachQQ")
    ch = Channel(source="youtube", external_id="UCq2", title="Ch2", is_trusted=True)
    db_session.add_all([coach, ch])
    db_session.commit()

    vid = Video(
        source="youtube",
        external_id="vq56______",
        url="https://www.youtube.com/watch?v=VQ56______",
        title="Lesson",
        channel_id=ch.id,
    )
    db_session.add(vid)
    db_session.commit()

    rng = np.random.default_rng(99)
    emb = rng.standard_normal(512).astype("float32")
    emb /= np.linalg.norm(emb)

    fi = MagicMock()
    fi.index.ntotal = 1
    fi.meta = [{"faiss_id": 0, "coach_id": coach.id, "sample_id": 1}]
    fi.search = MagicMock(return_value=[(0, 0.70)])

    settings = MagicMock()
    settings.preferred_coach_min_confidence = 0.65
    settings.face_match_frames = 16
    settings.face_match_frame_hit_quorum = 2
    settings.data_dir = tmp_path

    monkeypatch.setattr(vp, "get_settings", lambda: settings)
    monkeypatch.setattr(vp, "load_or_create_index", lambda: fi)

    frames = [tmp_path / "f1.jpg", tmp_path / "f2.jpg"]
    monkeypatch.setattr(vp, "extract_frames_evenly", lambda *a, **k: frames)
    monkeypatch.setattr(
        "app.vision.embeddings.embedding_from_image",
        lambda _path: emb.astype("float32"),
    )

    vp.match_video_coaches(db_session, vid, threshold=0.65)

    rows = db_session.query(VideoCoach).filter(VideoCoach.video_id == vid.id).all()
    assert len(rows) == 1
    assert rows[0].coach_id == coach.id
    assert rows[0].confidence >= 0.65
    assert isinstance(rows[0].evidence, list)
    assert len(rows[0].evidence) == 2
