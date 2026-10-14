import pytest

from clickwheel.urls import UrlError, canonical_url, video_id

ID = "CLeZyIID9Bo"


@pytest.mark.parametrize(
    "raw",
    [
        f"https://www.youtube.com/watch?v={ID}",
        f"https://youtube.com/watch?v={ID}&t=120s",
        f"https://www.youtube.com/watch?v={ID}&list=PL123&index=4",
        f"https://m.youtube.com/watch?v={ID}",
        f"https://music.youtube.com/watch?v={ID}&si=abc",
        f"https://youtu.be/{ID}",
        f"https://youtu.be/{ID}?si=share",
        f"https://www.youtube.com/shorts/{ID}",
        f"https://www.youtube.com/live/{ID}?feature=share",
        f"https://www.youtube.com/embed/{ID}",
        f"https://www.youtube-nocookie.com/embed/{ID}",
        f"youtu.be/{ID}",
        f"  www.youtube.com/watch?v={ID}  ",
        f"http://www.youtube.com/watch?v={ID}",
        f"HTTPS://WWW.YOUTUBE.COM/watch?v={ID}",
    ],
)
def test_accepts_video_links(raw):
    assert video_id(raw) == ID
    assert canonical_url(raw) == f"https://www.youtube.com/watch?v={ID}"


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "lofi hip hop",
        f"https://vimeo.com/{ID}",
        f"https://youtube.com.evil.example/watch?v={ID}",
        f"https://evilyoutube.com/watch?v={ID}",
        f"https://youtube.com@evil.example/watch?v={ID}",
        f"https://user:pass@www.youtube.com/watch?v={ID}",
        f"javascript:alert(1)//youtube.com/watch?v={ID}",
        f"ftp://www.youtube.com/watch?v={ID}",
        f"file:///etc/passwd?v={ID}",
        "https://www.youtube.com/watch?v=short",
        "https://www.youtube.com/watch?v=CLeZyIID9Bo123",
        "https://www.youtube.com/watch?v=CLeZy%20ID9Bo",
        "https://www.youtube.com/@LofiGirl",
        "https://www.youtube.com/",
        "https://youtu.be/",
        "https://[::1",
        "https://www.youtube.com/watch?v=" + "a" * 3000,
    ],
)
def test_rejects_everything_else(raw):
    with pytest.raises(UrlError):
        video_id(raw)


def test_playlist_has_its_own_message():
    with pytest.raises(UrlError) as err:
        video_id("https://www.youtube.com/playlist?list=PLOzDu-MXXLliO9fBNZOQTBDddoA3FzZUo")
    assert err.value.title == "PLAYLIST LINK."
