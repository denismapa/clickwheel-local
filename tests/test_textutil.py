import pytest

from clickwheel.textutil import clean_text, format_duration, safe_filename


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("lofi hip hop mix 📚 beats to relax/study to", "lofi hip hop mix beats to relax/study to"),
        ("Ｎｉｇｈｔ Ｄｒｉｖｅ ~ lofi hip hop mix ~", "Night Drive ~ lofi hip hop mix"),
        ("Best of lofi hip hop 2021 ✨ [beats to relax/study to]", "Best of lofi hip hop 2021 [beats to relax/study to]"),
        ("Lofi HipHop Mix 🌻 Happy Beats", "Lofi HipHop Mix Happy Beats"),
        ("coding 👩‍💻 session", "coding session"),
        ("tokyo nights 🇯🇵", "tokyo nights"),
        ("Track ☕️ (🌙)", "Track"),
        ("夜の散歩 – lofi", "夜の散歩 – lofi"),
        ("  spaced\tout\n title  ", "spaced out title"),
        ("", ""),
        (None, ""),
    ],
)
def test_clean_text(raw, expected):
    assert clean_text(raw) == expected


def test_safe_filename_strips_path_characters():
    assert safe_filename('AC/DC: "Back" <in> Black?') == "AC DC Back in Black"
    assert safe_filename("../../etc/passwd") == "etc passwd"


def test_safe_filename_truncates_on_utf8_boundary():
    name = safe_filename("夜" * 100, max_bytes=31)
    assert name == "夜" * 10
    assert len(name.encode()) <= 31


def test_safe_filename_fallback():
    assert safe_filename("📚✨", fallback="mix") == "mix"
    assert safe_filename("...") == "track"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0:00"), (7.4, "0:07"), (187, "3:07"), (6292, "1:44:52"), (88623, "24:37:03"), (None, "0:00")],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected
