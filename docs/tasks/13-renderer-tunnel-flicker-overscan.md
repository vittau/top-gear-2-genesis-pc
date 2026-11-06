# Task 13: widescreen renderer fixes from the second owner playtest

Read `AGENTS.md`, `docs/STATUS.md` (the "second playtest" section),
`docs/WIDESCREEN.md`, `docs/FRAMERATE.md` and `game/tg2_video.c`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4520** only;
- kill only your own PIDs;
- never open visible windows (the owner is away). Headless/dummy video only.

Task 12 (performance) may also touch hot paths in `tg2_video.c`. Keep
changes focused and merge `origin/main` before reporting. Commit often
and push your branch.

## Three defects

The owner played Auckland (track 1), Adaptive 16:9 with 60 fps on, using
a release-config build.

### 1. Tunnel margins

Inside the tunnel, the native centre shows black tunnel walls/ceiling
with the bright exit in the middle. The margins keep showing the outside
sky, skyline, water and grass from plane B, so it looks like two
different pictures. Screenshot:
`~/git/top-gear-2-genesis-pc/build/user-reports/tunnel-margins.png`.

- Find how the tunnel is drawn: plane A tiles covering plane B,
  sprites, the window plane, or raster colour changes.
- Make each margin line continue what actually covers the native edge
  columns of that line. Walls stay walls to the screen edge.
- Handle the entry and exit transitions, where the tunnel mouth grows
  or shrinks over a few frames.

### 2. Motion-only black-line flicker on hills

Brief thin black lines flicker in the margins when the road tilts. They
are smaller than the black bands task 11 fixed, and they are **not
visible while paused**, when only repeated real pictures are presented.
The prime suspect is the 60 fps **synthesized** frames. Interpolated
per-line geometry can move the horizon/separator line between pictures
so that a margin line has no source, or falls back to black.

- Run the per-line margin audit from task 11 on **every presented
  frame, including synthesized ones**, on a hill route with 60 fps on
  and off.
- The current code should show violations with 60 fps on. Fix them so
  both are 0.
- Also scan for single-frame black lines on the real pictures during
  fast hill transitions.

### 3. "Hide overscan" option

The black top band shows stock red marks: window-plane pattern 0 at
native x=16–31, lines 0–7 (see `docs/WIDESCREEN.md`). On a CRT that area
sat in overscan.
- Add a presentation option **Hide overscan**, default **On**, which
  blanks the top window band lines (presentation only) in all modes,
  including 4:3.
- Register it in the options UI like the other `[mods.*]` options: in
  the launcher and in the in-game overlay, persisted.
- With it **Off**, output stays byte-identical to today, so the Off
  hashes still match stock with all options off.

## Constraints

- With all options off (widescreen Off, 60 fps Off, Hide overscan Off),
  output stays byte-identical to stock: frame 60 `2A0B972960C5E325`,
  frame 300 `1131D937D70234FD`.
- These must still pass:
  - the 60 fps road artefact check (`tools/check_road_artifacts.py`);
  - the 60 fps physics replay identity;
  - the margin audits.
- Manifests stay empty.

## Evidence required

- Before/after PNGs for the tunnel: entry, inside, exit. Use 16:9 and
  21:9.
- The full-presented-frame margin audit: violation counts before/after,
  60 fps on and off.
- Hide overscan on/off crops.
- `docs/WIDESCREEN.md` updated.
