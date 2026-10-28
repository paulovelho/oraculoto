"""Who is calling (docs/api.md §2), as a FastAPI dependency on every route except /health.

ORACULOTO_AUTH picks who signs the tokens:
- `firebase` (the default): Google, for the project in FIREBASE_PROJECT_ID.
- `dev-key`: a local key (`oraculoto dev-token <email>` signs with it). Everything after the
  signature is the real code path. Only runs with ORACULOTO_ENV=dev.
"""

import logging
import os
from dataclasses import dataclass

from fastapi import Depends, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import Connection

from oraculoto.api.deps import get_conn
from oraculoto.api.envelope import ApiError
from oraculoto.auth.keys import DEV_PROJECT_ID, DevKey, GoogleKeys, KeysUnavailable
from oraculoto.auth.tokens import Claims, KeySource, TokenError, TokenRefused, verify_token
from oraculoto.config import var_dir
from oraculoto.db.users import LoginRefused, User, login

log = logging.getLogger(__name__)

AUTH_MODES = ("firebase", "dev-key")


@dataclass(frozen=True)
class AuthConfig:
    mode: str
    project_id: str


def auth_config() -> AuthConfig:
    """Read on every request (cheap); create_app() calls it first so a bad setup fails at startup."""
    mode = os.environ.get("ORACULOTO_AUTH") or "firebase"
    if mode not in AUTH_MODES:
        raise RuntimeError(f"ORACULOTO_AUTH={mode!r}: use one of {', '.join(AUTH_MODES)}")
    if mode == "dev-key":
        env = os.environ.get("ORACULOTO_ENV", "")
        if env != "dev":
            raise RuntimeError(
                f"ORACULOTO_AUTH=dev-key with ORACULOTO_ENV={env!r}: the dev signing key only runs "
                "with ORACULOTO_ENV=dev"
            )
        return AuthConfig(mode, DEV_PROJECT_ID)
    project_id = os.environ.get("FIREBASE_PROJECT_ID", "")
    if not project_id:
        raise RuntimeError("ORACULOTO_AUTH=firebase needs FIREBASE_PROJECT_ID (see .env.example)")
    return AuthConfig(mode, project_id)


def key_source(config: AuthConfig) -> KeySource:
    if config.mode == "dev-key":
        return DevKey(var_dir() / "dev-key.pem")
    return GoogleKeys(var_dir() / "cache" / "google-jwks.json")


# Declared as a security scheme so the OpenAPI docs get an "Authorize" button. auto_error=False:
# a missing or malformed header is our 401 envelope, not FastAPI's bare 403.
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Login:
    user: User
    claims: Claims


def authenticate(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    conn: Connection = Depends(get_conn),
) -> Login:
    if credentials is None:
        raise ApiError(401, "unauthorized", "missing or malformed Authorization: Bearer <token> header")
    config = auth_config()
    try:
        claims = verify_token(credentials.credentials, config.project_id, key_source(config))
    except TokenError as e:
        raise ApiError(401, "unauthorized", str(e)) from None
    except TokenRefused as e:
        raise ApiError(403, "not_invited", str(e)) from None
    except KeysUnavailable:
        log.exception("auth: no signing keys")
        raise ApiError(503, "auth_unavailable", "can't check tokens right now") from None
    try:
        return Login(login(conn, claims), claims)
    except LoginRefused as e:
        raise ApiError(403, e.code, e.message) from None


def require_user(session: Login = Depends(authenticate)) -> User:
    return session.user
