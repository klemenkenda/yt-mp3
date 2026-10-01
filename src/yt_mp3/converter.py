"""Audio -> MP3 conversion with PyAV (bundled FFmpeg + LAME) and ID3 tagging with mutagen."""
from __future__ import annotations

import os
import threading
import urllib.request
from pathlib import Path

import av
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, TRCK, ID3NoHeaderError

SAMPLE_RATE = 44100
# LAME in the desktop PyAV wheels; shine (fixed-point) in the python-for-android FFmpeg build.
MP3_ENCODERS = ("libmp3lame", "libshine")


class Cancelled(Exception):
    """Raised when the user cancels an operation."""


def mp3_encoder() -> str:
    for name in MP3_ENCODERS:
        try:
            av.codec.Codec(name, "w")
            return name
        except Exception:
            continue
    raise RuntimeError("No MP3 encoder available in this FFmpeg build")


def to_mp3(
    src: str | os.PathLike,
    dst: str | os.PathLike,
    bitrate_kbps: int = 192,
    cancel: threading.Event | None = None,
) -> None:
    """Transcode the first audio stream of `src` into a CBR stereo MP3 at `dst`.

    Writes to `dst + '.part'` and renames on success so a partial file never
    looks finished.
    """
    dst = Path(dst)
    tmp = dst.with_name(dst.name + ".part")
    try:
        with av.open(str(src)) as inp, av.open(str(tmp), "w", format="mp3") as out:
            in_stream = inp.streams.audio[0]
            out_stream = out.add_stream(mp3_encoder(), rate=SAMPLE_RATE, layout="stereo")
            out_stream.bit_rate = bitrate_kbps * 1000
            out_stream.format = "s16p"
            resampler = av.AudioResampler(format="s16p", layout="stereo", rate=SAMPLE_RATE)

            def encode(frames):
                for f in frames:
                    for packet in out_stream.encode(f):
                        out.mux(packet)

            for frame in inp.decode(in_stream):
                if cancel is not None and cancel.is_set():
                    raise Cancelled()
                encode(resampler.resample(frame))
            encode(resampler.resample(None))
            for packet in out_stream.encode(None):
                out.mux(packet)
        os.replace(tmp, dst)
    finally:
        if tmp.exists():
            tmp.unlink()


def fetch_cover(video_id: str, timeout: float = 10) -> bytes | None:
    """Download a JPEG thumbnail for a YouTube video id, or None if unavailable."""
    for name in ("maxresdefault", "hqdefault"):
        url = f"https://i.ytimg.com/vi/{video_id}/{name}.jpg"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                data = resp.read()
                if data:
                    return data
        except Exception:
            continue
    return None


def write_tags(
    path: str | os.PathLike,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    track: str | None = None,
    cover_jpeg: bytes | None = None,
) -> None:
    """Write ID3v2.3 tags (best compatibility with Windows Explorer / WMP)."""
    try:
        tags = ID3(str(path))
    except ID3NoHeaderError:
        tags = ID3()
    if title:
        tags.setall("TIT2", [TIT2(encoding=3, text=title)])
    if artist:
        tags.setall("TPE1", [TPE1(encoding=3, text=artist)])
    if album:
        tags.setall("TALB", [TALB(encoding=3, text=album)])
    if track:
        tags.setall("TRCK", [TRCK(encoding=3, text=track)])
    if cover_jpeg:
        tags.setall("APIC", [APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_jpeg)])
    tags.save(str(path), v2_version=3)
