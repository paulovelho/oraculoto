"""`ingest`: the server half of a run (docs/crawler.md §3, §7).

Reads the fetcher's lines, parses each found contest and saves it through `save_draw()`, one
transaction per contest, so a backfill that stops halfway keeps what it saved and can resume.
It stops at the first line it can't accept: blocked, a Caixa error, a malformed line or a
response that doesn't parse. One `sync_runs` row per run, written as `running` first, so a run
that dies leaves a trace.
"""

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Engine, insert, select, update

from oraculoto.crawler.caixa import CaixaFormatError, next_draw_date, parse_draw
from oraculoto.crawler.protocol import Plan, ProtocolError, classify
from oraculoto.db.draws import DrawValidationError, Game, get_game, save_draw
from oraculoto.db.schema import draws, sync_runs

BRASILIA = ZoneInfo("America/Sao_Paulo")
STALE_AFTER = timedelta(days=2)


@dataclass
class IngestReport:
    game: str
    kind: str = "crawl"
    responses: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    not_drawn: int | None = None  # the contest that closed the gap
    cap_reached: bool = False
    problem: str | None = None

    @property
    def draws_written(self) -> int:
        return self.inserted + self.updated

    @property
    def status(self) -> str:
        if self.problem:
            return "error"
        return "ok" if self.draws_written else "nothing_new"

    def summary(self) -> str:
        parts = [
            f"{self.game} {self.kind}: {self.responses} responses; inserted {self.inserted}, "
            f"updated {self.updated}, unchanged {self.unchanged}"
        ]
        if self.not_drawn is not None:
            parts.append(f"#{self.not_drawn} not drawn yet")
        if self.cap_reached:
            parts.append("the gap fill stopped at its cap")
        if self.problem:
            parts.append(self.problem)
        return "; ".join(parts)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _response_problem(line: dict[str, Any]) -> str | None:
    checks = {
        "contest": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "http_status": lambda v: v is None or (isinstance(v, int) and not isinstance(v, bool)),
        "content_type": lambda v: v is None or isinstance(v, str),
        "body": lambda v: v is None or isinstance(v, str),
    }
    bad = [k for k, ok in checks.items() if k not in line or not ok(line[k])]
    return f"bad response line: {', '.join(bad)}" if bad else None


def _lines(raw_lines: Iterable[str]) -> Iterator[tuple[int, dict[str, Any]]]:
    for number, raw in enumerate(raw_lines, start=1):
        if not raw.strip():
            continue
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
            raise ProtocolError(f"line {number} is not JSON") from None
        if not isinstance(line, dict) or line.get("type") not in ("plan", "response", "end"):
            raise ProtocolError(f"line {number} is not a plan, response or end line")
        yield number, line


def _read_plan(lines: Iterator[tuple[int, dict[str, Any]]], game: Game) -> Plan:
    first = next(lines, None)
    if first is None:
        raise ProtocolError("no input")
    number, line = first
    if line["type"] != "plan":
        raise ProtocolError(f"line {number}: expected the plan line first")
    plan = Plan.from_dict(line.get("plan"))
    if plan.game != game.slug:
        raise ProtocolError(f"the plan is for {plan.game!r}, not {game.slug!r}")
    return plan


def _save(engine: Engine, game: Game, plan: Plan, lines, report: IngestReport) -> None:
    listed, gap = set(plan.contests), plan.gap()
    ended = False
    for number, line in lines:
        if ended:
            raise ProtocolError(f"line {number} comes after the end line")
        if line["type"] == "end":
            ended = True
            continue
        if line["type"] != "response":
            raise ProtocolError(f"line {number}: a second plan line")
        if problem := _response_problem(line):
            raise ProtocolError(f"line {number}: {problem}")
        contest, status = line["contest"], line["http_status"]
        if contest not in listed and contest not in gap:
            raise ProtocolError(f"line {number}: #{contest} is not in the plan")

        report.responses += 1
        kind = classify(status, line["content_type"], line["body"])
        if kind == "found":
            draw = parse_draw(game, line["body"], contest)
            with engine.begin() as conn:
                result = save_draw(conn, game, draw)
            setattr(report, result, getattr(report, result) + 1)
            if contest in gap and contest == gap[-1]:
                report.cap_reached = True
        elif kind == "not_drawn" and contest in gap:
            report.not_drawn = contest
        elif kind == "not_drawn":
            report.problem = f"#{contest} was planned as existing, but Caixa says it isn't drawn"
            return
        elif kind == "blocked":
            report.problem = (
                f"blocked by Caixa on #{contest} (HTTP {status}); fall back to the xlsx (docs/crawler.md §2)"
            )
            return
        else:
            detail = line.get("error") or f"HTTP {status}"
            report.problem = f"Caixa error on #{contest}: {detail} after {line.get('attempts')} attempts"
            return
    if not ended:
        report.problem = "the input stopped before the fetcher's end line (run cut off?)"


def _check_stale(engine: Engine, game: Game, today: date, report: IngestReport) -> None:
    """§5: nothing new, and the next draw Caixa announced is more than 2 days overdue."""
    with engine.connect() as conn:
        row = conn.execute(
            select(draws.c.contest_number, draws.c.source, draws.c.source_payload)
            .where(draws.c.game_id == game.id)
            .order_by(draws.c.contest_number.desc())
            .limit(1)
        ).first()
    if row is None or row.source != "api":
        return  # xlsx rows carry no announced next date
    due = next_draw_date(row.source_payload)
    if due is not None and today > due + STALE_AFTER:
        report.problem = f"stale: #{row.contest_number + 1} was due on {due.isoformat()}, nothing new since"


def ingest(
    engine: Engine, game_slug: str, raw_lines: Iterable[str], *, today: date | None = None
) -> IngestReport:
    """Raises LookupError for an unknown game (nothing written); everything else is in the report."""
    with engine.connect() as conn:
        game = get_game(conn, game_slug)
    report = IngestReport(game=game.slug)
    with engine.begin() as conn:
        run_id = conn.execute(
            insert(sync_runs).values(game_id=game.id, kind=report.kind, status="running", started_at=_now())
        ).inserted_primary_key[0]

    try:
        lines = _lines(raw_lines)
        plan = _read_plan(lines, game)
        report.kind = plan.kind
        _save(engine, game, plan, lines, report)
    except (ProtocolError, CaixaFormatError, DrawValidationError) as e:
        report.problem = str(e)
    except Exception as e:
        report.problem = f"crashed: {type(e).__name__}: {e}"
        raise
    finally:
        if not report.problem and report.kind == "crawl" and not report.draws_written:
            _check_stale(engine, game, today or datetime.now(BRASILIA).date(), report)
        with engine.begin() as conn:
            conn.execute(
                update(sync_runs)
                .where(sync_runs.c.id == run_id)
                .values(
                    kind=report.kind,
                    status=report.status,
                    finished_at=_now(),
                    draws_written=report.draws_written,
                    message=report.summary()[:65000],
                )
            )
    return report
