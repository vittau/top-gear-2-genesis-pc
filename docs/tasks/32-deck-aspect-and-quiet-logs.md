# Task 32: Steam Deck feedback — device aspect, no logs in normal use

Read `AGENTS.md` first. Follow the "Machine resources" rules: at most 3 build
jobs (`JOBS=3 tools/build-linux.sh`, which also works on macOS), and run every
build and heavy analysis under `flock ~/.cache/tg2-heavy.lock`. Never trigger
CI, push tags or change workflow triggers. Use `SDL_VIDEODRIVER=dummy` and
`SDL_AUDIODRIVER=dummy` for every run, except short windowed checks you close
at once. One runtime instance at a time. The ROM is `~/roms/genesis/tg2.bin`.

Engine changes go in patches numbered **0045–0049** (reserved for this task),
each with a one-line reason in `patches/segagenesisrecomp/README.md`. Another
worker is doing high-resolution step S3 at the same time (`game/tg2_video.c`,
`game/tg2_highres.c`, presentation; patches 0034+). Stay out of those files;
if you must touch shared engine files such as `runner/main.c`, keep the change
small so the patches stack. Commit often on your branch and push it. Do not
merge into `main`.

## 1. The picture must follow the device's aspect (owner, Steam Deck)

The owner played on a Steam Deck (1280×800, 16:10, Game Mode / Gamescope). The
game ran fine but the picture was **16:9 instead of 16:10**. It must use the
device's resolution and aspect.

Likely cause, to confirm: `runner/main.c` creates the first window at 16:9
(`win_w = (win_h * 16 + 4) / 9` for custom-video games) and only goes
fullscreen when `settings.ini` says so. Adaptive widescreen (`fit`, the
default) follows the *window*, so under Gamescope a 16:9 window is scaled and
letterboxed on the 16:10 panel. The same happens on any device whose panel is
not 16:9 (e.g. the owner's 16:10 MacBook in fullscreen).

Fix it so that:

- In fullscreen (desktop or exclusive), Adaptive uses the actual output size,
  whatever the panel's aspect.
- Under Gamescope / Steam Deck Game Mode (detect it from the environment:
  `SteamDeck`, `SteamGamepadUI`, `GAMESCOPE_WAYLAND_DISPLAY`, … — document
  what you rely on), the game starts fullscreen at the display's size by
  default, with no setup and no terminal, so Adaptive fills 16:10.
- A windowed desktop start keeps working; the first window may follow the
  display's aspect instead of a fixed 16:9 if that is simpler and correct.
- Fixed aspects (16:9, 21:9) and widescreen Off still letterbox as chosen.

Verify what you can here: Adaptive in fullscreen-desktop on a non-16:9 output
(the SDL dummy driver's display or a forced mode), the window size and aspect
the game computes with Gamescope variables set, and the presented picture size.
Say plainly what still needs the owner's Deck.

## 2. No logs in normal use (owner)

After a session the Deck's `logs/` folder held a ~1.4 MB file. The owner
doesn't want logs written in normal use, and suggests a debug flag. The big
file is almost certainly `TG2-feedback.replay`: the **Diagnostics** mod
(`[mods.diagnostics]`, `runner/diagnostic_replay.c`, described in
`runner/app_config.c`) is on by default and records every input for bug
reports (a short smoke test here already wrote 1.1 MB).

Change it so that:

- In normal use nothing is written to `logs/` (and nothing else grows next to
  the executable) beyond settings, saves and a crash report when the game
  actually crashes. Audit every file a release build writes during a normal
  session and list them in your report.
- A `--debug` command-line flag turns on the feedback replay and the other
  diagnostics. Keep the Diagnostics toggle in the launcher/Esc menu so a Deck
  user can turn it on without a terminal; its default becomes **off**.
- Existing installs whose `settings.ini` saved the old default (`enabled = 1`)
  must end up off too; design a migration and explain it.
- Our own tooling must keep working: the probes rely on the runtime manifests
  (`dispatch_misses.toml` & co.) and stderr logs. Keep them in dev builds
  (`GEN_ENABLE_TRACE=ON`) or behind `--debug`, and update any tool that needs
  the flag.
- README (controls/settings and bug-report section) says how to turn
  diagnostics on for a bug report.

## Acceptance

- Off-mode hashes unchanged: frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD` (`tools/probe_run.py --widescreen off --frames 360`);
  all four manifests empty.
- Evidence for part 1: computed window/output sizes and presented picture size
  for 16:10 (1280×800), 16:9 and 4:3 outputs, in Adaptive and in a fixed 16:9.
- Evidence for part 2: a release-profile session (no `--debug`) leaves `logs/`
  empty; the same with `--debug` writes the replay; a migrated old
  `settings.ini` ends with diagnostics off.
- `tools/tg2_release_smoke.py` passes.

Report with `worker_done`: commits, commands and exit codes, hashes, evidence
paths, the file audit, and what needs the owner's Deck.
