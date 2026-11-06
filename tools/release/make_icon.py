#!/usr/bin/env python3
"""Render the project's release icon (1024x1024 RGBA PNG).

The repository ships no box art, so this draws an original speedometer mark
with the Python standard library only (no Pillow dependency). It is used for
the Linux AppImage desktop entry and the macOS .app icon.

Usage:
    make_icon.py [--out tools/release/tg2recomp.png] [--size 1024]
"""
import argparse
import math
import struct
import zlib

BACKGROUND_TOP = (12, 20, 30)
BACKGROUND_BOTTOM = (28, 44, 62)
RING = (235, 239, 244)
TICK = (235, 239, 244)
NEEDLE = (226, 58, 44)
HUB = (235, 239, 244)
SHADOW = (0, 0, 0, 90)

SUPERSAMPLE = 2


def blend(base, colour, coverage):
    if coverage <= 0.0:
        return base
    if coverage >= 1.0:
        return colour
    return tuple(int(round(b + (c - b) * coverage)) for b, c in zip(base, colour))


def inside_ring(x, y, radius, width):
    distance = math.hypot(x, y)
    return abs(distance - radius) <= width / 2.0


def tick_angle(index, count):
    # Speedometer sweep: 150 degrees (left) through 30 degrees (right).
    start, end = math.radians(150), math.radians(30)
    return start + (end - start) * (index / (count - 1))


def pixel(x, y, size):
    """Return (r, g, b, a) for one sample in [-1, 1] icon space."""
    t = (y + 1.0) / 2.0
    colour = tuple(int(round(a + (b - a) * t)) for a, b in zip(BACKGROUND_TOP, BACKGROUND_BOTTOM))
    alpha = 255

    distance = math.hypot(x, y)

    if inside_ring(x, y + 0.02, 0.74, 0.075):
        colour = blend(colour, SHADOW, 0.5)
    if inside_ring(x, y, 0.74, 0.075):
        colour = RING

    for index in range(13):
        angle = tick_angle(index, 13)
        inner, outer = 0.56, 0.68
        tx, ty = math.cos(angle), -math.sin(angle)
        # Distance from the tick segment (inner..outer along the ray).
        projection = x * tx + y * ty
        perpendicular = abs(-x * ty + y * tx)
        if inner <= projection <= outer and perpendicular <= 0.012:
            colour = TICK

    # Needle: a tapered red bar from the hub toward 67 degrees.
    angle = math.radians(67)
    nx, ny = math.cos(angle), -math.sin(angle)
    projection = x * nx + y * ny
    perpendicular = abs(-x * ny + y * nx)
    if 0.0 <= projection <= 0.56 and perpendicular <= 0.035 * (1.0 - 0.55 * projection / 0.56):
        colour = NEEDLE

    if distance <= 0.095:
        colour = HUB
    elif distance <= 0.13:
        colour = blend(colour, (60, 74, 90), 0.9)

    # Round the outer corners slightly: a cheap alpha mask.
    if max(abs(x), abs(y)) > 0.985:
        alpha = 255
    return colour[0], colour[1], colour[2], alpha


def render(size):
    rows = []
    for py in range(size):
        row = bytearray()
        for px in range(size):
            r = g = b = a = 0
            for sy in range(SUPERSAMPLE):
                for sx in range(SUPERSAMPLE):
                    x = ((px + (sx + 0.5) / SUPERSAMPLE) / size) * 2.0 - 1.0
                    y = ((py + (sy + 0.5) / SUPERSAMPLE) / size) * 2.0 - 1.0
                    sr, sg, sb, sa = pixel(x, y, size)
                    r += sr
                    g += sg
                    b += sb
                    a += sa
            samples = SUPERSAMPLE * SUPERSAMPLE
            row += bytes((r // samples, g // samples, b // samples, a // samples))
        rows.append(bytes(row))
    return b"".join(rows)


def write_png(path, size, raw):
    def chunk(kind, payload):
        return (struct.pack(">I", len(payload)) + kind + payload
                + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF))

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    stride = size * 4
    scanlines = b"".join(b"\x00" + raw[y * stride:(y + 1) * stride] for y in range(size))
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", header))
        handle.write(chunk(b"IDAT", zlib.compress(scanlines, 9)))
        handle.write(chunk(b"IEND", b""))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="tools/release/tg2recomp.png")
    parser.add_argument("--size", type=int, default=1024)
    args = parser.parse_args()
    raw = render(args.size)
    write_png(args.out, args.size, raw)
    print(f"make_icon: wrote {args.out} ({args.size}x{args.size})")


if __name__ == "__main__":
    main()
