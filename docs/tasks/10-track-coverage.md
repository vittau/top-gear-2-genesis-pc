# Task 10: all-track coverage (16 tracks, rain, nitro)

Read `AGENTS.md`, `docs/VALIDATION.md` (section 2 explains why only 2
tracks were reached), `docs/RAM_MAP.md` and the qualification tools
`tools/tg2_runner.py`, `tools/tg2_race_driver.py` and
`tools/tg2_country_probe.py`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4490** only;
- kill only your own PIDs.

Only change `tools/`, `game/*.json`, `docs/`, and `game/game.toml` (only
for audited discovery fixes). Report renderer or 60 fps bugs instead of
fixing them; another agent owns 60 fps physics right now. Commit often
and push your branch.

## Goal

Race every one of the 16 tracks for at least 60 s of driving. Cover the
weather and lighting variants (rain, night, whatever exists) and nitro.
Run each in Off and in 16:9 + HUD Edges. With every option combination,
the manifests must stay empty and the widescreen margins must be free of
artefacts.

## How to reach the tracks (pick what works, in this order)

1. **Password system.** Reverse the password encoding from the ROM:
   - find the routine that validates ENTER PASSWORD;
   - document the format in `docs/PASSWORDS.md`;
   - write `tools/tg2_password.py` to generate a valid password for each
     country/level.
   This is the cleanest route, because it uses the game's own UI.
2. **Test-only RAM assist.** If the password can't be reversed in
   reasonable time:
   - find the championship progress / current-track RAM variable(s);
   - set them through the engine's TCP RAM write command while in the
     menus, before the race loads;
   - label it clearly as a **test harness** in tools and docs. It never
     ships in the game.
   Prefer setting the value the game itself writes at a known
   progression point (e.g. after a race result), over arbitrary pokes.
3. **Better driver.** Improve `tg2_race_driver.py` until it finishes top
   ten (needs nitro, better racing line, overtaking) and progress
   normally. Slow, but fully authentic.

**Nitro.** Find the nitro input. Check the game's controls/options screen
and the input remap tables at `$FF19AE..$FF19BA` (RAM_MAP.md); it may be
a button combination or depend on the control configuration. Verify the
nitro count decrements and speed rises.

## Evidence required

- `docs/VALIDATION.md` section 2 rewritten as a per-track table:
  - track, country, weather/lighting;
  - Off pass/fail and 16:9+Edges pass/fail;
  - manifest counts and screenshot paths.
- Nitro: input found, plus before/after speed.
- The password doc and generator, if route 1.
- A precise reproduction (frame, input, mode, screenshot) for any visual
  or behavioural bug found, especially widescreen margin artefacts on
  other tracks: wrapped plane content, missing scenery, sprite
  pop-in/out at the edges.

Partial coverage is acceptable if the ledger is honest.
