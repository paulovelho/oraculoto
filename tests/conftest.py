"""Test database: TEST_DB_NAME (default oraculoto_test), wiped and migrated once per run.

Needs the local MySQL from docker-compose.yml (`docker compose up -d`).
"""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text

from oraculoto.config import PROJECT_ROOT, db_settings, load_env
from oraculoto.db import make_engine
from oraculoto.db.draws import Game, get_game
from oraculoto.importer.caixa_xlsx import import_xlsx

# Logins in tests: the dev signing key, in a throwaway folder (set before .env is read, so they win).
os.environ["ORACULOTO_AUTH"] = "dev-key"
os.environ["ORACULOTO_VAR_DIR"] = tempfile.mkdtemp(prefix="oraculoto-test-var-")
atexit.register(shutil.rmtree, os.environ["ORACULOTO_VAR_DIR"], ignore_errors=True)

load_env()
TEST_DB = os.environ.get("TEST_DB_NAME", "oraculoto_test")
if TEST_DB == os.environ.get("DB_NAME"):
    raise RuntimeError("TEST_DB_NAME must not be the main database: the tests wipe it")

DATA_TABLES = [
    "draw_winner_locations",
    "draw_prizes",
    "draw_balls",
    "draws",
    "sync_runs",
    "ticket_numbers",
    "tickets",
    "users",
]


@pytest.fixture(scope="session")
def engine() -> Engine:
    eng = make_engine(db_settings(name=TEST_DB))
    with eng.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        conn.execute(text("DROP VIEW IF EXISTS draw_balls_flat"))
        for table, _kind in conn.execute(text("SHOW FULL TABLES WHERE Table_type = 'BASE TABLE'")):
            conn.execute(text(f"DROP TABLE `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))

    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.attributes["configure_logger"] = False
    with eng.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def clean_db(engine: Engine) -> Engine:
    """No draws, users or tickets (games stay seeded)."""
    with engine.begin() as conn:
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 0"))
        for table in DATA_TABLES:
            conn.execute(text(f"DELETE FROM `{table}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS = 1"))
    return engine


@pytest.fixture
def conn(clean_db: Engine):
    """A connection inside a transaction that is rolled back after the test."""
    with clean_db.connect() as connection:
        trans = connection.begin()
        yield connection
        trans.rollback()


@pytest.fixture
def megasena(engine: Engine) -> Game:
    with engine.connect() as c:
        return get_game(c, "megasena")


@pytest.fixture(scope="session")
def real_xlsx() -> Path:
    path = PROJECT_ROOT / "files" / "Mega-Sena.xlsx"
    if not path.exists():
        pytest.skip("files/Mega-Sena.xlsx not present")
    return path


@pytest.fixture(scope="module")
def imported(engine: Engine, real_xlsx: Path):
    """files/Mega-Sena.xlsx imported into an empty database, once per test module: (engine, report)."""
    with engine.begin() as c:
        for table in DATA_TABLES:
            c.execute(text(f"DELETE FROM `{table}`"))
    report = import_xlsx(engine, "megasena", real_xlsx)
    return engine, report
