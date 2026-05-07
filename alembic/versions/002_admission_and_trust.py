"""Add video.is_admitted and backfill admission/trust from seeds + preferred coaches.

Backfill rules:
  - channel.is_trusted = True for channels whose external_id is in seeds/youtube_channels.txt;
    others remain at their stored value (default False).
  - video.is_admitted = True iff the video has at least one video_coach row whose coach_id is
    in user_profile.preferred_coaches and confidence >= 0.55. All other videos are False
    (they will be re-evaluated on the next pipeline run).
  - All recommendation rows are deleted so the feed rebuilds cleanly under the new admission
    rule on the next scheduled / manual pipeline run.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa

from alembic import op

revision: str = "002_admission_and_trust"
down_revision: str | None = "001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SEEDS_PATH = Path("seeds/youtube_channels.txt")
LEGACY_THRESHOLD = 0.55


def _read_seed_channel_ids() -> list[str]:
    if not SEEDS_PATH.exists():
        return []
    out: list[str] = []
    for line in SEEDS_PATH.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def upgrade() -> None:
    with op.batch_alter_table("video") as batch_op:
        batch_op.add_column(
            sa.Column(
                "is_admitted",
                sa.Boolean(),
                nullable=False,
                server_default="0",
            )
        )

    bind = op.get_bind()

    seed_ids = _read_seed_channel_ids()
    if seed_ids:
        bind.execute(
            sa.text(
                "UPDATE channel SET is_trusted = 1 "
                "WHERE external_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": seed_ids},
        )

    profile_row = bind.execute(
        sa.text("SELECT preferred_coaches FROM user_profile WHERE id = 1")
    ).fetchone()
    preferred_coach_ids: list[int] = []
    if profile_row and profile_row[0]:
        raw = profile_row[0]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = []
        if isinstance(raw, list):
            for token in raw:
                if isinstance(token, int):
                    preferred_coach_ids.append(token)
                elif isinstance(token, str):
                    name_row = bind.execute(
                        sa.text(
                            "SELECT id FROM coach WHERE display_name = :name"
                        ),
                        {"name": token},
                    ).fetchone()
                    if name_row:
                        preferred_coach_ids.append(int(name_row[0]))

    if preferred_coach_ids:
        bind.execute(
            sa.text(
                "UPDATE video SET is_admitted = 1 WHERE id IN ("
                "  SELECT DISTINCT vc.video_id FROM video_coach vc "
                "  WHERE vc.coach_id IN :cids AND vc.confidence >= :thr"
                ")"
            ).bindparams(sa.bindparam("cids", expanding=True)),
            {"cids": preferred_coach_ids, "thr": LEGACY_THRESHOLD},
        )

    bind.execute(sa.text("DELETE FROM recommendation"))


def downgrade() -> None:
    with op.batch_alter_table("video") as batch_op:
        batch_op.drop_column("is_admitted")
