"""The caller and their tickets (docs/api.md §4, Service and Tickets, and §6)."""

from decimal import Decimal

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Connection, func, select

from oraculoto.api.auth import Login, authenticate, require_user
from oraculoto.api.deps import Paging, get_conn, paging
from oraculoto.api.envelope import ApiError, day, money, ok, page_of, utc_timestamp
from oraculoto.config import ticket_max_span
from oraculoto.db import tickets as db
from oraculoto.db.draws import Game
from oraculoto.db.draws import get_game as load_game
from oraculoto.db.results import DrawFilter, list_draws
from oraculoto.db.schema import draws
from oraculoto.db.users import User, record_session
from oraculoto.guess import REGISTRY
from oraculoto.tickets import MAX_CONTEST, TicketError, check_contests, check_numbers, score

router = APIRouter(tags=["me"])

TICKET_ID = Path(ge=1, le=2**63 - 1)


def user_json(user: User) -> dict:
    return {
        "email": user.email,
        "display_name": user.display_name,
        "photo_url": user.photo_url,
        "role": user.role,
        "last_login_at": utc_timestamp(user.last_login_at),
    }


def ticket_json(t: db.Ticket) -> dict:
    return {
        "id": t.id,
        "game": t.game,
        "numbers": list(t.numbers),
        "first_contest": t.first_contest,
        "last_contest": t.last_contest,
        "label": t.label,
        "source": t.source,
        "created_at": utc_timestamp(t.created_at),
    }


def clean_label(label: str | None) -> str | None:
    label = (label or "").strip()
    return label or None


@router.get("/me", summary="the current user; marks the start of a session")
def me(session: Login = Depends(authenticate), conn: Connection = Depends(get_conn)) -> JSONResponse:
    return ok(user_json(record_session(conn, session.user, session.claims)))


class NewTicket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    game: str = Field(max_length=32)
    numbers: list[int] = Field(max_length=100)
    first_contest: int = Field(ge=1, le=MAX_CONTEST)
    last_contest: int | None = Field(None, ge=1, le=MAX_CONTEST, description="defaults to first_contest")
    label: str | None = Field(None, max_length=120)
    source: str | None = Field(None, description="the guess function the numbers came from, as key@version")


class TicketLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str | None = Field(max_length=120, description="null or empty clears it")


def owned_ticket(conn: Connection, user: User, ticket_id: int) -> db.Ticket:
    ticket = db.get_ticket(conn, user.id, ticket_id)
    if ticket is None:
        raise ApiError(404, "not_found", f"no ticket {ticket_id}")
    return ticket


@router.get("/me/tickets", summary="the user's tickets, newest first")
def list_tickets(
    user: User = Depends(require_user),
    conn: Connection = Depends(get_conn),
    pg: Paging = Depends(paging),
    game: str | None = Query(None, max_length=32, description="only this game's tickets"),
) -> JSONResponse:
    game_id = None
    if game is not None:
        try:
            game_id = load_game(conn, game).id
        except LookupError:
            raise ApiError(404, "not_found", f"unknown game {game!r}") from None
    found, total = db.list_tickets(conn, user.id, game_id, pg.limit, pg.offset)
    return ok(page_of([ticket_json(t) for t in found], pg.page, pg.limit, total))


@router.post("/me/tickets", summary="register a ticket", status_code=201)
def create_ticket(
    body: NewTicket, user: User = Depends(require_user), conn: Connection = Depends(get_conn)
) -> JSONResponse:
    try:
        game = load_game(conn, body.game)
    except LookupError:
        raise ApiError(400, "invalid_input", f"game: unknown game {body.game!r}") from None
    if body.source is not None and body.source not in {f.ref for f in REGISTRY.values()}:
        raise ApiError(400, "invalid_input", f"source: {body.source!r} is not a guess function (key@version)")
    try:
        numbers = check_numbers(game, body.numbers)
        first, last = check_contests(body.first_contest, body.last_contest, ticket_max_span())
    except TicketError as e:
        raise ApiError(400, "invalid_input", str(e)) from None
    ticket_id = db.create_ticket(
        conn, user.id, game.id, numbers, first, last, clean_label(body.label), body.source
    )
    conn.commit()
    return ok(ticket_json(owned_ticket(conn, user, ticket_id)), status=201)


