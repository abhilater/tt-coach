from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.ingest.url_validate import validate_coach_sample_url
from app.models import Coach, CoachSample, Recommendation, UserProfile, Video, VideoAnalysis
from app.ranking.personalize import watch_next
from app.vision.pipeline import enroll_coach_samples

templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))

router = APIRouter(tags=["web"])


def media_url(rel: str | None) -> str | None:
    if not rel:
        return None
    return f"/media/{rel.lstrip('/')}"


@router.get("/", response_class=HTMLResponse)
def home():
    return RedirectResponse("/feed", status_code=302)


@router.get("/feed", response_class=HTMLResponse)
def feed(request: Request, db: Session = Depends(get_db)):
    recs = db.query(Recommendation).order_by(Recommendation.score.desc()).limit(50).all()
    items = []
    for r in recs:
        items.append({"rec": r, "video": r.video, "thumb": media_url(r.video.thumbnail_path)})
    return templates.TemplateResponse(
        request=request,
        name="feed.html",
        context={"items": items},
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
    coaches = db.query(Coach).order_by(Coach.display_name).all()
    return templates.TemplateResponse(
        request=request,
        name="coaches.html",
        context={"coaches": coaches},
    )


@router.post("/coaches")
def coaches_create(display_name: str = Form(...), db: Session = Depends(get_db)):
    c = Coach(display_name=display_name.strip())
    db.add(c)
    db.commit()
    db.refresh(c)
    return RedirectResponse("/coaches", status_code=303)


@router.post("/coaches/{coach_id}/samples")
def coach_add_sample(
    coach_id: int,
    source_url: str = Form(...),
    db: Session = Depends(get_db),
):
    url = source_url.strip()
    if not validate_coach_sample_url(url):
        return HTMLResponse("Invalid YouTube URL", status_code=400)
    s = CoachSample(coach_id=coach_id, source_url=url)
    db.add(s)
    db.commit()
    enroll_coach_samples(db, coach_id)
    return RedirectResponse("/coaches", status_code=303)


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
        return RedirectResponse("/profile", status_code=303)
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
    return RedirectResponse("/profile", status_code=303)


@router.post("/admin/run-pipeline")
def admin_run_pipeline():
    from sqlalchemy.orm import sessionmaker

    from app.core.db import get_engine
    from app.scheduler.jobs import daily_refresh_job

    SessionLocal = sessionmaker(bind=get_engine())
    daily_refresh_job(SessionLocal)
    return RedirectResponse("/feed", status_code=303)
