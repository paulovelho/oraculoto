"""seed Mega-Sena

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-24

Rules checked 2026-10-24: 6 balls from 1-60, prizes for 6, 5 and 4 hits, tickets of 6 to 20 numbers.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO games (id, slug, name, balls_drawn, ball_min, ball_max, min_winning_hits,"
            " bet_min_numbers, bet_max_numbers)"
            " VALUES (1, 'megasena', 'Mega-Sena', 6, 1, 60, 4, 6, 20)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM games WHERE slug = 'megasena'"))
