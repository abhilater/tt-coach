import hashlib
import re


def normalize_title(title: str) -> str:
    t = title.lower()
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split())


def duration_bucket(seconds: int | None) -> str:
    if seconds is None:
        return "unknown"
    if seconds < 120:
        return "short"
    if seconds < 600:
        return "medium"
    return "long"


def dedupe_key(title: str, duration_s: int | None, coach_key: str | None) -> str:
    raw = f"{normalize_title(title)}|{duration_bucket(duration_s)}|{coach_key or 'none'}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
