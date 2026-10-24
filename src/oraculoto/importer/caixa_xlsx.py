"""Import Caixa's results xlsx into the database (docs/database.md §7).

The whole file goes in one transaction through `save_draw()`: it's imported completely or
not at all. Contests already saved from Caixa's API are skipped unless `force`, because the
API has more than the xlsx (docs/database.md §4, rule 3).
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import Engine, insert, select

from oraculoto.db.draws import DrawData, DrawValidationError, Game, Prize, get_game, save_draw, validate_draw
from oraculoto.db.schema import draws, sync_runs
from oraculoto.importer.parse import parse_date, parse_int, parse_locations, parse_money
from oraculoto.importer.xlsx import read_rows

# Header of the special-contest reserve column, per game. Only Mega-Sena is modeled so far.
SPECIAL_RESERVE_HEADER = {"megasena": "Acumulado Sorteio Especial Mega da Virada"}


class ImportFileError(ValueError):
    """The file can't be imported; nothing was written."""


@dataclass
class ImportReport:
    file: str
    rows: int = 0
    first_contest: int | None = None
    last_contest: int | None = None
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_api: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def draws_written(self) -> int:
        return self.inserted + self.updated

    def summary(self) -> str:
        span = f"#{self.first_contest}-#{self.last_contest}" if self.rows else "no rows"
        return (
            f"{Path(self.file).name}: {self.rows} rows ({span}); inserted {self.inserted}, "
            f"updated {self.updated}, unchanged {self.unchanged}, skipped (from API) {self.skipped_api}; "
            f"{len(self.warnings)} warnings"
        )


def required_headers(game: Game) -> dict[str, str]:
    """Field key -> header text, for every column the import needs."""
    if game.slug not in SPECIAL_RESERVE_HEADER:
        raise ImportFileError(f"no xlsx column map for game {game.slug!r}")
    headers = {
        "contest": "Concurso",
        "date": "Data do Sorteio",
        "locations": "Cidade / UF",
        "rollover": f"Acumulado {game.balls_drawn} acertos",
        "total_collected": "Arrecadação Total",
        "next_estimate": "Estimativa prêmio",
        "special_reserve": SPECIAL_RESERVE_HEADER[game.slug],
        "notes": "Observação",
    }
    for i in range(1, game.balls_drawn + 1):
        headers[f"ball{i}"] = f"Bola{i}"
    for hits in game.prize_tiers:
        headers[f"winners{hits}"] = f"Ganhadores {hits} acertos"
        headers[f"prize{hits}"] = f"Rateio {hits} acertos"
    return headers


def _normalize(header: str | None) -> str:
    return " ".join((header or "").split())


def _map_header(header_row: list[str | None], game: Game, warnings: list[str]) -> dict[str, int]:
    position = {_normalize(h): i for i, h in enumerate(header_row) if _normalize(h)}
    needed = required_headers(game)
    missing = [h for h in needed.values() if h not in position]
    if missing:
        raise ImportFileError(f"missing columns: {', '.join(missing)}")
    known = set(needed.values())
    for h in position:
        if h not in known:
            warnings.append(f"unknown column {h!r} ignored")
    return {key: position[h] for key, h in needed.items()}


def _nonzero(value: Decimal) -> Decimal | None:
    """In Caixa's file, 0 means 'unknown' for these columns (docs/database.md §2)."""
    return None if value == 0 else value


def parse_row(cells: list[str | None], cols: dict[str, int], game: Game) -> tuple[DrawData, list[str]]:
    def cell(key: str) -> str | None:
        return cells[cols[key]]

    locations, warnings = parse_locations(cell("locations"))
    notes = (cell("notes") or "").strip() or None
    draw = DrawData(
        contest_number=parse_int(cell("contest")),
        draw_date=parse_date(cell("date")),
        balls=tuple(parse_int(cell(f"ball{i}")) for i in range(1, game.balls_drawn + 1)),
        prizes=tuple(
            Prize(
                hits=h,
                winners=parse_int(cell(f"winners{h}")),
                prize_per_winner=parse_money(cell(f"prize{h}")),
            )
            for h in game.prize_tiers
        ),
        rollover_amount=parse_money(cell("rollover")),
        special_accumulated=parse_money(cell("special_reserve")),
        total_collected=_nonzero(parse_money(cell("total_collected"))),
        next_estimated_prize=_nonzero(parse_money(cell("next_estimate"))),
        locations=locations,
        notes=notes,
        source="xlsx",
    )
    return draw, warnings


def parse_file(path: str | Path, game: Game) -> tuple[list[DrawData], list[str]]:
    """Read and check the whole file. Raises ImportFileError on the first bad row."""
    rows = read_rows(path)
    warnings: list[str] = []
    try:
        header = next(rows)
    except StopIteration:
        raise ImportFileError("the sheet is empty") from None
    cols = _map_header(header, game, warnings)
    width = len(header)

    result: list[DrawData] = []
    for line, cells in enumerate(rows, start=2):
        if not any((c or "").strip() for c in cells):
            continue  # trailing empty rows
        if len(cells) != width:
            raise ImportFileError(f"row {line}: {len(cells)} cells, the header has {width}")
        try:
            draw, row_warnings = parse_row(cells, cols, game)
            validate_draw(game, draw)
        except (ValueError, DrawValidationError) as e:
            raise ImportFileError(f"row {line}: {e}") from e
        warnings += [f"row {line} (#{draw.contest_number}): {w}" for w in row_warnings]

        if result:
            prev = result[-1]
            if draw.contest_number <= prev.contest_number:
                raise ImportFileError(
                    f"row {line}: contest #{draw.contest_number} after #{prev.contest_number}"
                    " (contests must be unique and increasing)"
                )
            if draw.draw_date < prev.draw_date:
                raise ImportFileError(
                    f"row {line}: #{draw.contest_number} is dated before #{prev.contest_number}"
                )
            if draw.contest_number != prev.contest_number + 1:
                warnings.append(f"contests #{prev.contest_number + 1}-#{draw.contest_number - 1} are missing")
        result.append(draw)
    return result, warnings


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def import_xlsx(
    engine: Engine, game_slug: str, path: str | Path, *, dry_run: bool = False, force: bool = False
) -> ImportReport:
    started = _now()
    report = ImportReport(file=str(path))
    with engine.connect() as conn:
        game = get_game(conn, game_slug)

    try:
        parsed, report.warnings = parse_file(path, game)
        report.rows = len(parsed)
        if parsed:
            report.first_contest, report.last_contest = parsed[0].contest_number, parsed[-1].contest_number
        if dry_run:
            return report

        with engine.begin() as conn:
            from_api = set(
                conn.execute(
                    select(draws.c.contest_number).where(draws.c.game_id == game.id, draws.c.source == "api")
                ).scalars()
            )
            for draw in parsed:
                if draw.contest_number in from_api and not force:
                    report.skipped_api += 1
                    continue
                result = save_draw(conn, game, draw)
                setattr(report, result, getattr(report, result) + 1)
            conn.execute(
                insert(sync_runs).values(
                    game_id=game.id,
                    kind="xlsx_import",
                    status="ok" if report.draws_written else "nothing_new",
                    started_at=started,
                    finished_at=_now(),
                    draws_written=report.draws_written,
                    message=report.summary(),
                )
            )
        return report
    except Exception as e:
        if not dry_run:
            with engine.begin() as conn:
                conn.execute(
                    insert(sync_runs).values(
                        game_id=game.id,
                        kind="xlsx_import",
                        status="error",
                        started_at=started,
                        finished_at=_now(),
                        message=f"{Path(path).name}: {e}"[:65000],
                    )
                )
        raise
