"""Who is calling (docs/api.md §2), as a FastAPI dependency on every route except /health.

Until step 5 (Firebase tokens checked with PyJWT) this is a dev stub: it wants an
`Authorization: Bearer <anything>` header and answers with a fake user. The app refuses to
start unless ORACULOTO_ENV=dev, so the stub can never guard a real deployment.
"""

import os
from dataclasses import dataclass

from fastapi import Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from oraculoto.api.envelope import ApiError


@dataclass(frozen=True)
class CurrentUser:
    id: int
    email: str
    role: str


DEV_USER = CurrentUser(id=0, email="dev@localhost", role="admin")


def check_auth_config() -> None:
    """Called by create_app(): no real token check exists yet, so only dev may run."""
    env = os.environ.get("ORACULOTO_ENV", "")
    if env != "dev":
        raise RuntimeError(
            f"ORACULOTO_ENV={env!r}: only the dev auth stub exists until Firebase auth (roadmap step 5); "
            "the API runs only with ORACULOTO_ENV=dev"
        )


# Declared as a security scheme so the OpenAPI docs get an "Authorize" button. auto_error=False:
# a missing or malformed header is our 401 envelope, not FastAPI's bare 403.
bearer_scheme = HTTPBearer(auto_error=False)


def require_user(credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme)) -> CurrentUser:
    if credentials is None:
        raise ApiError(401, "unauthorized", "missing or malformed Authorization: Bearer <token> header")
    return DEV_USER
