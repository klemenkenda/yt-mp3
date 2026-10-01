import queue
from pathlib import Path
from unittest import mock

from yt_mp3 import worker as w
from yt_mp3.resolver import Resolved, Track
from yt_mp3.worker import JobOptions, Worker, short_error


def run_job(tmp_path, tracks_by_url, fail_ids=(), existing=(), **opts):
    def fake_resolve(url, logger=None):
        if url not in tracks_by_url:
            raise RuntimeError("ERROR: [generic] 'bad' is not a valid URL")
        return tracks_by_url[url]

    def fake_download(url, tmp_dir, on_progress, cancel, logger):
        vid = url.rsplit("=", 1)[-1]
        if vid in fail_ids:
            raise RuntimeError(f"ERROR: [youtube] {vid:_<11}: Private video")
        on_progress(1.0)
        p = Path(tmp_dir) / f"{vid}.webm"
        p.write_bytes(b"x")
        return p, {"id": vid, "title": vid.upper(), "uploader": "U"}

    def fake_to_mp3(src, dst, kbps, cancel):
        Path(dst).write_bytes(b"mp3")

    for rel in existing:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"old")

    events = queue.Queue()
    with mock.patch.object(w, "resolve", fake_resolve), \
         mock.patch.object(w, "download_audio", fake_download), \
         mock.patch.object(w, "to_mp3", fake_to_mp3), \
         mock.patch.object(w, "write_tags"), \
         mock.patch.object(w, "fetch_cover", return_value=None):
        job = Worker(JobOptions(urls=list(opts.pop("urls", tracks_by_url)), out_dir=tmp_path, **opts), events)
        job.run()

    out = []
    while not events.empty():
        out.append(events.get())
    return out


def t(vid, title, pl=None, i=None):
    return Track(vid, f"https://www.youtube.com/watch?v={vid}", title, playlist_title=pl, playlist_index=i, playlist_count=2 if pl else None)


def final_status(events):
    status = {}
    for e in events:
        if e[0] == "track":
            status[e[1]] = e[2]
    return status


def test_mixed_job(tmp_path):
    tracks = {
        "v1": Resolved([t("a", "Song: A")], None),
        "pl": Resolved([t("b", "B", "My/List", 1), t("c", "C", "My/List", 2)], "My/List"),
    }
    events = run_job(tmp_path, tracks, fail_ids={"c"}, urls=["v1", "bad", "pl"])
    assert (tmp_path / "Song_ A.mp3").exists()
    assert (tmp_path / "My_List" / "B.mp3").exists()
    assert not (tmp_path / "My_List" / "C.mp3").exists()
    statuses = final_status(events)
    assert sorted(statuses.values()) == ["Done", "Done", "Error: 'bad' is not a valid URL", "Error: Private video"]
    assert events[-1] == ("done", "Finished. 2 downloaded, 2 failed.")


def test_skip_existing_and_duplicates(tmp_path):
    tracks = {"pl": Resolved([t("a", "Same", "P", 1), t("b", "Same", "P", 2)], "P")}
    events = run_job(tmp_path, tracks, existing=["P/Same.mp3"])
    assert (tmp_path / "P" / "Same.mp3").read_bytes() == b"old"
    assert (tmp_path / "P" / "Same [b].mp3").exists()
    assert events[-1] == ("done", "Finished. 1 downloaded, 1 skipped (already exist).")


def test_no_subfolder_overwrite(tmp_path):
    tracks = {"pl": Resolved([t("a", "A", "P", 1)], "P")}
    run_job(tmp_path, tracks, existing=["A.mp3"], playlist_subfolder=False, skip_existing=False)
    assert (tmp_path / "A.mp3").read_bytes() == b"mp3"


def test_short_error():
    assert short_error(RuntimeError("\x1b[0;31mERROR:\x1b[0m [youtube] jNQXAC9IVRw: Video unavailable\nmore")) == "Video unavailable"
