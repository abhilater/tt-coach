from __future__ import annotations

import json
import logging
from pathlib import Path

import faiss
import numpy as np

logger = logging.getLogger(__name__)


class FaceIndex:
    """Cosine similarity via normalized inner product."""

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim
        self.index = faiss.IndexFlatIP(dim)
        self.meta: list[dict] = []

    def add(self, embedding: np.ndarray, coach_id: int, sample_id: int | None = None) -> int:
        vec = embedding.astype("float32").reshape(1, -1)
        faiss.normalize_L2(vec)
        idx = self.index.ntotal
        self.index.add(vec)
        self.meta.append({"faiss_id": idx, "coach_id": coach_id, "sample_id": sample_id})
        return idx

    def search(self, embedding: np.ndarray, k: int = 5) -> list[tuple[int, float]]:
        vec = embedding.astype("float32").reshape(1, -1)
        faiss.normalize_L2(vec)
        scores, ids = self.index.search(vec, k)
        result: list[tuple[int, float]] = []
        for score, i in zip(scores[0], ids[0], strict=False):
            if i < 0:
                continue
            result.append((int(i), float(score)))
        return result

    def save(self, index_path: Path, meta_path: Path) -> None:
        index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(index_path))
        meta_path.write_text(json.dumps(self.meta))

    @classmethod
    def load(cls, index_path: Path, meta_path: Path, dim: int = 512) -> "FaceIndex":
        fi = cls(dim=dim)
        if index_path.exists():
            fi.index = faiss.read_index(str(index_path))
        if meta_path.exists():
            fi.meta = json.loads(meta_path.read_text())
        return fi


def merge_scores(matches: list[tuple[int, float]], meta: list[dict], threshold: float = 0.55) -> dict[int, float]:
    """Map coach_id -> max similarity."""
    best: dict[int, float] = {}
    for idx, sim in matches:
        if idx >= len(meta):
            continue
        cid = meta[idx]["coach_id"]
        if sim >= threshold:
            best[cid] = max(best.get(cid, 0.0), sim)
    return best
