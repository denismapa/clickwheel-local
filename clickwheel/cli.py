"""Command line. ./run.sh with no command starts the app.

run.sh uses the project's .venv; `python -m clickwheel ...` works too when
that Python has the dependencies (the container, or an activated venv).
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import threading
import webbrowser

from .config import LOOPBACK_HOSTS, Settings
from .source import js_runtime

log = logging.getLogger("clickwheel")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="./run.sh", description="Lofi to iPod.")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("serve", help="start the app (default)")
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env()
    except ValueError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    return serve(settings)


def serve(settings: Settings) -> int:
    import uvicorn

    from .api import create_app

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            log.error("%s not found. Install it with: brew install ffmpeg", tool)
            return 1
    if js_runtime() is None:
        log.warning("No JavaScript runtime found; YouTube needs one. Install it with: brew install deno")
    log.info("Local edition: no sign-in, so Clickwheel only listens on this computer.")

    browse_host = "localhost" if settings.host in LOOPBACK_HOSTS | {"0.0.0.0", "::"} else settings.host
    url = f"http://{browse_host}:{settings.port}/"
    log.info("Clickwheel on %s (files in %s)", url, settings.work_dir)
    if settings.open_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="warning")
    return 0
