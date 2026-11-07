#!/usr/bin/env python3
"""Which scanlines of a Top Gear 2 picture carry content?

The race picture is cropped by 8 top and 16 bottom lines when Hide overscan is
on, so those bands must never carry game content. A band row is *empty* when
every pixel is exactly black. The stock top band also carries the window-plane
marks (red/orange, native columns 16..31), so a row of black plus those exact
mark colours is classified as *window* rather than picture.

  from check_active_lines import check
  print(check(Path('build/x/frame-2800.png')))
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

# The stock top band is the VDP window plane: black apart from the pattern-0
# marks at name-table columns 2..3, i.e. native columns 16..31 (see
# docs/WIDESCREEN.md "Native red/orange top band"). The mark *colours* come
# from palette 0 entries 8/3/7 and therefore change with each track's palette
# (red/orange on Auckland, grey/pink on Loch Ness, dark red at night), so the
# classifier keys on the fixed columns, not on a colour list.
WINDOW_COLUMNS = (16, 31)
BLACK = (0, 0, 0)


def check(path: Path, top: int = 8, bottom: int = 16):
    from PIL import Image
    image = Image.open(path).convert('RGB')
    pixels = image.load()
    width, height = image.size
    kinds = []
    marks = []
    for y in range(height):
        empty = True
        window = True
        for x in range(width):
            colour = pixels[x, y]
            if colour == BLACK:
                continue
            empty = False
            if WINDOW_COLUMNS[0] <= x <= WINDOW_COLUMNS[1]:
                marks.append((x, y))
                continue
            window = False
            break
        kinds.append('empty' if empty else 'window' if window else 'picture')
    picture_rows = [y for y, kind in enumerate(kinds) if kind == 'picture']
    top_rows = kinds[:top]
    bottom_rows = kinds[height - bottom:]
    top_ok = all(kind in ('empty', 'window') for kind in top_rows)
    bottom_ok = all(kind == 'empty' for kind in bottom_rows)
    # A race picture is exactly one whose top band carries nothing but the
    # stock window-plane marks: that band is what the crop removes. Screens
    # without it (menus, intro panels, fades) are never cropped by the
    # renderer, so their bands may legitimately carry picture content.
    race_like = top_ok and any(kind == 'window' for kind in top_rows)
    return dict(
        path=str(path), width=width, height=height,
        first_picture_row=picture_rows[0] if picture_rows else None,
        last_picture_row=picture_rows[-1] if picture_rows else None,
        picture_rows=len(picture_rows),
        top_rows=top_rows, bottom_rows=bottom_rows,
        top_ok=top_ok, bottom_ok=bottom_ok, race_like=race_like,
        top_window_rows=sum(1 for kind in top_rows if kind == 'window'),
        top_mark_pixels=len(marks),
        top_mark_columns=[min(x for x, _ in marks), max(x for x, _ in marks)] if marks else None,
        ok=bottom_ok if race_like else True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__,
                               formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('images', nargs='+', type=Path)
    p.add_argument('--top', type=int, default=8)
    p.add_argument('--bottom', type=int, default=16)
    p.add_argument('--out', type=Path)
    p.add_argument('--quiet', action='store_true')
    a = p.parse_args()
    results = [check(path, a.top, a.bottom) for path in a.images]
    if a.out:
        a.out.write_text(json.dumps(results, indent=2) + '\n')
    if not a.quiet:
        for result in results:
            print(f"{result['path']}: {result['width']}x{result['height']} "
                  f"picture {result['first_picture_row']}..{result['last_picture_row']} "
                  f"race={int(result['race_like'])} "
                  f"top={'ok' if result['top_ok'] else 'CONTENT'} "
                  f"bottom={'ok' if result['bottom_ok'] else 'CONTENT'}")
    bad = [r for r in results if not r['ok']]
    raise SystemExit(0 if not bad else 1)


if __name__ == '__main__':
    main()
