"""Caixa's JSON response → `DrawData` (docs/crawler.md §4).

Anything unexpected raises `CaixaFormatError`: the API has no docs and no versioning, so a
changed shape must stop the run rather than be guessed at. Game rules are checked afterwards by
`save_draw()`, the same as for the xlsx.
"""

import json
import math
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from oraculoto.db.draws import DrawData, Game, Prize, WinnerLocation
from oraculoto.importer.parse import CENTS, DATE_BR, ONLINE

# tipoJogo per game slug: a response for another game must never be saved
GAME_TYPES = {"megasena": "MEGA_SENA"}
BALL = re.compile(r"^\d{1,2}$")


class CaixaFormatError(ValueError):
    """The response isn't shaped like docs/crawler.md §4 expects; nothing is saved."""


def strip_nul(value: Any) -> Any:
    """Remove NUL characters everywhere (`nomeTimeCoracaoMesSorte` is made of them)."""
    if isinstance(value, str):
        return value.replace("\x00", "")
    if isinstance(value, list):
        return [strip_nul(v) for v in value]
    if isinstance(value, dict):
        return {strip_nul(k): strip_nul(v) for k, v in value.items()}
    return value


def _int(value: Any, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CaixaFormatError(f"{name} is not an integer: {value!r}")
    return value


def _str(value: Any, name: str) -> str:
    if not isinstance(value, str):
        raise CaixaFormatError(f"{name} is not a string: {value!r}")
    return value.strip()


def _money(value: Any, name: str) -> Decimal:
    """The API sends floats; round once, here, and never keep the float."""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise CaixaFormatError(f"{name} is not a number: {value!r}")
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


def _nonzero(value: Decimal) -> Decimal | None:
    """0 means 'unknown' for these fields, the same as in the xlsx (docs/database.md §2)."""
    return None if value == 0 else value


def _date(value: Any, name: str) -> date:
    m = DATE_BR.match(_str(value, name))
    if not m:
        raise CaixaFormatError(f"{name} is not dd/mm/yyyy: {value!r}")
    try:
        return date(int(m[3]), int(m[2]), int(m[1]))
    except ValueError:
        raise CaixaFormatError(f"{name} is not a date: {value!r}") from None


def _balls(value: Any, name: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not all(isinstance(b, str) and BALL.match(b) for b in value):
        raise CaixaFormatError(f'{name} is not a list of numbers like "07": {value!r}')
    return tuple(int(b) for b in value)


def _prizes(value: Any, game: Game) -> tuple[Prize, ...]:
    if not isinstance(value, list):
        raise CaixaFormatError(f"listaRateioPremio is not a list: {value!r}")
    prizes = []
    for item in value:
        if not isinstance(item, dict):
            raise CaixaFormatError(f"listaRateioPremio item is not an object: {item!r}")
        hits = game.balls_drawn - _int(item.get("faixa"), "faixa") + 1
        label = _str(item.get("descricaoFaixa"), "descricaoFaixa")
        if label != f"{hits} acertos":
            raise CaixaFormatError(f"faixa {item.get('faixa')} should be '{hits} acertos', got {label!r}")
        prizes.append(
            Prize(
                hits=hits,
                winners=_int(item.get("numeroDeGanhadores"), "numeroDeGanhadores"),
                prize_per_winner=_money(item.get("valorPremio"), "valorPremio"),
            )
        )
    return tuple(prizes)


def _locations(value: Any) -> tuple[WinnerLocation, ...]:
    """Jackpot winners per city. `raw` is spelled like the xlsx's: `CITY/UF`, or the online channel."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise CaixaFormatError(f"listaMunicipioUFGanhadores is not a list: {value!r}")
    locations = []
    for item in value:
        if not isinstance(item, dict):
            raise CaixaFormatError(f"listaMunicipioUFGanhadores item is not an object: {item!r}")
        if item.get("posicao", 1) != 1:
            continue  # only jackpot winners are listed so far; anything else stays in source_payload
        city = _str(item.get("municipio"), "municipio")
        uf = _str(item.get("uf"), "uf")
        winners = _int(item.get("ganhadores"), "ganhadores")
        if uf == "--" or city.casefold() in ONLINE:
            locations.append(WinnerLocation(raw=city or uf, is_online=True, winners=winners))
        else:
            raw = f"{city}/{uf}" if city else uf
            locations.append(WinnerLocation(raw=raw, city=city or None, uf=uf or None, winners=winners))
    return tuple(locations)


def parse_draw(game: Game, body: str, contest: int) -> DrawData:
    """One `found` response body → DrawData with source 'api'. `contest` is the number requested."""
    try:
        payload = strip_nul(json.loads(body))
    except json.JSONDecodeError as e:
        raise CaixaFormatError(f"not JSON: {e}") from None
    if not isinstance(payload, dict):
        raise CaixaFormatError("not a JSON object")

    def get(name: str) -> Any:
        if name not in payload:
            raise CaixaFormatError(f"missing field {name}")
        return payload[name]

    numero = _int(get("numero"), "numero")
    if numero != contest:
        raise CaixaFormatError(f"asked for #{contest}, got #{numero}")
    expected_type = GAME_TYPES.get(game.slug)
    if expected_type is None:
        raise CaixaFormatError(f"no Caixa mapping for game {game.slug!r}")
    if get("tipoJogo") != expected_type:
        raise CaixaFormatError(f"tipoJogo is {payload['tipoJogo']!r}, expected {expected_type!r}")

    special = get("indicadorConcursoEspecial")
    if special not in (1, 2) or isinstance(special, bool):
        raise CaixaFormatError(f"indicadorConcursoEspecial is {special!r}, expected 1 or 2")

    try:
        return DrawData(
            contest_number=numero,
            draw_date=_date(get("dataApuracao"), "dataApuracao"),
            balls=_balls(get("listaDezenas"), "listaDezenas"),
            draw_order=_balls(get("dezenasSorteadasOrdemSorteio"), "dezenasSorteadasOrdemSorteio"),
            prizes=_prizes(get("listaRateioPremio"), game),
            locations=_locations(get("listaMunicipioUFGanhadores")),
            is_special=special == 2,
            total_collected=_nonzero(_money(get("valorArrecadado"), "valorArrecadado")),
            rollover_amount=_money(get("valorAcumuladoProximoConcurso"), "valorAcumuladoProximoConcurso"),
            next_estimated_prize=_nonzero(
                _money(get("valorEstimadoProximoConcurso"), "valorEstimadoProximoConcurso")
            ),
            special_accumulated=_money(
                get("valorAcumuladoConcursoEspecial"), "valorAcumuladoConcursoEspecial"
            ),
            notes=_str(get("observacao") or "", "observacao") or None,
            source="api",
            source_payload=payload,
        )
    except CaixaFormatError as e:
        raise CaixaFormatError(f"#{contest}: {e}") from None


def next_draw_date(payload: dict[str, Any] | None) -> date | None:
    """`dataProximoConcurso` of a stored response, for the staleness alarm (§5). Empty on old contests."""
    try:
        return _date((payload or {}).get("dataProximoConcurso"), "dataProximoConcurso")
    except CaixaFormatError:
        return None
