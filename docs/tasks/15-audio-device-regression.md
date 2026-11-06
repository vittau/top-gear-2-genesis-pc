# Task 15: real-device audio is broken (pops, dropouts, delays): owner bug, top priority

Read `AGENTS.md` (follow its "CI budget" rules: never trigger CI),
`docs/PERFORMANCE.md`, `docs/AUDIO.md`, the engine patches
`patches/segagenesisrecomp/0005-exact-guest-clock-and-frame-telemetry.patch`
and `0006-audio-drc-prime-snap-and-ratio-bound.patch`, and the engine audio docs
(`segagenesisrecomp/docs/ENGINE_AUDIO_*.md`).

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Also build a release-config binary, the same as the owner plays:
`cmake -S . -B build-rel -G Ninja -DCMAKE_BUILD_TYPE=Release
-DGENESIS_RECOMP_ROOT=$PWD/segagenesisrecomp -DTG2_ROM=$HOME/roms/genesis/tg2.bin
-DGEN_ENABLE_TRACE=OFF -DSONIC_REVERSE_DEBUG=OFF -DTG2_BUILD_VERSION=0.1.0-dev`,
then `ninja -C build-rel TG2Recomp`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4540** only;
- kill only your own PIDs.

**The owner is using this desktop. Never play sound on the real speakers**
(see "Reproduce" for a silent sink). Don't open visible windows unless
they are tiny and closed within 60 s. Commit often and push your branch.

## Owner report (latest)

The machine is a Ryzen 5 3500U laptop running KDE/Wayland, monitor at
60.00 Hz, with PipeWire. He played a release-config build of main
c27839b, windowed, Adaptive 16:9 + 60 fps on.

> The music is all broken: pops, dropouts, delays.

History, which matters:
- First playtest, dev build 69a96ef: music "slightly slow, sometimes
  wobbles".
- Second, release-config f618606, before the task 12 pacing changes:
  still slow during races, **no pops** reported.
- Now, c27839b, after task 12 patches 0005/0006 (exact guest clock,
  vsync dropped when the display ≈ the pacer, DRC bounded to ±0.2%,
  80 ms target, 200 ms ring, concealment on): **pops, dropouts, delays.**

So task 12 made the real-device experience worse. Its measurements
showed 0 underruns, which means they did not capture what the device
really plays. The runner log of the owner's session shows only
`[audio] DRC bridge: 223721 Hz internal -> 48000 Hz device (preroll 200 ms -> target 80 ms, conceal on, max correction 0.20%, ring 200 ms)`
and `[pacer] vsync off: display 60.00 Hz vs target 59.9401 fps; the
deadline pacer owns the guest clock`.

## Reproduce objectively (required first)

1. Create a **silent PipeWire/Pulse null sink** as the user, without
   sudo, without changing the default device and without touching the
   owner's audio:
   `pactl load-module module-null-sink sink_name=tg2_test sink_properties=device.description=tg2_test`.
   Point only your process at it (`PULSE_SINK=tg2_test`, with
   `SDL_AUDIODRIVER=pulseaudio` or `pipewire` as appropriate). Record
   what the device actually receives from the monitor: `pw-record` or
   `parecord --device=tg2_test.monitor`.
   **Unload the module when done** (`pactl unload-module <id>`).
2. Run the release-config binary through a race with real-time pacing.
   That's not turbo and not the dummy video driver. Use the offscreen
   or a real GL path at 60 Hz, so the vsync/pacer path is the one the
   owner uses.
3. Write `tools/audio_glitch_detect.py`. On the device recording, detect:
   - dropouts: runs of exact-zero or repeated samples ≥ 2 ms mid-music;
   - pops: sample-to-sample discontinuities far above the music's
     local derivative envelope;
   - timing drift/delays: cross-correlate against the offline
     deterministic WAV of the same route, and measure the local tempo
     ratio over time.
   Report the counts per minute.
4. **Bisect.** Run the same measurement on:
   - f618606, before task 12;
   - c27839b, after it;
   - c27839b with each task-12 behaviour individually reverted or
     disabled: vsync-off decision, DRC bound, 80 ms target,
     prime-snap, overdue-frame skip.
   Find which change or changes cause the pops and dropouts.

## Fix

The music on a real device must be clean: zero dropouts and zero pops in
a 3-minute race, steady tempo, no audible pitch wobble. That must hold
in the owner's configuration (16:9 + 60 fps) and with 60 fps off, and
under a moderate background load (one CPU burner).

The likely policy, but prove it:
- keep vsync on when it works;
- give the device buffer enough headroom (latency ≤ ~100 ms is fine);
- let DRC correct the real device-vs-guest clock offset smoothly, with
  a bound large enough for real crystals (±0.5% is inaudible as pitch);
- never let a short frame-time spike become an underrun.

Measure the device-side result. Offline WAV identity must still hold:
the deterministic WAV SHA-256 is unchanged in offline capture, and the
Off hashes are frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`.

## Evidence required

- `docs/PERFORMANCE.md`, a new "Real-device audio" section with:
  - the null-sink method;
  - the glitch-detector numbers per build and variant (the bisect
    table);
  - the root cause;
  - the fix;
  - after-fix numbers for 3-minute races in both configurations, with
    and without load.
- Engine patch updates recorded in `patches/segagenesisrecomp/README.md`.
- The null sink unloaded, and nothing left running.
