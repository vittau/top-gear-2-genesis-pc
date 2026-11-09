# Task 27: save states on the car setup screen

Status: mapped for later (owner, 2026-11-09). Not started. The owner wants
this one; the password screen is explicitly out of scope.

Read `AGENTS.md` first. Follow the "Machine resources" rules: at most 3 build
jobs, and run every build under `flock ~/.cache/tg2-heavy.lock`. Never trigger
CI. Use SDL_VIDEODRIVER=dummy and SDL_AUDIODRIVER=dummy for every run. Engine
changes go in new patches numbered after the highest one on origin/main, with a
line in `patches/segagenesisrecomp/README.md`.

## Where things stand

A quickstate is only written at a declared per-frame **boundary** that the host
can re-enter in a fresh process (engine patch 0018, `game/tg2_spec.c`
`tg2_resume_sites`). Today there are four: the race loop `$0065F2`, the
top-level loop `$001E18`, the title START spin `$001E9D8` and the main-menu page
loop `$001EBF6`. On load, patch 0021 resumes the loop with the restored stack and,
when it returns, continues each guest return address that follows a JSR/BSR.
`$001E82` (after the race) and `$001E1E` (after the title/menu) are seeded for
that.

The setup screen has no boundary:

- **New game** (main menu → START → game setup): the save is refused with
  `SAVE UNAVAILABLE HERE` (`menu-setup` in the quickstate matrix,
  docs/VALIDATION.md "Task 25 — cross-session quickstates").
- **Between races** (results → championship → setup/shop → next intro): since
  patch 0024 the save is queued and written at the start of the next race
  (`SAVING AT NEXT BOUNDARY...`). The file holds the race start, not the
  setup screen.

Confirm first that the owner's "car setup" is this game-setup screen (the one
`tools/tg2_race_driver.py boot_to_setup` reaches and where writing `$FF16BE`
picks the race), and whether the new-game and between-race visits run the same
code. If the shop is a separate screen, it is not part of this task.

## Why the obvious fix failed

Seeding the inter-race screens' own one-frame waits as boundaries was tried
(docs/VALIDATION.md, "Quickstate lost between races"). The saves landed, but a
load bailed out of the race flow to the main menu. Those screens' loops are
reached by **dispatch** (a jump table), not by a JSR/BSR chain, so after the
resumed loop returns the engine can't follow the guest callers:
`floor_unsafe: $001E6A ... capsule exit_pc != native loose-A7 return`
(`build/evidence/resume-5/loadcheck2/step1.png`). A save that loads wrong is
worse than a refusal, so the sites were removed.

## Approaches to evaluate (in this order)

1. **Map the call chain from the ROM.** Disassemble from the top-level loop
   (`$001E52`/`$001E6A`/`$001E82`) to the setup screen's frame loop
   (`tools/disasm_tg2.py`), and read the real guest stack on that screen
   (`get_registers` + WRAM, as was done for `$001E82`). Record which links
   are JSR/BSR and which are a jump-table dispatch.
2. **Resume one level up.** If the dispatcher that selects the setup screen
   is itself reached by JSR/BSR, resume there instead of inside the screen
   loop, with the screen's selector in restored RAM. Check that re-running the
   screen's init from the saved RAM redraws the same picture (VRAM/CRAM come
   back from the snapshot, but the init may clear them or reset the cursor).
3. **Record the dispatch continuation in the host payload.** Add the address
   the dispatch would return to (or the jump-table index) to `Tg2HostState`
   (bump `TG2_STATE_VERSION` and `state_build_id`), and have
   `tg2_state_resume_pc` / an engine hook continue there when the resumed loop
   returns. This probably needs an engine patch next to 0021 for a
   non-JSR return. Do it only if 2 is not possible.

Every new seed is checked against the raw ROM before it goes into
`game/game.toml` (engine PRINCIPLES #16).

## Acceptance

- Saving on the setup screen writes the file at once (no queue, no refusal),
  on a new game and between races.
- Loading it in a **fresh process** (boot 600 frames first) shows the same
  picture (0.0 % differing pixels against the saving process's screenshot),
  with the setup cursor and money/upgrades intact.
- From the loaded state, START → intro → race starts the right race
  (`$FF16BE` unchanged), the race finishes and the post-race flow continues
  to the next race (the `$001E82` path), not to the title.
- Rewind and same-process F-key loads still work. Saves on the other
  inter-race screens keep the patch 0024 behaviour.
- New cases in `tools/tg2_state_matrix.py` (`menu-setup` turns from refused
  to live; add `setup-between-races`) and a row in
  `tools/tg2_postrace_save_probe.py`'s table.
- Stock identity unchanged (frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD`), all four manifests empty.
