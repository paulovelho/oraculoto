"""Builds small xlsx files with the same defects as Caixa's download (docs/database.md §2):
no row/cell position attributes, a `<dimension>` that claims one row, data as `t="str"` /
`t="n"` text, and only the header in the shared-strings table.
"""

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

MEGASENA_HEADER = [
    "Concurso",
    "Data do Sorteio",
    "Bola1",
    "Bola2",
    "Bola3",
    "Bola4",
    "Bola5",
    "Bola6",
    "Ganhadores 6 acertos",
    "Cidade / UF",
    "Rateio 6 acertos",
    "Ganhadores 5 acertos",
    "Rateio 5 acertos",
    "Ganhadores 4 acertos",
    "Rateio 4 acertos",
    "Acumulado 6 acertos",
    "Arrecadação Total",
    "Estimativa prêmio",
    "Acumulado Sorteio Especial Mega da Virada",
    "Observação",
]


def megasena_row(
    contest: int,
    date: str,
    balls: list[str],
    *,
    jackpot: tuple[str, str] = ("0", "R$0,00"),
    locations: str = "",
    five: tuple[str, str] = ("10", "R$40.000,00"),
    four: tuple[str, str] = ("1000", "R$500,00"),
    rollover: str = "R$1.000.000,00",
    total: str = "R$50.000.000,00",
    estimate: str = "R$3.000.000,00",
    special: str = "R$0,00",
    notes: str = "",
) -> list[str]:
    return [
        str(contest),
        date,
        *balls,
        jackpot[0],
        locations,
        jackpot[1],
        five[0],
        five[1],
        four[0],
        four[1],
        rollover,
        total,
        estimate,
        special,
        notes,
    ]


SAMPLE_ROWS = [
    megasena_row(1, "11/03/1996", ["04", "05", "30", "33", "41", "52"], total="R$0,00", estimate="R$0,00"),
    megasena_row(
        2,
        "18/03/1996",
        ["09", "37", "39", "41", "43", "49"],
        jackpot=("2", "R$2.000.000,00"),
        locations="SÃO PAULO/SP; Canal Eletrônico",
        rollover="R$0,00",
        notes="Estimativa de prêmio para o próximo concurso",
    ),
    megasena_row(3, "25/03/1996", ["10", "11", "29", "30", "36", "47"], locations="", special="R$12.345,67"),
]


def _cell(value: str, numeric_looking: bool) -> str:
    # Caixa marks numbers as t="n" but still stores them as text ("04").
    kind = "n" if numeric_looking else "str"
    return f'<x:c t="{kind}"><x:v>{escape(value)}</x:v></x:c>'


def build_xlsx(path: Path, rows: list[list[str]], header: list[str] = MEGASENA_HEADER) -> Path:
    ns = 'xmlns:x="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    shared = "".join(f"<si><t>{escape(h)}</t></si>" for h in header)
    header_cells = "".join(f'<x:c r="{_col(i)}1" t="s"><x:v>{i}</x:v></x:c>' for i in range(len(header)))
    data_rows = "".join("<x:row>" + "".join(_cell(v, v.isdigit()) for v in row) + "</x:row>" for row in rows)
    sheet = (
        f'<?xml version="1.0" encoding="utf-8"?><x:worksheet {ns}><x:dimension ref="A1:T1" />'
        f'<x:sheetData><x:row r="1">{header_cells}</x:row>{data_rows}</x:sheetData></x:worksheet>'
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?><Types '
            'xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="utf-8"?><x:workbook '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            f'{ns}><x:sheets><x:sheet name="MEGA SENA" sheetId="1" r:id="rId1" /></x:sheets></x:workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?><Relationships '
            'xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
        ),
        "xl/sharedStrings.xml": (
            '<?xml version="1.0" encoding="UTF-8"?><sst '
            f'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{shared}</sst>'
        ),
        "xl/worksheets/sheet1.xml": sheet,
    }
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return path


def _col(i: int) -> str:
    name = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        name = chr(ord("A") + rem) + name
    return name
