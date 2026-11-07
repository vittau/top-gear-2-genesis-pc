# Task 25: cross-session save states, then the 19 unreached races

Read `AGENTS.md` first. Follow the "Machine resources" rules: at most 3 build
jobs, and run every build under `flock ~/.cache/tg2-heavy.lock`. Never trigger
CI. Use SDL_VIDEODRIVER=dummy and SDL_AUDIODRIVER=dummy for every run. The owner
is asleep, so ask only the coordinator, and only when you are blocked.

## Part A: a quickstate loaded in a fresh process freezes the race (major)

Task 22's findings are in docs/VALIDATION.md. Repro: `tools/tg2_state_freeze.py`
(build/qual/qa-state). After the load, the guest clock and RAM keep advancing
but the picture freezes on "GO!". Over 420 frames there is 1 distinct picture,
against 8 in a same-process load. Same-process rewind works.

The root cause is likely in the adapter:
- TG2 sets neither `resume_main_loop_pc` nor `save_resume_pc`, and `game_mode`
  is 0. So the load resumes inside the title's native chain, not at the top of
  a game loop.
- `on_state_loaded = tg2_post_reset` also wipes host presentation state that
  the snapshot never carried.

Fix it properly. Either provide the resume PCs and game-mode address the
framework expects, or implement host-side `state_size/state_save/state_load`
for TG2's own state, or both. Check how RocketKnightAdventuresRecomp
(`~/git/tg2-deps/RocketKnightAdventuresRecomp`) does it.

Acceptance:
- F1..F9 save states survive a restart and resume the race live: in menus,
  in a race, with 60 fps on and off, in widescreen, in BOTH sound, and in 2P
  if reachable.
- Rewind still works.
- Off-mode hashes are unchanged (frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD`).
- Every manifest stays empty.

If a full fix is not safe for 0.1.0, refuse cross-build or cross-session
loads with a clear on-screen message rather than freezing. Report which one
you chose.

## Part B: qualify the 19 races passwords can't reach

The password always resumes at a country's first race, and the top-ten gate
stopped the scripted runs. The missing races:
- Canada race 4;
- Egypt races 2-4;
- India races 2-4;
- Italy race 4;
- Scandinavia races 3-4;
- South America races 3-4;
- Spain races 3-4;
- Switzerland races 2-4;
- U.S.A. races 3-4.

Reach them anyway. One way is to set the race index in RAM once the country
is loaded; another is a state saved after winning. Ground the RAM address in
the ROM ($01B8E8 progression) first. Drive each race to the finish with the
release defaults. Update the coverage table in docs/VALIDATION.md, keeping
the same columns.

Commit often, push your branch, and report with `worker_done`.
