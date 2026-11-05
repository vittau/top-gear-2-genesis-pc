# Task 06: player-facing options (controller-friendly)

Read `AGENTS.md`, `docs/WIDESCREEN.md`, `docs/FRAMERATE.md`,
`docs/RELEASING.md` and `game/tg2_spec.c`. Look at how RKA exposes its
options: `~/git/tg2-deps/RocketKnightAdventuresRecomp/game/rka_options.c`
plus its `.mods` / `load_settings` in `rka_spec.c`, and recomp-ui's mods
and settings pages (`recomp-ui/`).

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4450** only;
- kill only your own PIDs.

Another agent is working on the audio "BOTH" feature (task 05). It may
add one host option too. Keep your option plumbing generic so a third
option is a one-line addition. Commit often and push your branch.

## Goal

Every port option can be changed by a player with **only a gamepad**,
e.g. a Steam Deck in Gamescope:
- from the launcher before starting;
- from the in-game recomp-ui overlay (F1/Esc, or the controller's
  overlay binding);
- persisted across launches.

The options:

| Option | Values | Default |
|---|---|---|
| Widescreen | Off / Adaptive (fit) / 16:9 / 21:9 | Adaptive |
| 60 fps races | Off / On | On |

The 60 fps option currently reads `tg2.ini race_60fps` and env
`TG2_RACE_60FPS` (`game/tg2_spec.c`). Move it onto the same settings
mechanism the engine/recomp-ui uses for mods (the persisted
`settings.ini`). Keep the env var as a probe override. Toggling it at
runtime must be safe: take effect at the next race start, or immediately
only if you prove that's glitch-free.

## Constraints

- With every option off, output stays byte-identical to stock: frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD`.
  `tools/verify_widescreen.py --modes off` must report all manifests empty.
- Settings live next to the executable, or in the platform's user
  config dir if the engine already does that. Follow the engine's
  convention and document it in `docs/RELEASING.md`.
- No ROM-derived data in git.

## Evidence required

- PNGs of the launcher and of the in-game overlay showing both options,
  driven headless via TCP/input script, under `build/options/`.
- A run proving persistence: set options, quit, relaunch, read them back.
- A run with 60 fps toggled via the new setting (not the env var) showing
  60 changed pictures/s with `tools/probe_framerate.py`. Note it's
  hard-wired to port 4410; add a `--port` argument and use 4450.
- `docs/RELEASING.md` updated with an end-user "Options" section, in
  Portuguese and English.
