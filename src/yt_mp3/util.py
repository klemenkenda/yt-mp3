"""Small helpers: filename sanitizing, app paths."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_NAME_LEN = 150


def sanitize_filename(name: str, fallback: str = "untitled") -> str:
    """Return a string safe to use as a Windows file or folder name (no extension)."""
    name = _INVALID_CHARS.sub("_", name or "")
    name = re.sub(r"\s+", " ", name).strip()
    name = name[:MAX_NAME_LEN].rstrip(" .")
    if not name:
        name = fallback
    if name.split(".")[0].upper() in _RESERVED:
        name = f"_{name}"
    return name


def app_dir() -> Path:
    """Directory containing the running executable (frozen) or the project root (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parents[2]


def resource_path(rel: str) -> Path:
    """Path to a bundled read-only resource (PyInstaller _MEIPASS aware)."""
    base = Path(getattr(sys, "_MEIPASS", app_dir()))
    return base / rel


def settings_dir() -> Path:
    return Path(os.environ.get("APPDATA", Path.home())) / "yt-mp3"
