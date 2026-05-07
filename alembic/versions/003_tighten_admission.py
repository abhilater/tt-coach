"""Demote videos lacking a preferred-coach match at tightened threshold; wipe recommendations."""

from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "003_tighten_admission"
down_revision: str | None = "002_admission_and_trust"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ADMISSION_THRESHOLD = 0.65


def upgrade() -> None:
    bind = op.get_bind()

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
                        sa.text("SELECT id FROM coach WHERE display_name = :name"),
                        {"name": token},
                    ).fetchone()
                    if name_row:
                        preferred_coach_ids.append(int(name_row[0]))

    if preferred_coach_ids:
        bind.execute(
            sa.text(
                "UPDATE video SET is_admitted = 0 WHERE id NOT IN ("
                "SELECT DISTINCT vc.video_id FROM video_coach vc "
                "WHERE vc.coach_id IN :cids AND vc.confidence >= :thr)"
            ).bindparams(sa.bindparam("cids", expanding=True)),
            {"cids": preferred_coach_ids, "thr": ADMISSION_THRESHOLD},
        )
    else:
        bind.execute(sa.text("UPDATE video SET is_admitted = 0"))

    bind.execute(sa.text("DELETE FROM recommendation"))


def downgrade() -> None:
    pass
