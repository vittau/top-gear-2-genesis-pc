# Task 07: edge-anchored HUD option for widescreen races

Read `AGENTS.md`, `docs/WIDESCREEN.md` (the limitation section explains
why the HUD currently stays centred), `game/tg2_video.c` and
`docs/RAM_MAP.md`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4460** only;
- kill only your own PIDs.

Another agent (task 06) is adding the options UI plumbing. Expose your
option as a function/flag in `tg2_video.c`, e.g. `tg2_video_set_hud_mode`,
and add the settings row only if task 06 has already merged into
`origin/main`. Rebase on it then. Commit often and push your branch.

## Goal

In widescreen races, an option **HUD: Centered / Edges**:
- **Edges** moves the left HUD cluster (speed, MPH, gear/AUTO, nitro,
  car icon) to the true left screen edge;
- it moves the right cluster (track map, LAP n/4, position) to the true
  right edge;
- each keeps its original inset from the edge it belongs to.

**Centered** is today's behaviour and stays the default.

## What's known

The HUD shares plane A with the player car and the per-line raster
effects, so you can't just shift a plane. Find out exactly how each HUD
element is produced: plane A tiles in fixed rows/columns, the window
plane, or sprites. Use read-only VRAM/name-table dumps over TCP, as the
widescreen work did. Then choose:

- **Sprite HUD pieces:** offset their X in the renderer's sprite pass by
  ±margin when they fall in a HUD region.
- **Plane-A HUD tiles above the horizon:** the renderer composes the
  margins itself. In the screen rows where the HUD lives, take the
  native-image columns that belong to the HUD clusters (bounding boxes
  derived from the name table's non-sky tiles, not hard-coded pixels if
  avoidable), draw them at the edges, and fill the vacated native
  columns with whatever is behind them. That's the sky/background
  composition the margins already use. Watch for the HUD rows that also
  carry raster scroll.
- Anything else the evidence shows.

Stay presentation-only: no guest RAM/VRAM writes.

## Constraints

- With widescreen Off, output is byte-identical to stock (frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD`). With HUD=Centered,
  output is identical to the current widescreen output. Prove both with
  frame hashes on the baseline route.
- The HUD must not tear or flicker as the car moves, the camera turns
  or the 60 fps mode is on (`TG2_RACE_60FPS=1`).
- Manifests stay empty.

## Evidence required

PNGs under `build/hud/`:
- 16:9 and 21:9, Centered vs Edges, at baseline frames 2800, 3300 and
  4501;
- plus a 6-frame consecutive sequence with 60 fps on and Edges.

Also add a section on the HUD to `docs/WIDESCREEN.md`.
