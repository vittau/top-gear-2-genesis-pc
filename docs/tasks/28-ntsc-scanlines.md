# Task 28: Blargg NTSC filter and scanlines

Read `AGENTS.md` first. Follow the "Machine resources" rules: at most 3 build
jobs (`JOBS=3 tools/build-linux.sh`, which also works on macOS), and run every
build and heavy analysis under `flock ~/.cache/tg2-heavy.lock`. Never trigger
CI, push tags or change workflow triggers. Use `SDL_VIDEODRIVER=dummy` and
`SDL_AUDIODRIVER=dummy` for every run. One runtime instance at a time. The ROM
is `~/roms/genesis/tg2.bin`. The system Python has no Pillow; make a venv in
your own scratch space if a tool needs it.

Engine changes go in new patches numbered **0028–0032** (reserved for this
task), each with a one-line reason in `patches/segagenesisrecomp/README.md`.
Commit often on your branch and push it. Do not merge into `main`; the
coordinator merges.

The owner's requirements are in `docs/ROADMAP.md`, "NTSC filter and
scanlines". Read that section in full; it is the spec. Reference
implementation (owner's own project, GPL):
`/Users/vitor/git/modern-tyrian` (`docs/CRT.md`, `src/ntsc.c`,
`src/crt_filter.c`, `test/regress/modern-crt-*`). Copy its approach, not its
game-specific layout.

## Design constraints (to avoid rework with later tasks)

High-resolution rendering (next task) and gradient skies / arbitrary car
colours (later) are coming. Build this so they don't force a rewrite:

1. **Two independent stages.** NTSC and scanlines are separate post-process
   stages on the final presented frame: after widescreen composition and the
   overscan crop, and on the 60 fps synthesized frames too. Modes: Off /
   Scanlines / NTSC / Scanlines + NTSC.
2. **NTSC takes any RGB colour.** Don't key tables on the Genesis 512-colour
   palette. Start with RGB555-keyed tables (as modern-tyrian), keep the code
   structured so the three-kernel exact path can replace the table later, and
   report the gradient banding you measure. Blargg's `md_ntsc` has the Genesis
   signal parameters; `snes_ntsc` is what modern-tyrian ports. Choose, and say
   why.
3. **NTSC works at native source resolution.** Its stage takes a frame of any
   width (256, 320, the widescreen widths 356/467/...) and height. When
   high-resolution rendering lands, NTSC and a render scale above 1× will be
   mutually exclusive; leave one obvious place where that rule goes.
4. **Scanlines work at output resolution**, matched to the window size, so
   they also apply to a high-resolution frame later. The look is the owner's
   reference: *Animal Well*
   (https://godotshaders.com/shader/animal-well-inspired-crt-effect/). Study
   it (scanline profile, brightness compensation, mask, bloom, curvature);
   check its licence before copying anything and prefer an original
   implementation of the same look.
5. **Presets and strength.** Composite / S-Video / RGB for NTSC, a strength
   for scanlines. Persist in `settings.ini` (`[mods.crt]` or similar), expose
   in the launcher and the in-game Esc menu like the other options
   (`game/tg2_options.c`).

## Licence gate (ask before adding Blargg code)

Blargg's code is LGPL 2.1; this project is PolyForm NC. The coordinator is
getting the owner's decision on how to ship it (separate shared library,
static with relink provisions, or an original filter). **Put the NTSC filter
in its own translation unit and CMake target from the start**, so it can
become a shared library without code changes. Do the stage plumbing, scanlines
and options first. Before committing any Blargg-derived code, ask the
coordinator for the decision.

## Where to look

`game/tg2_video.c` (TG2's renderer), the engine's presentation path
(`present_window`, patch 0012; linear filter, patch 0025 and
`docs/LINEAR_FILTER.md`), `docs/WIDESCREEN.md`, `docs/FRAMERATE.md` (60 fps
synthesized frames), `game/tg2_options.c`.

## Acceptance

- With the mode Off, output is byte-identical: frame 60 `2A0B972960C5E325`,
  frame 300 `1131D937D70234FD` (`tools/probe_run.py --widescreen off
  --frames 360`), and `tools/verify_widescreen.py --modes off` unchanged.
- Captures of the presented picture (`screenshot` with `"presented":1`) in each
  mode and preset: a race at 4:3, 16:9 and 21:9, with 60 fps on and off, a
  menu, split-screen 2P, and a gradient-like test (e.g. the race sky at dusk).
  Put a few curated PNGs in `docs/images/` (owner-approved for docs) and the
  rest under `build/`.
- Measured cost per presented frame for each mode on this Mac (Apple Silicon,
  release build), and an estimate for the Ryzen 5 3500U / Steam Deck.
- No new dispatch misses; all four manifests empty.
- A `docs/CRT.md` describing the design, the measurements and the licence
  outcome; the ROADMAP item updated.

Report with `worker_done`: commits, commands and exit codes, hashes, capture
paths, costs, and what is not verified.
