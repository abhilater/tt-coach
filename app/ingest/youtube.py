from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingest.topics import infer_topics_from_text
from app.ingest.url_validate import extract_youtube_video_id
from app.models import Channel, Coach, CoachSample, UserProfile, Video

logger = logging.getLogger(__name__)

_VTT_TIMING_RE = re.compile(r"^\s*\d{1,2}:\d{2}(?::\d{2})?\.\d{3}\s*-->")
_VTT_TAG_RE = re.compile(r"<[^>]+>")


def _vtt_to_text(content: str) -> str:
    """Convert a WebVTT/SRT-ish caption file to plain text (no ffmpeg needed)."""
    out: list[str] = []
    last = ""
    for raw in content.splitlines():
        s = raw.strip()
        if not s:
            continue
        if s.startswith(("WEBVTT", "Kind:", "Language:", "NOTE", "STYLE")):
            continue
        if _VTT_TIMING_RE.match(s) or "-->" in s:
            continue
        if s.isdigit():
            continue
        s = _VTT_TAG_RE.sub("", s).strip()
        if not s or s == last:
            continue
        out.append(s)
        last = s
    return " ".join(out).strip()


def _published_after(days: int) -> str:
    dt = datetime.now(tz=UTC) - timedelta(days=days)
    return dt.isoformat().replace("+00:00", "Z")


def yt_service(api_key: str):
    return build("youtube", "v3", developerKey=api_key, cache_discovery=False)


def upsert_channel(db: Session, external_id: str, title: str | None = None) -> Channel:
    ch = db.query(Channel).filter(Channel.external_id == external_id).first()
    if ch:
        if title and ch.title != title:
            ch.title = title
            db.commit()
        return ch
    ch = Channel(source="youtube", external_id=external_id, title=title or "", is_trusted=False)
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


def fetch_video_details(api_key: str, video_ids: list[str]) -> list[dict]:
    if not video_ids:
        return []
    yt = yt_service(api_key)
    out: list[dict] = []
    # chunks of 50
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i : i + 50]
        resp = yt.videos().list(part="snippet,contentDetails", id=",".join(chunk)).execute()
        out.extend(resp.get("items", []))
    return out


def channel_uploads(api_key: str, channel_external_id: str, days: int, max_results: int = 50) -> list[str]:
    yt = yt_service(api_key)
    ch_resp = yt.channels().list(part="contentDetails", id=channel_external_id).execute()
    items = ch_resp.get("items", [])
    if not items:
        return []
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids: list[str] = []
    req = yt.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=min(50, max_results))
    cutoff = datetime.now(tz=UTC) - timedelta(days=days)
    while req is not None and len(ids) < max_results:
        resp = req.execute()
        for it in resp.get("items", []):
            vid = it["contentDetails"]["videoId"]
            pub = it["contentDetails"].get("videoPublishedAt")
            if pub:
                pdt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if pdt < cutoff:
                    continue
            ids.append(vid)
        req = yt.playlistItems().list_next(req, resp)
    return ids[:max_results]


def download_thumbnail(url: str, dest: Path) -> bool:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            r = client.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)
        return True
    except Exception as e:
        logger.warning("thumbnail_download_failed path=%s err=%s", dest.name, type(e).__name__)
        return False


def yt_dlp_transcript(video_url: str) -> tuple[str | None, list | None]:
    """Extract subtitles via yt-dlp (auto-generated OK)."""
    cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-sub",
        "--sub-lang",
        "en,hi",
        "--sub-format",
        "json3",
        "-o",
        "-",
        "--dump-json",
        video_url,
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            return None, None
        meta = json.loads(proc.stdout.split("\n", 1)[0])
        # subtitles file paths sometimes in meta - simplified: use write-subs to tempfile
    except Exception:
        pass
    tmp_cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-auto-sub",
        "--sub-lang",
        "en",
        "-o",
        "/tmp/ttcoach_%(id)s.%(ext)s",
        video_url,
    ]
    try:
        subprocess.run(tmp_cmd, capture_output=True, text=True, timeout=180)
        vid = extract_youtube_video_id(video_url)
        if not vid:
            return None, None
        candidates = sorted(Path("/tmp").glob(f"ttcoach_{vid}.*.vtt")) + sorted(
            Path("/tmp").glob(f"ttcoach_{vid}.*.srt")
        )
        if not candidates:
            return None, None
        sub_path = candidates[0]
        raw = sub_path.read_text(errors="ignore")
        text = _vtt_to_text(raw) if sub_path.suffix.lower() == ".vtt" else raw.strip()
        return (text or None), None
    except Exception as e:
        logger.debug("yt_dlp_transcript_failed %s", e)
        return None, None


