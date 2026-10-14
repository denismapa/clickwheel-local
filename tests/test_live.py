"""Real YouTube, opt-in:  CLICKWHEEL_LIVE=1 .venv/bin/python -m pytest -m live"""

import os

import pytest
from mutagen.mp4 import MP4

from clickwheel import pipeline, source
from clickwheel.artwork import is_baseline_jpeg
from clickwheel.audio import Mode, probe
from clickwheel.jobs import Job
from clickwheel.preview import summarize

from .fakes import settings_for

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("CLICKWHEEL_LIVE") != "1", reason="network test; set CLICKWHEEL_LIVE=1"),
]

SHORT_TRACK = "https://www.youtube.com/watch?v=TteonQUWP6M"  # 2:55 lofi beat
CHAPTERED_MIX = "https://www.youtube.com/watch?v=CLeZyIID9Bo"  # 1:44:52 mix, 53 chapters
LIVE_RADIO = "https://www.youtube.com/watch?v=rFZHOHl-L8A"  # 24/7 lofi radio


def test_probe_reads_chaptered_mix(tmp_path):
    summary = summarize(source.probe(CHAPTERED_MIX), settings_for(tmp_path))
    assert summary["source"]["codec"] == "OPUS" and summary["source"]["khz"] == 48.0
    assert len(summary["tracks"]) >= 40
    assert all(t["artist"] and t["title"] for t in summary["tracks"])
    assert summary["thumbnail"].startswith("https://i.ytimg.com/")


def test_live_radio_is_rejected(tmp_path):
    with pytest.raises(source.SourceError) as err:
        summarize(source.probe(LIVE_RADIO), settings_for(tmp_path))
    assert err.value.title == "LIVE STREAM."


def test_real_track_end_to_end(tmp_path):
    settings = settings_for(tmp_path)
    job = Job(SHORT_TRACK, Mode.AAC, split=True, root=settings.work_dir)
    job.dir.mkdir(parents=True)
    result = pipeline.run(job, settings)

    info = probe(result.path)
    assert (info.codec, info.profile, info.sample_rate, info.channels) == ("aac", "LC", 44100, 2)
    assert info.duration == pytest.approx(175, abs=2)
    tags = MP4(result.path).tags
    (cover,) = tags["covr"]
    assert is_baseline_jpeg(bytes(cover))
    assert tags["\xa9cmt"] == [SHORT_TRACK] and tags["\xa9gen"] == ["Lo-Fi"]
