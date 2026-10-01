"""Shared yt-dlp configuration."""
from __future__ import annotations

import shutil

from .util import app_dir


class QuietLogger:
    """yt-dlp logger that never touches stdout (which is None in a windowed exe).

    Warnings and errors are forwarded to `sink(level, msg)` if given.
    """

    def __init__(self, sink=None):
        self.sink = sink

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        if self.sink:
            self.sink("warning", msg)

    def error(self, msg):
        if self.sink:
            self.sink("error", msg)


def js_runtimes() -> dict:
    """JS runtimes for YouTube's signature challenges.

    A `deno.exe` placed next to the app wins; otherwise deno or node on PATH.
    With none available yt-dlp still works, with possibly fewer formats.
    """
    local = app_dir() / "deno.exe"
    if local.exists():
        return {"deno": {"path": str(local)}}
    runtimes = {}
    if shutil.which("deno"):
        runtimes["deno"] = {}
    if shutil.which("node"):
        runtimes["node"] = {}
    return runtimes or {"deno": {}}


def base_options(logger=None) -> dict:
    return {
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "logger": logger or QuietLogger(),
        "js_runtimes": js_runtimes(),
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
    }
