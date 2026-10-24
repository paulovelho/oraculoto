"""Table definitions (SQLAlchemy Core), as designed in docs/database.md §5.

This is what the code queries. The migrations create the same tables explicitly;
tests/test_schema.py checks that the two agree.
"""

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    SmallInteger,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.mysql import BIGINT, CHAR

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

ID = BIGINT(unsigned=True)
MONEY = Numeric(15, 2)
NOW = text("CURRENT_TIMESTAMP")
TABLE_ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"}


def timestamps() -> list[Column]:
    # updated_at is set by the code on every write, not by ON UPDATE (see save_draw).
    return [
        Column("created_at", DateTime, nullable=False, server_default=NOW),
        Column("updated_at", DateTime, nullable=False, server_default=NOW),
    ]


games = Table(
    "games",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("slug", String(32), nullable=False, unique=True),
    Column("name", String(64), nullable=False),
    Column("balls_drawn", SmallInteger, nullable=False),
    Column("ball_min", SmallInteger, nullable=False),
    Column("ball_max", SmallInteger, nullable=False),
    Column("min_winning_hits", SmallInteger, nullable=False),
    Column("bet_min_numbers", SmallInteger, nullable=False),
    Column("bet_max_numbers", SmallInteger, nullable=False),
    Column("created_at", DateTime, nullable=False, server_default=NOW),
    CheckConstraint("ball_min <= ball_max", name="ball_range"),
    CheckConstraint("min_winning_hits >= 1 AND min_winning_hits <= balls_drawn", name="winning_hits"),
    CheckConstraint("balls_drawn <= bet_min_numbers AND bet_min_numbers <= bet_max_numbers", name="bet_size"),
    **TABLE_ARGS,
)

draws = Table(
    "draws",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=False),
    Column("contest_number", Integer, nullable=False),
    Column("draw_date", Date, nullable=False),
    Column("is_special", Boolean, nullable=True),
    Column("total_collected", MONEY, nullable=True),
    Column("rollover_amount", MONEY, nullable=False),
    Column("next_estimated_prize", MONEY, nullable=True),
    Column("special_accumulated", MONEY, nullable=False),
    Column("notes", Text, nullable=True),
    Column("source", String(8), nullable=False),
    Column("source_payload", JSON, nullable=True),
    *timestamps(),
    UniqueConstraint("game_id", "contest_number"),
    Index(None, "game_id", "draw_date"),
    CheckConstraint("contest_number >= 1", name="contest_number"),
    CheckConstraint(
        "(total_collected IS NULL OR total_collected >= 0) AND rollover_amount >= 0"
        " AND (next_estimated_prize IS NULL OR next_estimated_prize >= 0) AND special_accumulated >= 0",
        name="money",
    ),
    CheckConstraint("source IN ('xlsx', 'api')", name="source"),
    **TABLE_ARGS,
)

draw_balls = Table(
    "draw_balls",
    metadata,
    Column("draw_id", ID, ForeignKey("draws.id", ondelete="CASCADE"), nullable=False),
    Column("ball", SmallInteger, nullable=False),
    Column("draw_position", SmallInteger, nullable=True),
    PrimaryKeyConstraint("draw_id", "ball"),
    UniqueConstraint("draw_id", "draw_position"),
    Index(None, "ball", "draw_id"),
    CheckConstraint("ball BETWEEN 0 AND 99", name="ball"),
    CheckConstraint("draw_position >= 1", name="draw_position"),
    **TABLE_ARGS,
)

draw_prizes = Table(
    "draw_prizes",
    metadata,
    Column("draw_id", ID, ForeignKey("draws.id", ondelete="CASCADE"), nullable=False),
    Column("hits", SmallInteger, nullable=False),
    Column("winners", Integer, nullable=False),
    Column("prize_per_winner", MONEY, nullable=False),
    PrimaryKeyConstraint("draw_id", "hits"),
    CheckConstraint("winners >= 0", name="winners"),
    CheckConstraint("prize_per_winner >= 0", name="prize"),
    **TABLE_ARGS,
)

draw_winner_locations = Table(
    "draw_winner_locations",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("draw_id", ID, ForeignKey("draws.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("city", String(128), nullable=True),
    Column("uf", CHAR(2), nullable=True),
    Column("is_online", Boolean, nullable=False),
    Column("winners", Integer, nullable=True),
    Column("raw", String(255), nullable=False),
    CheckConstraint("winners IS NULL OR winners >= 0", name="winners"),
    **TABLE_ARGS,
)

users = Table(
    "users",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("email", String(255), nullable=False, unique=True),
    Column("firebase_uid", String(128), nullable=True, unique=True),
    Column("display_name", String(255), nullable=True),
    Column("photo_url", Text, nullable=True),
    Column("role", String(16), nullable=False, server_default="member"),
    Column("status", String(16), nullable=False, server_default="active"),
    Column("last_login_at", DateTime, nullable=True),
    *timestamps(),
    CheckConstraint("role IN ('admin', 'member')", name="role"),
    CheckConstraint("status IN ('active', 'blocked')", name="status"),
    **TABLE_ARGS,
)

tickets = Table(
    "tickets",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("user_id", ID, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=False),
    Column("first_contest", Integer, nullable=False),
    Column("last_contest", Integer, nullable=False),
    Column("label", String(120), nullable=True),
    Column("source", String(64), nullable=False, server_default="manual"),
    *timestamps(),
    Index(None, "game_id", "first_contest", "last_contest"),
    CheckConstraint("first_contest >= 1 AND last_contest >= first_contest", name="contests"),
    **TABLE_ARGS,
)

ticket_numbers = Table(
    "ticket_numbers",
    metadata,
    Column("ticket_id", ID, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
    Column("ball", SmallInteger, nullable=False),
    PrimaryKeyConstraint("ticket_id", "ball"),
    CheckConstraint("ball BETWEEN 0 AND 99", name="ball"),
    **TABLE_ARGS,
)

sync_runs = Table(
    "sync_runs",
    metadata,
    Column("id", ID, primary_key=True, autoincrement=True),
    Column("game_id", Integer, ForeignKey("games.id"), nullable=True),
    Column("kind", String(16), nullable=False),
    Column("status", String(16), nullable=False),
    Column("started_at", DateTime, nullable=False),
    Column("finished_at", DateTime, nullable=True),
    Column("draws_written", Integer, nullable=False, server_default="0"),
    Column("message", Text, nullable=True),
    Index(None, "game_id", "kind", "started_at"),
    CheckConstraint("kind IN ('xlsx_import', 'crawl', 'backfill')", name="kind"),
    CheckConstraint("status IN ('running', 'ok', 'nothing_new', 'error')", name="status"),
    CheckConstraint("draws_written >= 0", name="draws_written"),
    **TABLE_ARGS,
)

# The draw_balls_flat view is created by migration 0002.
