"""Starting the server: a busy port falls through to the next free one."""

import socket
import sys
import types
from dataclasses import replace

from clickwheel import cli

from .fakes import settings_for


def listening_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    return sock


def test_busy_port_is_skipped():
    with listening_socket() as busy:
        port = busy.getsockname()[1]
        chosen = cli.free_port("127.0.0.1", port)
        assert chosen is not None and chosen != port
        assert cli.free_port("localhost", port) != port


def test_free_port_is_kept():
    with listening_socket() as sock:
        port = sock.getsockname()[1]
    assert cli.free_port("127.0.0.1", port) == port


def test_gives_up_when_every_port_is_taken():
    with listening_socket() as busy:
        assert cli.free_port("127.0.0.1", busy.getsockname()[1], attempts=1) is None


def test_serve_moves_to_the_next_port_with_its_own_folder(tmp_path, monkeypatch):
    started = {}

    def fake_run(app, host, port, log_level):
        started.update(app=app, host=host, port=port)

    monkeypatch.setitem(sys.modules, "uvicorn", types.SimpleNamespace(run=fake_run))
    with listening_socket() as busy:
        port = busy.getsockname()[1]
        settings = replace(settings_for(tmp_path), port=port)
        assert cli.serve(settings) == 0
    assert started["host"] == "127.0.0.1" and started["port"] != port
    used = started["app"].state.settings
    assert used.port == started["port"]
    assert used.work_dir == settings.work_dir / f"port-{started['port']}"
