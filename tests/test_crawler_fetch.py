"""The home fetcher's run logic (docs/crawler.md §3, §5) against a fake Caixa. Never hits the network."""

import httpx2
import pytest

from oraculoto.crawler.fetch import USER_AGENT, Fetcher
from oraculoto.crawler.protocol import Plan
from tests.caixa_fixtures import FORBIDDEN_HTML, JSON, fake_body, not_drawn_body


class FakeCaixa:
    """Serves contests up to `latest`; `script` overrides answers per contest, consumed in order."""

    def __init__(self, latest: int, script: dict[int, list] | None = None):
        self.latest = latest
        self.script = script or {}
        self.requests: list[httpx2.Request] = []

    def contests(self) -> list[int]:
        return [int(r.url.path.rsplit("/", 1)[1]) for r in self.requests]

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        contest = int(request.url.path.rsplit("/", 1)[1])
        if self.script.get(contest):
            answer = self.script[contest].pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        if contest <= self.latest:
            return httpx2.Response(200, text=fake_body(contest), headers={"content-type": JSON})
        return httpx2.Response(500, text=not_drawn_body(), headers={"content-type": JSON})


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def __call__(self) -> float:
        return self.now


def run(caixa: FakeCaixa, plan: Plan, clock: Clock | None = None) -> list[dict]:
    clock = clock or Clock()
    client = httpx2.Client(transport=httpx2.MockTransport(caixa), headers={"User-Agent": USER_AGENT})
    return list(Fetcher(client, sleep=clock.sleep, clock=clock).run(plan))


def crawl(top: int) -> Plan:
    return Plan(
        game="megasena", kind="crawl", contests=list(range(max(1, top - 2), top + 1)), gap_start=top + 1
    )


def responses(lines: list[dict]) -> list[tuple[int, str]]:
    return [(x["contest"], x["classification"]) for x in lines if x["type"] == "response"]


def test_refresh_then_gap_fill_until_not_drawn():
    caixa = FakeCaixa(latest=3073)
    lines = run(caixa, crawl(3071))
    assert caixa.contests() == [3069, 3070, 3071, 3072, 3073, 3074]
    assert responses(lines)[-3:] == [(3072, "found"), (3073, "found"), (3074, "not_drawn")]
    assert lines[0] == {"type": "plan", "plan": crawl(3071).__dict__ | {"contests": [3069, 3070, 3071]}}
    assert lines[-1] == {"type": "end", "requests": 6}
    assert all(r.headers["user-agent"].startswith("oraculoto-crawler/") for r in caixa.requests)
    assert all(str(r.url).startswith("https://servicebus2.caixa.gov.br/") for r in caixa.requests)


def test_nothing_new_is_one_request_past_the_refresh():
    caixa = FakeCaixa(latest=3071)
    assert responses(run(caixa, crawl(3071)))[-1] == (3072, "not_drawn")
    assert len(caixa.requests) == 4


def test_empty_database_starts_at_contest_one():
    caixa = FakeCaixa(latest=2)
    run(caixa, Plan(game="megasena", kind="crawl", contests=[], gap_start=1))
    assert caixa.contests() == [1, 2, 3]


def test_blocked_stops_everything():
    blocked = httpx2.Response(403, text=FORBIDDEN_HTML, headers={"content-type": "text/html"})
    caixa = FakeCaixa(latest=3073, script={3070: [blocked]})
    lines = run(caixa, crawl(3071))
    assert caixa.contests() == [3069, 3070]  # no retry, no gap fill
    assert responses(lines) == [(3069, "found"), (3070, "blocked")]
    assert lines[-1] == {"type": "end", "requests": 2}


def test_the_gap_fill_stops_at_the_cap():
    caixa = FakeCaixa(latest=10_000)
    plan = Plan(game="megasena", kind="crawl", contests=[], gap_start=3072, cap=5)
    lines = run(caixa, plan)
    assert caixa.contests() == [3072, 3073, 3074, 3075, 3076]
    assert lines[-1] == {"type": "end", "requests": 5}


def test_server_errors_are_retried_with_backoff():
    down = httpx2.Response(503, text="<html>unavailable</html>", headers={"content-type": "text/html"})
    caixa = FakeCaixa(latest=3072, script={3072: [down, httpx2.ConnectTimeout("slow")]})
    clock = Clock()
    lines = run(caixa, Plan(game="megasena", kind="crawl", contests=[3072]), clock)
    assert caixa.contests() == [3072, 3072, 3072]
    assert responses(lines) == [(3072, "found")]
    assert lines[1]["attempts"] == 3
    assert clock.sleeps == [2.0, 4.0]


def test_giving_up_after_four_attempts():
    caixa = FakeCaixa(latest=0, script={1: [httpx2.ConnectError("refused")] * 10})
    clock = Clock()
    lines = run(caixa, Plan(game="megasena", kind="crawl", contests=[1], gap_start=2), clock)
    assert len(caixa.requests) == 4
    assert clock.sleeps == [2.0, 4.0, 8.0]
    [line] = [x for x in lines if x["type"] == "response"]
    assert (line["classification"], line["http_status"], line["attempts"]) == ("error", None, 4)
    assert line["error"] == "ConnectError: refused"


def test_not_drawn_is_not_retried():
    caixa = FakeCaixa(latest=0)
    run(caixa, Plan(game="megasena", kind="crawl", contests=[], gap_start=1))
    assert len(caixa.requests) == 1


def test_at_most_one_request_per_second():
    clock = Clock()
    run(FakeCaixa(latest=3073), crawl(3071), clock)
    # every request comes one second after the previous one: 5 waits for 6 requests
    assert clock.sleeps == [pytest.approx(1.0)] * 5


def test_backfill_follows_the_list_and_never_gap_fills():
    caixa = FakeCaixa(latest=3072)
    lines = run(caixa, Plan(game="megasena", kind="backfill", contests=[2, 5, 9], cap=0))
    assert caixa.contests() == [2, 5, 9]
    assert lines[-1] == {"type": "end", "requests": 3}
