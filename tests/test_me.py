"""Logins (docs/api.md §2 and §8), /me, tickets and their results, and the users command line."""

from datetime import datetime

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from oraculoto.api.app import PREFIX, create_app
from oraculoto.api.deps import get_engine
from oraculoto.auth.keys import dev_uid
from oraculoto.cli import main
from oraculoto.importer.caixa_xlsx import import_xlsx
from tests.auth_tokens import MEMBER, bearer, dev_key, invite
from tests.conftest import TEST_DB
from tests.xlsx_builder import SAMPLE_ROWS, build_xlsx

OTHER = "other@test.example"
# Contest 2 of the sample: 9 37 39 41 43 49; 2 jackpot winners of 2,000,000, 5 hits pay 40,000, 4 pay 500.
SEVEN = [49, 9, 37, 39, 41, 43, 50]


@pytest.fixture
def sample(clean_db, tmp_path):
    import_xlsx(clean_db, "megasena", build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS))
    return clean_db


@pytest.fixture
def app(sample):
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: sample
    return app


def as_user(app, email: str | None = MEMBER, **claims) -> TestClient:
    return TestClient(app, headers=bearer(email, **claims) if email else {})


def user_row(engine, email: str = MEMBER) -> dict:
    with engine.connect() as conn:
        return dict(conn.execute(text("SELECT * FROM users WHERE email = :e"), {"e": email}).mappings().one())


def error_code(r) -> tuple[int, str]:
    return r.status_code, r.json()["error"]["code"]


# ---------------------------------------------------------------- logins


def test_first_login_links_the_invite(app, sample):
    invite(sample, MEMBER.upper())  # stored as given here; the API matches lowercase
    with sample.begin() as conn:
        conn.execute(text("UPDATE users SET email = LOWER(email)"))
    r = as_user(app, MEMBER.upper(), name="Ana").get(f"{PREFIX}/me")
    assert r.status_code == 200, r.text
    me = r.json()["data"]
    assert (me["email"], me["display_name"], me["role"]) == (MEMBER, "Ana", "member")
    assert me["last_login_at"].endswith("Z")
    row = user_row(sample)
    assert row["firebase_uid"] == dev_uid(MEMBER) and row["last_login_at"] is not None


def test_later_logins_find_the_uid_even_with_a_new_email(app, sample):
    invite(sample)
    as_user(app).get(f"{PREFIX}/me")
    r = as_user(app, "renamed@test.example", uid=dev_uid(MEMBER)).get(f"{PREFIX}/games")
    assert r.status_code == 200


def test_other_routes_dont_touch_last_login(app, sample):
    invite(sample)
    assert as_user(app).get(f"{PREFIX}/games").status_code == 200
    row = user_row(sample)
    assert row["firebase_uid"] is not None and row["last_login_at"] is None


def test_not_invited(app, sample):
    assert error_code(as_user(app).get(f"{PREFIX}/me")) == (403, "not_invited")
    with sample.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == 0  # never creates a user


@pytest.mark.parametrize("claims", [{"verified": False}, {"provider": "password"}])
def test_unverified_or_not_google(app, sample, claims):
    invite(sample)
    assert error_code(as_user(app, **claims).get(f"{PREFIX}/me")) == (403, "not_invited")
    assert user_row(sample)["firebase_uid"] is None


def test_blocked(app, sample):
    invite(sample, status="blocked")
    assert error_code(as_user(app).get(f"{PREFIX}/me")) == (403, "blocked")
    assert user_row(sample)["firebase_uid"] is None  # not linked either
    with sample.begin() as conn:
        conn.execute(text("UPDATE users SET status = 'active'"))
    assert as_user(app).get(f"{PREFIX}/me").status_code == 200
    with sample.begin() as conn:
        conn.execute(text("UPDATE users SET status = 'blocked'"))
    assert error_code(as_user(app).get(f"{PREFIX}/games")) == (403, "blocked")  # linked, then blocked


def test_email_linked_to_another_uid(app, sample, caplog):
    invite(sample)
    as_user(app).get(f"{PREFIX}/me")
    r = as_user(app, uid="someone-else").get(f"{PREFIX}/me")
    assert error_code(r) == (403, "not_invited")
    assert "linked to another Firebase uid" in caplog.text
    assert user_row(sample)["firebase_uid"] == dev_uid(MEMBER)


def test_bad_tokens_are_401(app, sample):
    invite(sample)
    for headers in [{}, {"Authorization": "Bearer garbage"}, bearer(lifetime_seconds=-120)]:
        r = TestClient(app).get(f"{PREFIX}/me", headers=headers)
        assert error_code(r) == (401, "unauthorized"), headers
    expired = TestClient(app).get(f"{PREFIX}/me", headers=bearer(lifetime_seconds=-120))
    assert "expired" in expired.json()["error"]["message"]


