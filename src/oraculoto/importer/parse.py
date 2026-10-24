"""Parsers for Caixa's cell texts (docs/database.md §7, "Parsing rules").

Caixa's original download holds everything as text (`"04"`, `"11/03/1996"`, `"R$1.714.650,23"`).
A re-saved file can hold real numbers and Excel date serials instead, so both are accepted.
"""

import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from oraculoto.db.draws import WinnerLocation

CENTS = Decimal("0.01")
EXCEL_EPOCH = date(1899, 12, 30)

MONEY_TEXT = re.compile(r"^R\$\d{1,3}(\.\d{3})*,\d{2}$")
PLAIN_NUMBER = re.compile(r"^\d+(\.\d+)?$")
DATE_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
CITY_UF = re.compile(r"^(.+?)\s*/\s*([A-Z]{2})$")
UF = re.compile(r"^[A-Z]{2}$")
ONLINE = {"canal eletrônico", "canal eletronico"}


def parse_int(text: str | None) -> int:
    s = (text or "").strip()
    if re.fullmatch(r"\d+", s):
        return int(s)
    if re.fullmatch(r"\d+\.0+", s):  # re-saved file: 4.0
        return int(s.split(".")[0])
    raise ValueError(f"not an integer: {text!r}")


def parse_date(text: str | None) -> date:
    s = (text or "").strip()
    try:
        if m := DATE_BR.match(s):
            return date(int(m[3]), int(m[2]), int(m[1]))
        if m := DATE_ISO.match(s):
            return date(int(m[1]), int(m[2]), int(m[3]))
        if PLAIN_NUMBER.match(s):  # re-saved file: Excel serial day number
            return EXCEL_EPOCH + timedelta(days=int(Decimal(s)))
    except ValueError:
        pass
    raise ValueError(f"not a date: {text!r}")


def parse_money(text: str | None) -> Decimal:
    s = (text or "").strip()
    if MONEY_TEXT.match(s):
        return Decimal(s[2:].replace(".", "").replace(",", "."))
    if PLAIN_NUMBER.match(s):  # re-saved file: 1714650.23
        try:
            return Decimal(s).quantize(CENTS, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            pass
    raise ValueError(f"not a money value: {text!r}")


def parse_locations(text: str | None) -> tuple[tuple[WinnerLocation, ...], list[str]]:
    """Split `Cidade / UF` into locations. Returns (locations, warnings).

    Rules, first match wins: online sales; CITY/UF; bare UF; anything else is kept as raw text
    with a warning. Spelling and known data errors are kept as they are.
    """
    locations: list[WinnerLocation] = []
    warnings: list[str] = []
    for piece in (text or "").split(";"):
        raw = piece.strip()
        if not raw:
            continue
        if raw.casefold() in ONLINE:
            locations.append(WinnerLocation(raw=raw, is_online=True))
        elif m := CITY_UF.match(raw):
            locations.append(WinnerLocation(raw=raw, city=m[1].strip(), uf=m[2]))
        elif UF.match(raw):
            locations.append(WinnerLocation(raw=raw, uf=raw))
        else:
            locations.append(WinnerLocation(raw=raw))
            warnings.append(f"unrecognized location {raw!r}")
    return tuple(locations), warnings
