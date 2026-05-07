"""Admission gate: only videos with a confident preferred-coach face match are admitted."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Channel, Coach, UserProfile, Video, VideoCoach
from app.ranking.score import compute_personalized_scores
from app.scheduler.jobs import _resolve_preferred_coach_ids, _video_passes_admission


def _make_video(db: Session, *, ch: Channel, ext: str, title: str = "T") -> Video:
    v = Video(
        source="youtube",
        external_id=ext,
        url=f"https://youtu.be/{ext}",
        title=title,
        channel_id=ch.id,
        is_admitted=False,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_video_passes_admission_with_match(db_session: Session) -> None:
    coach = Coach(display_name="Alice")
    db_session.add(coach)
    db_session.commit()

    profile = UserProfile(id=1, preferred_coaches=[coach.id])
    db_session.add(profile)
    ch = Channel(source="youtube", external_id="UC_seed", title="Seed", is_trusted=True)
    db_session.add(ch)
    db_session.commit()

    v = _make_video(db_session, ch=ch, ext="VID_OK_______")
    db_session.add(VideoCoach(video_id=v.id, coach_id=coach.id, confidence=0.72))
    db_session.commit()

    pref = _resolve_preferred_coach_ids(db_session)
    assert pref == {coach.id}
    assert _video_passes_admission(db_session, v, pref, min_confidence=0.65) is True


def test_video_rejected_below_threshold(db_session: Session) -> None:
    coach = Coach(display_name="Bob")
    db_session.add(coach)
    db_session.commit()
    db_session.add(UserProfile(id=1, preferred_coaches=[coach.id]))
    ch = Channel(source="youtube", external_id="UC_x", is_trusted=False)
    db_session.add(ch)
    db_session.commit()

    v = _make_video(db_session, ch=ch, ext="VID_LOW______")
    db_session.add(VideoCoach(video_id=v.id, coach_id=coach.id, confidence=0.40))
    db_session.commit()

    pref = _resolve_preferred_coach_ids(db_session)
    assert _video_passes_admission(db_session, v, pref, min_confidence=0.65) is False


def test_video_rejected_when_match_is_non_preferred_coach(db_session: Session) -> None:
    pref_coach = Coach(display_name="Pref")
    other = Coach(display_name="Other")
    db_session.add_all([pref_coach, other])
    db_session.commit()
    db_session.add(UserProfile(id=1, preferred_coaches=[pref_coach.id]))
    ch = Channel(source="youtube", external_id="UC_y", is_trusted=False)
    db_session.add(ch)
    db_session.commit()

    v = _make_video(db_session, ch=ch, ext="VID_WRONG____")
    db_session.add(VideoCoach(video_id=v.id, coach_id=other.id, confidence=0.85))
    db_session.commit()

    pref = _resolve_preferred_coach_ids(db_session)
    assert _video_passes_admission(db_session, v, pref, min_confidence=0.65) is False


def test_admission_disabled_when_no_preferred_coaches(db_session: Session) -> None:
    db_session.add(UserProfile(id=1, preferred_coaches=[]))
    coach = Coach(display_name="Z")
    db_session.add(coach)
    ch = Channel(source="youtube", external_id="UC_z", is_trusted=True)
    db_session.add(ch)
    db_session.commit()
    v = _make_video(db_session, ch=ch, ext="VID_NO_PREF__")
    db_session.add(VideoCoach(video_id=v.id, coach_id=coach.id, confidence=0.9))
    db_session.commit()

    pref = _resolve_preferred_coach_ids(db_session)
    assert pref == set()
    assert _video_passes_admission(db_session, v, pref, min_confidence=0.65) is False


def test_score_filter_skips_non_admitted(db_session: Session) -> None:
    db_session.add(UserProfile(id=1, preferred_coaches=[]))
    ch = Channel(source="youtube", external_id="UC_q", is_trusted=False)
    db_session.add(ch)
    db_session.commit()

    admitted = _make_video(db_session, ch=ch, ext="VID_ADMIT____")
    admitted.is_admitted = True
    rejected = _make_video(db_session, ch=ch, ext="VID_REJECT___")
    rejected.is_admitted = False
    db_session.commit()

    n = compute_personalized_scores(db_session, "2099-01-01")

    assert n == 1
    from app.models import Recommendation

    recs = db_session.query(Recommendation).all()
    assert {r.video_id for r in recs} == {admitted.id}
