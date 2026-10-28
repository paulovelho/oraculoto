"""Users' tickets (docs/database.md, `tickets` and `ticket_numbers`).

Every function takes the owner's id: another user's ticket is simply not found.
Numbers and contests never change after saving; only the label does.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Connection, delete, func, insert, select, update

from oraculoto.db.schema import games, ticket_numbers, tickets


@dataclass(frozen=True)
class Ticket:
    id: int
    game: str  # slug
    numbers: tuple[int, ...]  # ascending
    first_contest: int
    last_contest: int
    label: str | None
    source: str | None
    created_at: datetime


_COLUMNS = (
    tickets.c.id,
    games.c.slug,
    tickets.c.first_contest,
    tickets.c.last_contest,
    tickets.c.label,
    tickets.c.source,
    tickets.c.created_at,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _load(conn: Connection, rows: list) -> list[Ticket]:
    ids = [r.id for r in rows]
    numbers: dict[int, list[int]] = {i: [] for i in ids}
    if ids:
        for ticket_id, ball in conn.execute(
            select(ticket_numbers.c.ticket_id, ticket_numbers.c.ball)
            .where(ticket_numbers.c.ticket_id.in_(ids))
            .order_by(ticket_numbers.c.ticket_id, ticket_numbers.c.ball)
        ):
            numbers[ticket_id].append(ball)
    return [
        Ticket(
            id=r.id,
            game=r.slug,
            numbers=tuple(numbers[r.id]),
            first_contest=r.first_contest,
            last_contest=r.last_contest,
            label=r.label,
            source=r.source,
            created_at=r.created_at,
        )
        for r in rows
    ]


def _select():
    return select(*_COLUMNS).join(games, games.c.id == tickets.c.game_id)


def create_ticket(
    conn: Connection,
    user_id: int,
    game_id: int,
    numbers: tuple[int, ...],
    first_contest: int,
    last_contest: int,
    label: str | None,
    source: str | None,
) -> int:
    """Insert the ticket and its numbers; the caller commits. Checks are the caller's (tickets.py)."""
    ticket_id = conn.execute(
        insert(tickets).values(
            user_id=user_id,
            game_id=game_id,
            first_contest=first_contest,
            last_contest=last_contest,
            label=label,
            source=source,
        )
    ).inserted_primary_key[0]
    conn.execute(insert(ticket_numbers), [{"ticket_id": ticket_id, "ball": n} for n in numbers])
    return ticket_id


def get_ticket(conn: Connection, user_id: int, ticket_id: int) -> Ticket | None:
    rows = conn.execute(_select().where(tickets.c.id == ticket_id, tickets.c.user_id == user_id)).all()
    found = _load(conn, rows)
    return found[0] if found else None


def list_tickets(
    conn: Connection, user_id: int, game_id: int | None, limit: int, offset: int
) -> tuple[list[Ticket], int]:
    """A page of the user's tickets, newest first, and how many there are."""
    where = [tickets.c.user_id == user_id]
    if game_id is not None:
        where.append(tickets.c.game_id == game_id)
    total = conn.execute(select(func.count()).select_from(tickets).where(*where)).scalar_one()
    rows = conn.execute(
        _select().where(*where).order_by(tickets.c.id.desc()).limit(limit).offset(offset)
    ).all()
    return _load(conn, rows), total


def set_label(conn: Connection, user_id: int, ticket_id: int, label: str | None) -> bool:
    """False if the user has no such ticket; the caller commits."""
    return (
        conn.execute(
            update(tickets)
            .where(tickets.c.id == ticket_id, tickets.c.user_id == user_id)
            .values(label=label, updated_at=_now())
        ).rowcount
        == 1
    )


def delete_ticket(conn: Connection, user_id: int, ticket_id: int) -> bool:
    """False if the user has no such ticket; its numbers go with it (cascade). The caller commits."""
    return (
        conn.execute(delete(tickets).where(tickets.c.id == ticket_id, tickets.c.user_id == user_id)).rowcount
        == 1
    )
