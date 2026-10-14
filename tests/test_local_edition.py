"""The local edition has no sign-in, so it must stay on this computer."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from clickwheel.api import create_app
from clickwheel.config import Settings
from clickwheel.jobs import JobManager

from .fakes import settings_for

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "clickwheel" / "static"
SIGN_IN_TERMS = ("passkey", "webauthn", "totp", "password")


def client_for(tmp_path) -> TestClient:
    settings = settings_for(tmp_path)
    return TestClient(create_app(settings, JobManager(settings), prober=lambda url: {}))


def test_no_sign_in_code_ships():
    assert not (ROOT / "clickwheel" / "auth").exists()
    for name in ("access.js", "admin.js", "passkey.js"):
        assert not (STATIC / "js" / name).exists(), name
    for path in [*(ROOT / "clickwheel").rglob("*.py"), *STATIC.rglob("*.*")]:
        text = path.read_text(errors="ignore").lower()
        for term in SIGN_IN_TERMS:
            assert term not in text, f"{term} in {path.relative_to(ROOT)}"


@pytest.mark.parametrize("host", ["0.0.0.0", "::", "192.168.1.20", "my-mac.local"])
def test_refuses_to_listen_beyond_this_computer(host):
    with pytest.raises(ValueError):
        Settings(host=host)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost"])
def test_listens_on_this_computer(host):
    assert Settings(host=host).host == host


def test_works_without_signing_in(tmp_path):
    client = client_for(tmp_path)
    assert client.get("/api/health").json() == {"ok": True, "edition": "local"}
    assert client.get("/api/info").status_code == 200
    assert client.get("/api/jobs").status_code == 200
    assert client.get("/api/auth/state").status_code == 404


def test_page_loads_nothing_from_other_sites(tmp_path):
    csp = client_for(tmp_path).get("/").headers["content-security-policy"]
    assert "googleapis" not in csp and "gstatic" not in csp
    assert "style-src 'self';" in csp or csp.endswith("style-src 'self'")
    html = (STATIC / "index.html").read_text()
    assert "https://" not in html.split("<body")[0]
    assert '<link rel="stylesheet" href="/css/neutral.css">' in html


def test_ships_its_own_neutral_theme():
    assert (STATIC / "css" / "neutral.css").is_file()
    assert not (STATIC / "css" / "tokens.css").exists()
    assert not (STATIC / "css" / "slipstream.css").exists()
