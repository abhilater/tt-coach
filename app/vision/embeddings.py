from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)
_face_app = None


def get_face_app():
    global _face_app
    if _face_app is None:
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(name="buffalo_s", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        _face_app = app
    return _face_app


def embedding_from_image(path: Path) -> np.ndarray | None:
    """Return the embedding of the highest-confidence face in the image.

    Multi-face frames are common in coaching videos (coach + student). Picking
    the strongest detection mirrors how `embeddings_with_meta` behaves during
    enrollment and avoids arbitrary `faces[0]` selection from the detector.
    """
    import cv2

    img = cv2.imread(str(path))
    if img is None:
        return None
    faces = get_face_app().get(img)
    if not faces:
        return None
    f = max(faces, key=lambda x: float(getattr(x, "det_score", 0.0)))
    return f.normed_embedding.astype("float32")


def embeddings_from_paths(paths: list[Path]) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for p in paths:
        e = embedding_from_image(p)
        if e is not None:
            out.append(e)
    return out


def embeddings_with_meta(paths: list[Path]) -> list[tuple[Path, np.ndarray, float]]:
    import cv2

    out: list[tuple[Path, np.ndarray, float]] = []
    for p in paths:
        img = cv2.imread(str(p))
        if img is None:
            continue
        faces = get_face_app().get(img)
        if not faces:
            continue
        f = max(faces, key=lambda x: float(getattr(x, "det_score", 0.0)))
        out.append((p, f.normed_embedding.astype("float32"), float(getattr(f, "det_score", 0.0))))
    return out
