import pytest

from clickwheel.tracks import build_release, channel_name, parse_artist_title

from .conftest import chapter_info


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("No Spirit - Memories We Made", ("No Spirit", "Memories We Made")),
        ("S N U G, Mondo Loops - Night Coffee", ("S N U G, Mondo Loops", "Night Coffee")),
        ("Sutton – Lunch Break", ("Sutton", "Lunch Break")),
        ("home grown — out of office", ("home grown", "out of office")),
        ("01. Noji - Exhale", ("Noji", "Exhale")),
        ("1) Noji - Exhale", ("Noji", "Exhale")),
        ("[03] Noji - Exhale", ("Noji", "Exhale")),
        ("07 - Noji - Exhale", ("Noji", "Exhale")),
        ("00:00 Noji - Exhale", ("Noji", "Exhale")),
        ("[1:02:03] Noji - Exhale", ("Noji", "Exhale")),
        ("Noji - Exhale (12:34)", ("Noji", "Exhale")),
        ('Noji - "Exhale"', ("Noji", "Exhale")),
        ("Noji - Exhale 🌙", ("Noji", "Exhale")),
        ("2 Chainz - Birthday Song", ("2 Chainz", "Birthday Song")),
        ("(1999) Daydream", ("Channel", "(1999) Daydream")),
        ("1.5 Degrees", ("Channel", "1.5 Degrees")),
        ("Intro", ("Channel", "Intro")),
        ("lo-fi beats", ("Channel", "lo-fi beats")),
        ("Noji -", ("Channel", "Noji")),
        ("📚", ("Channel", "Untitled")),
    ],
)
def test_parse_artist_title(raw, expected):
    assert parse_artist_title(raw, "Channel") == expected


def test_channel_name_drops_topic_suffix():
    assert channel_name({"uploader": "Kupla - Topic"}) == "Kupla"
    assert channel_name({"channel": "Lofi Girl", "uploader": "x"}) == "Lofi Girl"
    assert channel_name({}) == "YouTube"


def test_split_release_from_chapters():
    release = build_release(chapter_info(), split=True, genre="Lo-Fi")
    assert release.is_split
    assert release.album == "lofi hip hop mix beats to relax/study to"
    assert release.album_artist == "Lofi Girl"
    assert release.year == "2024"
    assert release.genre == "Lo-Fi"
    assert release.compilation and release.gapless
    assert [(t.number, t.artist, t.title) for t in release.tracks] == [
        (1, "No Spirit", "Memories We Made"),
        (2, "S N U G, Mondo Loops", "Night Coffee"),
        (3, "Yasumu", "We Met"),
    ]
    assert [(t.start, t.end) for t in release.tracks] == [(0.0, 4.0), (4.0, 8.0), (8.0, 12.0)]
    assert release.duration == pytest.approx(12.0)


def test_intro_added_and_short_chapters_dropped():
    info = chapter_info()
    info["chapters"] = [
        {"start_time": 3.0, "end_time": 3.5, "title": "Blip - Too Short"},
        {"start_time": 3.5, "end_time": 8.0, "title": "Noji - Exhale"},
        {"start_time": 8.0, "end_time": 99.0, "title": "Sutton - Lunch Break"},
    ]
    release = build_release(info, split=True, genre="")
    assert [(t.title, t.start, t.end) for t in release.tracks] == [
        ("Intro", 0.0, 3.5),
        ("Exhale", 3.5, 8.0),
        ("Lunch Break", 8.0, 12.0),
    ]
    assert release.tracks[0].artist == "Lofi Girl"


def test_split_off_or_no_chapters_gives_one_track():
    for info, split in ((chapter_info(), False), ({**chapter_info(), "chapters": None}, True)):
        release = build_release(info, split=split, genre="Lo-Fi")
        assert not release.is_split
        (track,) = release.tracks
        assert (track.number, track.start, track.end) == (1, 0.0, 12.0)
        assert track.artist == "Lofi Girl"
        assert release.album == track.title == "lofi hip hop mix beats to relax/study to"
        assert not release.compilation and not release.gapless


def test_single_prefers_youtube_music_metadata():
    info = {
        **chapter_info(),
        "chapters": None,
        "title": "Owls of the Night (Official Audio)",
        "track": "Owls of the Night",
        "artists": ["Kupla"],
        "album": "Kingdom in Blue",
        "release_year": 2019,
    }
    release = build_release(info, split=True, genre="Lo-Fi")
    (track,) = release.tracks
    assert (track.artist, track.title) == ("Kupla", "Owls of the Night")
    assert (release.album, release.album_artist, release.year) == ("Kingdom in Blue", "Kupla", "2019")


def test_single_parses_artist_from_video_title():
    info = {**chapter_info(), "chapters": [], "title": "Kupla - Owls of the Night"}
    (track,) = build_release(info, split=True, genre="").tracks
    assert (track.artist, track.title) == ("Kupla", "Owls of the Night")
