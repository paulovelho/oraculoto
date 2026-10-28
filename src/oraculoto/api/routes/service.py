"""GET /health: the only route without a token."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text

from oraculoto.api.deps import get_engine
from oraculoto.api.envelope import day, error, ok, utc_timestamp

router = APIRouter(tags=["service"])
log = logging.getLogger(__name__)

# A crawl older than this means the home fetcher hasn't run (docs/crawler.md §5).
STALE_AFTER = timedelta(days=2)

# Latest contest and latest successful crawl per game, in one round trip. Only crawls count:
# an xlsx import says nothing about whether the home fetcher still runs.
HEALTH_SQL = text(
    "SELECT g.slug,"
    " (SELECT MAX(d.contest_number) FROM draws d WHERE d.game_id = g.id) AS latest_contest,"
    " (SELECT d.draw_date FROM draws d WHERE d.game_id = g.id ORDER BY d.contest_number DESC LIMIT 1)"
    "   AS latest_date,"
    " (SELECT MAX(s.finished_at) FROM sync_runs s"
    "   WHERE s.game_id = g.id AND s.kind = 'crawl' AND s.status IN ('ok', 'nothing_new')) AS last_crawl"
    " FROM games g ORDER BY g.slug"
)


def _stale(last_crawl: datetime | None) -> bool:
    now = datetime.now(UTC).replace(tzinfo=None)
    return last_crawl is None or now - last_crawl > STALE_AFTER


@router.get("/health", summary="database status, latest contest and last successful crawl per game")
def health(engine: Engine = Depends(get_engine)) -> JSONResponse:
    try:
        with engine.connect() as conn:
            rows = conn.execute(HEALTH_SQL).all()
    except Exception:
        # Public endpoint: the details go to the log, never to the response.
        log.exception("health: database unreachable")
        return error(503, "db_unavailable", "database unavailable")
    return ok(
        {
            "database": "ok",
            "games": [
                {
                    "game": slug,
                    "latest_contest": latest,
                    "latest_date": day(latest_date),
                    "last_crawl": utc_timestamp(last_crawl),
                    "stale": _stale(last_crawl),
                }
                for slug, latest, latest_date, last_crawl in rows
            ],
        }
    )
