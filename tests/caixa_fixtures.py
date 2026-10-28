"""Caixa responses recorded on 2026-10-28 (docs/crawler.md §8), and helpers to bend them.

- #3072: normal, no jackpot winner
- #2955: Mega da Virada 2025 (special), jackpot winners including online sales
- #1: the oldest, with an empty `dataProximoConcurso`
- #9999: "not drawn yet", an HTTP 500 wrapping the real 404
"""

import json
from pathlib import Path

from oraculoto.crawler.protocol import end_line, plan_line, response_line

FIXTURES = Path(__file__).parent / "fixtures" / "caixa"
JSON = "application/json"
FORBIDDEN_HTML = "<html><head><title>Forbidden</title></head><body><h1>Forbidden</h1></body></html>"


def body(contest: int) -> str:
    return (FIXTURES / f"megasena-{contest}.body").read_text()


def payload(contest: int) -> dict:
    return json.loads(body(contest))


def not_drawn_body() -> str:
    return body(9999)


def fake_body(contest: int, **changes) -> str:
    """#3072's response renumbered as `contest`, with `changes` applied: for contests not recorded."""
    data = payload(3072) | {"numero": contest} | changes
    return json.dumps(data)


def lines(plan, *responses) -> list[str]:
    """Protocol lines for `ingest`: the plan, (contest, status, body) responses and the end line."""
    out = [plan_line(plan)]
    for contest, status, text in responses:
        content_type = "text/html" if text and text.startswith("<") else JSON
        out.append(response_line(contest, status, content_type, text))
    out.append(end_line(len(responses)))
    return [json.dumps(line) for line in out]
