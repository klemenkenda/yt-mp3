"""Material-style icons rasterized in pure Python (no Pillow) as PNG data for tk.PhotoImage.

Shapes are defined on Material's 24x24 grid; each icon is a list of (color, shape) layers,
later layers painted over earlier ones, with supersampling for antialiasing.
"""
from __future__ import annotations

import base64
import math
import struct
import zlib


# -- shapes: functions of (x, y) on the 24x24 grid -> bool ----------------------

def circle(cx, cy, r):
    return lambda x, y: (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def ring(cx, cy, r, w):
    return lambda x, y: abs(math.hypot(x - cx, y - cy) - r) <= w / 2


def _seg_dist(x, y, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    t = max(0.0, min(1.0, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy or 1)))
    return math.hypot(x - x1 - t * dx, y - y1 - t * dy)


def stroke(points, w):
    """Polyline with round caps/joins."""
    segs = list(zip(points, points[1:]))
    return lambda x, y: any(_seg_dist(x, y, *a, *b) <= w / 2 for a, b in segs)


def rrect(x1, y1, x2, y2, r):
    def inside(x, y):
        if not (x1 <= x <= x2 and y1 <= y <= y2):
            return False
        cx, cy = min(max(x, x1 + r), x2 - r), min(max(y, y1 + r), y2 - r)
        return (x - cx) ** 2 + (y - cy) ** 2 <= r * r
    return inside


def rrect_stroke(x1, y1, x2, y2, r, w):
    outer = rrect(x1 - w / 2, y1 - w / 2, x2 + w / 2, y2 + w / 2, r + w / 2)
    inner = rrect(x1 + w / 2, y1 + w / 2, x2 - w / 2, y2 - w / 2, max(r - w / 2, 0))
    return lambda x, y: outer(x, y) and not inner(x, y)


def arc(cx, cy, r, w, start, extent):
    """Arc stroke; angles in degrees, clockwise from 12 o'clock, round caps."""
    def pt(a):
        a = math.radians(a)
        return cx + r * math.sin(a), cy - r * math.cos(a)
    caps = [circle(*pt(start), w / 2), circle(*pt(start + extent), w / 2)]

    def inside(x, y):
        if abs(math.hypot(x - cx, y - cy) - r) <= w / 2:
            a = (math.degrees(math.atan2(x - cx, cy - y)) - start) % 360
            if a <= extent:
                return True
        return any(c(x, y) for c in caps)
    return inside


def polygon(points):
    n = len(points)

    def inside(x, y):
        c = False
        for i in range(n):
            (xa, ya), (xb, yb) = points[i], points[i - 1]
            if (ya > y) != (yb > y) and x < (xb - xa) * (y - ya) / (yb - ya) + xa:
                c = not c
        return c
    return inside


# -- icon definitions: name -> layers, colors are role names --------------------

def _glyph(name, fg):
    """Single-color glyphs."""
    shapes = {
        "close": [stroke([(6, 6), (18, 18)], 2), stroke([(18, 6), (6, 18)], 2)],
        "paste": [rrect_stroke(5, 4.5, 19, 21, 2, 2), rrect(8.5, 2, 15.5, 7, 1.2)],
        "folder": [rrect(2, 4, 11, 9, 1.5), rrect(2, 6.5, 22, 20, 2)],
        "music": [circle(9.5, 17, 4), rrect(11.5, 3, 13.5, 17, 0), rrect(11.5, 3, 18, 7, 0.5)],
        "download": [stroke([(12, 4), (12, 15)], 2.2), stroke([(7, 10.5), (12, 15.5), (17, 10.5)], 2.2),
                     stroke([(5, 20), (19, 20)], 2.2)],
        "library": [rrect_stroke(7.5, 2.5, 21.5, 16.5, 2, 2), stroke([(2.5, 7), (2.5, 21.5), (17, 21.5)], 2),
                    circle(13.5, 12.5, 2.5), stroke([(15.5, 12.5), (15.5, 5.5), (18.5, 7)], 1.8)],
        "refresh": [arc(12, 12, 7, 2, 60, 290), polygon([(20.5, 3.5), (20.5, 10.5), (13.5, 10.5)])],
        "open": [rrect_stroke(4, 4, 20, 20, 2, 2), stroke([(11, 13), (19, 5)], 2),
                 stroke([(13.5, 4), (20, 4), (20, 10.5)], 2)],
    }[name]
    return [(fg, s) for s in shapes]


def _status(name, frame=0):
    if name == "done":
        return [("success", circle(12, 12, 10)), ("on_success", stroke([(7, 12.5), (10.5, 16), (17, 9)], 2.2))]
    if name == "error":
        return [("error", circle(12, 12, 10)), ("on_error", stroke([(12, 6.5), (12, 13)], 2.4)),
                ("on_error", circle(12, 17, 1.4))]
    if name == "skipped":
        return [("outline", ring(12, 12, 9, 1.8)), ("outline", stroke([(8, 12), (16, 12)], 1.8))]
    if name == "queued":
        return [("outline", ring(12, 12, 9, 1.8))]
    if name == "active":
        return [("primary", arc(12, 12, 9, 2.4, frame * 30, 270))]
    raise KeyError(name)


def _app_icon():
    return [("#E12626", rrect(1, 1, 23, 23, 5.3)), ("#FFFFFF", polygon([(9.1, 6.7), (9.1, 17.3), (17.8, 12)]))]


SPINNER_FRAMES = 12


# -- rendering --------------------------------------------------------------------

def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def render_png(layers, size, ss=3) -> bytes:
    """layers: [(#rrggbb, shape)] -> RGBA PNG bytes of size x size pixels."""
    layers = [(_hex(c), f) for c, f in layers]
    k = 24 / size
    rows = []
    for j in range(size):
        row = bytearray([0])
        for i in range(size):
            r = g = b = n = 0
            for sj in range(ss):
                y = (j + (sj + 0.5) / ss) * k
                for si in range(ss):
                    x = (i + (si + 0.5) / ss) * k
                    for col, f in reversed(layers):
                        if f(x, y):
                            r += col[0]; g += col[1]; b += col[2]; n += 1
                            break
            if n:
                row += bytes((r // n, g // n, b // n, 255 * n // (ss * ss)))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"".join(rows), 6))
            + chunk(b"IEND", b""))


class Icons:
    """Cache of tk.PhotoImage icons; `colors` maps role names to #rrggbb for the current theme."""

    def __init__(self, master, colors: dict[str, str]):
        self.master = master
        self.colors = colors
        self._cache = {}

    def _image(self, key, layers, size):
        import tkinter as tk

        if key not in self._cache:
            layers = [(self.colors.get(c, c), f) for c, f in layers]
            data = base64.b64encode(render_png(layers, size))
            self._cache[key] = tk.PhotoImage(master=self.master, data=data, format="png")
        return self._cache[key]

    def glyph(self, name, size, color="on_surface_variant"):
        return self._image(("g", name, size, color), _glyph(name, color), size)

    def status(self, name, size, frame=0):
        return self._image(("s", name, size, frame), _status(name, frame), size)

    def app(self, size):
        return self._image(("app", size), _app_icon(), size)