def test_a_token_for_another_project_is_401(app, sample):
    invite(sample)
    claims = jwt.decode(dev_key().sign(MEMBER), options={"verify_signature": False})
    claims["aud"] = "real-firebase-project"
    token = jwt.encode(
        claims, dev_key()._private_key(), algorithm="RS256", headers={"kid": "oraculoto-dev-key"}
    )
    r = TestClient(app).get(f"{PREFIX}/me", headers={"Authorization": f"Bearer {token}"})
    assert error_code(r) == (401, "unauthorized")


# ---------------------------------------------------------------- tickets


@pytest.fixture
def member(app, sample) -> TestClient:
    invite(sample)
    return as_user(app)


def create(client: TestClient, status: int = 201, **body) -> dict:
    r = client.post(
        f"{PREFIX}/me/tickets", json={"game": "megasena", "numbers": SEVEN, "first_contest": 1, **body}
    )
    assert r.status_code == status, r.text
    return r.json()["data"] if status < 400 else r.json()["error"]


def test_create_and_read_a_ticket(member):
    t = create(member, label="  bolão  ")
    assert t["numbers"] == sorted(SEVEN)
    assert (t["game"], t["first_contest"], t["last_contest"], t["label"], t["source"]) == (
        "megasena",
        1,
        1,
        "bolão",
        None,
    )
    assert member.get(f"{PREFIX}/me/tickets/{t['id']}").json()["data"] == t


def test_source_must_be_a_guess_function(member):
    assert create(member, source="hot_recent@1")["source"] == "hot_recent@1"
    for bad in ("manual", "hot_recent@99", "nope@1"):
        err = create(member, 400, source=bad)
        assert err["code"] == "invalid_input" and "source" in err["message"]


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"numbers": [1, 2, 3, 4, 5]}, "6-20 numbers"),
        ({"numbers": [1, 1, 2, 3, 4, 5]}, "repeated"),
        ({"numbers": [1, 2, 3, 4, 5, 61]}, "outside"),
        ({"first_contest": 10, "last_contest": 62}, "at most 52 contests, got 53"),
        ({"first_contest": 10, "last_contest": 9}, "before"),
        ({"first_contest": 0}, "first_contest"),
        ({"game": "quina"}, "unknown game"),
        ({"user_id": 2}, "user_id"),  # can't register a ticket for someone else
        ({"label": "x" * 121}, "label"),
    ],
)
def test_bad_tickets(member, body, message):
    err = create(member, 400, **body)
    assert err["code"] == "invalid_input" and message in err["message"], err


def test_span_cap_is_configurable(member, monkeypatch):
    monkeypatch.setenv("ORACULOTO_TICKET_MAX_SPAN", "2")
    assert "at most 2 contests" in create(member, 400, last_contest=3)["message"]


def test_list_tickets(member, app, sample):
    ids = [create(member, first_contest=c)["id"] for c in (1, 2, 3)]
    page = member.get(f"{PREFIX}/me/tickets", params={"limit": 2}).json()["data"]
    assert ([t["id"] for t in page["items"]], page["total"]) == (ids[::-1][:2], 3)
    assert member.get(f"{PREFIX}/me/tickets", params={"game": "megasena"}).json()["data"]["total"] == 3
    assert error_code(member.get(f"{PREFIX}/me/tickets", params={"game": "quina"})) == (404, "not_found")

    invite(sample, OTHER)
    assert as_user(app, OTHER).get(f"{PREFIX}/me/tickets").json()["data"]["total"] == 0


def test_another_users_ticket_is_404(member, app, sample):
    t = create(member)
    invite(sample, OTHER)
    other = as_user(app, OTHER)
    url = f"{PREFIX}/me/tickets/{t['id']}"
    assert error_code(other.get(url)) == (404, "not_found")
    assert error_code(other.get(url + "/results")) == (404, "not_found")
    assert error_code(other.patch(url, json={"label": "mine"})) == (404, "not_found")
    assert error_code(other.delete(url)) == (404, "not_found")
    assert member.get(url).json()["data"] == t  # untouched


