"""Token checks (docs/api.md §2) and Google's key cache, with fake keys. No database, no network."""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from oraculoto.auth.keys import DEV_KID, DEV_PROJECT_ID, DevKey, GoogleKeys, KeysUnavailable, dev_uid
from oraculoto.auth.tokens import ISSUER_PREFIX, Claims, TokenError, TokenRefused, verify_token


@pytest.fixture
def key(tmp_path) -> DevKey:
    return DevKey(tmp_path / "dev-key.pem")


def forge(key: DevKey, signer=None, headers=None, **overrides) -> str:
    """A dev token with some claims replaced (None removes one), signed by `signer` if given."""
    claims = jwt.decode(key.sign("a@b.com"), options={"verify_signature": False})
    for name, value in overrides.items():
        if value is None:
            claims.pop(name, None)
        else:
            claims[name] = value
    return jwt.encode(
        claims, signer or key._private_key(), algorithm="RS256", headers=headers or {"kid": DEV_KID}
    )


def check(token: str, key: DevKey) -> Claims:
    return verify_token(token, DEV_PROJECT_ID, key)


def test_a_good_token(key):
    claims = check(key.sign(" A@B.com ", name="Ana"), key)
    assert claims == Claims(uid=dev_uid("a@b.com"), email="a@b.com", name="Ana", picture=None)
    assert dev_uid("A@b.com") == dev_uid("a@b.com") != dev_uid("c@b.com")


def test_the_key_file_is_private_and_reused(key):
    first = key.sign("a@b.com")
    assert key.path.stat().st_mode & 0o777 == 0o600
    check(first, DevKey(key.path))  # a new instance reads the same key


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"exp": int(time.time()) - 61}, "expired"),
        ({"aud": "someone-else"}, "(?i)audience"),
        ({"iss": ISSUER_PREFIX + "someone-else"}, "issuer"),
        ({"iat": int(time.time()) + 3600}, "not yet valid"),
        ({"sub": None}, "sub"),
        ({"sub": ""}, "bad sub"),
        ({"sub": "x" * 129}, "bad sub"),
        ({"exp": None}, "exp"),
    ],
)
def test_bad_claims_are_401(key, overrides, message):
    with pytest.raises(TokenError, match=message):
        check(forge(key, **overrides), key)


def test_the_leeway_is_60_seconds(key):
    check(forge(key, exp=int(time.time()) - 50), key)


def test_bad_signatures_are_401(key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(TokenError, match="invalid token"):
        check(forge(key, signer=other), key)
    with pytest.raises(TokenError, match="unknown key"):
        check(forge(key, headers={"kid": "nope"}), key)
    with pytest.raises(TokenError, match="not signed the way"):
        check(jwt.encode({"sub": "x"}, "s" * 32, algorithm="HS256", headers={"kid": DEV_KID}), key)
    with pytest.raises(TokenError, match="malformed"):
        check("garbage", key)
    unsigned = jwt.encode({"sub": "x"}, None, algorithm="none", headers={"kid": DEV_KID})
    with pytest.raises(TokenError):
        check(unsigned, key)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"email_verified": False}, "not verified"),
        ({"email_verified": "true"}, "not verified"),  # only a real true counts
        ({"firebase": {"sign_in_provider": "password"}}, "only Google"),
        ({"firebase": None}, "only Google"),
        ({"email": None}, "no email"),
    ],
)
def test_logins_we_dont_accept_are_refused(key, overrides, message):
    with pytest.raises(TokenRefused, match=message):
        check(forge(key, **overrides), key)


# ---------------------------------------------------------------- Google's keys, cached on disk


class FakeGoogle:
    def __init__(self, key: DevKey, kid: str = "g1", max_age: int = 3600):
        self.jwks = {
            "keys": [{**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.key(DEV_KID))), "kid": kid}]
        }
        self.max_age = max_age
        self.calls = 0
        self.down = False

    def __call__(self):
        self.calls += 1
        if self.down:
            raise OSError("Google is down")
        return self.jwks, self.max_age


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def google(key):
    return FakeGoogle(key)


def keys(tmp_path, google, clock) -> GoogleKeys:
    # A new instance per "request", as under CGI: only the disk is shared.
    return GoogleKeys(tmp_path / "cache" / "google-jwks.json", fetch=google, clock=clock)


def test_google_keys_are_cached_for_max_age(tmp_path, google):
    clock = Clock()
    assert keys(tmp_path, google, clock).key("g1") is not None
    clock.now += 3599
    assert keys(tmp_path, google, clock).key("g1") is not None
    assert google.calls == 1
    clock.now += 2
    keys(tmp_path, google, clock).key("g1")
    assert google.calls == 2
    cached = json.loads((tmp_path / "cache" / "google-jwks.json").read_text())
    assert cached["expires_at"] == clock.now + 3600
    assert list((tmp_path / "cache").iterdir()) == [tmp_path / "cache" / "google-jwks.json"]  # no temp files


def test_an_unknown_kid_refetches_at_most_once_a_minute(tmp_path, google):
    clock = Clock()
    keys(tmp_path, google, clock).key("g1")
    assert keys(tmp_path, google, clock).key("rotated") is None
    assert google.calls == 1  # fetched a moment ago: no point asking again
    clock.now += 61
    google.jwks["keys"][0]["kid"] = "rotated"
    assert keys(tmp_path, google, clock).key("rotated") is not None
    assert google.calls == 2


def test_google_down(tmp_path, google):
    clock = Clock()
    google.down = True
    with pytest.raises(KeysUnavailable):
        keys(tmp_path, google, clock).key("g1")
    google.down = False
    keys(tmp_path, google, clock).key("g1")
    clock.now += 10_000  # expired, and Google is down again: the known key is still used
    google.down = True
    assert keys(tmp_path, google, clock).key("g1") is not None
    with pytest.raises(KeysUnavailable):
        keys(tmp_path, google, clock).key("other")


def test_a_corrupt_cache_is_refetched(tmp_path, google):
    path = tmp_path / "cache" / "google-jwks.json"
    path.parent.mkdir()
    path.write_text("{not json")
    assert keys(tmp_path, google, Clock()).key("g1") is not None
    assert google.calls == 1


def test_a_token_through_google_keys(tmp_path, key, google):
    """The firebase path end to end: a token Google would sign, for project p1."""
    token = forge(key, headers={"kid": "g1"}, aud="p1", iss=ISSUER_PREFIX + "p1")
    assert verify_token(token, "p1", keys(tmp_path, google, Clock())).email == "a@b.com"
    with pytest.raises(TokenError, match="invalid token"):
        verify_token(token, "p2", keys(tmp_path, google, Clock()))
