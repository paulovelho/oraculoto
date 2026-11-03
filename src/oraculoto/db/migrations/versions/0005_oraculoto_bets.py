"""oraculoto_bets: oraculoto's own bet, one per contest

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-03

Decided 2026-11-03: oraculoto bets on every contest, as if it played itself. Unlike function
guesses (never stored, judged by backtests), its bet is stored before the draw and never changes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}


def upgrade() -> None:
    op.create_table(
        "oraculoto_bets",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("contest_number", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("contest_number >= 1", name=op.f("ck_oraculoto_bets_contest_number")),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name=op.f("fk_oraculoto_bets_game_id_games")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oraculoto_bets")),
        sa.UniqueConstraint(
            "game_id", "contest_number", name=op.f("uq_oraculoto_bets_game_id_contest_number")
        ),
        **TABLE_ARGS,
    )
    op.create_table(
        "oraculoto_bet_numbers",
        sa.Column("bet_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("ball", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("ball BETWEEN 0 AND 99", name=op.f("ck_oraculoto_bet_numbers_ball")),
        sa.ForeignKeyConstraint(
            ["bet_id"],
            ["oraculoto_bets.id"],
            name=op.f("fk_oraculoto_bet_numbers_bet_id_oraculoto_bets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("bet_id", "ball", name=op.f("pk_oraculoto_bet_numbers")),
        **TABLE_ARGS,
    )


def downgrade() -> None:
    op.drop_table("oraculoto_bet_numbers")
    op.drop_table("oraculoto_bets")
