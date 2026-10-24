"""A small xlsx reader for Caixa's results file (docs/database.md §7).

Caixa's file breaks generic readers: rows and cells have no position attributes, and
`<dimension>` claims the sheet is one row long. So this reads the first sheet's rows in
document order and ignores `<dimension>`. If a cell does carry a position (the file was
re-saved in Excel or LibreOffice), the position wins.
"""

import posixpath
import re
import zipfile
from collections.abc import Iterator
from pathlib import Path
from xml.etree import ElementTree as ET

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

ROW, CELL, VALUE, INLINE, TEXT = (f"{{{NS}}}{t}" for t in ("row", "c", "v", "is", "t"))


class XlsxError(ValueError):
    """The file isn't a readable xlsx."""


def read_rows(path: str | Path) -> Iterator[list[str | None]]:
    """Yield each row of the first sheet as a list of cell texts (None for empty cells)."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, FileNotFoundError) as e:
        raise XlsxError(f"{path}: {e}") from e
    with zf:
        shared = _shared_strings(zf)
        with zf.open(_first_sheet(zf)) as sheet:
            for _event, el in ET.iterparse(sheet, events=("end",)):
                if el.tag == ROW:
                    yield _row(el, shared)
                    el.clear()


def _shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    # A shared string is either <si><t>…</t></si> or rich text runs <si><r><t>…</t></r>…</si>.
    return ["".join(t.text or "" for t in si.iter(TEXT)) for si in root]


def _first_sheet(zf: zipfile.ZipFile) -> str:
    try:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    except KeyError as e:
        raise XlsxError(f"not an xlsx workbook: missing {e}") from e
    sheet = workbook.find(f"{{{NS}}}sheets/{{{NS}}}sheet")
    if sheet is None:
        raise XlsxError("workbook has no sheets")
    rel_id = sheet.get(f"{{{NS_DOC_REL}}}id")
    for rel in rels.iter(f"{{{NS_PKG_REL}}}Relationship"):
        if rel.get("Id") == rel_id:
            target = rel.get("Target", "")
            return target.lstrip("/") if target.startswith("/") else posixpath.normpath(f"xl/{target}")
    raise XlsxError(f"sheet relationship {rel_id} not found")


def _column_index(ref: str) -> int:
    """'A1' -> 0, 'T7' -> 19, 'AA3' -> 26."""
    letters = re.match(r"[A-Z]+", ref)
    if letters is None:
        raise XlsxError(f"bad cell reference {ref!r}")
    index = 0
    for ch in letters.group():
        index = index * 26 + (ord(ch) - ord("A") + 1)
    return index - 1


def _row(row: ET.Element, shared: list[str]) -> list[str | None]:
    values: list[str | None] = []
    for cell in row.iter(CELL):
        ref = cell.get("r")
        col = _column_index(ref) if ref else len(values)
        while len(values) < col:
            values.append(None)
        if col < len(values):
            raise XlsxError(f"cell {ref} is out of order")
        values.append(_cell_text(cell, shared))
    return values


def _cell_text(cell: ET.Element, shared: list[str]) -> str | None:
    kind = cell.get("t")
    if kind == "inlineStr":
        inline = cell.find(INLINE)
        return "".join(t.text or "" for t in inline.iter(TEXT)) if inline is not None else None
    v = cell.find(VALUE)
    if v is None or v.text is None:
        return None
    if kind == "s":
        return shared[int(v.text)]
    # "str", "n", "b", "e" or no type: Caixa puts text in "n" cells too, so keep the raw text.
    return v.text
