"""Tokens for tests: signed by a throwaway dev key (conftest points ORACULOTO_VAR_DIR at a temp dir),
with the same code `oraculoto dev-token` uses. Never real Firebase."""

import os
from pathlib import Path

from sqlalchemy import Engine, text

from oraculoto.auth.keys import DevKey

MEMBER = "member@test.example"


def dev_key() -> DevKey:
    return DevKey(Path(os.environ["ORACULOTO_VAR_DIR"]) / "dev-key.pem")


def bearer(email: str = MEMBER, **claims) -> dict[str, str]:
    return {"Authorization": f"Bearer {dev_key().sign(email, **claims)}"}


def invite(engine: Engine, email: str = MEMBER, status: str = "active") -> int:
    """Put the email on the invite list (if it isn't yet); its users.id."""
    with engine.begin() as conn:
        conn.execute(
            text("INSERT IGNORE INTO users (email, status) VALUES (:email, :status)"),
            {"email": email, "status": status},
        )
        return conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).scalar_one()
