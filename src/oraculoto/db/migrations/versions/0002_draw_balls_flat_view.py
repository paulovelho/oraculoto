"""draw_balls_flat view

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-24

One row per ball with its contest: the shape guess functions and ad-hoc analysis want.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE VIEW draw_balls_flat AS
        SELECT g.slug AS game, d.contest_number, d.draw_date, b.ball, b.draw_position
        FROM draw_balls b
        JOIN draws d ON d.id = b.draw_id
        JOIN games g ON g.id = d.game_id
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW draw_balls_flat")