def upsert_video_from_api_item(
    db: Session,
    item: dict,
    settings,
    ingest_run_id: str,
) -> Video | None:
    vid = item["id"]
    snip = item["snippet"]
    details_cd = item.get("contentDetails", {})
    channel_ext = snip["channelId"]
    title = snip["title"]
    description = snip.get("description") or ""
    published = snip.get("publishedAt")
    thumbs = snip.get("thumbnails", {})
    thumb_url = (
        thumbs.get("high", {}).get("url")
        or thumbs.get("medium", {}).get("url")
        or thumbs.get("default", {}).get("url")
    )

    duration_iso = details_cd.get("duration", "")
    duration_s = _parse_iso_duration(duration_iso)

    ch = upsert_channel(db, channel_ext, title=snip.get("channelTitle"))

    topics = infer_topics_from_text(title + " " + description)

    pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00")) if published else None

    existing = (
        db.query(Video).filter(Video.source == "youtube", Video.external_id == vid).first()
    )
    thumb_path_str: str | None = None
    if thumb_url:
        thumb_dest = settings.data_dir / "thumbnails" / f"{vid}.jpg"
        if download_thumbnail(thumb_url, thumb_dest):
            thumb_path_str = f"thumbnails/{vid}.jpg"

    if existing:
        existing.title = title
        existing.description = description
        existing.duration_s = duration_s
        existing.topics = topics
        existing.ingest_run_id = ingest_run_id
        if thumb_path_str:
            existing.thumbnail_path = thumb_path_str
        db.commit()
        db.refresh(existing)
        return existing

    v = Video(
        source="youtube",
        external_id=vid,
        url=f"https://www.youtube.com/watch?v={vid}",
        title=title,
        description=description,
        thumbnail_path=thumb_path_str,
        channel_id=ch.id,
        published_at=pub_dt,
        duration_s=duration_s,
        topics=topics,
        ingest_run_id=ingest_run_id,
        language=None,
        skill_level=None,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _parse_iso_duration(iso: str) -> int | None:
    """Parse PT1H2M10S -> seconds."""
    if not iso or not iso.startswith("PT"):
        return None
    import re

    h = re.search(r"(\d+)H", iso)
    m = re.search(r"(\d+)M", iso)
    s = re.search(r"(\d+)S", iso)
    secs = 0
    if h:
        secs += int(h.group(1)) * 3600
    if m:
        secs += int(m.group(1)) * 60
    if s:
        secs += int(s.group(1))
    return secs


def read_seed_channels(path: Path) -> list[str]:
    """Read channel IDs from a seeds file. Skips blanks and comment lines."""
    if not path.exists():
        return []
    out: list[str] = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def preferred_coach_seed_channels(db: Session, api_key: str) -> list[str]:
    """Return distinct YouTube channel IDs hosting any preferred coach's CoachSample videos.

    Resolves UserProfile.preferred_coaches (which may contain ints or display_name strings)
    to coach IDs, walks each coach's CoachSample.source_url list, extracts the YouTube
    video ID, and batches videos.list to map video -> channel.
    """
    if not api_key:
        return []
    profile = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if not profile or not profile.preferred_coaches:
        return []

    coach_ids: set[int] = set()
    for token in profile.preferred_coaches or []:
        if isinstance(token, int):
            coach_ids.add(token)
        else:
            c = db.query(Coach).filter(Coach.display_name == str(token)).first()
            if c:
                coach_ids.add(c.id)
    if not coach_ids:
        return []

    sample_video_ids: list[str] = []
    samples = db.query(CoachSample).filter(CoachSample.coach_id.in_(coach_ids)).all()
    for s in samples:
        if not s.source_url:
            continue
        vid = extract_youtube_video_id(s.source_url)
        if vid:
            sample_video_ids.append(vid)
    if not sample_video_ids:
        return []

    items = fetch_video_details(api_key, list(set(sample_video_ids)))
    channels: set[str] = set()
    for it in items:
        ch = it.get("snippet", {}).get("channelId")
        if ch:
            channels.add(ch)
    return sorted(channels)


def yt_dlp_related_video_ids(video_url: str, limit: int) -> list[str]:
    """Scrape YouTube's watch-page 'related videos' sidebar via yt-dlp.

    Returns up to ``limit`` related video IDs. The official Data API endpoint
    (search.list?relatedToVideoId=) was deprecated in 2023; this is the
    pragmatic substitute. Failures (timeout, parse error, network) return [].
    """
    if limit <= 0:
        return []
    try:
        proc = subprocess.run(
            [
                "yt-dlp",
                "--dump-single-json",
                "--skip-download",
                "--no-playlist",
                video_url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except Exception as e:
        logger.debug("yt_dlp_related_subprocess_failed url=%s err=%s", video_url, type(e).__name__)
        return []
    if proc.returncode != 0 or not proc.stdout:
        return []
    try:
        meta = json.loads(proc.stdout.split("\n", 1)[0])
    except json.JSONDecodeError:
        return []
    related = meta.get("related_videos") or []
    out: list[str] = []
    for entry in related:
        if not isinstance(entry, dict):
            continue
        vid = entry.get("id") or entry.get("video_id")
        if not vid:
            url = entry.get("url") or ""
            vid = extract_youtube_video_id(url) if url else None
        if vid and vid not in out:
            out.append(vid)
        if len(out) >= limit:
            break
    return out


def _expand_related(seed_video_ids: list[str], per_seed: int, total_cap: int) -> set[str]:
    """1-hop related-video expansion. Bounded by per-seed and total caps."""
    if total_cap <= 0 or per_seed <= 0:
        return set()
    seed_set = set(seed_video_ids)
    discovered: set[str] = set()
    for vid in seed_video_ids:
        if len(discovered) >= total_cap:
            break
        url = f"https://www.youtube.com/watch?v={vid}"
        try:
            related = yt_dlp_related_video_ids(url, per_seed)
        except Exception as e:
            logger.warning("related_expansion_failed seed=%s err=%s", vid, type(e).__name__)
            continue
        for r in related:
            if r in discovered or r in seed_set:
                continue
            discovered.add(r)
            if len(discovered) >= total_cap:
                break
    return discovered


def run_ingestion(db: Session, days: int = 7) -> dict[str, int]:
    """Discover candidate videos under the new admission model.

    Sources (videos are *candidates*; admission is decided later by face match):
      1. Recent uploads of seed channels from seeds/youtube_channels.txt (marked is_trusted=True).
      2. Recent uploads of channels derived from preferred coaches' CoachSample URLs.
      3. yt-dlp related-video expansion (1 hop) from sources 1+2, bounded by
         settings.related_per_seed and settings.related_total_cap.

    No admission filter is applied here. The scheduler runs face matching on every
    new candidate and flips Video.is_admitted based on preferred-coach presence.
    """
    settings = get_settings()
    ingest_run_id = str(uuid.uuid4())
    counts = {
        "videos_upserted": 0,
        "trusted_channels": 0,
        "coach_seed_channels": 0,
        "related_discovered": 0,
    }

    if not settings.youtube_api_key:
        logger.warning("ingestion_no_youtube_api_key — discovery disabled")
        return counts

    trusted_channel_ids = read_seed_channels(Path("seeds/youtube_channels.txt"))
    coach_channel_ids = preferred_coach_seed_channels(db, settings.youtube_api_key)
    counts["trusted_channels"] = len(trusted_channel_ids)
    counts["coach_seed_channels"] = len(coach_channel_ids)

    trusted_channels: dict[str, Channel] = {}
    for cid in trusted_channel_ids:
        trusted_channels[cid] = upsert_channel(db, cid)
    candidate_channels: dict[str, Channel] = {}
    for cid in coach_channel_ids:
        if cid in trusted_channels:
            continue
        candidate_channels[cid] = upsert_channel(db, cid)

    for cid, ch in trusted_channels.items():
        if not ch.is_trusted:
            ch.is_trusted = True
    for cid, ch in candidate_channels.items():
        if ch.is_trusted:
            ch.is_trusted = False
    db.commit()

    seed_video_ids: set[str] = set()
    for cid in trusted_channel_ids:
        seed_video_ids.update(channel_uploads(settings.youtube_api_key, cid, days))
    for cid in coach_channel_ids:
        if cid in trusted_channels:
            continue
        seed_video_ids.update(channel_uploads(settings.youtube_api_key, cid, days))

    related_ids = _expand_related(
        list(seed_video_ids),
        per_seed=settings.related_per_seed,
        total_cap=settings.related_total_cap,
    )
    counts["related_discovered"] = len(related_ids)

    all_video_ids = seed_video_ids | related_ids
    details = fetch_video_details(settings.youtube_api_key, list(all_video_ids))

    for item in details:
        v = upsert_video_from_api_item(db, item, settings, ingest_run_id)
        if v is not None:
            counts["videos_upserted"] += 1

    db.commit()
    logger.info(
        "ingestion_complete run=%s upserted=%s trusted=%s coach_seeds=%s related=%s",
        ingest_run_id,
        counts["videos_upserted"],
        counts["trusted_channels"],
        counts["coach_seed_channels"],
        counts["related_discovered"],
    )
    return counts
