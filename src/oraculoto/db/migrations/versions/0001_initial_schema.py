"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-24

MySQL DDL is not transactional: keep one schema change per migration (docs/database.md §9).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "games",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slug", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("balls_drawn", sa.SmallInteger(), nullable=False),
        sa.Column("ball_min", sa.SmallInteger(), nullable=False),
        sa.Column("ball_max", sa.SmallInteger(), nullable=False),
        sa.Column("min_winning_hits", sa.SmallInteger(), nullable=False),
        sa.Column("bet_min_numbers", sa.SmallInteger(), nullable=False),
        sa.Column("bet_max_numbers", sa.SmallInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("ball_min <= ball_max", name=op.f("ck_games_ball_range")),
        sa.CheckConstraint(
            "balls_drawn <= bet_min_numbers AND bet_min_numbers <= bet_max_numbers",
            name=op.f("ck_games_bet_size"),
        ),
        sa.CheckConstraint(
            "min_winning_hits >= 1 AND min_winning_hits <= balls_drawn", name=op.f("ck_games_winning_hits")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_games")),
        sa.UniqueConstraint("slug", name=op.f("uq_games_slug")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "users",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("firebase_uid", sa.String(length=128), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=16), server_default="member", nullable=False),
        sa.Column("status", sa.String(length=16), server_default="active", nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'member')", name=op.f("ck_users_role")),
        sa.CheckConstraint("status IN ('active', 'blocked')", name=op.f("ck_users_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("firebase_uid", name=op.f("uq_users_firebase_uid")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "draws",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("contest_number", sa.Integer(), nullable=False),
        sa.Column("draw_date", sa.Date(), nullable=False),
        sa.Column("is_special", sa.Boolean(), nullable=True),
        sa.Column("total_collected", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("rollover_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("next_estimated_prize", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("special_accumulated", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=8), nullable=False),
        sa.Column("source_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("source IN ('xlsx', 'api')", name=op.f("ck_draws_source")),
        sa.CheckConstraint(
            "(total_collected IS NULL OR total_collected >= 0) AND rollover_amount >= 0 AND (next_estimated_prize IS NULL OR next_estimated_prize >= 0) AND special_accumulated >= 0",
            name=op.f("ck_draws_money"),
        ),
        sa.CheckConstraint("contest_number >= 1", name=op.f("ck_draws_contest_number")),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name=op.f("fk_draws_game_id_games")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draws")),
        sa.UniqueConstraint("game_id", "contest_number", name=op.f("uq_draws_game_id_contest_number")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_draws_game_id_draw_date"), "draws", ["game_id", "draw_date"], unique=False)
    op.create_table(
        "sync_runs",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("draws_written", sa.Integer(), server_default="0", nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.CheckConstraint("kind IN ('xlsx_import', 'crawl', 'backfill')", name=op.f("ck_sync_runs_kind")),
        sa.CheckConstraint(
            "status IN ('running', 'ok', 'nothing_new', 'error')", name=op.f("ck_sync_runs_status")
        ),
        sa.CheckConstraint("draws_written >= 0", name=op.f("ck_sync_runs_draws_written")),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name=op.f("fk_sync_runs_game_id_games")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_sync_runs_game_id_kind_started_at"),
        "sync_runs",
        ["game_id", "kind", "started_at"],
        unique=False,
    )
    op.create_table(
        "tickets",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("user_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("game_id", sa.Integer(), nullable=False),
        sa.Column("first_contest", sa.Integer(), nullable=False),
        sa.Column("last_contest", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=True),
        sa.Column("source", sa.String(length=64), server_default="manual", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint(
            "first_contest >= 1 AND last_contest >= first_contest", name=op.f("ck_tickets_contests")
        ),
        sa.ForeignKeyConstraint(["game_id"], ["games.id"], name=op.f("fk_tickets_game_id_games")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_tickets_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tickets")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_tickets_game_id_first_contest_last_contest"),
        "tickets",
        ["game_id", "first_contest", "last_contest"],
        unique=False,
    )
    op.create_index(op.f("ix_tickets_user_id"), "tickets", ["user_id"], unique=False)
    op.create_table(
        "draw_balls",
        sa.Column("draw_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("ball", sa.SmallInteger(), nullable=False),
        sa.Column("draw_position", sa.SmallInteger(), nullable=True),
        sa.CheckConstraint("ball BETWEEN 0 AND 99", name=op.f("ck_draw_balls_ball")),
        sa.CheckConstraint("draw_position >= 1", name=op.f("ck_draw_balls_draw_position")),
        sa.ForeignKeyConstraint(
            ["draw_id"], ["draws.id"], name=op.f("fk_draw_balls_draw_id_draws"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("draw_id", "ball", name=op.f("pk_draw_balls")),
        sa.UniqueConstraint("draw_id", "draw_position", name=op.f("uq_draw_balls_draw_id_draw_position")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(op.f("ix_draw_balls_ball_draw_id"), "draw_balls", ["ball", "draw_id"], unique=False)
    op.create_table(
        "draw_prizes",
        sa.Column("draw_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("hits", sa.SmallInteger(), nullable=False),
        sa.Column("winners", sa.Integer(), nullable=False),
        sa.Column("prize_per_winner", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.CheckConstraint("prize_per_winner >= 0", name=op.f("ck_draw_prizes_prize")),
        sa.CheckConstraint("winners >= 0", name=op.f("ck_draw_prizes_winners")),
        sa.ForeignKeyConstraint(
            ["draw_id"], ["draws.id"], name=op.f("fk_draw_prizes_draw_id_draws"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("draw_id", "hits", name=op.f("pk_draw_prizes")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_table(
        "draw_winner_locations",
        sa.Column("id", mysql.BIGINT(unsigned=True), autoincrement=True, nullable=False),
        sa.Column("draw_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("uf", mysql.CHAR(length=2), nullable=True),
        sa.Column("is_online", sa.Boolean(), nullable=False),
        sa.Column("winners", sa.Integer(), nullable=True),
        sa.Column("raw", sa.String(length=255), nullable=False),
        sa.CheckConstraint("winners IS NULL OR winners >= 0", name=op.f("ck_draw_winner_locations_winners")),
        sa.ForeignKeyConstraint(
            ["draw_id"], ["draws.id"], name=op.f("fk_draw_winner_locations_draw_id_draws"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_draw_winner_locations")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )
    op.create_index(
        op.f("ix_draw_winner_locations_draw_id"), "draw_winner_locations", ["draw_id"], unique=False
    )
    op.create_table(
        "ticket_numbers",
        sa.Column("ticket_id", mysql.BIGINT(unsigned=True), nullable=False),
        sa.Column("ball", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("ball BETWEEN 0 AND 99", name=op.f("ck_ticket_numbers_ball")),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_numbers_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_id", "ball", name=op.f("pk_ticket_numbers")),
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_ai_ci",
        mysql_engine="InnoDB",
    )


def downgrade() -> None:
    op.drop_table("ticket_numbers")
    op.drop_index(op.f("ix_draw_winner_locations_draw_id"), table_name="draw_winner_locations")
    op.drop_table("draw_winner_locations")
    op.drop_table("draw_prizes")
    op.drop_index(op.f("ix_draw_balls_ball_draw_id"), table_name="draw_balls")
    op.drop_table("draw_balls")
    op.drop_index(op.f("ix_tickets_user_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_game_id_first_contest_last_contest"), table_name="tickets")
    op.drop_table("tickets")
    op.drop_index(op.f("ix_sync_runs_game_id_kind_started_at"), table_name="sync_runs")
    op.drop_table("sync_runs")
    op.drop_index(op.f("ix_draws_game_id_draw_date"), table_name="draws")
    op.drop_table("draws")
    op.drop_table("users")
    op.drop_table("games")
