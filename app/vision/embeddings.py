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
    import cv2

    img = cv2.imread(str(path))
    if img is None:
        return None
    faces = get_face_app().get(img)
    if not faces:
        return None
    emb = faces[0].normed_embedding.astype("float32")
    return emb


def embeddings_from_paths(paths: list[Path]) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for p in paths:
        e = embedding_from_image(p)
        if e is not None:
            out.append(e)
    return out
