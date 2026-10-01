import math
import threading
from fractions import Fraction

import av
import numpy as np
import pytest
from mutagen.id3 import ID3
from mutagen.mp3 import MP3

from yt_mp3.converter import Cancelled, to_mp3, write_tags


def make_sine(path, seconds=3.0, rate=48000, layout="mono"):
    """Write a sine tone to an Opus-in-WebM file (what YouTube usually serves)."""
    with av.open(str(path), "w", format="webm") as out:
        stream = out.add_stream("libopus", rate=rate, layout=layout)
        frame_size = 960
        total = int(seconds * rate)
        pts = 0
        while pts < total:
            n = min(frame_size, total - pts)
            t = (np.arange(pts, pts + n) / rate).astype(np.float32)
            samples = (0.3 * np.sin(2 * math.pi * 440 * t)).astype(np.float32).reshape(1, -1)
            frame = av.AudioFrame.from_ndarray(samples, format="flt", layout=layout)
            frame.sample_rate = rate
            frame.pts = pts
            frame.time_base = Fraction(1, rate)
            for p in stream.encode(frame):
                out.mux(p)
            pts += n
        for p in stream.encode(None):
            out.mux(p)


@pytest.mark.parametrize("kbps", [128, 192, 320])
def test_to_mp3(tmp_path, kbps):
    src = tmp_path / "in.webm"
    dst = tmp_path / "out.mp3"
    make_sine(src)
    to_mp3(src, dst, bitrate_kbps=kbps)

    assert dst.exists()
    assert not (tmp_path / "out.mp3.part").exists()
    info = MP3(str(dst)).info
    assert info.channels == 2
    assert info.sample_rate == 44100
    assert abs(info.length - 3.0) < 0.2
    assert info.bitrate == pytest.approx(kbps * 1000, rel=0.01)


def test_tags(tmp_path):
    src = tmp_path / "in.webm"
    dst = tmp_path / "out.mp3"
    make_sine(src, seconds=1)
    to_mp3(src, dst)
    jpeg = b"\xff\xd8\xff\xe0fakejpeg"
    write_tags(dst, title="Tïtle", artist="Artist", album="Album", track="3/10", cover_jpeg=jpeg)

    tags = ID3(str(dst))
    assert tags.version[:2] == (2, 3)
    assert str(tags["TIT2"]) == "Tïtle"
    assert str(tags["TPE1"]) == "Artist"
    assert str(tags["TALB"]) == "Album"
    assert str(tags["TRCK"]) == "3/10"
    assert tags.getall("APIC")[0].data == jpeg


def test_cancel_leaves_no_files(tmp_path):
    src = tmp_path / "in.webm"
    dst = tmp_path / "out.mp3"
    make_sine(src, seconds=1)
    ev = threading.Event()
    ev.set()
    with pytest.raises(Cancelled):
        to_mp3(src, dst, cancel=ev)
    assert list(tmp_path.iterdir()) == [src]
