# Task 11: black widescreen margins on hills (owner-reported)

Read `AGENTS.md`, `docs/WIDESCREEN.md`, `docs/FRAMERATE.md` (the
60 fps interpolation also lives in the renderer) and `game/tg2_video.c`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4500** only;
- kill only your own PIDs.

Another agent is working on performance (task 12). It may touch hot
paths in `tg2_video.c`; keep your change focused and merge `origin/main`
before reporting. Commit often and push your branch.

## Bug

The owner played on Auckland, track 1, in Adaptive 16:9 (796×448 window)
with 60 fps on. On a **downhill** the left and right margins go
**solid black** in a horizontal band:
- the band sits just below the skyline/water, across the full margin
  width on both sides;
- the native centre shows green grass there.

Screenshot: `~/git/top-gear-2-genesis-pc/build/user-reports/black-margins-downhill.png`.
At that 2× scale the margins are x<143 and x>655, and the band is
y≈192–225 window px, roughly native lines 96–112. The game was paused
at that moment.

Likely cause: on hills the horizon line moves, and the rows between the
background (plane B skyline/water) and the road raster area get content
the margin fill doesn't cover. `docs/WIDESCREEN.md` says margins sample
"only plane B", so lines where the native picture shows plane-A grass
(or backdrop colour) above the road area may have no margin source and
fall back to black. The interpolated frames may make it worse, so check
60 fps on and off.

## Goal

The margins never show black (or any wrong colour) bands on any line
where the native picture shows scenery, on hills (up and down), crests,
dips and flat ground, in Off-HUD/Edges and 60 fps on/off:
- each margin line continues what the native edge columns of that line
  show;
- grass/backdrop colour, road-side bands and the per-line road raster
  colours (the alternating grass shades) must continue into the margins
  with the same per-line colour as the native edge.

## Steps

1. **Reproduce.** Find a downhill on Auckland with the replay/driver
   tools (`tools/tg2_replay_route.py`, `tools/tg2_race_driver.py`), or
   any frame where the horizon line moves. Capture the bad frame in 16:9
   and record which source each margin line uses.
2. **Fix** in `game/tg2_video.c`.
3. **Add an automated check.**
   - On a route covering hills, for every frame in 16:9 and 21:9 and for
     every line, the margin pixels next to the native image must not be
     the black backdrop when the native edge pixel isn't black.
   - Count violations. It must be 0 after the fix; the current code
     should fail it.
   - Fold the check into `tools/verify_widescreen.py` or the road audit.

## Constraints

- Off-mode hashes unchanged: frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD`.
- The 60 fps road artefact check (`tools/check_road_artifacts.py`) still
  passes.
- Manifests stay empty.

## Evidence required

- Before/after PNGs of the reproduced frame under `build/hills/`.
- Violation counts before and after on the hill route.
- `docs/WIDESCREEN.md` updated.
