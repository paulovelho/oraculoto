import zipfile

import pytest

from oraculoto.importer.caixa_xlsx import ImportFileError, parse_file
from oraculoto.importer.xlsx import XlsxError, read_rows
from tests.xlsx_builder import MEGASENA_HEADER, SAMPLE_ROWS, build_xlsx, megasena_row


def test_reads_rows_without_positions_despite_wrong_dimension(tmp_path):
    path = build_xlsx(tmp_path / "sample.xlsx", SAMPLE_ROWS)
    rows = list(read_rows(path))
    assert rows[0] == MEGASENA_HEADER
    # empty cells come back as None
    assert rows[1:] == [[v or None for v in row] for row in SAMPLE_ROWS]
    assert len(rows) == 4


def test_cell_positions_win_when_present(tmp_path):
    path = tmp_path / "positioned.xlsx"
    build_xlsx(path, [])
    sheet = (
        '<x:worksheet xmlns:x="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><x:sheetData>'
        '<x:row r="1"><x:c r="A1" t="inlineStr"><x:is><x:t>a</x:t></x:is></x:c>'
        '<x:c r="C1"><x:v>3</x:v></x:c></x:row></x:sheetData></x:worksheet>'
    )
    _replace_sheet(path, sheet)
    assert list(read_rows(path)) == [["a", None, "3"]]


def test_not_an_xlsx(tmp_path):
    path = tmp_path / "x.xlsx"
    path.write_text("not a zip")
    with pytest.raises(XlsxError):
        list(read_rows(path))


def test_parse_sample(tmp_path, megasena):
    draws, warnings = parse_file(build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS), megasena)
    assert warnings == []
    assert [d.contest_number for d in draws] == [1, 2, 3]
    first, second, third = draws
    assert first.balls == (4, 5, 30, 33, 41, 52)
    assert first.total_collected is None and first.next_estimated_prize is None  # 0 means unknown
    assert first.notes is None and first.locations == ()
    assert first.draw_order is None and first.is_special is None and first.source == "xlsx"
    assert [(p.hits, p.winners) for p in second.prizes] == [(6, 2), (5, 10), (4, 1000)]
    assert [loc.raw for loc in second.locations] == ["SÃO PAULO/SP", "Canal Eletrônico"]
    assert second.rollover_amount == 0  # a real zero: the jackpot was won
    assert second.notes == "Estimativa de prêmio para o próximo concurso"
    assert str(third.special_accumulated) == "12345.67"


def test_columns_in_another_order(tmp_path, megasena):
    order = list(reversed(range(len(MEGASENA_HEADER))))
    header = [MEGASENA_HEADER[i] for i in order]
    rows = [[row[i] for i in order] for row in SAMPLE_ROWS]
    draws, _ = parse_file(build_xlsx(tmp_path / "r.xlsx", rows, header=header), megasena)
    assert [d.balls for d in draws] == [
        d.balls for d in parse_file(build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS), megasena)[0]
    ]


def test_missing_header_stops(tmp_path, megasena):
    header = [h for h in MEGASENA_HEADER if h != "Rateio 5 acertos"]
    rows = [r[:12] + r[13:] for r in SAMPLE_ROWS]
    with pytest.raises(ImportFileError, match="missing columns: Rateio 5 acertos"):
        parse_file(build_xlsx(tmp_path / "m.xlsx", rows, header=header), megasena)


def test_unknown_header_is_a_warning(tmp_path, megasena):
    header = [*MEGASENA_HEADER, "Coluna Nova"]
    rows = [[*r, "x"] for r in SAMPLE_ROWS]
    _, warnings = parse_file(build_xlsx(tmp_path / "u.xlsx", rows, header=header), megasena)
    assert warnings == ["unknown column 'Coluna Nova' ignored"]


def test_wrong_cell_count_stops(tmp_path, megasena):
    rows = [SAMPLE_ROWS[0], SAMPLE_ROWS[1][:-1]]
    with pytest.raises(ImportFileError, match="row 3: 19 cells"):
        parse_file(build_xlsx(tmp_path / "w.xlsx", rows), megasena)


@pytest.mark.parametrize(
    ("balls", "message"),
    [
        (["04", "05", "30", "33", "41", "41"], "repeated balls"),
        (["04", "05", "30", "33", "41", "61"], "out of range"),
        (["00", "05", "30", "33", "41", "52"], "out of range"),
    ],
)
def test_bad_balls_stop(tmp_path, megasena, balls, message):
    rows = [megasena_row(1, "11/03/1996", balls)]
    with pytest.raises(ImportFileError, match=message):
        parse_file(build_xlsx(tmp_path / "b.xlsx", rows), megasena)


def test_contests_must_increase(tmp_path, megasena):
    rows = [SAMPLE_ROWS[1], SAMPLE_ROWS[0]]
    with pytest.raises(ImportFileError, match="unique and increasing"):
        parse_file(build_xlsx(tmp_path / "o.xlsx", rows), megasena)


def test_dates_must_not_go_backwards(tmp_path, megasena):
    rows = [SAMPLE_ROWS[0], megasena_row(2, "01/01/1990", ["01", "02", "03", "04", "05", "06"])]
    with pytest.raises(ImportFileError, match="dated before"):
        parse_file(build_xlsx(tmp_path / "d.xlsx", rows), megasena)


def test_missing_contest_is_a_warning(tmp_path, megasena):
    rows = [SAMPLE_ROWS[0], SAMPLE_ROWS[2]]
    draws, warnings = parse_file(build_xlsx(tmp_path / "g.xlsx", rows), megasena)
    assert len(draws) == 2
    assert warnings == ["contests #2-#2 are missing"]


def test_winners_without_prize_stops(tmp_path, megasena):
    rows = [megasena_row(1, "11/03/1996", ["04", "05", "30", "33", "41", "52"], five=("10", "R$0,00"))]
    with pytest.raises(ImportFileError, match="5 hits: 10 winners but prize 0.00"):
        parse_file(build_xlsx(tmp_path / "p.xlsx", rows), megasena)


def test_bad_money_stops(tmp_path, megasena):
    rows = [megasena_row(1, "11/03/1996", ["04", "05", "30", "33", "41", "52"], rollover="1.000,00")]
    with pytest.raises(ImportFileError, match="not a money value"):
        parse_file(build_xlsx(tmp_path / "x.xlsx", rows), megasena)


def _replace_sheet(path, sheet_xml: str) -> None:
    with zipfile.ZipFile(path) as zf:
        files = {n: zf.read(n) for n in zf.namelist()}
    files["xl/worksheets/sheet1.xml"] = sheet_xml.encode()
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
