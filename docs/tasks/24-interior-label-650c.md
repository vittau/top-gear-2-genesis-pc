# Task 24: fix the skipped scene-init call at $00650C (release bug)

Read `AGENTS.md` first, plus `segagenesisrecomp/CLAUDE.md`, `PRINCIPLES.md` and `DEBUG.md`.
Follow the "Machine resources" rules: at most 3 build jobs, and run every build
under `flock ~/.cache/tg2-heavy.lock`. Never trigger CI. Use SDL_VIDEODRIVER=dummy
and SDL_AUDIODRIVER=dummy for every run. The owner is asleep, so ask only the
coordinator, and only when you are blocked.

## Bug (from task 22, docs/VALIDATION.md)

In races from Greece onward the release build logs an interior-label miss and
a floor-unsafe entry for `$00650C`. A computed dispatch lands in the middle of
the scene-init block that starts at `$64C2`. The floor capsule cannot return
(exit_pc `$7F18`, expected_ret `$001E82`), so the call is **skipped**. Task 22
reproduced it 9 times. Repro:
`tools/tg2_progress.py --country 6 --races 1` on main `77f6e83` or later, then
read the manifests with `tools/tg2_runner.manifest_counts`.

## Goal

The scene init runs exactly as on hardware. Every manifest stays empty in that
repro and across a broader multi-country run.

1. Disassemble `$64C2..` from the raw ROM and establish ground truth. Is
   `$650C` a real entry point? Who dispatches there, and how (a jump table,
   a pushed return address, `JMP (a0)`)?
2. Fix it the way the framework intends. Look at how interior labels and
   in-function dispatch are already handled (`game.toml`,
   `game/*.discovery.toml`, the recompiler's interior-label support) before
   you add anything new. Change the engine only for a genuine framework gap.
   Such a change goes in as a new patch in `patches/segagenesisrecomp/`: take
   the next free number after the highest one on origin/main (0017 today), and
   add a line to that folder's README.
3. Evidence:
   - the repro and a run covering several more countries (Greece, India,
     Italy, Japan, Spain, Switzerland), all with empty manifests;
   - a before/after picture or RAM check proving the scene init's effect is
     present;
   - Off-mode hashes unchanged: frame 60 `2A0B972960C5E325`, frame 300
     `1131D937D70234FD`.

Commit often, push your branch, and report with `worker_done`.
