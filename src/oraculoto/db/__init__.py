"""Database access: engine, schema and the single write path for draws."""

from sqlalchemy import URL, Engine, create_engine, event

from oraculoto.config import DbSettings, db_settings

# Strict mode on every connection, whatever the server's default (DreamHost's isn't ours to set).
SQL_MODE = ",".join(
    [
        "ONLY_FULL_GROUP_BY",
        "STRICT_TRANS_TABLES",
        "STRICT_ALL_TABLES",
        "NO_ZERO_IN_DATE",
        "NO_ZERO_DATE",
        "ERROR_FOR_DIVISION_BY_ZERO",
        "NO_ENGINE_SUBSTITUTION",
    ]
)


def make_url(settings: DbSettings) -> URL:
    return URL.create(
        "mysql+pymysql",
        username=settings.user,
        password=settings.password,
        host=settings.host,
        port=settings.port,
        database=settings.name,
        query={"charset": "utf8mb4"},
    )


def make_engine(settings: DbSettings | None = None) -> Engine:
    engine = create_engine(make_url(settings or db_settings()))

    @event.listens_for(engine, "connect")
    def _session_setup(dbapi_conn, _record):
        with dbapi_conn.cursor() as cur:
            # Timestamps are stored in UTC; CURRENT_TIMESTAMP follows the session time zone.
            cur.execute("SET time_zone = '+00:00'")
            cur.execute(f"SET SESSION sql_mode = '{SQL_MODE}'")

    return engine
