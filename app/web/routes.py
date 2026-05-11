import logging
import math
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.db import get_db
from app.ingest.url_validate import coach_sample_url_dedupe_key, validate_coach_sample_url
from app.models import Coach, CoachSample, Recommendation, UserProfile, Video, VideoAnalysis
from app.ranking.feed_query import feed_recommendations_query
from app.ranking.personalize import watch_next
from app.vision.pipeline import enroll_coach_samples
from app.web.flash import ERR, OK, redirect_with_flash

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))


def humanize_views(n: int | None) -> str:
    if n is None:
        return ""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K views"
    return f"{n} views"


def format_date(dt) -> str:
    if not dt:
        return ""
    from datetime import datetime

    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        except ValueError:
            return dt
    return dt.strftime("%b %d, %Y")


templates.env.filters["humanize_views"] = humanize_views
templates.env.filters["format_date"] = format_date

router = APIRouter(tags=["web"])


def media_url(rel: str | None) -> str | None:
    if not rel:
        return None
    return f"/media/{rel.lstrip('/')}"


def coach_sample_thumb(image_path: str | None) -> str | None:
    if not image_path:
        return None
    data_dir = get_settings().data_dir.resolve()
    raw = Path(image_path)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw.resolve())
    else:
        if raw.parts and raw.parts[0] == data_dir.name:
            candidates.append((data_dir / Path(*raw.parts[1:])).resolve())
        candidates.append((data_dir / raw).resolve())
    for cand in candidates:
        try:
            rel = cand.relative_to(data_dir)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] == data_dir.name:
            rel = Path(*rel.parts[1:])
        return media_url(str(rel).replace("\\", "/"))
    return None


@router.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/feed", status_code=302)


@router.get("/feed", response_class=HTMLResponse)
def feed(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1),
    per_page: int = Query(30),
):
    page = max(1, page)
    per_page = max(1, min(30, per_page))
    base = feed_recommendations_query(db)
    total = base.count()
    total_pages = max(1, math.ceil(total / per_page)) if total else 1
    if page > total_pages and total > 0:
        page = total_pages
    offset = (page - 1) * per_page
    recs = (
        base.order_by(Recommendation.score.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    items = []
    for r in recs:
        items.append({"rec": r, "video": r.video, "thumb": media_url(r.video.thumbnail_path)})
    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context={
            "items": items,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
        },
    )


@router.get("/videos/{video_id}", response_class=HTMLResponse)
def video_detail(request: Request, video_id: int, db: Session = Depends(get_db)):
    v = db.query(Video).filter(Video.id == video_id).first()
    if not v:
        return HTMLResponse("Not found", status_code=404)
    ana = db.query(VideoAnalysis).filter(VideoAnalysis.video_id == video_id).first()
    next_videos = watch_next(db, video_id, limit=5)
    return templates.TemplateResponse(
        request=request,
        name="video_detail.html",
        context={
            "video": v,
            "analysis": ana,
            "thumb": media_url(v.thumbnail_path),
            "next_videos": next_videos,
        },
    )


@router.get("/coaches", response_class=HTMLResponse)
def coaches_page(request: Request, db: Session = Depends(get_db)):
    coaches = db.query(Coach).options(joinedload(Coach.samples)).order_by(Coach.display_name).all()
    coach_rows = []
    for c in coaches:
        samples_sorted = sorted(c.samples, key=lambda s: s.id)
        seen_keys: set[str] = set()
        sample_rows: list[dict] = []
        for s in samples_sorted:
            key = coach_sample_url_dedupe_key(s.source_url, s.id)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            sample_rows.append(
                {"url": s.source_url or "", "thumb": coach_sample_thumb(s.image_path)}
            )
        best_thumb = None
        for s in samples_sorted:
            t = coach_sample_thumb(s.image_path)
            if t:
                best_thumb = t
                break
        coach_rows.append({"coach": c, "best_thumb": best_thumb, "samples": sample_rows})
    return templates.TemplateResponse(
        request=request,
        name="coaches.html",
        context={"coach_rows": coach_rows},
    )


@router.post("/coaches")
def coaches_create(display_name: str = Form(...), db: Session = Depends(get_db)):
    name = display_name.strip()
    c = Coach(display_name=name)
    db.add(c)
    db.commit()
    db.refresh(c)
    return redirect_with_flash("/coaches", OK, f"Coach '{name}' added.")


@router.post("/coaches/{coach_id}/samples")
def coach_add_sample(
    coach_id: int,
    source_url: str = Form(...),
    db: Session = Depends(get_db),
):
    url = source_url.strip()
    if not validate_coach_sample_url(url):
        return redirect_with_flash("/coaches", ERR, "Invalid YouTube URL.")
    existing = db.query(CoachSample).filter(CoachSample.coach_id == coach_id).all()
    new_key = coach_sample_url_dedupe_key(url, 0)
    if any(coach_sample_url_dedupe_key(s.source_url, s.id) == new_key for s in existing):
        return redirect_with_flash(
            "/coaches",
            OK,
            "That YouTube video is already listed for this coach.",
        )
    s = CoachSample(coach_id=coach_id, source_url=url)
    db.add(s)
    db.commit()
    try:
        n = enroll_coach_samples(db, coach_id)
    except Exception as e:
        logger.warning(
            "coach_enroll_failed coach_id=%s err=%s",
            coach_id,
            type(e).__name__,
        )
        return redirect_with_flash(
            "/coaches",
            ERR,
            f"Sample saved but face extraction failed: {type(e).__name__}.",
        )
    return redirect_with_flash(
        "/coaches",
        OK,
        f"Sample added; {n} face embedding(s) extracted.",
    )


@router.get("/profile", response_class=HTMLResponse)
def profile_get(request: Request, db: Session = Depends(get_db)):
    p = db.query(UserProfile).filter(UserProfile.id == 1).first()
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={"profile": p},
    )


@router.post("/profile")
def profile_post(
    level: str = Form(""),
    play_style: str = Form(""),
    weaknesses: str = Form(""),
    goals: str = Form(""),
    langs: str = Form("en"),
    preferred_coaches: str = Form(""),
    db: Session = Depends(get_db),
):
    p = db.query(UserProfile).filter(UserProfile.id == 1).first()
    if not p:
        return redirect_with_flash("/profile", ERR, "Profile not found.")
    p.level = level or None
    p.play_style = play_style or None
    p.weaknesses = [x.strip() for x in weaknesses.split(",") if x.strip()]
    p.goals = [x.strip() for x in goals.split(",") if x.strip()]
    p.preferred_languages = [x.strip() for x in langs.split(",") if x.strip()]
    raw_pc = [x.strip() for x in preferred_coaches.split(",") if x.strip()]
    pref_ids: list[int | str] = []
    for token in raw_pc:
        if token.isdigit():
            pref_ids.append(int(token))
        else:
            pref_ids.append(token)
    p.preferred_coaches = pref_ids
    db.commit()
    return redirect_with_flash("/profile", OK, "Profile saved.")


@router.post("/admin/run-pipeline")
def admin_run_pipeline():
    from sqlalchemy.orm import sessionmaker

    from app.core.db import get_engine
    from app.scheduler.jobs import daily_refresh_job

    SessionLocal = sessionmaker(bind=get_engine())
    try:
        daily_refresh_job(SessionLocal)
    except Exception as e:
        logger.warning("admin_run_pipeline_failed err=%s", type(e).__name__)
        return redirect_with_flash("/feed", ERR, f"Pipeline failed: {type(e).__name__}.")
    return redirect_with_flash("/feed", OK, "Pipeline finished.")
