# Task 26: bugs from the owner's e586c00 playtest (release)

Read `AGENTS.md` first. Follow the "Machine resources" rules: at most 3 build
jobs, and run every build under `flock ~/.cache/tg2-heavy.lock`. Never trigger
CI. Use SDL_VIDEODRIVER=dummy and SDL_AUDIODRIVER=dummy for every run. Engine
changes go in new patches numbered after the highest one on origin/main. Task
24 may take 0019, so check before you number yours. Add a line for each to
`patches/segagenesisrecomp/README.md`.

Evidence from the owner's session is in
`/home/vitor/git/top-gear-2-genesis-pc/build/owner-session-e586c00/`:
- `settings.ini` with RACE SOUND = BOTH persisted, plus unfiltered audio, HUD
  edges, Adaptive widescreen and 60 fps;
- `TG2-feedback.replay*`;
- `play.log`.

The build was main `e586c00`.

## 1. The RACE SOUND menu page is empty, then garbled (major)

The owner opened the RACE SOUND page and it was empty. He backed out, opened
it again, and this time the text was garbled. Reproduce it headless with his
`settings.ini`: navigate the menus over TCP and capture screenshots. Find the
cause. Suspects:
- the BOTH menu leaf in `game/tg2_audio_both.c` or `tg2_options`;
- patch 0014's second Z80 or its upload window interfering with VRAM/DMA or
  with the menu's text writes;
- the 0018 state hooks.

Fix it. Then show correct page text over several opens and closes, in every
RACE SOUND mode, for both a fresh `settings.ini` and his.

## 2. Player 2 cannot press Start (major for 2P)

The owner ended up at a 2-player race start and could not continue, because
player 2 is `device = 0` (none) by default (`runner/input_map.c`:
"2-player is opt-in").

For TG2, make P2 usable by default: the right-hand keyboard set (IJKL, M/N/comma,
right Shift = Start) plus the second gamepad. Use a game-level default if
GameSpec offers one, or a small patch otherwise.
- Don't change P1.
- Don't break single-controller play on the Steam Deck.
- Existing `settings.ini` files keep what they have.

Also find out why a 1-player user lands at a 2P start. Is the menu cursor
remembered? Is it a default? Report what you find, and fix it if it is a bug.

## 3. The feedback replay diverges at execution 0 (diagnostics)

`segagenesisrecomp/tools/replay_diagnostic.py build/owner-session-e586c00/TG2-feedback.replay --exe <e586c00 build> --rom ~/roms/genesis/tg2.bin --headless`
prints `FIRST DIVERGENCE execution=0 ... checkpoint mismatch`. Owner bug reports
depend on these replays.
- Find which machine or host state is missing from the replay's
  boot/checkpoint image. Likely candidates are the second Z80 (0014), the BOTH
  chip state, and the 0018 host payload.
- Fix it so that a fresh recording on the fixed build replays to the end
  without divergence. Cover the default settings and the owner's
  `settings.ini` (BOTH, unfiltered audio).

## 4. Release log noise

Remove or gate the `[DUAL-DBG]` lines that the release build prints every 600
frames.

## Acceptance

- Each item comes with evidence: screenshots, replay output, logs.
- Off-mode hashes are unchanged: frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD`.
- `tools/verify_both_boot.py` passes.
- Every manifest is empty (count them with `tools/tg2_runner.manifest_counts`).

Commit often, push your branch, and report with `worker_done`.
