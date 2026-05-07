from __future__ import annotations

import json
import logging
import subprocess
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingest.dedupe import dedupe_key
from app.ingest.topics import infer_topics_from_text
from app.ingest.url_validate import extract_youtube_video_id
from app.models import Channel, Video

logger = logging.getLogger(__name__)


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


def search_videos(api_key: str, query: str, days: int, max_results: int = 25) -> list[str]:
    yt = yt_service(api_key)
    ids: list[str] = []
    req = yt.search().list(
        part="id",
        q=query,
        type="video",
        maxResults=max_results,
        order="date",
        publishedAfter=_published_after(days),
    )
    while req is not None and len(ids) < max_results:
        resp = req.execute()
        for it in resp.get("items", []):
            vid = it.get("id", {}).get("videoId")
            if vid:
                ids.append(vid)
        req = yt.search().list_next(req, resp)
        if len(ids) >= max_results:
            break
    return ids[:max_results]


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
        "--convert-subs",
        "srt",
        "-o",
        "/tmp/ttcoach_%(id)s.%(ext)s",
        video_url,
    ]
    try:
        subprocess.run(tmp_cmd, capture_output=True, text=True, timeout=180)
        vid = extract_youtube_video_id(video_url)
        if not vid:
            return None, None
        p = Path(f"/tmp/ttcoach_{vid}.en.srt")
        if not p.exists():
            return None, None
        text = p.read_text(errors="ignore")
        return text, None
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


def run_ingestion(db: Session, days: int = 7) -> dict[str, int]:
    settings = get_settings()
    ingest_run_id = str(uuid.uuid4())
    counts = {"videos_upserted": 0, "queries": 0, "channels": 0}

    queries_path = Path("seeds/search_queries.txt")
    channels_path = Path("seeds/youtube_channels.txt")

    video_ids: set[str] = set()

    if settings.youtube_api_key:
        if queries_path.exists():
            for line in queries_path.read_text().splitlines():
                q = line.strip()
                if not q or q.startswith("#"):
                    continue
                counts["queries"] += 1
                video_ids.update(search_videos(settings.youtube_api_key, q, days))

        if channels_path.exists():
            for line in channels_path.read_text().splitlines():
                cid = line.strip()
                if not cid or cid.startswith("#"):
                    continue
                counts["channels"] += 1
                video_ids.update(channel_uploads(settings.youtube_api_key, cid, days))

    details = fetch_video_details(settings.youtube_api_key, list(video_ids)) if settings.youtube_api_key else []

    # Fallback: allow manual video IDs file
    manual = Path("seeds/manual_video_ids.txt")
    if manual.exists():
        extra = [x.strip() for x in manual.read_text().splitlines() if len(x.strip()) == 11]
        if extra and settings.youtube_api_key:
            details.extend(fetch_video_details(settings.youtube_api_key, extra))

    for item in details:
        upsert_video_from_api_item(db, item, settings, ingest_run_id)
        counts["videos_upserted"] += 1

    db.commit()
    logger.info(
        "ingestion_complete run=%s upserted=%s queries=%s channels=%s",
        ingest_run_id,
        counts["videos_upserted"],
        counts["queries"],
        counts["channels"],
    )
    return counts
