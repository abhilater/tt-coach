"""Initial schema."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=64), nullable=True),
        sa.Column("play_style", sa.String(length=128), nullable=True),
        sa.Column("goals", sa.JSON(), nullable=True),
        sa.Column("weaknesses", sa.JSON(), nullable=True),
        sa.Column("preferred_languages", sa.JSON(), nullable=True),
        sa.Column("preferred_coaches", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "coach",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "channel",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("external_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("subscriber_count", sa.Integer(), nullable=True),
        sa.Column("is_trusted", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "coach_sample",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("coach_id", sa.Integer(), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("image_path", sa.String(length=1024), nullable=True),
        sa.Column("embedding_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["coach_id"], ["coach.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "video",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("thumbnail_path", sa.String(length=1024), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("published_at", sa.DateTime(), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("skill_level", sa.String(length=64), nullable=True),
        sa.Column("topics", sa.JSON(), nullable=True),
        sa.Column("ingest_run_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["channel.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "external_id", name="uq_video_source_external"),
    )
    op.create_table(
        "video_coach",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("coach_id", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["coach_id"], ["coach.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["video.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "transcript",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("segments", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["video.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "video_analysis",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("drills", sa.JSON(), nullable=True),
        sa.Column("tips", sa.JSON(), nullable=True),
        sa.Column("mistakes", sa.JSON(), nullable=True),
        sa.Column("try_next_session", sa.Text(), nullable=True),
        sa.Column("chapters", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("llm_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["video.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "recommendation",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reasons", sa.JSON(), nullable=True),
        sa.Column("feed_date", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["video.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id", "feed_date", name="uq_rec_video_day"),
    )


def downgrade() -> None:
    op.drop_table("recommendation")
    op.drop_table("video_analysis")
    op.drop_table("transcript")
    op.drop_table("video_coach")
    op.drop_table("video")
    op.drop_table("coach_sample")
    op.drop_table("channel")
    op.drop_table("coach")
    op.drop_table("user_profile")
