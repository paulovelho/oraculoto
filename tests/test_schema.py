from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from oraculoto.db.schema import metadata


def test_migrations_match_schema_module(engine):
    """The migrations and src/oraculoto/db/schema.py describe the same tables."""
    with engine.connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(context, metadata) == []


def test_check_constraints_are_enforced(engine):
    """MySQL >= 8.0.16 enforces CHECKs; older servers silently ignore them."""
    with engine.connect() as conn:
        version = conn.execute(text("SELECT VERSION()")).scalar_one()
        major, minor, patch = (int(p) for p in version.split("-")[0].split(".")[:3])
        assert (major, minor, patch) >= (8, 0, 16), version
        enforced = conn.execute(
            text(
                "SELECT COUNT(*) FROM information_schema.CHECK_CONSTRAINTS"
                " WHERE CONSTRAINT_SCHEMA = DATABASE()"
            )
        ).scalar_one()
        assert enforced >= 15
