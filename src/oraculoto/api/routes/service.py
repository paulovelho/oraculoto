"""GET /health: the only route without a token."""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, text

from oraculoto.api.deps import get_engine
from oraculoto.api.envelope import day, error, ok, utc_timestamp

router = APIRouter(tags=["service"])
log = logging.getLogger(__name__)

# Latest contest and latest successful sync per game, in one round trip.
HEALTH_SQL = text(
    "SELECT g.slug,"
    " (SELECT MAX(d.contest_number) FROM draws d WHERE d.game_id = g.id) AS latest_contest,"
    " (SELECT d.draw_date FROM draws d WHERE d.game_id = g.id ORDER BY d.contest_number DESC LIMIT 1)"
    "   AS latest_date,"
    " (SELECT MAX(s.finished_at) FROM sync_runs s"
    "   WHERE s.game_id = g.id AND s.status IN ('ok', 'nothing_new')) AS last_sync"
    " FROM games g ORDER BY g.slug"
)


@router.get("/health", summary="database status, latest contest and last successful sync per game")
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
                    "last_sync": utc_timestamp(last_sync),
                }
                for slug, latest, latest_date, last_sync in rows
            ],
        }
    )