def test_only_the_label_changes(member):
    t = create(member, label="old")
    url = f"{PREFIX}/me/tickets/{t['id']}"
    assert member.patch(url, json={"label": "new"}).json()["data"]["label"] == "new"
    assert member.patch(url, json={"label": ""}).json()["data"]["label"] is None
    for body in ({"numbers": [1, 2, 3, 4, 5, 6]}, {"label": "x", "first_contest": 2}, {}):
        assert error_code(member.patch(url, json=body)) == (400, "invalid_input"), body
    assert member.get(url).json()["data"]["numbers"] == sorted(SEVEN)


def test_delete(member, sample):
    t = create(member)
    url = f"{PREFIX}/me/tickets/{t['id']}"
    r = member.delete(url)
    assert r.status_code == 200 and r.json() == {"success": True, "data": None}
    assert error_code(member.get(url)) == (404, "not_found")
    with sample.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM ticket_numbers")).scalar_one() == 0


def test_deleting_a_user_deletes_their_tickets(member, sample):
    create(member)
    with sample.begin() as conn:
        conn.execute(text("DELETE FROM users"))
        assert conn.execute(text("SELECT COUNT(*) FROM tickets")).scalar_one() == 0


# ---------------------------------------------------------------- results


def test_results(member):
    t = create(member, first_contest=1, last_contest=5)
    d = member.get(f"{PREFIX}/me/tickets/{t['id']}/results").json()["data"]
    assert d["ticket"] == t
    by = {i["contest"]: i for i in d["items"]}
    assert [i["status"] for i in d["items"]] == ["drawn", "drawn", "drawn", "pending", "pending"]
    assert by[2] == {
        "contest": 2,
        "status": "drawn",
        "date": "1996-03-18",
        "hits": 6,
        "matched": [9, 37, 39, 41, 43, 49],
        "prizes": [
            {"hits": 6, "combinations": 1, "prize_per_winner": "2000000.00", "amount": "2000000.00"},
            {"hits": 5, "combinations": 6, "prize_per_winner": "40000.00", "amount": "240000.00"},
        ],
        "total": "2240000.00",
        "registered_after_draw": True,
    }
    assert (by[1]["hits"], by[1]["matched"], by[1]["prizes"], by[1]["total"]) == (1, [41], [], "0.00")
    assert by[4] == {
        "contest": 4,
        "status": "pending",
        "date": None,
        "hits": None,
        "matched": None,
        "prizes": [],
        "total": None,
        "registered_after_draw": None,
    }
    assert d["total"] == "2240000.00"


def test_registered_before_the_draw(member, sample):
    t = create(member, first_contest=2)
    with sample.begin() as conn:
        conn.execute(text("UPDATE tickets SET created_at = :d"), {"d": datetime(1996, 3, 17, 23, 0)})
    [item] = member.get(f"{PREFIX}/me/tickets/{t['id']}/results").json()["data"]["items"]
    assert item["registered_after_draw"] is False


def test_a_gap_in_our_data_is_missing_not_pending(member, sample):
    t = create(member, first_contest=1, last_contest=4)
    with sample.begin() as conn:
        conn.execute(text("DELETE FROM draws WHERE contest_number = 2"))
    d = member.get(f"{PREFIX}/me/tickets/{t['id']}/results").json()["data"]
    assert [i["status"] for i in d["items"]] == ["drawn", "missing", "drawn", "pending"]
    assert d["total"] == "0.00"


# ---------------------------------------------------------------- command line


@pytest.fixture
def cli_db(clean_db, monkeypatch):
    monkeypatch.setenv("DB_NAME", TEST_DB)  # the commands use the main settings
    return clean_db


def test_users_command(cli_db, capsys):
    assert main(["users", "invite", " Boss@Test.Example ", "--admin"]) == 0
    assert main(["users", "invite", "boss@test.example"]) == 1
    assert "already invited" in capsys.readouterr().err
    assert main(["users", "invite", "not-an-email"]) == 1
    assert main(["users", "block", "boss@test.example"]) == 0
    assert main(["users", "unblock", "nobody@test.example"]) == 1
    capsys.readouterr()
    assert main(["users", "list"]) == 0
    assert capsys.readouterr().out == "boss@test.example\tadmin\tblocked\tnever logged in\n"


def test_dev_token_command(cli_db, app, capsys):
    assert main(["users", "invite", MEMBER]) == 0
    capsys.readouterr()
    assert main(["dev-token", MEMBER, "--name", "Ana"]) == 0
    token = capsys.readouterr().out.strip()
    r = TestClient(app).get(f"{PREFIX}/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["data"]["display_name"] == "Ana"
    main(["dev-token", MEMBER, "--expired"])
    expired = capsys.readouterr().out.strip()
    assert (
        TestClient(app).get(f"{PREFIX}/me", headers={"Authorization": f"Bearer {expired}"}).status_code == 401
    )
