from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class UserProfile(Base):
    __tablename__ = "user_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    play_style: Mapped[str | None] = mapped_column(String(128), nullable=True)
    goals: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    weaknesses: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    preferred_languages: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    preferred_coaches: Mapped[list | None] = mapped_column(
        JSON, nullable=True, default=list
    )  # coach ids or names
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class Coach(Base):
    __tablename__ = "coach"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    samples: Mapped[list["CoachSample"]] = relationship(back_populates="coach")
    video_links: Mapped[list["VideoCoach"]] = relationship(back_populates="coach")


class CoachSample(Base):
    __tablename__ = "coach_sample"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coach.id"), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    embedding_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # FAISS row index
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    coach: Mapped["Coach"] = relationship(back_populates="samples")


class Channel(Base):
    __tablename__ = "channel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), default="youtube")  # youtube
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    subscriber_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_trusted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    videos: Mapped[list["Video"]] = relationship(back_populates="channel_rel")


class Video(Base):
    __tablename__ = "video"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), default="youtube")
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("channel.id"), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    skill_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topics: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    ingest_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_admitted: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    channel_rel: Mapped["Channel | None"] = relationship(back_populates="videos")
    transcripts: Mapped[list["Transcript"]] = relationship(back_populates="video")
    analyses: Mapped[list["VideoAnalysis"]] = relationship(back_populates="video")
    coach_links: Mapped[list["VideoCoach"]] = relationship(back_populates="video")
    recommendations: Mapped[list["Recommendation"]] = relationship(back_populates="video")

    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_video_source_external"),)


class VideoCoach(Base):
    __tablename__ = "video_coach"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"), nullable=False)
    coach_id: Mapped[int] = mapped_column(ForeignKey("coach.id"), nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    video: Mapped["Video"] = relationship(back_populates="coach_links")
    coach: Mapped["Coach"] = relationship(back_populates="video_links")


class Transcript(Base):
    __tablename__ = "transcript"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"), nullable=False)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    segments: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))

    video: Mapped["Video"] = relationship(back_populates="transcripts")


class VideoAnalysis(Base):
    __tablename__ = "video_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    drills: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    tips: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    mistakes: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    try_next_session: Mapped[str | None] = mapped_column(Text, nullable=True)
    chapters: Mapped[list | dict | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    video: Mapped["Video"] = relationship(back_populates="analyses")


class Recommendation(Base):
    __tablename__ = "recommendation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("video.id"), nullable=False)
    score: Mapped[float] = mapped_column(default=0.0)
    reasons: Mapped[list | None] = mapped_column(JSON, nullable=True, default=list)
    feed_date: Mapped[str] = mapped_column(String(10), nullable=False)  # YYYY-MM-DD

    video: Mapped["Video"] = relationship(back_populates="recommendations")

    __table_args__ = (UniqueConstraint("video_id", "feed_date", name="uq_rec_video_day"),)
