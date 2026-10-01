"""Turn a user-supplied URL into a list of tracks to download (yt-dlp, metadata only)."""
from __future__ import annotations

from dataclasses import dataclass

import yt_dlp

from .ytdl import base_options


@dataclass
class Track:
    video_id: str
    url: str
    title: str
    uploader: str | None = None
    playlist_title: str | None = None
    playlist_index: int | None = None
    playlist_count: int | None = None


@dataclass
class Resolved:
    tracks: list[Track]
    playlist_title: str | None  # None for a single video


def _video_url(entry: dict) -> str:
    url = entry.get("url") or ""
    if url.startswith("http"):
        return url
    return f"https://www.youtube.com/watch?v={entry['id']}"


def resolve(url: str, logger=None) -> Resolved:
    """Resolve a video or playlist URL.

    A watch URL that also carries `&list=` resolves to the single video
    (`noplaylist`); a pure playlist URL resolves to all its entries.
    """
    opts = base_options(logger) | {"extract_flat": "in_playlist", "noplaylist": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info.get("_type") == "playlist" or "entries" in info:
        title = info.get("title") or info.get("id") or "Playlist"
        entries = [e for e in (info.get("entries") or []) if e and e.get("id")]
        count = len(entries)
        tracks = [
            Track(
                video_id=e["id"],
                url=_video_url(e),
                title=e.get("title") or e["id"],
                uploader=e.get("uploader") or e.get("channel"),
                playlist_title=title,
                playlist_index=i,
                playlist_count=count,
            )
            for i, e in enumerate(entries, start=1)
        ]
        return Resolved(tracks, title)

    track = Track(
        video_id=info["id"],
        url=info.get("webpage_url") or _video_url(info),
        title=info.get("title") or info["id"],
        uploader=info.get("uploader") or info.get("channel"),
    )
    return Resolved([track], None)
