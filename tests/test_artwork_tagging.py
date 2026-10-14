import json
import subprocess

from mutagen.mp4 import MP4, MP4Cover

from clickwheel import audio
from clickwheel.artwork import is_baseline_jpeg, make_cover
from clickwheel.audio import Mode, build_command, probe
from clickwheel.tagging import write_tags
from clickwheel.tracks import build_release

from .conftest import chapter_info


def test_cover_is_600_square_baseline_jpeg(thumbnail, tmp_path):
    cover = make_cover(thumbnail, tmp_path / "cover.jpg")
    out = subprocess.run(
        [audio.ffprobe_bin(), "-v", "error", "-show_entries", "stream=width,height", "-of", "json", str(cover)],
        capture_output=True, text=True, check=True,
    )
    stream = json.loads(out.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (600, 600)
    assert is_baseline_jpeg(cover.read_bytes())


def test_baseline_check_rejects_progressive_and_non_jpeg():
    progressive = b"\xff\xd8" + b"\xff\xe0\x00\x04ab" + b"\xff\xc2\x00\x02"
    assert not is_baseline_jpeg(progressive)
    assert not is_baseline_jpeg(b"\x89PNG\r\n\x1a\n")
    assert not is_baseline_jpeg(b"")


def test_tags_round_trip(opus_source, thumbnail, tmp_path):
    dst = tmp_path / "track.m4a"
    source = probe(opus_source)
    audio.run(build_command(opus_source, dst, Mode.AAC, source, duration=4.0), 4.0)
    release = build_release(chapter_info(), split=True, genre="Lo-Fi")
    cover = make_cover(thumbnail, tmp_path / "cover.jpg").read_bytes()

    write_tags(dst, release, release.tracks[1], cover)

    tags = MP4(dst).tags
    assert tags["\xa9nam"] == ["Night Coffee"]
    assert tags["\xa9ART"] == ["S N U G, Mondo Loops"]
    assert tags["aART"] == ["Lofi Girl"]
    assert tags["\xa9alb"] == ["lofi hip hop mix beats to relax/study to"]
    assert tags["\xa9day"] == ["2024"]
    assert tags["\xa9gen"] == ["Lo-Fi"]
    assert tags["\xa9cmt"] == ["https://www.youtube.com/watch?v=abcdefghijk"]
    assert tags["trkn"] == [(2, 3)]
    assert tags["disk"] == [(1, 1)]
    assert tags["stik"] == [1]
    assert tags["cpil"] is True and tags["pgap"] is True
    (art,) = tags["covr"]
    assert bytes(art) == cover and art.imageformat == MP4Cover.FORMAT_JPEG
    assert probe(dst).codec == "aac"  # tagging leaves the audio untouched


def test_single_track_tags_have_no_compilation_flags(opus_source, tmp_path):
    dst = tmp_path / "single.m4a"
    audio.run(build_command(opus_source, dst, Mode.ALAC, probe(opus_source), duration=1.0), 1.0)
    release = build_release(chapter_info(), split=False, genre="")
    write_tags(dst, release, release.tracks[0])
    tags = MP4(dst).tags
    assert "cpil" not in tags and "pgap" not in tags and "covr" not in tags and "\xa9gen" not in tags
    assert tags["trkn"] == [(1, 1)]
