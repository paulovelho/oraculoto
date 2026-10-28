"""The invite list (docs/database.md, `users`) and the login rules of docs/api.md §2.

Logging in never creates a user: only `invite()` does, from the command line.
"""

import logging
import re
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from sqlalchemy import Connection, insert, select, update

from oraculoto.auth.tokens import Claims
from oraculoto.db.schema import users

log = logging.getLogger(__name__)

ROLES = ("admin", "member")
EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


@dataclass(frozen=True)
class User:
    id: int
    email: str
    firebase_uid: str | None
    display_name: str | None
    photo_url: str | None
    role: str
    status: str
    last_login_at: datetime | None
    created_at: datetime


class LoginRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _one(conn: Connection, *where) -> User | None:
    row = conn.execute(select(*(users.c[f] for f in User.__dataclass_fields__)).where(*where)).first()
    return None if row is None else User(*row)


def normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.fullmatch(email) or len(email) > 255:
        raise ValueError(f"not an email address: {email!r}")
    return email


def login(conn: Connection, claims: Claims) -> User:
    """The users row behind a verified token, linking it on the first login; commits a link."""
    user = _one(conn, users.c.firebase_uid == claims.uid)
    if user is None:
        user = _one(conn, users.c.email == claims.email)
        if user is None:
            raise LoginRefused("not_invited", "this account is not invited")
        if user.firebase_uid is not None:
            log.warning("login refused: %s is linked to another Firebase uid", claims.email)
            raise LoginRefused("not_invited", "this account is not invited")
        if user.status == "blocked":
            raise LoginRefused("blocked", "this account is blocked")
        now = _now()
        linked = conn.execute(
            update(users)
            .where(users.c.id == user.id, users.c.firebase_uid.is_(None))
            .values(
                firebase_uid=claims.uid, display_name=claims.name, photo_url=claims.picture, updated_at=now
            )
        ).rowcount
        if linked != 1:  # another first login of the same email got there first
            raise LoginRefused("not_invited", "this account is not invited")
        conn.commit()
        user = replace(user, firebase_uid=claims.uid, display_name=claims.name, photo_url=claims.picture)
    if user.status == "blocked":
        raise LoginRefused("blocked", "this account is blocked")
    return user


def record_session(conn: Connection, user: User, claims: Claims) -> User:
    """GET /me: a session starts. Stamps last_login_at and refreshes the name and photo."""
    now = _now()
    conn.execute(
        update(users)
        .where(users.c.id == user.id)
        .values(last_login_at=now, display_name=claims.name, photo_url=claims.picture, updated_at=now)
    )
    conn.commit()
    return replace(user, last_login_at=now, display_name=claims.name, photo_url=claims.picture)


# ---------------------------------------------------------------- command line (docs/api.md §7)


def invite(conn: Connection, email: str, role: str = "member") -> User:
    email = normalize_email(email)
    if role not in ROLES:
        raise ValueError(f"unknown role {role!r}")
    if _one(conn, users.c.email == email) is not None:
        raise ValueError(f"{email} is already invited")
    conn.execute(insert(users).values(email=email, role=role))
    return _one(conn, users.c.email == email)


def set_status(conn: Connection, email: str, status: str) -> User:
    email = normalize_email(email)
    user = _one(conn, users.c.email == email)
    if user is None:
        raise LookupError(f"{email} is not invited")
    conn.execute(update(users).where(users.c.id == user.id).values(status=status, updated_at=_now()))
    return replace(user, status=status)


def list_users(conn: Connection) -> list[User]:
    rows = conn.execute(select(*(users.c[f] for f in User.__dataclass_fields__)).order_by(users.c.email))
    return [User(*r) for r in rows]
