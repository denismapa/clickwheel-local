import threading
import time
import zipfile

import pytest
from mutagen.mp4 import MP4

from clickwheel import pipeline
from clickwheel.audio import Mode, probe
from clickwheel.jobs import Job, JobManager, QueueFull, State
from clickwheel.source import SourceError

from .conftest import chapter_info
from .fakes import FakeFetcher, settings_for

URL = "https://www.youtube.com/watch?v=abcdefghijk"


def manager_for(tmp_path, fetcher, **overrides) -> JobManager:
    settings = settings_for(tmp_path, **overrides)
    return JobManager(settings, runner=lambda job: pipeline.run(job, settings, fetcher=fetcher))


def wait_finished(job: Job, timeout: float = 60) -> Job:
    deadline = time.time() + timeout
    while not job.is_finished:
        assert time.time() < deadline, f"job stuck in {job.state}"
        time.sleep(0.02)
    return job


def test_split_mix_becomes_tagged_zip(tmp_path, opus_source, thumbnail):
    manager = manager_for(tmp_path, FakeFetcher(opus_source, thumbnail))
    job = wait_finished(manager.submit(URL, Mode.AAC, split=True))

    assert job.state is State.DONE, job.error
    snap = job.snapshot()
    assert snap["sectors"] == [1.0, 1.0, 1.0] and snap["progress"] == 1.0
    assert snap["title"] == "lofi hip hop mix beats to relax/study to"
    result = job.result
    assert result.tracks == 3 and result.filename == "lofi hip hop mix beats to relax study to.zip"
    assert not (job.dir / "src").exists() and not (job.dir / "out").exists()

    with zipfile.ZipFile(result.path) as archive:
        names = archive.namelist()
        assert names == [
            "lofi hip hop mix beats to relax study to/01 No Spirit - Memories We Made.m4a",
            "lofi hip hop mix beats to relax study to/02 S N U G, Mondo Loops - Night Coffee.m4a",
            "lofi hip hop mix beats to relax study to/03 Yasumu - We Met.m4a",
        ]
        archive.extractall(tmp_path / "unzipped")
    for number, name in enumerate(names, start=1):
        path = tmp_path / "unzipped" / name
        info = probe(path)
        assert (info.codec, info.profile, info.sample_rate) == ("aac", "LC", 44100)
        assert info.duration == pytest.approx(4.0, abs=0.06)
        tags = MP4(path).tags
        assert tags["trkn"] == [(number, 3)] and tags["aART"] == ["Lofi Girl"]
        assert tags["covr"] and tags["cpil"] is True


def test_single_alac_file(tmp_path, opus_source):
    manager = manager_for(tmp_path, FakeFetcher(opus_source, thumbnail=None))
    job = wait_finished(manager.submit(URL, Mode.ALAC, split=False))

    assert job.state is State.DONE, job.error
    assert job.result.filename == "Lofi Girl - lofi hip hop mix beats to relax study to.m4a"
    info = probe(job.result.path)
    assert (info.codec, info.sample_rate) == ("alac", 44100)
    assert info.duration == pytest.approx(12.0, abs=0.06)
    tags = MP4(job.result.path).tags
    assert tags["\xa9ART"] == ["Lofi Girl"] and "covr" not in tags


def test_cancel_while_fetching(tmp_path, opus_source):
    fetcher = FakeFetcher(opus_source, None, gate=threading.Event())
    manager = manager_for(tmp_path, fetcher)
    job = manager.submit(URL, Mode.AAC, split=True)
    assert fetcher.started.wait(10)
    manager.cancel(job.id)
    wait_finished(job)
    assert job.state is State.CANCELLED
    assert not job.dir.exists()


def test_cancel_queued_job_never_runs(tmp_path, opus_source):
    gate = threading.Event()
    fetcher = FakeFetcher(opus_source, None, gate=gate)
    manager = manager_for(tmp_path, fetcher, max_jobs=1)
    first = manager.submit(URL, Mode.AAC, split=True)
    queued = manager.submit(URL, Mode.AAC, split=True)
    manager.cancel(queued.id)
    assert queued.state is State.CANCELLED
    gate.set()
    wait_finished(first)
    time.sleep(0.1)
    assert len(fetcher.calls) == 1


def test_source_error_is_reported(tmp_path, opus_source):
    def refuse(*_args):
        raise SourceError("PRIVATE VIDEO.", "Only its owner can play it.", "ERROR: Private video")

    job = wait_finished(manager_for(tmp_path, refuse).submit(URL, Mode.AAC, split=True))
    assert job.state is State.ERROR
    assert job.error == {"title": "PRIVATE VIDEO.", "message": "Only its owner can play it.",
                         "detail": "ERROR: Private video"}
    assert not job.dir.exists()


def test_live_stream_rejected_after_fetch(tmp_path, opus_source):
    info = {**chapter_info(), "live_status": "is_live"}
    job = wait_finished(manager_for(tmp_path, FakeFetcher(opus_source, None, info)).submit(URL, Mode.AAC, True))
    assert job.state is State.ERROR and job.error["title"] == "LIVE STREAM."


def test_broken_audio_is_an_encode_error(tmp_path):
    bad = tmp_path / "bad.webm"
    bad.write_bytes(b"\x1a\x45\xdf\xa3 not really webm")
    job = wait_finished(manager_for(tmp_path, FakeFetcher(bad, None)).submit(URL, Mode.AAC, split=True))
    assert job.state is State.ERROR and job.error["title"] == "ENCODE FAILED."
    assert str(tmp_path) not in job.error["detail"]


def test_queue_limit(tmp_path, opus_source):
    gate = threading.Event()
    manager = manager_for(tmp_path, FakeFetcher(opus_source, None, gate=gate), max_active_jobs=1)
    first = manager.submit(URL, Mode.AAC, split=True)
    with pytest.raises(QueueFull):
        manager.submit(URL, Mode.AAC, split=True)
    gate.set()
    wait_finished(first)


def test_expired_jobs_are_swept(tmp_path, opus_source):
    manager = manager_for(tmp_path, FakeFetcher(opus_source, None))
    job = wait_finished(manager.submit(URL, Mode.AAC, split=False))
    assert job.dir.exists()
    job.finished_at = time.time() - 2 * 3600
    assert manager.get(job.id) is None
    assert not job.dir.exists()


def test_startup_purges_only_job_folders(tmp_path):
    work = tmp_path / "work"
    (work / ("a" * 32)).mkdir(parents=True)
    (work / "keep-me").mkdir()
    (work / "notes.txt").write_text("x")
    JobManager(settings_for(tmp_path))
    assert sorted(p.name for p in work.iterdir()) == ["keep-me", "notes.txt"]


def test_track_filename_padding():
    release = pipeline.build_release({**chapter_info(), "chapters": chapter_info()["chapters"] * 4},
                                     split=True, genre="")
    assert len(release.tracks) == 12
    assert pipeline.track_filename(release, release.tracks[0]).startswith("01 ")
