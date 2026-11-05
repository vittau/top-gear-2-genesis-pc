# Task 02: adaptive widescreen for Top Gear 2

Read `AGENTS.md`, `docs/BRINGUP.md`, `docs/RAM_MAP.md`, then the engine's
`WIDESCREEN_ISSUES.md` and `runner/game_video.h`. Also read the reference
renderer `~/git/tg2-deps/RocketKnightAdventuresRecomp/game/rka_video.c` and
its `CUSTOM-VIDEO.md`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp instances in parallel on this machine:
- use **TCP port 4400** and only that one;
- kill only processes you started (by PID). Never `pkill TG2Recomp`.

Commit often and push your branch to origin.

## Goal

During races, the game renders a wider view than 4:3:
- **Adaptive** (follows the window aspect) plus fixed 16:9 and 21:9 choices;
- an **Off** mode that is byte-identical to stock (same frame hashes as
  `docs/BRINGUP.md`: frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD`).

Expose it as a mod/option the way RKA does (`video_default`, mods page,
settings). Non-race screens (menus, title, shop) stay at their native
centered 4:3 with pillarbox unless widening them is trivially correct.

## Facts to start from

- Races run in **H32 (256×224)**; menus run in H40 (320×224). At 224 lines,
  16:9 is about 398 px. The race therefore needs about 71 extra pixels per
  side, more than a 320-px game would.
- The road is drawn by a raster H-int pipeline: copied self-modifying
  H-int code at `$FFF9FE`, raster lists via A5 from `$FF231E`, road
  renderers at `$007B00` / `$007CDC` / `$007E70`. Everything that comes out
  of it is per-line scroll/state. Find how the road plane, the roadside
  scenery, the skyline/background plane and the sprites (cars, signs, trees)
  are each produced.

## What a good result looks like

- **Road:** the road and its edges and rumble strips extend to the new
  screen edges with correct per-line perspective. No wrapped or repeated
  plane content in the margins.
- **Background:** the skyline/background fills the margins, continuing
  its scroll.
- **Sprites:** opponent cars and roadside objects stay visible and
  correctly projected into the margins, not culled at the old 256-px edge.
  This probably needs widened culling (`[[widescreen_site]]` injections or
  renderer-side capture) and a wider projection. Cars must not pop in at
  the old edges.
- **HUD:** speed, gear, nitro, lap, position and the track map are
  anchored to the new screen edges (or kept centred via an option).
- **Logic:** game logic and collision are unchanged. Widescreen is
  presentation plus the minimum culling and projection changes.

Choose the technique on the evidence, either recompiler injection sites,
a game-owned `GameVideo` renderer, or both. Document why in
`docs/WIDESCREEN.md`. If you need H40-like output from a game that is in
H32 mode, that's a renderer decision; don't flip the guest's VDP mode
behind its back unless you prove it's safe.

## Evidence required

- PNG screenshots under `build/ws/`, in 4:3 Off, 16:9 and 21:9, at the
  same race frames as the baseline route (`game/baseline-route.json`, at
  least frames 2800, 3300 and 4501). Include one with an opponent car or a
  roadside object crossing the margin.
- Off-mode frame hashes matching the stock values above.
- `dispatch_misses.toml` / floor manifests still empty after the route.
- `docs/WIDESCREEN.md`: technique, what is widened, known artefacts, and
  what is still untested (other tracks, rain/night, split-screen 2P, which
  should simply stay 4:3).

If something can't be done cleanly, deliver the best correct subset (road
and background first, then sprites, then HUD), state exactly what is
missing, and report it as partial.
