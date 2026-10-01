"""YT to MP3 - Android app (Kivy). Shares the core pipeline with the desktop app (yt_mp3 package).

On a PC this also runs for UI development:  python android/main.py
"""
import os
import queue
import re
import sys
import tempfile
from pathlib import Path

from kivy.utils import platform

ANDROID = platform == "android"
if not ANDROID:  # dev: use the package from ../src
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from kivy.app import App  # noqa: E402
from kivy.clock import Clock  # noqa: E402
from kivy.core.clipboard import Clipboard  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.lang import Builder  # noqa: E402
from kivy.storage.jsonstore import JsonStore  # noqa: E402

BITRATES = ("128 kbps", "192 kbps", "256 kbps", "320 kbps")
URL_RE = re.compile(r"https?://\S+")

GREEN = (0.40, 0.78, 0.40, 1)
RED = (0.93, 0.38, 0.38, 1)
GRAY = (0.6, 0.6, 0.6, 1)
WHITE = (0.92, 0.92, 0.92, 1)

KV = """
#:import dp kivy.metrics.dp

<Btn@Button>:
    background_normal: ''
    background_color: (0.12, 0.42, 0.65, 1) if self.state == 'normal' else (0.09, 0.32, 0.5, 1)
    background_disabled_normal: ''
    disabled_color: 1, 1, 1, 0.4
    font_size: '16sp'

<TrackRow@BoxLayout>:
    title: ''
    status: ''
    color: 1, 1, 1, 1
    size_hint_y: None
    height: dp(44)
    padding: dp(10), 0
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: 1, 1, 1, 0.06
        Rectangle:
            pos: self.x, self.y
            size: self.width, dp(1)
    Label:
        text: root.title
        color: root.color
        font_size: '14sp'
        text_size: self.width, None
        shorten: True
        shorten_from: 'right'
        halign: 'left'
    Label:
        text: root.status
        color: root.color
        font_size: '13sp'
        size_hint_x: None
        width: dp(120)
        text_size: self.width, None
        shorten: True
        halign: 'right'

<Check@BoxLayout>:
    text: ''
    active: True
    size_hint_y: None
    height: dp(40)
    CheckBox:
        size_hint_x: None
        width: dp(40)
        active: root.active
        on_active: root.active = self.active
    Label:
        text: root.text
        font_size: '15sp'
        text_size: self.size
        halign: 'left'
        valign: 'middle'

BoxLayout:
    orientation: 'vertical'
    padding: dp(14), dp(10)
    spacing: dp(8)
    canvas.before:
        Color:
            rgba: 0.11, 0.11, 0.12, 1
        Rectangle:
            pos: self.pos
            size: self.size

    Label:
        text: '[b]YT to MP3[/b]'
        markup: True
        font_size: '22sp'
        size_hint_y: None
        height: dp(40)
        text_size: self.size
        halign: 'left'
        valign: 'middle'

    TextInput:
        id: urls
        hint_text: 'Paste YouTube links (video or playlist), one per line'
        size_hint_y: None
        height: dp(110)
        font_size: '14sp'
        background_color: 0.17, 0.17, 0.18, 1
        foreground_color: 1, 1, 1, 1
        hint_text_color: 0.6, 0.6, 0.6, 1
        cursor_color: 1, 1, 1, 1

    BoxLayout:
        size_hint_y: None
        height: dp(42)
        spacing: dp(8)
        Btn:
            text: 'Paste'
            on_release: app.paste()
        Btn:
            text: 'Clear'
            background_color: 0.25, 0.25, 0.27, 1
            on_release: urls.text = ''

    BoxLayout:
        size_hint_y: None
        height: dp(42)
        spacing: dp(8)
        Label:
            text: 'Save to  Music /'
            font_size: '15sp'
            size_hint_x: None
            width: dp(120)
            text_size: self.size
            halign: 'left'
            valign: 'middle'
        TextInput:
            id: folder
            multiline: False
            font_size: '15sp'
            padding: dp(8), dp(10)
            background_color: 0.17, 0.17, 0.18, 1
            foreground_color: 1, 1, 1, 1
            cursor_color: 1, 1, 1, 1

    BoxLayout:
        size_hint_y: None
        height: dp(42)
        spacing: dp(8)
        Label:
            text: 'Quality'
            font_size: '15sp'
            size_hint_x: None
            width: dp(120)
            text_size: self.size
            halign: 'left'
            valign: 'middle'
        Spinner:
            id: bitrate
            values: app.bitrates
            font_size: '15sp'
            background_normal: ''
            background_color: 0.25, 0.25, 0.27, 1

    Check:
        id: subfolder
        text: 'Playlists into their own folder'
    Check:
        id: skip
        text: 'Skip existing files'

    BoxLayout:
        size_hint_y: None
        height: dp(50)
        spacing: dp(8)
        Btn:
            id: start
            text: 'Download MP3'
            bold: True
            on_release: app.start()
        Btn:
            id: cancel
            text: 'Cancel'
            disabled: True
            size_hint_x: 0.5
            background_color: (0.7, 0.23, 0.23, 1) if self.state == 'normal' else (0.55, 0.18, 0.18, 1)
            on_release: app.cancel()

    RecycleView:
        id: tracks
        viewclass: 'TrackRow'
        canvas.before:
            Color:
                rgba: 0.15, 0.15, 0.16, 1
            Rectangle:
                pos: self.pos
                size: self.size
        RecycleBoxLayout:
            default_size: None, dp(44)
            default_size_hint: 1, None
            size_hint_y: None
            height: self.minimum_height
            orientation: 'vertical'

    ProgressBar:
        id: progress
        max: 1
        value: 0
        size_hint_y: None
        height: dp(16)

    Label:
        id: status
        text: 'Ready.'
        font_size: '14sp'
        size_hint_y: None
        height: dp(36)
        text_size: self.size
        halign: 'left'
        valign: 'middle'
        shorten: True
"""


