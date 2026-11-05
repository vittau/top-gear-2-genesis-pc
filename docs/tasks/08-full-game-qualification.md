# Task 08: full-game qualification (complete races, tracks, modes)

Read `AGENTS.md`, `docs/BRINGUP.md`, `docs/WIDESCREEN.md`,
`docs/FRAMERATE.md`, `docs/RAM_MAP.md`, `game/baseline-route.json` and
the probe tools in `tools/`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4470** only;
- kill only your own PIDs.

Only change files under `tools/`, `game/*.json` (input routes),
`game/game.toml` (only to fix discovery misses, with raw-ROM evidence)
and `docs/`. If you find a bug in the renderer or 60 fps code, document
it precisely and report it; don't fix it in this task. Commit often and
push your branch.

## Goal

So far, qualification is one 5600-frame route that never finishes a lap.
Prove the port plays the actual game, in every option combination that
matters:
- Off;
- widescreen 16:9;
- widescreen 16:9 + 60 fps (`TG2_RACE_60FPS=1`).

## Steps

1. **A full race.** Write an automated driver that completes a full race:
   4 laps of the first track, then the results screen and the
   post-race flow (shop/upgrades, password, next race).
   - Use controller input only. A closed-loop driver is fine: read the
     road curvature, player lateral position and speed through read-only
     RAM dumps via TCP, and steer with input. Find those RAM fields and
     add them to `docs/RAM_MAP.md`.
   - Must be deterministic enough to compare Off vs 60 fps: same final
     race time within a small tolerance. Report the lap times for each
     mode.
2. **Coverage.** Reach and race a few seconds of:
   - at least 3 further tracks, using the password system or by
     progressing, whatever is reliable;
   - a rain race and a night/dark race, if the game has them;
   - nitro use, a crash/collision, a pit stop if any;
   - the 2-player split-screen mode (it must stay 4:3, and 60 fps must
     not engage).
3. **Manifests.** After each run, the dispatch-miss/floor manifests must
   be empty. Any new miss is a discovery gap: root-cause it against the
   raw ROM (`tools/disasm_tg2.py`) and add audited seeds to
   `game/game.toml`, as the bring-up did, then re-run.
4. **Long-run soak.** 30+ minutes of wall time of continuous racing in
   16:9 + 60 fps without a crash, watchdog exit or stack drift. Sample
   SP like BRINGUP.md does.

## Evidence required

- `docs/VALIDATION.md`: a ledger table of scenario × mode, each marked
  passed / failed / untested, with evidence paths, lap times and
  manifest counts.
- The reusable driver/route scripts, committed.
- PNGs under `build/qual/` for each scenario.
- A precise reproduction for every failure found: frame, inputs, mode,
  screenshot.

Partial coverage is fine if the ledger says so honestly.
