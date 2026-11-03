"""`oraculoto db-check`: is the database reachable, one layer at a time.

Each step only runs if the one before it passed, so the first FAIL is the layer that's broken:
settings (.env) → DNS → TCP port → MySQL login → the schema (Alembic revision, draws loaded).
"""

import socket
from collections.abc import Callable

from sqlalchemy import text

from oraculoto.config import db_settings

TCP_TIMEOUT = 5

HINTS = {
    "dns": "the hostname doesn't resolve: check DB_HOST (DreamHost's is mysql.<your domain>); "
    "a hostname just created in the panel can take a while to exist",
    "tcp_refused": "the host answers but nothing listens on that port: check DB_PORT "
    "(DreamHost uses 3306; .env.example's 3307 is the local Docker one), and that the MySQL "
    "hostname is attached to this database in the panel",
    "tcp_timeout": "no answer: a firewall drops it. From outside DreamHost, the database "
    "user needs this machine's IP under 'allowable hosts' in the panel",
    "login": "the server is there but refused the login: check DB_USER, DB_PASSWORD, DB_NAME, "
    "and that this user has access to that database",
}


def run() -> int:
    ok = True

    def step(name: str, fn: Callable[[], str]) -> bool:
        nonlocal ok
        if not ok:
            print(f"SKIP  {name}")
            return False
        try:
            print(f"ok    {name}: {fn()}")
            return True
        except Exception as e:  # report every failure the same way; this is a diagnostic tool
            print(f"FAIL  {name}: {type(e).__name__}: {e}")
            ok = False
            return False

    holder: dict = {}

    def settings() -> str:
        s = holder["s"] = db_settings()
        return f"{s.user}@{s.host}:{s.port}/{s.name} (password {'set' if s.password else 'EMPTY'})"

    def dns() -> str:
        s = holder["s"]
        try:
            addrs = sorted({a[4][0] for a in socket.getaddrinfo(s.host, s.port, type=socket.SOCK_STREAM)})
        except socket.gaierror:
            holder["hint"] = HINTS["dns"]
            raise
        return ", ".join(addrs)

    def tcp() -> str:
        s = holder["s"]
        try:
            with socket.create_connection((s.host, s.port), timeout=TCP_TIMEOUT):
                pass
        except ConnectionRefusedError:
            holder["hint"] = HINTS["tcp_refused"]
            raise
        except TimeoutError:
            holder["hint"] = HINTS["tcp_timeout"]
            raise
        return f"port {s.port} open"

    def login() -> str:
        from oraculoto.db import make_engine

        holder["engine"] = engine = make_engine(holder["s"])
        try:
            with engine.connect() as conn:
                version = conn.execute(text("SELECT VERSION()")).scalar_one()
        except Exception:
            holder["hint"] = HINTS["login"]
            raise
        return f"MySQL {version}"

    def schema() -> str:
        with holder["engine"].connect() as conn:
            tables = {r[0] for r in conn.execute(text("SHOW TABLES"))}
            if "alembic_version" not in tables:
                return "empty database, no migrations yet (run: alembic upgrade head)"
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if "draws" not in tables:
                return f"alembic revision {rev}, but no draws table"
            n, last = conn.execute(text("SELECT COUNT(*), MAX(contest_number) FROM draws")).one()
        return f"alembic revision {rev}; {n} draws, last contest {last}"

    step("settings", settings)
    step("dns", dns)
    step("tcp", tcp)
    step("login", login)
    step("schema", schema)

    if "engine" in holder:
        holder["engine"].dispose()
    if not ok and "hint" in holder:
        print(f"\nhint: {holder['hint']}")
    return 0 if ok else 1
