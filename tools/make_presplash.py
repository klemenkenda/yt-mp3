"""Generate android/presplash.png: small app icon + app name on the app background.

python-for-android scales the presplash to fit the screen, so it is drawn on a full
portrait canvas (the icon then appears at a normal size instead of filling the width).
Needs Kivy (same Roboto font as the app):  python tools/make_presplash.py
"""
import os
from pathlib import Path

os.environ.setdefault("KIVY_NO_ARGS", "1")
from kivy.config import Config  # noqa: E402

Config.set("graphics", "window_state", "hidden")
from kivy.core.text import Label as CoreLabel  # noqa: E402
from kivy.core.window import Window  # noqa: E402, F401  (creates the GL context)
from kivy.graphics import Color, Rectangle  # noqa: E402
from kivy.uix.widget import Widget  # noqa: E402
from kivy.utils import get_color_from_hex  # noqa: E402

W, H = 1080, 1920
ICON = 220
BG = "#141218"  # = android.presplash_color in buildozer.spec
FG = "#E6E0E9"

root = Path(__file__).resolve().parents[1]
title = CoreLabel(text="YT to MP3", font_size=76, color=get_color_from_hex(FG))
title.refresh()
tw, th = title.texture.size

canvas = Widget(size=(W, H))
with canvas.canvas:
    Color(*get_color_from_hex(BG))
    Rectangle(pos=(0, 0), size=(W, H))
    Color(1, 1, 1, 1)
    gap = 48
    top = H / 2 + (ICON + gap + th) / 2
    Rectangle(source=str(root / "android" / "icon.png"), pos=((W - ICON) / 2, top - ICON), size=(ICON, ICON))
    Rectangle(texture=title.texture, pos=((W - tw) / 2, top - ICON - gap - th), size=(tw, th))

out = root / "android" / "presplash.png"
canvas.export_to_png(str(out))
print(f"wrote {out}")
