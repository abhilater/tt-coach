import re


def extract_youtube_video_id(url: str) -> str | None:
    u = url.strip()
    m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", u)
    return m.group(1) if m else None


def validate_coach_sample_url(url: str) -> bool:
    """Allow only http(s) YouTube watch / youtu.be URLs."""
    u = url.strip()
    if not u.startswith(("http://", "https://")):
        return False
    return extract_youtube_video_id(u) is not None


def coach_sample_url_dedupe_key(url: str | None, sample_id: int) -> str:
    """Stable key for deduplicating sample rows (same YouTube video = one link)."""
    u = (url or "").strip()
    if not u:
        return f"__empty_{sample_id}"
    vid = extract_youtube_video_id(u)
    if vid:
        return vid
    return f"raw:{u.lower()}"
