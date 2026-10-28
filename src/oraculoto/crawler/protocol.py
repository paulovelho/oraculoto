"""What the home fetcher and the server send each other (docs/crawler.md §7).

Standard library only: the home machine imports this without database settings.

`crawl-plan` prints one `Plan` as JSON. `fetch` writes JSON lines: a `plan` line (the plan it
followed), one `response` line per contest requested, and an `end` line. `ingest` reads them; a
missing `end` line means the run was cut off.
"""

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

CAIXA_API = "https://servicebus2.caixa.gov.br/portaldeloterias/api"
GAP_CAP = 50
KINDS = ("crawl", "backfill")

Classification = Literal["found", "not_drawn", "blocked", "error"]

# "Not drawn yet" is an HTTP 500 wrapping a .NET exception, with the real 404 inside a string
# that is itself JSON, so the quotes may arrive escaped: \"StatusCode\":404
NOT_DRAWN = re.compile(r'\\*"StatusCode\\*"\s*:\s*404\b')


class ProtocolError(ValueError):
    """A plan or a line that doesn't follow this module's format."""


@dataclass(frozen=True)
class Plan:
    game: str
    kind: str  # sync_runs.kind: crawl or backfill
    contests: list[int] = field(default_factory=list)  # fetched first, in order; each must exist
    gap_start: int | None = None  # then gap_start, gap_start + 1, ... until "not drawn yet"
    cap: int = GAP_CAP  # most contests the gap fill may request

    def __post_init__(self):
        if not isinstance(self.game, str) or not self.game:
            raise ProtocolError(f"bad game {self.game!r}")
        if self.kind not in KINDS:
            raise ProtocolError(f"bad kind {self.kind!r}")
        if not isinstance(self.contests, list) or not all(_is_contest(n) for n in self.contests):
            raise ProtocolError(f"bad contest list {self.contests!r}")
        if self.gap_start is not None and not _is_contest(self.gap_start):
            raise ProtocolError(f"bad gap start {self.gap_start!r}")
        if not _is_int(self.cap) or self.cap < 0:
            raise ProtocolError(f"bad cap {self.cap!r}")

    def gap(self) -> range:
        return range(0) if self.gap_start is None else range(self.gap_start, self.gap_start + self.cap)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_dict(cls, data: Any) -> "Plan":
        if not isinstance(data, dict) or set(data) - set(cls.__dataclass_fields__):
            raise ProtocolError(f"not a plan: {data!r}")
        try:
            return cls(**data)
        except TypeError as e:
            raise ProtocolError(f"not a plan: {e}") from None

    @classmethod
    def from_json(cls, text: str) -> "Plan":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ProtocolError(f"plan is not JSON: {e}") from None
        return cls.from_dict(data)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_contest(value: Any) -> bool:
    return _is_int(value) and value >= 1


def contest_url(game: str, contest: int) -> str:
    """The game slug is Caixa's API path (docs/database.md, `games.slug`)."""
    return f"{CAIXA_API}/{game}/{contest}"


def classify(http_status: int | None, content_type: str | None, body: str | None) -> Classification:
    """docs/crawler.md §3, "Reading the response". `http_status` is None when no response arrived."""
    if http_status is None:
        return "error"
    text = body or ""
    is_html = "html" in (content_type or "").lower() or text.lstrip().startswith("<")
    if http_status in (404, 500) and NOT_DRAWN.search(text):
        return "not_drawn"
    if http_status in (403, 429) or (http_status == 200 and is_html):
        return "blocked"  # Azion's "Forbidden" page, a rate limit or a bot challenge
    if http_status == 200:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return "error"
        return "found" if isinstance(payload, dict) and "numero" in payload else "error"
    return "error"


def is_retryable(http_status: int | None, classification: Classification) -> bool:
    """Timeouts, connection errors and server errors that aren't "not drawn yet" (§5)."""
    return classification == "error" and (http_status is None or http_status >= 500)


def plan_line(plan: Plan) -> dict[str, Any]:
    return {"type": "plan", "plan": asdict(plan)}


def response_line(
    contest: int,
    http_status: int | None,
    content_type: str | None,
    body: str | None,
    *,
    attempts: int = 1,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "response",
        "contest": contest,
        "http_status": http_status,
        "content_type": content_type,
        "classification": classify(http_status, content_type, body),
        "attempts": attempts,
        "error": error,
        "body": body,
    }


def end_line(requests: int) -> dict[str, Any]:
    return {"type": "end", "requests": requests}
