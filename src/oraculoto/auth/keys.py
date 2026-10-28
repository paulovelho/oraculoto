"""Who signs the tokens: Google (production) or a local dev key (ORACULOTO_AUTH=dev-key).

GoogleKeys caches Google's public keys on disk for as long as their Cache-Control max-age says:
under CGI nothing survives in memory between requests. DevKey is an RSA key in the var folder
that signs tokens shaped exactly like Firebase's, so local work and tests run the real checks
without a Firebase project or a Google login.
"""

import hashlib
import json
import logging
import os
import re
import tempfile
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

import jwt

from oraculoto.auth.tokens import ISSUER_PREFIX

log = logging.getLogger(__name__)

GOOGLE_JWKS_URL = "https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com"
FETCH_TIMEOUT_SECONDS = 5
DEFAULT_MAX_AGE = 3600
# An unknown kid triggers a refetch (Google rotates keys), but at most this often, so a stream of
# garbage tokens can't turn every request into a call to Google.
REFETCH_AFTER_SECONDS = 60

DEV_PROJECT_ID = "oraculoto-dev"
DEV_KID = "oraculoto-dev-key"


class KeysUnavailable(Exception):
    """Google's keys couldn't be fetched and there is no usable copy on disk."""


def fetch_google_jwks() -> tuple[dict, int]:
    """Google's JWKS and how many seconds it may be cached."""
    with urllib.request.urlopen(GOOGLE_JWKS_URL, timeout=FETCH_TIMEOUT_SECONDS) as response:
        body = json.load(response)
        match = re.search(r"max-age=(\d+)", response.headers.get("Cache-Control", ""))
    return body, int(match.group(1)) if match else DEFAULT_MAX_AGE


def _write_atomically(path: Path, text: str) -> None:
    # Two CGI processes may refresh at once: each writes its own temp file and renames it over.
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as f:
        f.write(text)
    os.replace(f.name, path)


class GoogleKeys:
    def __init__(
        self,
        cache_path: Path,
        fetch: Callable[[], tuple[dict, int]] | None = None,
        clock: Callable[[], float] = time.time,
    ):
        self.cache_path = cache_path
        self.fetch = fetch or fetch_google_jwks
        self.clock = clock

    def _read_cache(self) -> dict | None:
        try:
            cached = json.loads(self.cache_path.read_text())
            return cached if isinstance(cached.get("jwks"), dict) else None
        except (OSError, ValueError, AttributeError):
            return None

    def _refresh(self) -> dict:
        jwks, max_age = self.fetch()
        now = self.clock()
        cached = {"fetched_at": now, "expires_at": now + max_age, "jwks": jwks}
        _write_atomically(self.cache_path, json.dumps(cached))
        return cached

    @staticmethod
    def _find(cached: dict | None, kid: str) -> Any | None:
        if cached is None:
            return None
        try:
            return jwt.PyJWKSet.from_dict(cached["jwks"])[kid].key
        except (KeyError, jwt.PyJWKSetError, jwt.PyJWKError):
            return None

    def key(self, kid: str) -> Any | None:
        cached = self._read_cache()
        now = self.clock()
        found = self._find(cached, kid)
        if cached is not None and now < cached.get("expires_at", 0):
            if found is not None or now - cached.get("fetched_at", 0) < REFETCH_AFTER_SECONDS:
                return found
        try:
            return self._find(self._refresh(), kid)
        except (OSError, ValueError) as e:
            if found is not None:
                # Google rotates keys over days; an expired copy beats refusing everyone.
                log.warning("Google's keys couldn't be refreshed, using the cached copy: %s", e)
                return found
            raise KeysUnavailable(f"Google's keys couldn't be fetched: {e}") from e


def dev_uid(email: str) -> str:
    """A stable fake Firebase uid per email, so repeated dev logins land on the same users row."""
    return "dev-" + hashlib.sha256(email.strip().lower().encode()).hexdigest()[:24]


class DevKey:
    def __init__(self, path: Path):
        self.path = path

    def _private_key(self):
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        if not self.path.exists():
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pem = key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(pem)
        return serialization.load_pem_private_key(self.path.read_bytes(), password=None)

    def key(self, kid: str) -> Any | None:
        return self._private_key().public_key() if kid == DEV_KID else None

    def sign(
        self,
        email: str,
        *,
        uid: str | None = None,
        name: str | None = None,
        verified: bool = True,
        provider: str = "google.com",
        lifetime_seconds: int = 3600,
        now: float | None = None,
    ) -> str:
        """A token with the claims Firebase puts in a Google sign-in's ID token."""
        issued = int(time.time() if now is None else now)
        claims = {
            "iss": ISSUER_PREFIX + DEV_PROJECT_ID,
            "aud": DEV_PROJECT_ID,
            "auth_time": issued,
            "iat": issued,
            "exp": issued + lifetime_seconds,
            "sub": uid or dev_uid(email),
            "email": email,
            "email_verified": verified,
            "firebase": {"sign_in_provider": provider, "identities": {"email": [email]}},
        }
        if name:
            claims["name"] = name
        return jwt.encode(claims, self._private_key(), algorithm="RS256", headers={"kid": DEV_KID})
