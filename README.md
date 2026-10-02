# YT to MP3

A small Windows desktop app that downloads YouTube videos and playlists as MP3 files.
It ships as a single `yt-mp3.exe` (~52 MB). Users don't need Python, ffmpeg or anything else installed.

## Usage
1. Paste one or more YouTube links into the box, one per line. Single videos and playlists can be mixed.
2. Choose the destination folder.
3. Click **Download MP3**.

Options:
- **Quality**: 128, 192 (default), 256 or 320 kbps CBR.
- **Playlists into their own folder**: each playlist goes to `<destination>\<playlist title>\`.
- **Skip existing files**: re-running a playlist only fetches new tracks. Turn it off to overwrite.

Each MP3 gets ID3v2.3 tags (title, artist/uploader, album = playlist title, track number) and the video thumbnail as cover art.
Unavailable or private videos are marked as errors, and the rest of the batch continues.
Settings are remembered in `%APPDATA%\yt-mp3\settings.json`.

A watch link that includes `&list=...` downloads only that video. To download the whole playlist, use the playlist link (`youtube.com/playlist?list=...`).

### Headless mode
```
yt-mp3.exe --headless "D:\Music" https://www.youtube.com/playlist?list=...
```
This runs without a window, uses the default settings (192 kbps, subfolders, skip existing) and writes a log to `<folder>\yt-mp3.log`. The exit code is 1 if any track failed.

## Android app
`yt-mp3.apk` is on the [Releases](https://github.com/klemenkenda/yt-mp3/releases) page. Install it on the phone and allow installing from unknown sources when asked. It's sideload-only: Google Play doesn't allow YouTube downloaders. It requires Android 7.0 or newer on a 64-bit ARM phone.

- Paste links (or use **Paste**), or share straight from the YouTube app: **Share → YT to MP3**.
- MP3s are saved to `Music/<folder>` (default `Music/YT-MP3`) and show up in music players right away.
- The **Library** tab lists the downloaded MP3s (playlist folders first). Tap a file to play it in your music app.
- It has the same options as the desktop app. Pressing Back while downloading sends the app to the background instead of closing it. Keep the app open for long playlists, because Android may stop background apps.
- MP3 encoding uses FFmpeg's `libshine` encoder (the desktop app uses LAME).

## How it works
| Step | Library |
|---|---|
| Resolve links and download the best audio-only stream | [yt-dlp](https://github.com/yt-dlp/yt-dlp), used as a library |
| Decode the audio and encode it to MP3 in-process | [PyAV](https://github.com/PyAV-Org/PyAV). Its wheel bundles the FFmpeg libraries with LAME, so no `ffmpeg.exe` is needed |
| ID3 tags and cover art | [mutagen](https://github.com/quodlibet/mutagen) |
| GUI | [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) |
| Packaging | PyInstaller, one file, windowed |

Code lives in `src/yt_mp3/`:
- `resolver.py`: URL → tracks
- `downloader.py`: track → temp audio file
- `converter.py`: audio → MP3, plus tags
- `worker.py`: the background job, which sends events to the GUI through a queue
- `gui.py`: the main window

## Optional: JavaScript runtime (deno)
YouTube increasingly relies on JavaScript challenges. Without a JS runtime, yt-dlp still works, but it logs a deprecation warning and some formats may be missing.
To make the app more robust, put [`deno.exe`](https://github.com/denoland/deno/releases) (~100 MB) **next to `yt-mp3.exe`**, and the app will use it automatically.
A `deno` or `node` already on `PATH` is picked up too.

## Building
Requires Python 3.10+ on the build machine.
```powershell
.\build.ps1            # creates .venv, installs deps, runs tests, builds dist\yt-mp3.exe
.\build.ps1 -SkipTests
```

### Android APK
This needs only Docker Desktop: Buildozer, the Android SDK/NDK and JDK all run in the `kivy/buildozer` container.
```powershell
.\android\build.ps1          # signed release APK -> android\bin\
.\android\build.ps1 -Debug   # debug APK
```
- **First build:** it downloads about 3 GB into the Docker volume `yt-mp3-buildozer` and takes 30–60 minutes. Later builds are much faster.
- **Signing:** the first release build creates a signing key in `%USERPROFILE%\.yt-mp3-android\` (`release.keystore` and `keystore.pass`, both outside the repo). **Back them up.** Every app update must be signed with the same key, or Android refuses to install it over the old version.
- **Code layout:** `android/main.py` is the Kivy UI. The build script copies the shared core (`src/yt_mp3/`, without the desktop GUI) next to it.
- **Testing the UI on a PC:** `python android/main.py` (needs `pip install kivy`).
- **Icons:** Google's [Material Icons](https://github.com/google/material-design-icons) font (`android/MaterialIcons-Regular.ttf`, Apache 2.0). Regenerate the splash screen with `python tools/make_presplash.py`.

**When downloads start failing**, YouTube has usually changed something. Re-run `.\build.ps1`: it always installs the newest yt-dlp. Then replace the exe.

## Development
```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
$env:PYTHONPATH = "src"; .\.venv\Scripts\python -m yt_mp3   # run the app
.\.venv\Scripts\python -m pytest -m "not network"          # offline tests
.\.venv\Scripts\python -m pytest                            # incl. a live YouTube test
```
To regenerate the icon, run `python tools/make_icon.py`.

## Notes
- Antivirus software sometimes flags one-file PyInstaller exes (false positive). Building it yourself, or switching the spec to one-folder mode, usually helps.
- Only download content you have the right to download. See the YouTube Terms of Service.