class AndroidBridge:
    """Thin pyjnius wrapper; only used on Android, always from the Kivy (UI) thread."""

    def __init__(self, app):
        from android import activity, mActivity
        from jnius import autoclass

        self.activity = mActivity
        self.Intent = autoclass("android.content.Intent")
        self.Scanner = autoclass("android.media.MediaScannerConnection")
        Environment = autoclass("android.os.Environment")
        self.sdk = autoclass("android.os.Build$VERSION").SDK_INT
        self.music_dir = Path(
            Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC).getAbsolutePath())

        # temp files in the app cache; CA bundle for HTTPS
        cache = mActivity.getCacheDir().getAbsolutePath()
        os.environ["TMPDIR"] = cache
        tempfile.tempdir = cache
        try:
            import certifi
            os.environ.setdefault("SSL_CERT_FILE", certifi.where())
        except ImportError:
            pass

        self._request_permissions()
        activity.bind(on_new_intent=lambda intent: Clock.schedule_once(lambda dt: self.handle_intent(app, intent)))
        self.handle_intent(app, mActivity.getIntent())

    def _request_permissions(self):
        from android.permissions import request_permissions

        if self.sdk >= 33:
            perms = ["android.permission.READ_MEDIA_AUDIO"]
        elif self.sdk >= 29:
            perms = ["android.permission.READ_EXTERNAL_STORAGE"]
        else:
            perms = ["android.permission.READ_EXTERNAL_STORAGE", "android.permission.WRITE_EXTERNAL_STORAGE"]
        request_permissions(perms)

    def handle_intent(self, app, intent):
        """Links shared from the YouTube app (Share -> YT to MP3)."""
        if intent is None or intent.getAction() != self.Intent.ACTION_SEND:
            return
        text = intent.getStringExtra(self.Intent.EXTRA_TEXT) or ""
        intent.setAction(self.Intent.ACTION_MAIN)  # handle once
        app.add_urls(URL_RE.findall(text))

    def scan(self, path):
        """Make a new file visible to music players immediately."""
        self.Scanner.scanFile(self.activity, [str(path)], None, None)

    def keep_screen_on(self, on):
        from android.runnable import run_on_ui_thread
        from jnius import autoclass

        flag = autoclass("android.view.WindowManager$LayoutParams").FLAG_KEEP_SCREEN_ON

        @run_on_ui_thread
        def apply():
            window = self.activity.getWindow()
            window.addFlags(flag) if on else window.clearFlags(flag)

        apply()

    def to_background(self):
        self.activity.moveTaskToBack(True)


