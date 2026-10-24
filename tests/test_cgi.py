"""The app through the real CGI entry point: public/index.cgi in a subprocess, with the environment
Apache sets after the .htaccess rewrite (PATH_INFO and SCRIPT_NAME point at index.cgi)."""

import json
import os
import subprocess

import pytest

from oraculoto.api.cgi import fix_environ
from oraculoto.config import PROJECT_ROOT
from oraculoto.importer.caixa_xlsx import import_xlsx
from tests.conftest import TEST_DB
from tests.xlsx_builder import SAMPLE_ROWS, build_xlsx

INDEX_CGI = PROJECT_ROOT / "public" / "index.cgi"


@pytest.fixture
def sample(clean_db, tmp_path):
    import_xlsx(clean_db, "megasena", build_xlsx(tmp_path / "s.xlsx", SAMPLE_ROWS))
    return clean_db


def run_cgi(uri: str, tmp_path, **extra: str) -> tuple[int, dict[str, str], dict]:
    env = {
        "PATH": "/usr/bin:/bin",
        "GATEWAY_INTERFACE": "CGI/1.1",
        "SERVER_PROTOCOL": "HTTP/1.1",
        "SERVER_NAME": "oraculoto.test",
        "SERVER_PORT": "443",
        "HTTPS": "on",
        "REQUEST_METHOD": "GET",
        "REQUEST_URI": uri,
        "SCRIPT_NAME": "/index.cgi",
        "SCRIPT_FILENAME": str(INDEX_CGI),
        "PATH_INFO": "",
        "QUERY_STRING": uri.partition("?")[2],
        "HTTP_AUTHORIZATION": "",
        "ORACULOTO_ENV": "dev",
        "ORACULOTO_CGI_LOG": str(tmp_path / "cgi-error.log"),
        **{k: os.environ[k] for k in ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD") if k in os.environ},
        "DB_NAME": TEST_DB,
        **extra,
    }
    out = subprocess.run([str(INDEX_CGI)], env=env, capture_output=True, timeout=60, cwd=INDEX_CGI.parent)
    assert out.returncode == 0, out.stderr.decode()
    head, _, body = out.stdout.partition(b"\r\n\r\n")
    headers = dict(line.split(": ", 1) for line in head.decode("latin-1").split("\r\n"))
    status = int(headers.pop("Status").split()[0])
    return status, headers, json.loads(body)


def test_health(sample, tmp_path):
    status, headers, body = run_cgi("/api/v1/health", tmp_path)
    assert status == 200 and headers["content-type"] == "application/json"
    assert body["data"]["games"][0]["latest_contest"] == 3


def test_authorization_through_the_rewrite_and_query_string(sample, tmp_path):
    status, _, body = run_cgi(
        "/api/v1/games/megasena/draws?limit=1&page=2", tmp_path, REDIRECT_HTTP_AUTHORIZATION="Bearer dev"
    )
    assert status == 200, body
    assert (body["data"]["total"], [d["contest"] for d in body["data"]["items"]]) == (3, [2])


def test_no_token(sample, tmp_path):
    status, _, body = run_cgi("/api/v1/games", tmp_path)
    assert status == 401 and body["error"]["code"] == "unauthorized"


def test_crash_goes_to_the_log_not_the_client(tmp_path):
    status, _, body = run_cgi("/api/v1/health", tmp_path, ORACULOTO_ENV="production")
    assert status == 500
    assert body == {"success": False, "error": {"code": "internal", "message": "internal server error"}}
    assert "ORACULOTO_ENV='production'" in (tmp_path / "cgi-error.log").read_text()


def test_fix_environ():
    env = {
        "REQUEST_URI": "/api/v1/games/mega%20sena/draws?from=1&to=2",
        "PATH_INFO": "/index.cgi",
        "SCRIPT_NAME": "/index.cgi",
        "QUERY_STRING": "",
        "HTTP_AUTHORIZATION": "",
        "REDIRECT_HTTP_AUTHORIZATION": "Bearer abc",
    }
    fix_environ(env)
    assert env["PATH_INFO"] == "/api/v1/games/mega sena/draws"
    assert (env["QUERY_STRING"], env["SCRIPT_NAME"], env["HTTP_AUTHORIZATION"]) == (
        "from=1&to=2",
        "",
        "Bearer abc",
    )

    empty = {"REQUEST_URI": "/", "HTTP_AUTHORIZATION": ""}
    fix_environ(empty)
    assert "HTTP_AUTHORIZATION" not in empty and empty["PATH_INFO"] == "/"
