"""yt-dlp related-videos scrape: parses output, respects per-seed and total caps."""

from __future__ import annotations

import json
import subprocess
from typing import Any
from unittest.mock import patch

from app.ingest.youtube import _expand_related, yt_dlp_related_video_ids


class _FakeProc:
    def __init__(self, stdout: str, returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = ""
        self.returncode = returncode


def test_yt_dlp_related_parses_ids_and_respects_limit() -> None:
    payload = {
        "id": "abc",
        "related_videos": [
            {"id": f"rid{i:08d}"} for i in range(20)
        ],
    }
    with patch.object(subprocess, "run", return_value=_FakeProc(json.dumps(payload))):
        out = yt_dlp_related_video_ids("https://www.youtube.com/watch?v=abc", limit=5)
    assert len(out) == 5
    assert out[0] == "rid00000000"
    assert out[-1] == "rid00000004"


def test_yt_dlp_related_falls_back_to_url_extraction() -> None:
    payload = {
        "related_videos": [
            {"url": "https://www.youtube.com/watch?v=AAAAAAAAAAA"},
            {"url": "https://youtu.be/BBBBBBBBBBB"},
            {"url": "not_a_youtube_url"},
        ]
    }
    with patch.object(subprocess, "run", return_value=_FakeProc(json.dumps(payload))):
        out = yt_dlp_related_video_ids("https://www.youtube.com/watch?v=z", limit=5)
    assert out == ["AAAAAAAAAAA", "BBBBBBBBBBB"]


def test_yt_dlp_related_returns_empty_on_nonzero_exit() -> None:
    with patch.object(subprocess, "run", return_value=_FakeProc("", returncode=1)):
        assert yt_dlp_related_video_ids("https://x", limit=5) == []


def test_yt_dlp_related_returns_empty_on_invalid_json() -> None:
    with patch.object(subprocess, "run", return_value=_FakeProc("not-json")):
        assert yt_dlp_related_video_ids("https://x", limit=5) == []


def test_yt_dlp_related_returns_empty_on_subprocess_exception() -> None:
    def boom(*args: Any, **kwargs: Any) -> None:
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=1)

    with patch.object(subprocess, "run", side_effect=boom):
        assert yt_dlp_related_video_ids("https://x", limit=5) == []


def test_expand_related_respects_total_cap() -> None:
    seeds = ["seed1", "seed2", "seed3"]

    def fake(url: str, limit: int) -> list[str]:
        return [f"{url[-1]}_{i}" for i in range(limit)]

    with patch("app.ingest.youtube.yt_dlp_related_video_ids", side_effect=fake):
        out = _expand_related(seeds, per_seed=10, total_cap=15)

    assert len(out) == 15
    assert all(r not in seeds for r in out)


def test_expand_related_excludes_seed_video_ids() -> None:
    seeds = ["aaa", "bbb"]

    def fake(url: str, limit: int) -> list[str]:
        return ["aaa", "bbb", "ccc", "ddd"]

    with patch("app.ingest.youtube.yt_dlp_related_video_ids", side_effect=fake):
        out = _expand_related(seeds, per_seed=10, total_cap=10)

    assert "aaa" not in out
    assert "bbb" not in out
    assert {"ccc", "ddd"} <= out


def test_expand_related_zero_caps_short_circuits() -> None:
    with patch("app.ingest.youtube.yt_dlp_related_video_ids") as m:
        assert _expand_related(["s"], per_seed=0, total_cap=10) == set()
        assert _expand_related(["s"], per_seed=5, total_cap=0) == set()
    m.assert_not_called()