class YtMp3App(App):
    bitrates = BITRATES

    def build(self):
        self.title = "YT to MP3"
        self.events = queue.Queue()
        self.worker = None
        self.rows = {}  # worker key -> index in RecycleView data
        self.root = Builder.load_string(KV)
        self.store = JsonStore(os.path.join(self.user_data_dir, "settings.json"))
        s = self.store.get("settings") if self.store.exists("settings") else {}
        ids = self.root.ids
        ids.folder.text = s.get("folder", "YT-MP3")
        ids.bitrate.text = s.get("bitrate", "192 kbps")
        ids.subfolder.active = s.get("subfolder", True)
        ids.skip.active = s.get("skip", True)

        self.bridge = AndroidBridge(self) if ANDROID else None
        Window.bind(on_keyboard=self._on_key)
        Clock.schedule_interval(self._poll, 0.1)
        return self.root

    # -- helpers --------------------------------------------------------------

    @property
    def running(self):
        return self.worker is not None and self.worker.is_alive()

    def music_dir(self) -> Path:
        return self.bridge.music_dir if self.bridge else Path.home() / "Music"

    def add_urls(self, urls):
        box = self.root.ids.urls
        existing = box.text.strip()
        new = [u for u in urls if u not in existing]
        if new:
            box.text = "\n".join(filter(None, [existing, *new]))

    def paste(self):
        self.add_urls(URL_RE.findall(Clipboard.paste() or ""))

    def _save_settings(self):
        ids = self.root.ids
        self.store.put("settings", folder=ids.folder.text.strip(), bitrate=ids.bitrate.text,
                       subfolder=ids.subfolder.active, skip=ids.skip.active)

    def _on_key(self, window, key, *args):
        if key == 27 and self.running and self.bridge:  # Back: keep downloading in the background
            self.bridge.to_background()
            return True
        return False

    # -- job ------------------------------------------------------------------

    def start(self):
        from yt_mp3.util import sanitize_filename
        from yt_mp3.worker import JobOptions, Worker

        ids = self.root.ids
        urls = [u.strip() for u in ids.urls.text.splitlines() if u.strip()]
        if not urls:
            ids.status.text = "Paste at least one YouTube link."
            return
        out = self.music_dir() / sanitize_filename(ids.folder.text.strip() or "YT-MP3", "YT-MP3")
        try:
            out.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            ids.status.text = f"Cannot create {out}: {e}"
            return
        self._save_settings()

        ids.tracks.data = []
        self.rows.clear()
        ids.progress.value = 0
        self.worker = Worker(
            JobOptions(
                urls=urls,
                out_dir=out,
                bitrate_kbps=int(ids.bitrate.text.split()[0]),
                playlist_subfolder=ids.subfolder.active,
                skip_existing=ids.skip.active,
                on_saved=lambda p: self.events.put(("saved", p)),
            ),
            self.events,
        )
        ids.start.disabled = True
        ids.cancel.disabled = False
        ids.status.text = "Starting..."
        if self.bridge:
            self.bridge.keep_screen_on(True)
        self.worker.start()

    def cancel(self):
        if self.worker:
            self.worker.cancel.set()
            self.root.ids.cancel.disabled = True
            self.root.ids.status.text = "Cancelling..."

    def on_stop(self):
        if self.worker:
            self.worker.cancel.set()

    # -- worker events (UI thread) --------------------------------------------

    def _poll(self, dt):
        rv = self.root.ids.tracks
        changed = False
        try:
            for _ in range(500):
                changed |= self._handle(self.events.get_nowait())
        except queue.Empty:
            pass
        if changed:
            rv.refresh_from_data()

    def _handle(self, event):
        ids = self.root.ids
        kind = event[0]
        if kind == "add":
            _, key, title = event
            self.rows[key] = len(ids.tracks.data)
            ids.tracks.data.append({"title": title, "status": "", "color": WHITE})
            return True
        if kind == "track":
            _, key, text = event
            idx = self.rows.get(key)
            if idx is None:
                return False
            color = RED if text.startswith("Error") else GREEN if text == "Done" else \
                GRAY if text.startswith(("Skipped", "Cancelled")) else WHITE
            row = ids.tracks.data[idx]
            row["status"], row["color"] = text, color
            return True
        if kind == "overall":
            _, frac, text = event
            if frac is not None:
                ids.progress.value = frac
            if text:
                ids.status.text = text
        elif kind == "saved":
            if self.bridge:
                self.bridge.scan(event[1])
        elif kind == "done":
            ids.status.text = event[1]
            ids.start.disabled = False
            ids.cancel.disabled = True
            if self.bridge:
                self.bridge.keep_screen_on(False)
        return False


if __name__ == "__main__":
    YtMp3App().run()
