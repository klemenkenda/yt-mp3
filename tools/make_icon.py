"""Generate assets/icon.ico (red rounded square, white play triangle, music note feel).

Pure Python (no Pillow): renders RGBA with simple supersampling and packs PNGs into an ICO.
Run: python tools/make_icon.py
"""
import struct
import zlib
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)
RED = (225, 38, 38)
WHITE = (255, 255, 255)


def inside(x, y):
    """Shape test in unit coordinates: returns 'tri', 'bg' or None."""
    # rounded square with radius 0.22, margin 0.04
    m, r = 0.04, 0.22
    cx = min(max(x, m + r), 1 - m - r)
    cy = min(max(y, m + r), 1 - m - r)
    if (x - cx) ** 2 + (y - cy) ** 2 > r * r:
        return None
    # play triangle
    ax, ay, bx, by, px, py = 0.38, 0.28, 0.38, 0.72, 0.74, 0.50
    def side(x1, y1, x2, y2):
        return (x - x2) * (y1 - y2) - (x1 - x2) * (y - y2)
    d1, d2, d3 = side(ax, ay, bx, by), side(bx, by, px, py), side(px, py, ax, ay)
    if (d1 < 0) == (d2 < 0) == (d3 < 0):
        return "tri"
    return "bg"


def render(size, ss=4):
    rows = []
    for j in range(size):
        row = bytearray([0])  # PNG filter: none
        for i in range(size):
            acc = [0, 0, 0, 0]
            for sj in range(ss):
                for si in range(ss):
                    k = inside((i + (si + 0.5) / ss) / size, (j + (sj + 0.5) / ss) / size)
                    if k:
                        c = WHITE if k == "tri" else RED
                        acc[0] += c[0]; acc[1] += c[1]; acc[2] += c[2]; acc[3] += 255
            n = ss * ss
            a = acc[3] // n
            if a:
                row += bytes((acc[0] * 255 // acc[3], acc[1] * 255 // acc[3], acc[2] * 255 // acc[3], a))
            else:
                row += b"\0\0\0\0"
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size, raw):
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def main():
    images = [render(s) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for s, data in zip(SIZES, images):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    out = Path(__file__).resolve().parents[1] / "assets" / "icon.ico"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(header + entries + b"".join(images))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
