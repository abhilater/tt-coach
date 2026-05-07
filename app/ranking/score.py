from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.ingest.dedupe import dedupe_key
from app.models import Channel, Coach, Recommendation, UserProfile, Video, VideoAnalysis, VideoCoach


def recency_decay(published_at) -> float:
    if published_at is None:
        return 0.3
    now = datetime.now(tz=UTC)
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=UTC)
    age_days = max(0.0, (now - published_at).total_seconds() / 86400)
    return float(max(0.05, 1.0 - min(age_days / 30.0, 0.95)))


def compute_personalized_scores(db: Session, feed_date: str) -> int:
    profile = db.query(UserProfile).filter(UserProfile.id == 1).first()
    preferred_coach_ids: set[int] = set()
    weakness_topics: set[str] = set()
    langs = {"en"}

    if profile:
        langs = set(profile.preferred_languages or ["en"])
        for pc in profile.preferred_coaches or []:
            if isinstance(pc, int):
                preferred_coach_ids.add(pc)
            else:
                c = db.query(Coach).filter(Coach.display_name == str(pc)).first()
                if c:
                    preferred_coach_ids.add(c.id)
        for w in profile.weaknesses or []:
            weakness_topics.add(str(w).lower().replace(" ", "_"))

    videos = db.query(Video).filter(Video.is_admitted.is_(True)).all()
    admitted_ids = {v.id for v in videos}

    stale_q = db.query(Recommendation)
    if admitted_ids:
        stale_q = stale_q.filter(~Recommendation.video_id.in_(admitted_ids))
    stale = stale_q.all()
    for r in stale:
        db.delete(r)
    if stale:
        db.commit()

    analyses = {a.video_id: a for a in db.query(VideoAnalysis).all()}
    channels = {c.id: c for c in db.query(Channel).all()}

    scored: list[tuple[float, str, int, list[str]]] = []

    for v in videos:
        ana = analyses.get(v.id)
        coach_links = db.query(VideoCoach).filter(VideoCoach.video_id == v.id).all()

        pref_coach = 1.0 if any(lc.coach_id in preferred_coach_ids for lc in coach_links) else 0.0

        tags = list(set((ana.tags if ana else []) or []) | set(v.topics or []))
        weakness_match = 0.0
        if weakness_topics:
            overlap = weakness_topics & set(t.lower().replace(" ", "_") for t in tags)
            weakness_match = min(1.0, len(overlap) * 0.35)
        elif tags:
            weakness_match = 0.15

        ch_trust = 0.0
        if v.channel_id and v.channel_id in channels:
            ch_trust = 1.0 if channels[v.channel_id].is_trusted else 0.3

        qual = float(ana.quality_score) if ana and ana.quality_score is not None else 0.5

        lang_bonus = 0.2 if (v.language in langs or not v.language) else 0.0

        score = (
            0.30 * recency_decay(v.published_at)
            + 0.25 * pref_coach
            + 0.20 * weakness_match
            + 0.15 * ch_trust
            + 0.10 * qual
            + lang_bonus * 0.05
        )

        reasons: list[str] = []
        if pref_coach:
            reasons.append("preferred_coach")
        if weakness_match > 0.2:
            reasons.append("matches_weakness")
        if recency_decay(v.published_at) > 0.7:
            reasons.append("recent_upload")

        primary_coach = coach_links[0].coach_id if coach_links else None
        pk = dedupe_key(v.title, v.duration_s, str(primary_coach) if primary_coach else None)
        scored.append((score, pk, v.id, reasons))

    scored.sort(key=lambda x: -x[0])
    picked: dict[str, tuple[float, int, list[str]]] = {}
    for score, pk, vid, reasons in scored:
        if pk in picked:
            continue
        picked[pk] = (score, vid, reasons)

    count = 0
    for _pk, (score, vid, reasons) in sorted(picked.items(), key=lambda x: -x[1][0]):
        existing = (
            db.query(Recommendation)
            .filter(Recommendation.video_id == vid, Recommendation.feed_date == feed_date)
            .first()
        )
        if existing:
            existing.score = score
            existing.reasons = reasons
        else:
            db.add(Recommendation(video_id=vid, score=score, reasons=reasons, feed_date=feed_date))
        count += 1

    db.commit()
    return count


def today_str() -> str:
    return datetime.now(tz=UTC).date().isoformat()
