from unittest import mock

import pytest

from yt_mp3 import resolver


def fake_ydl(info):
    ydl = mock.MagicMock()
    ydl.__enter__.return_value.extract_info.return_value = info
    return mock.patch.object(resolver.yt_dlp, "YoutubeDL", return_value=ydl)


def test_single_video():
    info = {"id": "abc", "title": "Song", "uploader": "Band", "webpage_url": "https://youtu.be/abc"}
    with fake_ydl(info) as cls:
        r = resolver.resolve("https://www.youtube.com/watch?v=abc&list=PL1")
    opts = cls.call_args.args[0]
    assert opts["noplaylist"] is True
    assert r.playlist_title is None
    assert [t.video_id for t in r.tracks] == ["abc"]
    assert r.tracks[0].uploader == "Band"


def test_playlist():
    info = {
        "_type": "playlist",
        "title": "My Mix",
        "entries": [
            {"id": "a", "title": "A", "url": "https://www.youtube.com/watch?v=a", "channel": "C"},
            None,  # yt-dlp can yield None for unavailable entries
            {"id": "b", "title": None, "url": "b"},
        ],
    }
    with fake_ydl(info):
        r = resolver.resolve("https://www.youtube.com/playlist?list=PL1")
    assert r.playlist_title == "My Mix"
    assert [t.video_id for t in r.tracks] == ["a", "b"]
    a, b = r.tracks
    assert a.uploader == "C"
    assert (a.playlist_index, a.playlist_count) == (1, 2)
    assert b.title == "b"
    assert b.url == "https://www.youtube.com/watch?v=b"


@pytest.mark.network
def test_real_video():
    r = resolver.resolve("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert r.tracks[0].title == "Me at the zoo"
