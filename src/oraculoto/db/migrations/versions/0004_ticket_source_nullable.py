"""tickets.source: nullable, no default

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-28

Decided 2026-10-28: source names the guess function a ticket's numbers came from (key@version),
checked against the registry; NULL when the user didn't say. 'manual' is gone.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "tickets",
        "source",
        existing_type=sa.String(length=64),
        nullable=True,
        server_default=None,
        existing_server_default="manual",
    )
    # No ticket existed before this migration (the API couldn't create them); just in case.
    op.execute(sa.text("UPDATE tickets SET source = NULL WHERE source = 'manual'"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE tickets SET source = 'manual' WHERE source IS NULL"))
    op.alter_column(
        "tickets", "source", existing_type=sa.String(length=64), nullable=False, server_default="manual"
    )
