"""Command line. ./run.sh with no command starts the app.

run.sh uses the project's .venv; `python -m clickwheel ...` works too when
that Python has the dependencies (the container, or an activated venv).
"""

from __future__ import annotations

import argparse
import logging
import shutil
import socket
import sys
import threading
import webbrowser
from dataclasses import replace

from .config import LOOPBACK_HOSTS, Settings
from .source import js_runtime

log = logging.getLogger("clickwheel")
PORT_ATTEMPTS = 20


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

    port = free_port(settings.host, settings.port)
    if port is None:
        last = settings.port + PORT_ATTEMPTS - 1
        log.error("Ports %d to %d are all in use. Set CLICKWHEEL_PORT to a free port.", settings.port, last)
        return 1
    if port != settings.port:
        log.warning("Port %d is in use (another Clickwheel?), so this one uses %d.", settings.port, port)
    # Each port keeps its own job folder, so two Clickwheels never clear each other's files.
    settings = replace(settings, port=port, work_dir=settings.work_dir / f"port-{port}")

    browse_host = "localhost" if settings.host in LOOPBACK_HOSTS | {"0.0.0.0", "::"} else settings.host
    url = f"http://{browse_host}:{settings.port}/"
    log.info("Clickwheel on %s (files in %s)", url, settings.work_dir)
    if settings.open_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="warning")
    return 0


def free_port(host: str, start: int, attempts: int = PORT_ATTEMPTS) -> int | None:
    """The first port from `start` that nothing is listening on, or None."""
    address = "127.0.0.1" if host == "localhost" else host
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    for port in range(start, min(start + attempts, 65536)):
        with socket.socket(family, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe.bind((address, port))
            except OSError:
                continue
            return port
    return None
