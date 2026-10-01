"""Background job: resolve URLs, then download + convert each track sequentially.

The worker never touches the GUI. It reports through `events` (a queue.Queue)
with tuples:

    ("log", text)
    ("add", key, title)                 new row in the track list
    ("track", key, status_text)         row status update
    ("overall", fraction, text)         overall progress 0..1 + status line
    ("done", summary_text)
"""
from __future__ import annotations

import itertools
import queue
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from .converter import Cancelled, fetch_cover, to_mp3, write_tags
from .downloader import download_audio
from .resolver import Track, resolve
from .util import sanitize_filename
from .ytdl import QuietLogger

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def short_error(exc: BaseException) -> str:
    msg = _ANSI.sub("", str(exc)).strip() or type(exc).__name__
    msg = re.sub(r"^ERROR:\s*", "", msg)
    msg = re.sub(r"^\[[\w:]+\]\s*", "", msg)  # "[youtube] "
    msg = re.sub(r"^[\w-]{11}:\s*", "", msg)  # video id
    return msg.splitlines()[0][:200]


@dataclass
class JobOptions:
    urls: list[str]
    out_dir: Path
    bitrate_kbps: int = 192
    playlist_subfolder: bool = True
    skip_existing: bool = True


class Worker(threading.Thread):
    def __init__(self, options: JobOptions, events: queue.Queue):
        super().__init__(daemon=True)
        self.opts = options
        self.events = events
        self.cancel = threading.Event()
        self._keys = itertools.count()
        self._used_names: set[Path] = set()
        self.logger = QuietLogger(lambda level, msg: self._emit("log", f"{level}: {_ANSI.sub('', msg)}"))

    def _emit(self, *event):
        self.events.put(event)

    # -- main -----------------------------------------------------------------

    def run(self):
        tmp_dir = Path(tempfile.mkdtemp(prefix="yt-mp3-"))
        counts = {"done": 0, "skipped": 0, "failed": 0}
        try:
            jobs = self._resolve_all(counts)
            total = len(jobs)
            finished = set()
            for n, (key, track) in enumerate(jobs):
                if self.cancel.is_set():
                    break
                base = n / total
                self._emit("overall", base, f"Track {n + 1} of {total}: {track.title}")
                try:
                    result = self._process(key, track, tmp_dir, lambda f: self._emit("overall", base + f / total, None))
                    counts[result] += 1
                except Cancelled:
                    break
                except Exception as e:
                    counts["failed"] += 1
                    self._emit("track", key, f"Error: {short_error(e)}")
                    self._emit("log", f"{track.title}: {short_error(e)}")
                finished.add(key)
            if self.cancel.is_set():
                for key, _ in jobs:
                    if key not in finished:
                        self._emit("track", key, "Cancelled")
            else:
                self._emit("overall", 1.0, None)
        except Exception as e:  # unexpected - don't let the thread die silently
            self._emit("log", f"Unexpected error: {short_error(e)}")
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            parts = [f"{counts['done']} downloaded"]
            if counts["skipped"]:
                parts.append(f"{counts['skipped']} skipped (already exist)")
            if counts["failed"]:
                parts.append(f"{counts['failed']} failed")
            prefix = "Cancelled. " if self.cancel.is_set() else "Finished. "
            self._emit("done", prefix + ", ".join(parts) + ".")

    def _resolve_all(self, counts) -> list[tuple[int, Track]]:
        jobs = []
        for url in self.opts.urls:
            if self.cancel.is_set():
                break
            self._emit("overall", 0.0, f"Reading {url} ...")
            try:
                resolved = resolve(url, self.logger)
            except Exception as e:
                key = next(self._keys)
                counts["failed"] += 1
                self._emit("add", key, url)
                self._emit("track", key, f"Error: {short_error(e)}")
                continue
            for track in resolved.tracks:
                key = next(self._keys)
                self._emit("add", key, track.title)
                self._emit("track", key, "Queued")
                jobs.append((key, track))
        return jobs

    # -- per track ------------------------------------------------------------

    def _target_path(self, track: Track) -> Path:
        out_dir = self.opts.out_dir
        if track.playlist_title and self.opts.playlist_subfolder:
            out_dir = out_dir / sanitize_filename(track.playlist_title, "Playlist")
        name = sanitize_filename(track.title, track.video_id)
        path = out_dir / f"{name}.mp3"
        if path in self._used_names:  # duplicate title within this job
            path = out_dir / f"{name} [{track.video_id}].mp3"
        self._used_names.add(path)
        return path

    def _process(self, key: int, track: Track, tmp_dir: Path, on_fraction) -> str:
        dst = self._target_path(track)
        if self.opts.skip_existing and dst.exists():
            self._emit("track", key, "Skipped (exists)")
            return "skipped"

        def progress(f):
            self._emit("track", key, f"Downloading {f:.0%}")
            on_fraction(f * 0.8)

        self._emit("track", key, "Downloading")
        src, info = download_audio(track.url, tmp_dir, progress, self.cancel, self.logger)
        try:
            self._emit("track", key, "Converting")
            on_fraction(0.85)
            dst.parent.mkdir(parents=True, exist_ok=True)
            to_mp3(src, dst, self.opts.bitrate_kbps, self.cancel)
        finally:
            src.unlink(missing_ok=True)

        track_no = None
        if track.playlist_index:
            track_no = f"{track.playlist_index}/{track.playlist_count}"
        try:
            write_tags(
                dst,
                title=info.get("title") or track.title,
                artist=info.get("artist") or info.get("uploader") or track.uploader,
                album=track.playlist_title or info.get("album"),
                track=track_no,
                cover_jpeg=fetch_cover(info.get("id") or track.video_id),
            )
        except Exception as e:  # tags are nice-to-have
            self._emit("log", f"{track.title}: could not write tags ({short_error(e)})")
        self._emit("track", key, "Done")
        return "done"
