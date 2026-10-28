"""The home-machine half of a run: request the plan's contests from Caixa (docs/crawler.md §3, §5).

No database here. It follows a `Plan` and yields the protocol lines; `ingest` on the server
decides what they mean. Needs the `fetch` extra (`uv sync --extra fetch`).
"""

import time
from collections.abc import Callable, Iterator
from importlib.metadata import version
from typing import Any

import httpx2

from oraculoto.crawler.protocol import Plan, contest_url, end_line, is_retryable, plan_line, response_line

CONTACT = "https://oraculoto.platypusweb.com.br"
USER_AGENT = f"oraculoto-crawler/{version('oraculoto')} (+{CONTACT})"
TIMEOUT = 10.0
MIN_INTERVAL = 1.0  # seconds between requests, retries included
RETRY_DELAYS = (2.0, 4.0, 8.0)  # after the first try: at most 4 requests per contest


def make_client() -> httpx2.Client:
    """HTTPS with certificate checks on, no redirects, one cookie jar per run, and an honest name."""
    return httpx2.Client(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, follow_redirects=False)


class Fetcher:
    def __init__(
        self,
        client: httpx2.Client,
        *,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] | None = None,
        min_interval: float = MIN_INTERVAL,
        retry_delays: tuple[float, ...] = RETRY_DELAYS,
    ):
        self.client = client
        self.sleep = sleep or time.sleep
        self.clock = clock or time.monotonic
        self.min_interval = min_interval
        self.retry_delays = retry_delays
        self._last_request: float | None = None

    def _wait_turn(self) -> None:
        if self._last_request is not None:
            wait = self._last_request + self.min_interval - self.clock()
            if wait > 0:
                self.sleep(wait)
        self._last_request = self.clock()

    def get(self, game: str, contest: int) -> dict[str, Any]:
        """One contest, retried on timeouts, connection errors and real server errors."""
        attempts = 0
        while True:
            attempts += 1
            self._wait_turn()
            try:
                r = self.client.get(contest_url(game, contest))
                line = response_line(
                    contest, r.status_code, r.headers.get("content-type"), r.text, attempts=attempts
                )
            except httpx2.TransportError as e:
                line = response_line(
                    contest, None, None, None, attempts=attempts, error=f"{type(e).__name__}: {e}"
                )
            if attempts > len(self.retry_delays) or not is_retryable(
                line["http_status"], line["classification"]
            ):
                return line
            self.sleep(self.retry_delays[attempts - 1])

    def run(self, plan: Plan) -> Iterator[dict[str, Any]]:
        """The plan's contests in order, then the gap fill until "not drawn yet" or the cap.

        Stops at the first response that isn't `found`, except the one that closes the gap.
        """
        yield plan_line(plan)
        requests = 0
        for contest in plan.contests:
            line = self.get(plan.game, contest)
            requests += 1
            yield line
            if line["classification"] != "found":
                yield end_line(requests)
                return
        for contest in plan.gap():
            line = self.get(plan.game, contest)
            requests += 1
            yield line
            if line["classification"] != "found":
                break
        yield end_line(requests)
