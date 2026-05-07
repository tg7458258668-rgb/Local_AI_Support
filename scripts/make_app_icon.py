from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
ICONSET = ROOT / "LocalAI.iconset"


def blend(dst, src):
    sr, sg, sb, sa = src
    if sa <= 0:
        return dst
    if sa >= 255:
        return (sr, sg, sb, 255)
    dr, dg, db, da = dst
    a = sa / 255
    inv = 1 - a
    return (
        max(0, min(255, int(sr * a + dr * inv))),
        max(0, min(255, int(sg * a + dg * inv))),
        max(0, min(255, int(sb * a + db * inv))),
        255,
    )


def write_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int, int]]):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend(pixels[y * width + x])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


class Canvas:
    def __init__(self, size: int):
        self.size = size
        self.pixels = [(0, 0, 0, 0)] * (size * size)

    def set(self, x: int, y: int, color):
        if 0 <= x < self.size and 0 <= y < self.size:
            idx = y * self.size + x
            self.pixels[idx] = blend(self.pixels[idx], color)

    def rounded_rect(self, x0, y0, x1, y1, radius, color):
        for y in range(max(0, int(y0)), min(self.size, int(y1))):
            for x in range(max(0, int(x0)), min(self.size, int(x1))):
                dx = max(x0 + radius - x, 0, x - (x1 - radius))
                dy = max(y0 + radius - y, 0, y - (y1 - radius))
                if dx * dx + dy * dy <= radius * radius:
                    self.set(x, y, color)

    def circle(self, cx, cy, radius, color):
        r2 = radius * radius
        for y in range(max(0, int(cy - radius)), min(self.size, int(cy + radius))):
            for x in range(max(0, int(cx - radius)), min(self.size, int(cx + radius))):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r2:
                    self.set(x, y, color)

    def line(self, x0, y0, x1, y1, width, color):
        steps = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(steps):
            t = i / max(steps - 1, 1)
            x = x0 + (x1 - x0) * t
            y = y0 + (y1 - y0) * t
            self.circle(x, y, width / 2, color)

    def arc(self, cx, cy, radius, start_deg, end_deg, width, color):
        steps = 220
        for i in range(steps + 1):
            deg = start_deg + (end_deg - start_deg) * i / steps
            rad = math.radians(deg)
            x = cx + math.cos(rad) * radius
            y = cy + math.sin(rad) * radius
            self.circle(x, y, width / 2, color)

    def save(self, path: Path):
        write_png(path, self.size, self.size, self.pixels)


def draw_icon(size: int) -> Canvas:
    c = Canvas(size)
    s = size / 1024

    # Main rounded app tile.
    for y in range(size):
        for x in range(size):
            dx = max(118 * s - x, 0, x - 906 * s)
            dy = max(118 * s - y, 0, y - 906 * s)
            if dx * dx + dy * dy <= (174 * s) ** 2:
                tx = x / max(size - 1, 1)
                ty = y / max(size - 1, 1)
                r = int(35 + 22 * tx)
                g = int(99 + 88 * ty)
                b = int(235 - 58 * ty + 22 * tx)
                c.set(x, y, (
                    max(0, min(255, r)),
                    max(0, min(255, g)),
                    max(0, min(255, b)),
                    255,
                ))

    # Soft inner highlight.
    c.rounded_rect(170 * s, 150 * s, 860 * s, 850 * s, 138 * s, (255, 255, 255, 22))

    # Chat bubble.
    c.rounded_rect(230 * s, 300 * s, 790 * s, 620 * s, 72 * s, (255, 255, 255, 242))
    c.rounded_rect(550 * s, 585 * s, 690 * s, 705 * s, 30 * s, (255, 255, 255, 242))

    # AI circuit lines inside bubble.
    ink = (37, 99, 235, 230)
    c.line(330 * s, 415 * s, 520 * s, 415 * s, 28 * s, ink)
    c.line(330 * s, 500 * s, 690 * s, 500 * s, 28 * s, ink)
    c.circle(330 * s, 415 * s, 31 * s, (20, 184, 166, 255))
    c.circle(520 * s, 415 * s, 31 * s, (37, 99, 235, 255))
    c.circle(690 * s, 500 * s, 31 * s, (20, 184, 166, 255))

    # Power/start symbol.
    c.circle(760 * s, 255 * s, 90 * s, (17, 24, 39, 210))
    c.arc(760 * s, 265 * s, 48 * s, 35, 325, 18 * s, (255, 255, 255, 250))
    c.line(760 * s, 200 * s, 760 * s, 265 * s, 18 * s, (255, 255, 255, 250))

    # Status light.
    c.circle(276 * s, 710 * s, 42 * s, (16, 185, 129, 255))
    c.circle(276 * s, 710 * s, 20 * s, (236, 253, 245, 255))

    return c


def main():
    ICONSET.mkdir(exist_ok=True)
    sizes = [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]
    for name, size in sizes:
        draw_icon(size).save(ICONSET / name)
    print(ICONSET)


if __name__ == "__main__":
    main()
