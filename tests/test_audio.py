import threading

import pytest

from clickwheel import audio
from clickwheel.audio import Cancelled, Mode, SourceInfo, build_command, can_passthrough, probe

OPUS = SourceInfo(codec="opus", profile="", sample_rate=48000, channels=2, duration=12.0)
AAC_LC = SourceInfo(codec="aac", profile="LC", sample_rate=44100, channels=2, duration=4.0)


def _after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def test_aac_command_uses_apple_encoder_at_256k(tmp_path):
    cmd = build_command(tmp_path / "in.webm", tmp_path / "out.m4a", Mode.AAC, OPUS, encoder="aac_at")
    assert _after(cmd, "-c:a") == "aac_at"
    assert _after(cmd, "-aac_at_mode") == "cvbr"
    assert _after(cmd, "-b:a") == "256k"
    assert "aresample=44100" in _after(cmd, "-af")
    assert "dither_method=triangular" in _after(cmd, "-af")
    assert "sample_fmts=s16:" in _after(cmd, "-af")
    assert _after(cmd, "-f") == "ipod"
    assert cmd[-1].endswith("out.m4a")


def test_aac_command_falls_back_to_native_encoder(tmp_path):
    cmd = build_command(tmp_path / "in.webm", tmp_path / "out.m4a", Mode.AAC, OPUS, encoder="aac")
    assert _after(cmd, "-c:a") == "aac"
    assert "sample_fmts=fltp:" in _after(cmd, "-af")


def test_alac_command_is_16_bit(tmp_path):
    cmd = build_command(tmp_path / "in.webm", tmp_path / "out.m4a", Mode.ALAC, OPUS)
    assert _after(cmd, "-c:a") == "alac"
    assert "sample_fmts=s16p:" in _after(cmd, "-af")


def test_segment_seek_is_an_input_option(tmp_path):
    cmd = build_command(tmp_path / "in.webm", tmp_path / "o.m4a", Mode.AAC, OPUS, start=4.0, duration=4.0)
    assert cmd.index("-ss") < cmd.index("-i") and cmd.index("-t") < cmd.index("-i")
    assert (_after(cmd, "-ss"), _after(cmd, "-t")) == ("4.000", "4.000")


def test_surround_is_downmixed(tmp_path):
    six = SourceInfo(codec="opus", profile="", sample_rate=48000, channels=6, duration=1)
    assert _after(build_command(tmp_path / "i", tmp_path / "o", Mode.AAC, six), "-ac") == "2"
    assert "-ac" not in build_command(tmp_path / "i", tmp_path / "o", Mode.AAC, OPUS)


def test_passthrough_only_for_aac_lc_at_44k1():
    assert can_passthrough(AAC_LC, Mode.AAC)
    assert not can_passthrough(AAC_LC, Mode.ALAC)
    assert not can_passthrough(OPUS, Mode.AAC)
    assert not can_passthrough(SourceInfo("aac", "HE-AAC", 44100, 2, 1), Mode.AAC)
    assert not can_passthrough(SourceInfo("aac", "LC", 48000, 2, 1), Mode.AAC)


def test_passthrough_command_copies(tmp_path):
    cmd = build_command(tmp_path / "in.m4a", tmp_path / "out.m4a", Mode.AAC, AAC_LC)
    assert _after(cmd, "-c:a") == "copy"
    assert "-af" not in cmd


def test_encoder_detection():
    assert audio.aac_encoder() in {"aac_at", "aac"}


@pytest.mark.parametrize(
    ("mode", "codec", "sample_fmt"),
    [(Mode.AAC, "aac", None), (Mode.ALAC, "alac", "s16p")],
)
def test_real_encode_is_ipod_spec(opus_source, tmp_path, mode, codec, sample_fmt):
    source = probe(opus_source)
    assert (source.codec, source.sample_rate) == ("opus", 48000)
    dst = tmp_path / "out.m4a"
    seen = []
    audio.run(build_command(opus_source, dst, mode, source), source.duration, seen.append)
    out = probe(dst)
    assert out.codec == codec
    assert out.sample_rate == 44100
    assert out.channels == 2
    assert out.duration == pytest.approx(12.0, abs=0.1)
    if codec == "aac":
        assert out.profile == "LC"
    assert seen[-1] == 1.0 and seen == sorted(seen)


def test_real_segment_encode_length(opus_source, tmp_path):
    source = probe(opus_source)
    dst = tmp_path / "seg.m4a"
    audio.run(build_command(opus_source, dst, Mode.AAC, source, start=4.0, duration=4.0), 4.0)
    assert probe(dst).duration == pytest.approx(4.0, abs=0.06)


def test_real_passthrough_keeps_codec(aac_source, tmp_path):
    source = probe(aac_source)
    assert can_passthrough(source, Mode.AAC)
    dst = tmp_path / "copy.m4a"
    audio.run(build_command(aac_source, dst, Mode.AAC, source), source.duration)
    assert (probe(dst).codec, probe(dst).sample_rate) == ("aac", 44100)


def test_cancel_stops_ffmpeg(opus_source, tmp_path):
    cancelled = threading.Event()
    cancelled.set()
    with pytest.raises(Cancelled):
        audio.run(build_command(opus_source, tmp_path / "x.m4a", Mode.ALAC, probe(opus_source)), 12.0, None, cancelled)


def test_failed_encode_raises(tmp_path):
    bad = tmp_path / "bad.webm"
    bad.write_bytes(b"not audio")
    with pytest.raises(audio.EncodeError):
        audio.run(build_command(bad, tmp_path / "x.m4a", Mode.AAC, OPUS), 1.0)
