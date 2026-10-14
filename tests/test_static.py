"""Guards for the UI files: CSP-safe markup, no HTML sinks, a dark theme."""

import hashlib
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "clickwheel" / "static"
INDEX = (STATIC / "index.html").read_text()
SCRIPTS = {path.name: path.read_text() for path in (STATIC / "js").glob("*.js")}
APP_CSS = (STATIC / "css" / "app.css").read_text()

EXPECTED_SCRIPTS = {"app.js", "core.js"}


def test_page_is_pinned_to_night_theme():
    assert '<html lang="en" data-theme="dark">' in INDEX
    assert 'class="ss-body"' in INDEX


def test_markup_fits_the_csp():
    assert " style=" not in INDEX, "inline styles are blocked by the CSP"
    assert re.findall(r"<script[^>]*>", INDEX) == ['<script type="module" src="/js/app.js">']
    external = re.findall(r'(?:href|src)="(https?://[^"]+)"', INDEX)
    assert all(url.startswith(("https://fonts.googleapis.com", "https://fonts.gstatic.com")) for url in external)


def test_scripts_have_no_html_sinks():
    assert set(SCRIPTS) == EXPECTED_SCRIPTS
    for name, code in SCRIPTS.items():
        for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
            assert sink not in code, f"{sink} in {name}"


def test_app_css_uses_tokens_only():
    assert not re.findall(r"#[0-9a-fA-F]{3,8}\b", APP_CSS)
    assert not re.findall(r"rgba?\(", APP_CSS)


ROOT = STATIC.parent.parent


