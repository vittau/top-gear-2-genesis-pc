# Task 22: v0.1.0 release qualification (every race, default options)

Read `AGENTS.md` (follow its "Machine resources" and "CI budget" rules: at
most 3 build jobs, `flock ~/.cache/tg2-heavy.lock` around every build and
heavy run, never trigger CI), `docs/STATUS.md` ("Priority: first playable
release"), `docs/VALIDATION.md`, `docs/PASSWORDS.md`, and the probe tools
(`tools/tg2_password.py`, `tools/tg2_password_ui.py`,
`tools/tg2_country_probe.py`, `tools/tg2_race_driver.py`,
`tools/tg2_soak.py`, `tools/tg2_split_screen.py`).

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- run `tools/apply-engine-patches.sh`;
- build with `JOBS=3 flock ~/.cache/tg2-heavy.lock tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Use **TCP port 4610** only, and kill only your own PIDs. No visible windows,
no sound on the owner's speakers: dummy video and audio drivers only. Commit
often and push your branch.

## Goal

The owner's priority is a first release that is playable and has no major
bugs. This task finds the bugs a player would hit before the owner
playtests the release candidate. It is a **qualification** task: the
deliverable is the evidence and a bug list. Fix a bug yourself only if the
fix is small, clearly correct, and in `game/` or discovery evidence
(`game.toml`). Otherwise report it with a reproduction.

## Coverage

Run with the **default options**: widescreen Adaptive (use a 16:9 canvas),
60 fps races On, HUD Centered, Hide overscan On, and the default race sound.
Then repeat a subset with every option off.

1. **Every race of every country.** The password `stage` field (0..2) and
   `country` (0..15) reach races the championship gate hides. Each
   country's later races have never been visited. First establish how many
   races each country really has and which `stage` reaches each. Then race
   each one for at least 60 s, or for a full race where practical, with
   screenshots at the start, mid-race and after the finish. Use
   `tools/tg2_password.py` to mint passwords.
2. **A full championship flow:** race → results → championship table →
   shop/setup → the next race, across at least 3 consecutive races,
   including a password continue.
3. **2-player split screen:** one full race.
4. **Sound modes:** a race each in MUSIC and SFX. Do BOTH only if
   `origin/main` already contains the dual-chip BOTH (task 20). Check each
   WAV with `tools/audio_glitch_detect.py`: 0 pops and 0 dropouts.
5. **Release-config smoke:** build with the release profile
   (`-DGEN_ENABLE_TRACE=OFF -DSONIC_REVERSE_DEBUG=OFF`; see
   `tools/release/build-linux.sh`), then run a scripted route with the ROM
   beside the binary under an unrelated name. It must boot, race and exit 0.

## Gates (after every run)

- No crash, hang or guest exception.
- `dispatch_misses.toml`, `floor_coverage.toml`, `floor_unsafe.toml` and
  `interior_label_misses.toml` are empty. A non-empty manifest is a bug:
  fix it in discovery (`game.toml`) with ROM evidence, then rerun.
- No visible corruption in the screenshots: road, margins, HUD and sprites.
  Use `tools/check_road_artifacts.py` and the margin audit where they apply.
- With every option off, frame 60 `2A0B972960C5E325` and frame 300
  `1131D937D70234FD`.

## Evidence required

- A coverage table added to `docs/VALIDATION.md`: country × stage, with
  password, result (passed / bug #), manifest counts and screenshot paths
  (under `build/`, outside git).
- A numbered **bug list** in your report: severity (blocker / major /
  minor), a reproduction (password plus input script or frame), and whether
  you fixed it (commit) or not.
- What is verified and what is not, stated plainly.
