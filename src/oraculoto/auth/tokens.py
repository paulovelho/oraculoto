"""The checks of docs/api.md §2 on a Firebase ID token, whichever key source signed it.

A TokenError is a bad token (401); a TokenRefused is a good token we won't accept (403):
an unverified email, or a sign-in provider other than Google.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import jwt

ISSUER_PREFIX = "https://securetoken.google.com/"
LEEWAY_SECONDS = 60
MAX_UID_LENGTH = 128  # Firebase's limit, and users.firebase_uid's width


class TokenError(Exception):
    """Missing, malformed, badly signed, expired or meant for another project."""


class TokenRefused(Exception):
    """Valid, but not a login this app accepts."""


class KeySource(Protocol):
    def key(self, kid: str) -> Any | None:
        """The public key for this key id (anything jwt.decode takes), or None if unknown."""


@dataclass(frozen=True)
class Claims:
    uid: str
    email: str  # lowercase
    name: str | None
    picture: str | None


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def verify_token(token: str, project_id: str, keys: KeySource) -> Claims:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise TokenError("malformed token") from None
    kid = header.get("kid")
    if header.get("alg") != "RS256" or not isinstance(kid, str):
        raise TokenError("token not signed the way Firebase signs")
    key = keys.key(kid)
    if key is None:
        raise TokenError("token signed by an unknown key")
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=project_id,
            issuer=ISSUER_PREFIX + project_id,
            leeway=LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise TokenError("token expired") from None
    except jwt.PyJWTError as e:
        raise TokenError(f"invalid token: {e}") from None

    uid = claims["sub"]
    if not isinstance(uid, str) or not uid or len(uid) > MAX_UID_LENGTH:
        raise TokenError("invalid token: bad sub")
    # Checked after the signature, so these answers only go to holders of a real token.
    if claims.get("email_verified") is not True:
        raise TokenRefused("the account's email is not verified")
    firebase = claims.get("firebase")
    provider = firebase.get("sign_in_provider") if isinstance(firebase, dict) else None
    if provider != "google.com":
        raise TokenRefused("only Google sign-in is accepted")
    email = claims.get("email")
    if not isinstance(email, str) or "@" not in email:
        raise TokenRefused("the token has no email")
    return Claims(
        uid=uid,
        email=email.strip().lower(),
        name=_optional_str(claims.get("name")),
        picture=_optional_str(claims.get("picture")),
    )
