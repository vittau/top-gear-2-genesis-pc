# Task 12: performance and audio pacing on low-end CPUs (owner-reported)

Read `AGENTS.md`, `docs/FRAMERATE.md`, `docs/WIDESCREEN.md`,
`docs/RELEASING.md` and the engine audio docs
(`segagenesisrecomp/docs/ENGINE_AUDIO_*.md`,
`GENESIS_AUDIO_FIDELITY.md`).

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4510** only;
- kill only your own PIDs.

Another agent is fixing widescreen margins in `game/tg2_video.c`
(task 11). Coordinate by keeping renderer changes surgical, and merge
`origin/main` before reporting. Commit often and push your branch.

## Owner report

Playing the development build (`build-main`, with `GEN_ENABLE_TRACE` and
`SONIC_REVERSE_DEBUG` on) in a window, with Adaptive widescreen and
60 fps on, **the music plays slightly slower than normal and sometimes
wobbles in speed**.

The machine is an **AMD Ryzen 5 3500U** (4c/8t Zen+ laptop, Vega 8). That's
the same class as a Steam Deck (Zen 2, 4c/8t), so performance here is a
release requirement. Wayland/KDE, monitor at 60.00 Hz. The runner logs
`[audio] DRC bridge: 223721 Hz internal -> 48000 Hz device (preroll 200
ms, conceal on)`, `[pacer] target frame rate: 59.9401 fps`,
`renderer=opengl vsync=1`.

Hypothesis: the runner can't sustain real time in some scenes. The
dynamic-rate-control audio bridge then stretches the audio (slower,
wobbling pitch/tempo). Or DRC is fighting vsync at 60.00 Hz vs the
59.94 Hz pacer target. Prove or disprove both.

## Goal

On this machine, the **release build** (CI configuration: tracing and
reverse-debug off; reproduce it locally with the same CMake options as
`.github/workflows/build.yml`) runs races at full speed:
- in a real window, with 16:9 + HUD Edges + 60 fps on;
- with comfortable headroom (target: ≤ 60% of the frame budget for
  emulation + render on a 60 Hz frame, 95th percentile);
- with music at the correct tempo and pitch and no audible wobble.

The development build should also be usable, but it's not the target.

## Desktop etiquette

The owner may be playing on this desktop. For windowed measurements, prefer
a nested/virtual compositor (`kwin_wayland --virtual`, `weston
--backend=headless` with GL, or similar, if installed without sudo), so
the real GL/vsync path runs without popping windows. If you must use the
real desktop, keep runs short (≤ 90 s) and close them yourself.

## Steps

1. **Measure.** Add frame-timing telemetry, or use the engine's existing
   timing:
   - per-frame wall time split into guest emulation, the widescreen
     renderer, 60 fps interpolation, audio, and present/vsync wait;
   - the DRC ratio over time and buffer fill.
   Run a race in a visible window: SDL video on, the default Wayland or
   X11 driver, not dummy. Do it for dev vs release, and with each option
   on/off. Report p50/p95/p99 frame times and the DRC ratio range.
2. **Profile** the release build with `perf` if available. If not, and
   installing it needs sudo, stop and `ask`. Use sampling or
   instrumentation otherwise. Find the hotspots. Optimise them (renderer,
   interpolation, per-pixel loops, unnecessary per-frame allocations,
   rewind snapshot cost, feedback-replay recording cost), with no change
   to output: hashes and WAVs identical.
3. **Fix audio pacing.**
   - The music must hold the exact stock tempo. The generated audio is
     already sample-identical; the problem is real-time delivery.
   - Check how the pacer, vsync and DRC interact when the display runs
     at 60.00 Hz and the pacer at 59.94 Hz. Consider a 60 Hz pacer that
     follows the display, or vsync off with the pacer in charge.
   - Bound DRC's maximum ratio deviation, so that a sustained deficit
     isn't masked by audible stretching.
   - Document the chosen policy.
4. **Feedback-replay path bug.** The runner logs
   `[feedback-replay] /home/vitor/.local/bin//logs/TG2-feedback.replay`,
   both from `build-main/` and from the release folder
   `~/Games/TG2-release-69a96ef/...`. It's writing logs into
   `~/.local/bin`. Find out why: base-path resolution through `PATH`,
   an `argv[0]` assumption, or similar. Make it write next to the
   executable, or to the platform user data dir per the engine's
   convention, and document where. Same check for `settings.ini`, the
   evidence manifests and save states.

## Evidence required

- `docs/PERFORMANCE.md` covering:
  - before/after frame-time tables (p50/p95/p99), dev vs release, per
    option;
  - hotspots found and fixes applied;
  - before/after DRC ratio ranges;
  - the pacing policy.
- Proof of identical output: Off hashes, the 60 fps replay identity and
  road artefact check, byte-identical WAVs.
- A 60 s windowed race recording of the DRC ratio and buffer fill,
  showing stable real-time delivery after the fix.
- The feedback path fix, with where files now go.
