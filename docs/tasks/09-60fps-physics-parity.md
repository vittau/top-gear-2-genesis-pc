# Task 09: make 60 fps races physics-identical to stock

Read `AGENTS.md`, `docs/FRAMERATE.md` (the current 60 fps design),
`docs/VALIDATION.md` (sections 1 and the same-route replay) and
`docs/RAM_MAP.md`. Read `game/tg2_spec.c` (the race60 code) and the
qualification tools `tools/tg2_runner.py`, `tools/tg2_race_driver.py`
and `tools/tg2_replay_route.py`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4480** only;
- kill only your own PIDs.

Commit often and push your branch.

## The problem

The 60 fps option produces 60 new pictures/s, but it changes the game:
- the closed-loop full race is +2.35% slower;
- a frame-exact replay of the same inputs gives very different lap splits
  (lap 1: 45.40 s with 60 fps vs 52.38 s stock).

The race clock is identical, so this is player physics/trajectory
divergence. The current design runs the main program with CPU headroom
(`main_cpu_divisor`), and only the view-position input of four IRQ routines
is forced onto a fixed 1-in-3 schedule. But stock picture builds take a
variable 2–3 V-ints, and the main program evidently also advances
gameplay state per build: steering response, curve/centrifugal push,
off-road checks, collision, opponents. That makes the simulation rate
depend on the picture rate.

## Goal

With 60 fps on, gameplay state evolves **exactly as in stock** for the
same controller input per V-int, while the screen updates every V-int:
- **Hard target:** a frame-exact replay of the same input route
  (`tools/tg2_replay_route.py`) gives identical race-clock lap times and an
  identical player state trace (track position, lateral position, speed,
  gear/RPM) at every V-int where stock has completed a logic step.
- **Fallback:** if exact identity is impossible, difference ≤ 1 frame of
  race clock per lap and no visible divergence in trajectory. Quantify it.

## Recommended approach

The decisive fix is to **decouple the stock simulation from the extra
pictures**. Two families of approach; pick on the evidence and justify it
in `docs/FRAMERATE.md`.

1. **Authentic simulation + interpolated presentation.**
   - Run the guest exactly as stock, with no CPU headroom, so all
     game/physics state is bit-identical to stock.
   - On the V-ints where stock has no new picture, the host presents a
     synthesized intermediate picture. Interpolate between the last two
     completed stock pictures in presentation space: per-line road raster
     scroll values, sprite positions, background scroll. The guest's
     raster lists (`$FF231E`/`$FF232C`), the SAT and the H-scroll data are
     all readable state.
   - This is presentation-only, like widescreen, and it composes with the
     widescreen renderer. Coordinate in `game/tg2_video.c`.
   - Since stock cadence is 2–3 V-ints per picture, either present with
     one picture of latency (interpolate towards the newest completed
     picture) or extrapolate. Latency is preferred for correctness.
     Measure added input latency in ms.
2. **Run the stock logic step on its exact stock schedule, render extra.**
   - Identify the per-picture logic step versus the render/build step in
     the main loop. Use the ROM: the main race loop, what it calls per
     iteration, and which calls mutate gameplay state vs only build the
     picture.
   - Execute the logic step exactly when stock would. That means
     replicating the stock CPU-starvation cadence, which is itself
     deterministic given the cycle model: run a shadow cycle count to
     decide when stock would have finished.
   - Execute additional render-only builds in between.
   - Only viable if the logic/render split is clean.

Whichever you choose, the existing measurement tooling must show both:
- 60 changed pictures/s (`tools/probe_framerate.py`; add `--port`);
- the replay identity above.

## Constraints

- With 60 fps Off, output stays byte-identical to stock (frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD`).
- Widescreen + HUD modes keep working with 60 fps on. Verify 16:9 + Edges
  + 60 fps screenshots.
- Music and sound tempo unchanged.
- 2-player races keep stock timing.
- Manifests stay empty.

## Evidence required

- A replay comparison table (stock vs 60 fps): lap times and a per-V-int
  state-trace diff summary (first divergent frame, if any, and max
  abs diff per field).
- The closed-loop full-race comparison re-run (`tools/tg2_race_driver.py`
  in Off vs 60 fps): total time and per lap.
- 60 changed pictures/s.
- Added latency, if any.
- A 6-frame consecutive PNG sequence with 60 fps + 16:9 under `build/fps/`.
- `docs/FRAMERATE.md` updated; the old design marked superseded if
  replaced.
