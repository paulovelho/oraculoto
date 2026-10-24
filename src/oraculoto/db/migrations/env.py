"""Alembic environment. Connects with the project's settings (.env), or with a connection
handed over in `config.attributes["connection"]` (the test suite does that)."""

from logging.config import fileConfig

from alembic import context

from oraculoto.db import make_engine
from oraculoto.db.schema import metadata

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def run(connection) -> None:
    context.configure(connection=connection, target_metadata=metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("offline mode is not supported; run against a database")

connection = config.attributes.get("connection")
if connection is not None:
    run(connection)
else:
    engine = make_engine()
    with engine.connect() as conn:
        run(conn)
    engine.dispose()