@router.get("/me/tickets/{ticket_id}", summary="one ticket")
def get_ticket(
    ticket_id: int = TICKET_ID, user: User = Depends(require_user), conn: Connection = Depends(get_conn)
) -> JSONResponse:
    return ok(ticket_json(owned_ticket(conn, user, ticket_id)))


@router.patch("/me/tickets/{ticket_id}", summary="change a ticket's label (nothing else can change)")
def label_ticket(
    body: TicketLabel,
    ticket_id: int = TICKET_ID,
    user: User = Depends(require_user),
    conn: Connection = Depends(get_conn),
) -> JSONResponse:
    if not db.set_label(conn, user.id, ticket_id, clean_label(body.label)):
        raise ApiError(404, "not_found", f"no ticket {ticket_id}")
    conn.commit()
    return ok(ticket_json(owned_ticket(conn, user, ticket_id)))


@router.delete("/me/tickets/{ticket_id}", summary="delete a ticket")
def delete_ticket(
    ticket_id: int = TICKET_ID, user: User = Depends(require_user), conn: Connection = Depends(get_conn)
) -> JSONResponse:
    if not db.delete_ticket(conn, user.id, ticket_id):
        raise ApiError(404, "not_found", f"no ticket {ticket_id}")
    conn.commit()
    return ok(None)


def _contest_json(contest: int, status: str) -> dict:
    return {
        "contest": contest,
        "status": status,
        "date": None,
        "hits": None,
        "matched": None,
        "prizes": [],
        "total": None,
        "registered_after_draw": None,
    }


@router.get("/me/tickets/{ticket_id}/results", summary="how a ticket did in each of its contests")
def ticket_results(
    ticket_id: int = TICKET_ID, user: User = Depends(require_user), conn: Connection = Depends(get_conn)
) -> JSONResponse:
    ticket = owned_ticket(conn, user, ticket_id)
    game: Game = load_game(conn, ticket.game)
    span = ticket.last_contest - ticket.first_contest + 1
    drawn, _ = list_draws(conn, game, DrawFilter(ticket.first_contest, ticket.last_contest), span, 0)
    by_contest = {d.contest_number: d for d in drawn}
    latest = conn.execute(select(func.max(draws.c.contest_number)).where(draws.c.game_id == game.id)).scalar()

    items = []
    totals = []
    for contest in range(ticket.first_contest, ticket.last_contest + 1):
        d = by_contest.get(contest)
        if d is None:
            # Below the latest contest but not stored: a gap in our data, not a future draw.
            status = "missing" if latest is not None and contest < latest else "pending"
            items.append(_contest_json(contest, status))
            continue
        s = score(game, ticket.numbers, d.balls, {p.hits: p.prize_per_winner for p in d.prizes})
        totals.append(s.total)
        item = _contest_json(contest, "drawn")
        item.update(
            date=day(d.draw_date),
            hits=s.hits,
            matched=list(s.matched),
            prizes=[
                {
                    "hits": w.hits,
                    "combinations": w.combinations,
                    "prize_per_winner": money(w.prize_per_winner),
                    "amount": money(w.amount),
                }
                for w in s.wins
            ],
            total=money(s.total),
            # Conservative: created_at is UTC and the draw is in the Brazilian evening, so a ticket
            # saved earlier on the draw day is flagged too.
            registered_after_draw=ticket.created_at.date() >= d.draw_date,
        )
        items.append(item)

    # Over the drawn contests; null if any of them has an unknown prize.
    total = None if None in totals else sum(totals, Decimal("0.00"))
    return ok({"ticket": ticket_json(ticket), "items": items, "total": money(total)})
