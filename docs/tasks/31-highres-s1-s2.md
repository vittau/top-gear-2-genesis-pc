# Task 31: high-resolution rendering, steps S1 and S2

Read `AGENTS.md` first. Follow the "Machine resources" rules: at most 3 build
jobs (`JOBS=3 tools/build-linux.sh`, which also works on macOS), and run every
build and heavy analysis under `flock ~/.cache/tg2-heavy.lock`. Never trigger
CI, push tags or change workflow triggers. Use `SDL_VIDEODRIVER=dummy` and
`SDL_AUDIODRIVER=dummy` for every run, except the one windowed S2 check, and
kill that window as soon as it is captured. One runtime instance at a time.
The ROM is `~/roms/genesis/tg2.bin`.

Engine changes go in patches numbered **0033–0039** (reserved for the
high-resolution work; S2 is 0033), each with a one-line reason in
`patches/segagenesisrecomp/README.md`. Commit often on your branch and push it.
Do not merge into `main`.

## Scope

The design is `docs/HIGHRES.md` (task 29). Implement **only S1 and S2** from
its §8, following §7.2 (compact per-row capture) and §7.4 (presented height,
the engine seam). Read the whole document first; its evidence and tool
(`tools/highres_probe.py`) are your starting point.

The owner has not yet decided the questions in §9 (road look, HUD scale,
detailed variants, whether the engine's "Internal resolution" row drives the
scale, defaults, first-release scope, 2P). S1 and S2 must not depend on any of
them:

- **No user-facing control yet.** Read the scale through one function (e.g.
  `tg2_highres_scale()`), default 1, with the `TG2_HIGHRES_SCALE` environment
  override for testing. Don't add a `settings.ini` key, a launcher row or an
  overlay row: which control drives the scale is decision 4, handled in S7.
- No road, sprite or HUD drawing at N× yet (that is S3+). The S2 test provider
  is temporary and must be off unless a test enables it.

## Acceptance (from §8, gates G1–G3)

- **G1:** with scale 1 (and every option off) output is byte-identical:
  frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`
  (`tools/probe_run.py --widescreen off --frames 360`).
- **G2:** all four manifests empty after every run.
- **G3:** the stock 1× + widescreen + 60 fps comparisons still pass
  (`tools/verify_widescreen.py`, and the 60 fps canonical comparison in
  `docs/FRAMERATE.md`).
- S1: with scale > 1 and the builder copying native rows, the picture is still
  identical at 1×; a dump of the captured row state against the live rows for
  3 frames; the capture cost measured and reported.
- S2: a temporary test provider that returns a 2× native height with a
  synthetic pattern presents correctly in screenshots (`--widescreen off` and
  `16:9`) and in one windowed run; interlaced and 2P frames are unaffected;
  with the provider returning 0, G1 holds.
- `docs/HIGHRES.md` updated with what was built and measured (mark S1/S2 done).

Report with `worker_done`: commits, commands and exit codes, hashes, the
evidence paths, the measured costs, and what is not verified.
