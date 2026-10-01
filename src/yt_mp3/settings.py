"""Persisted user preferences (%APPDATA%\\yt-mp3\\settings.json)."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .util import settings_dir

BITRATES = (128, 192, 256, 320)


@dataclass
class Settings:
    out_dir: str = str(Path.home() / "Music")
    bitrate_kbps: int = 192
    playlist_subfolder: bool = True
    skip_existing: bool = True

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads((settings_dir() / "settings.json").read_text(encoding="utf-8"))
            known = {f.name for f in fields(cls)}
            s = cls(**{k: v for k, v in data.items() if k in known})
        except Exception:
            s = cls()
        if s.bitrate_kbps not in BITRATES:
            s.bitrate_kbps = 192
        return s

    def save(self) -> None:
        try:
            d = settings_dir()
            d.mkdir(parents=True, exist_ok=True)
            (d / "settings.json").write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        except OSError:
            pass
