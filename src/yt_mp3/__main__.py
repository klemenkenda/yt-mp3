import os
import sys

# A windowed (no console) exe has no stdout/stderr; some libraries write to them anyway.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")


def headless(out_dir: str, urls: list[str]) -> int:
    """`yt-mp3.exe --headless OUT_DIR URL...` - no GUI, events logged to OUT_DIR/yt-mp3.log.

    Used to smoke-test the frozen exe; also handy for scripting.
    """
    import queue
    from pathlib import Path

    from yt_mp3.worker import JobOptions, Worker

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    events = queue.Queue()
    worker = Worker(JobOptions(urls=urls, out_dir=out), events)
    worker.start()
    worker.join()
    failed = False
    with open(out / "yt-mp3.log", "w", encoding="utf-8") as log:
        while not events.empty():
            e = events.get()
            if e[0] == "track" and e[2].startswith("Error"):
                failed = True
            if not (e[0] == "track" and e[2].startswith("Downloading ")) and e[0] != "overall":
                print(*e, sep="\t", file=log)
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "--headless":
        sys.exit(headless(sys.argv[2], sys.argv[3:]))
    from yt_mp3.gui import main

    main()
