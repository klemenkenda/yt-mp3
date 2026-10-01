"""Download the best audio-only stream of a single video (no post-processing)."""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable

import yt_dlp

from .converter import Cancelled
from .ytdl import base_options


def download_audio(
    url: str,
    tmp_dir: Path,
    on_progress: Callable[[float], None] | None = None,
    cancel: threading.Event | None = None,
    logger=None,
) -> tuple[Path, dict]:
    """Download audio to `tmp_dir`. Returns (file path, yt-dlp info dict).

    `on_progress` receives a fraction in [0, 1].
    """

    def hook(d):
        if cancel is not None and cancel.is_set():
            raise Cancelled()
        if on_progress and d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if total:
                on_progress(min(d.get("downloaded_bytes", 0) / total, 1.0))

    opts = base_options(logger) | {
        "format": "bestaudio/best",
        "outtmpl": str(tmp_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "progress_hooks": [hook],
        "overwrites": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        if cancel is not None and cancel.is_set():
            raise Cancelled() from e
        raise

    if cancel is not None and cancel.is_set():
        raise Cancelled()
    downloads = info.get("requested_downloads") or []
    path = Path(downloads[0]["filepath"]) if downloads else None
    if path is None or not path.exists():
        raise RuntimeError("Download finished but the file was not found")
    return path, info
