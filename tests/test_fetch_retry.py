"""YouTube refusing a stream (403 and friends) is retried with fresh links."""

import threading

import pytest

from clickwheel import source
from clickwheel.audio import Cancelled, Mode
from clickwheel.jobs import Job
from clickwheel.source import Download, FetchProgress, SourceError

REFUSED = "ERROR: unable to download video data: HTTP Error 403: Forbidden"


def refusal() -> SourceError:
    return source.to_source_error(Exception(REFUSED))


def test_403_is_retryable_with_a_clear_title():
    error = refusal()
    assert error.retryable and error.title == "YOUTUBE REFUSED THE STREAM."
    assert source.to_source_error(Exception("ERROR: HTTP Error 503: Service Unavailable")).retryable
    assert not source.to_source_error(Exception("ERROR: Private video. Sign in")).retryable
    assert not source.to_source_error(Exception("ERROR: something new")).retryable


def test_refusals_are_retried_with_fresh_links(tmp_path, monkeypatch):
    calls, notes = [], []

    def flaky(url, dest, on_progress, cancelled):
        calls.append(url)
        if len(calls) < 3:
            raise refusal()
        return Download(info={}, audio=dest / "source.webm", thumbnail=None)

    monkeypatch.setattr(source, "_fetch_once", flaky)
    result = source.fetch("u", tmp_path / "src", lambda p: notes.append(p.note), threading.Event(), delays=(0, 0))
    assert isinstance(result, Download) and len(calls) == 3
    assert [n for n in notes if n] == [
        "YouTube refused the stream. Retrying (2 of 3)",
        "YouTube refused the stream. Retrying (3 of 3)",
    ]


def test_gives_up_after_three_refusals(tmp_path, monkeypatch):
    calls = []

    def refuse(*_args):
        calls.append(1)
        raise refusal()

    monkeypatch.setattr(source, "_fetch_once", refuse)
    with pytest.raises(SourceError) as error:
        source.fetch("u", tmp_path, lambda p: None, threading.Event(), delays=(0, 0))
    assert len(calls) == 3 and error.value.title == "YOUTUBE REFUSED THE STREAM."


def test_permanent_errors_are_not_retried(tmp_path, monkeypatch):
    calls = []

    def private(*_args):
        calls.append(1)
        raise source.to_source_error(Exception("ERROR: Private video. Sign in if you've been granted access"))

    monkeypatch.setattr(source, "_fetch_once", private)
    with pytest.raises(SourceError) as error:
        source.fetch("u", tmp_path, lambda p: None, threading.Event(), delays=(0, 0))
    assert len(calls) == 1 and error.value.title == "PRIVATE VIDEO."


def test_cancel_during_the_pause_stops(tmp_path, monkeypatch):
    monkeypatch.setattr(source, "_fetch_once", lambda *_args: (_ for _ in ()).throw(refusal()))
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(Cancelled):
        source.fetch("u", tmp_path, lambda p: None, cancelled, delays=(30, 30))


def test_job_shows_the_retry_note(tmp_path):
    job = Job("u", Mode.AAC, True, tmp_path)
    job.fetch_progress(FetchProgress(0.0, note="YouTube refused the stream. Retrying (2 of 3)"))
    assert job.snapshot()["detail"] == "YouTube refused the stream. Retrying (2 of 3)"
    job.fetch_progress(FetchProgress(0.4, speed=1e6, eta=3))
    assert job.snapshot()["detail"] == "Downloading source"
