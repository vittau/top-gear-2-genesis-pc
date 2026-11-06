# Task 17: widescreen for the pre-race track intro screen (and similar menu screens)

Read `AGENTS.md` (follow its "CI budget" rules: never trigger CI),
`docs/WIDESCREEN.md` and `game/tg2_video.c`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4560** only;
- kill only your own PIDs.

No visible windows and no sound on speakers; the owner is at the desktop.
Task 16 (BOTH menu glyphs) and task 15 (engine audio) run in parallel.
Stay in the widescreen renderer. Commit often and push your branch.

## Owner request

The pre-race **track intro screen** shows the country's scenery strip at
the top, scrolling left, above a repeating blue patterned background, with
the track info panel (country, track, length, laps, weather, time and the
track map) in the middle. In widescreen it is currently pillarboxed 4:3.
The owner wants it extended to the full width: the background is a
repeating pattern, and the scrolling scenery can be widened.

An example capture (16:9, pillarboxed) is
`~/git/top-gear-2-genesis-pc/build-main/cov-recheck/c02-ws169-edges/intro-1.png`.
Use `tools/tg2_coverage.py` / `tools/tg2_password.py` to reach intro
screens for several countries.

## Goal

When widescreen is on, the track intro screen fills the whole window:
- **Scenery strip.** It continues to both edges with the same per-line
  scroll. The planes are probably 512 px wide while the view is 256
  (H32), so the off-screen part of the plane may already hold real
  continuation content. Use it when it's valid; otherwise repeat the
  strip's period. It must scroll seamlessly, with no seam or jump at
  the old 4:3 edges.
- **Background pattern.** It tiles out to the edges, phase-aligned with
  the native centre.
- **Info panel, map and text.** These stay centred and pixel-identical
  to the native image.

Then survey the other non-race screens, compare them, and extend those
where it's clearly correct; pillarbox the rest:
- title / "TOP GEAR 2" menu background;
- RACE/PLAYER/GEARS/SPEED/CONTROL setup;
- shop/upgrades;
- results;
- championship table;
- password.

Use a per-screen classification grounded in VDP state: which planes carry
full-width repeating content vs fixed artwork. Don't use guessed pixel
heuristics. Anything not confidently classified stays pillarboxed.

## Constraints

- With widescreen Off, output is byte-identical to stock (frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD`). Presentation-only:
  no guest RAM/VRAM writes.
- Fades and screen transitions must not flash wrong content in the
  margins. When a screen fades in or out, the margins fade with it.
- Race widescreen output must stay unchanged. Re-run
  `tools/verify_widescreen.py --modes off,16:9` and
  `tools/check_margin_artifacts.py`.
- Manifests stay empty.

## Evidence required

- 16:9 and 21:9 PNGs of the track intro screen for at least 4 countries.
- A 12-frame consecutive strip showing a seamless scroll at the old
  edges.
- A table of every non-race screen: extended or pillarboxed, and why.
- `docs/WIDESCREEN.md` updated.
