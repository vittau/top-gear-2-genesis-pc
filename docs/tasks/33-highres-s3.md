# Task 33: high-resolution rendering, step S3 (road + background) as an experimental option

**Status: implementation and local technical qualification complete; awaiting
the owner's visual acceptance.** The completed results, measured costs,
curated comparisons and remaining limitations are in
[HIGHRES §13](../HIGHRES.md) and the task-33 table in
[VALIDATION](../VALIDATION.md).

The experimental Internal resolution control defaults to 1×. Detailed
sprites/HUD/plane-A composition remains S4/S5; full N× + 60 fps qualification
remains S6, and live switching remains S7. NTSC exclusion awaits the future
NTSC option, and GPU/Steam Deck/release performance is unverified. The
coordinator will request the owner's visual review using the comparisons.

The original brief below is retained for reference. Its validation matrix is
superseded by the reduced reproduction plan in HIGHRES §13.4: retain valid
evidence, cover each scale briefly, keep one long audit at the largest
effective scale, and cover weather/tunnel at one scale unless a
scale-specific defect appears.

## Original implementation brief

Read `AGENTS.md` first. Follow the "Machine resources" rules: at most 3 build
jobs (`JOBS=3 tools/build-linux.sh`, which also works on macOS), and run every
build and heavy analysis under `flock ~/.cache/tg2-heavy.lock`. Never trigger
CI, push tags or change workflow triggers. Use `SDL_VIDEODRIVER=dummy` and
`SDL_AUDIODRIVER=dummy` for every run, except short windowed checks you close
at once. One runtime instance at a time. The ROM is `~/roms/genesis/tg2.bin`.

Engine changes go in patches numbered **0034–0039** (reserved for the
high-resolution work). Another worker is doing task 32 (Steam Deck aspect and
logging) at the same time in `runner/main.c`, `runner/app_config.c` and
`runner/diagnostic_replay.c` (patches 0045+); keep your edits to those files
small so the patches stack. Commit often on your branch and push it. Do not
merge into `main`.

## Scope

Start from `main` (it has S1/S2 merged as task 31, plus task 30). Implement
**S3** from `docs/HIGHRES.md` §8 with the architecture in §7.3 (road strip
rasteriser), following the owner's decisions recorded in §9:

- **Smooth** analytic road edges at N× (decision 1).
- Sprites, HUD and plane-A effects stay as in §8 S3: the native picture's
  non-road rows scaled by nearest until S4/S5 replace them. When S5 comes, the
  HUD will be integer N× (decision 2), so nearest-scaled HUD now is already the
  intended look.
- 2P stays native (decision 7).

Then make it **testable by the owner as an experimental option** (decisions 4,
5, 6) — the minimum of S7 needed for that:

- Un-hide the engine's **"Internal resolution"** row for TG2 (patch 0017 hid
  it) and make it drive `tg2_highres_scale()` (1×–4×), labelled experimental,
  **default 1×**. No separate `[mods.highres]` key; keep the
  `TG2_HIGHRES_SCALE` override for tests.
- When NTSC exists later it will be mutually exclusive with a scale above 1×;
  leave the slot noted, nothing to build now.

## Acceptance (from §8 S3, plus gates G1–G3)

- G1–G3 as in §8: Off/1× hashes unchanged (frame 60 `2A0B972960C5E325`,
  frame 300 `1131D937D70234FD`), all four manifests empty, the 1× widescreen
  and 60 fps comparisons still pass.
- 2×/3×/4× captures on straight, curve and hill frames of Auckland and at
  least two other tracks (one with weather, one with a tunnel): a continuous
  road with no gaps, no fan-shaped duplicates, no striped tearing.
- `check_road_artifacts.py` adapted to N× reports 0 violations on ≥ 3000
  presented frames; the margin audit rules re-run at N× with 0 violations.
- The downscale check: box-downsample the N× picture by N and compare with
  the 1× reference within a documented tolerance (road edges may differ by
  antialiasing; stripe counts and centres must not).
- The Internal resolution row round-trips through `settings.ini`, the launcher
  and the Esc menu; at 1× it is a no-op.
- Measured cost per presented frame at 2×/3×/4× on this Mac.
- A few curated 2× captures in `docs/images/` (owner-approved for docs);
  `docs/HIGHRES.md` updated (S3 done, measurements).

Report with `worker_done`: commits, commands and exit codes, hashes, evidence
paths, costs, and what is not verified.
