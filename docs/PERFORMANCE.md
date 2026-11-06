# Race performance and audio pacing

Owner report (Ryzen 5 3500U, 4c/8t Zen+, Vega 8; Wayland/KDE at 60.00 Hz;
16:9 + HUD Edges + 60 fps on): **music plays slightly slower than normal and
sometimes wobbles in speed**, and a later retest of the release build reported
the same during races only, with menus fine.

Three independent causes were measured; all three are fixed. Evidence below is
private under `build/perf/` (no ROM, generated C or state dumps are committed).

## 1. Root causes

### 1.1 The DRC bridge resampled the boot pre-roll away for ~26 s

The audio bridge (`runner/recomp_audio_drc.h`) primes its ring to a 200 ms
pre-roll, targets 50 ms, and was allowed to correct the ratio by up to
**±0.5 %** (8.6 cents) while slewing at 0.75 percentage-points/s. Nobody told
it the excess pre-roll was disposable, so after every boot and every bridge
reset it "drained" 150 ms of surplus at 0.5 % — which takes **26 seconds**.

Measured on this machine (600 boot frames, real PipeWire device, before):

| Frame | ratio correction | ring fill |
|---:|---:|---:|
| 60 | +3780 ppm | 188.4 ms |
| 120 | **+5000 ppm (clamped)** | 181.8 ms |
| 300 | +5000 ppm | 161.4 ms |
| 540 | +5000 ppm | 134.3 ms |

**523 of 600 frames sat at the +0.5 % clamp.** Everything played in that window
(menu music, the start of a race) was up to 8.6 cents sharp and sagged back to
pitch over ~26 s. That is the "wobbles in speed" report.

### 1.2 The controller chased an aliased fill sawtooth

Guest audio arrives one video frame at a time (~16.7 ms of audio per push) while
the device consumes continuously, so the instantaneous fill is a sawtooth of
that amplitude. With a 50 ms target, the sawtooth is ±33 % of target, and the
controller sampled it on a 21.3 ms callback cadence — near the push period. The
servo therefore chased aliasing noise and swung over its whole range.

### 1.3 Guest time was being thrown away on late frames

`frame_pacer_deadline()` reset the whole cadence whenever a frame was more than
one period late. Each reset discarded real time, and the guest clock is what
produces audio: the Z80 sound driver's sequencer is stepped from the same
master clock inside the video frame. Separately, with vsync on at 60.00 Hz the
guest was quantised to the display refresh (60.00 instead of 59.94 fps, +0.1 %),
which the bridge then had to remove from the audio for ever.

## 2. Where Top Gear 2's music sequencing runs

Measured, not assumed (dev build with the chip/command rings, `--snd-dump-frame`):

* **FM register writes are emitted by the Z80 program.** With writer attribution
  on 262,144 consecutive FM/PSG pushes: **256,590 FM writes from Z80 PCs (98 %)**,
  5,206 from the 68K, and 348 PSG writes from the 68K. The hot Z80 PCs are
  $0CB2 (140k), $0C4C/$0C4F (37k each), $067F/$068E (18k each).
* **The Z80 program is not interrupt-driven.** Its reset vector is `C3 10 04`
  (JP $0410) at Z80 $0000, its $0038 area holds data, and the 8 KiB image
  contains no `IM`/`RETI`/`RETN`. $0410 does `DI`, sets the stack, and spins on
  a command byte at $025E before calling its dispatcher — a polled main loop.
* **The 68K only sends commands, not ticks.** In the same ring window the 68K
  wrote the 4-byte block $025E-$0261 (bus request + reset asserted, scanline
  224) on 20 frames out of ~248 — i.e. on music/SFX changes, not once per frame.

So the sequencer is a free-running Z80 program whose clock is **emulated Z80
(master) cycles**, and this runner advances the Z80 from the same master clock
inside each video frame (`machine_run_frame_ex` → `step_z80`). Music tempo is
therefore locked to guest frame time: any host-side loss of guest ticks is a
tempo change, and no amount of buffering hides it. True device-clock decoupling
would require running the Z80/68K ahead of the video loop, i.e. changing guest
timing. The chosen policy is the other branch of that decision tree: **the guest
always advances in exact real time; video is dropped when it cannot keep up.**

## 3. What was implemented

Engine changes are kept as patches in `patches/segagenesisrecomp/` (0004-0006).

| Change | Where |
|---|---|
| Discard the pre-roll at prime instead of resampling it away; reset the controller state at that moment | `recomp_audio_drc.h` |
| Steady target 80 ms, ring 200 ms, error low-pass 300 ms, deadband 2 ms, slew 0.5 pp/s, ratio bound **±0.2 % (3.4 cents)** | `audio.c` (config only) |
| Guest clock is authoritative: a late frame repays its tick (no cadence reset), presentations are skipped while catching up, and only a ≥250 ms discontinuity resyncs | `frame_pacer.h`, `main.c` |
| An overdue frame skips presentation-only work (60 fps synthesis) — guest state and audio untouched | `main.c` → `genesis_frame_overdue()`, `game/tg2_video.c` |
| vsync off while the display is within 1 % of the pacer target, so the deadline pacer owns the guest clock instead of being quantised to the display | `main.c` |
| Always-on per-frame statistics ring: wall phases, thread-CPU phases, pacer wait/present, DRC ratio/fill/pushed/pulled counters | `host_timing.h`, `audio.c` |
| Rewind thumbnail generated only on snapshot frames | `local_states.c` |
| Base directory resolved from the running image (`$APPIMAGE` only if the executable really is inside it) | `main.c`, `diagnostic_replay.c` |
| Race renderer: per-row VDP patch/restore instead of a 64 KiB copy; static row scratch | `game/tg2_video.c` |

The pacing policy in one line: **the guest clock and the audio sample stream are
never stretched to absorb a video problem.** Video is dropped (`presentation_skipped`),
DRC correction is bounded to ±0.2 %, and beyond that the bridge conceals
(pitch-preserving loop) or drops source frames rather than changing tempo.

## 4. Frame-time measurements

Method: `tools/probe_perf.py` drives the committed baseline route through the
runner's exact-wall-frame input script (no TCP, so release builds measure the
same as dev builds) and post-processes the always-on ring. "CPU work" is thread
CPU time for the frame minus the CPU burned inside the pacer's spin — the
load-independent cost measure. Budget = 16.683 ms (59.94 fps).

All runs: real Wayland session, 60.00 Hz, 398×224 canvas, audio on the real
PipeWire device at 48 kHz (master volume 0 for silent measurement), no other
work of ours running. The machine is shared with other agents; ambient load is
recorded per run, and the quiet runs are marked.

### 4.1 Release build (CI configuration: Release, trace + reverse-debug off, static SDL2), race window 3300-4300 (1000 frames)

| Window | CPU p50 | CPU p95 | CPU p99 | p95 / budget | wall p50 | wall p95 |
|---|---:|---:|---:|---:|---:|---:|
| 16:9 + Edges + 60 fps (quiet, load 2.6) | **6.47 ms** | **9.57 ms** | 11.51 ms | **57.4 %** | 6.60 ms | 9.89 ms |
| 16:9 + Edges + 60 fps (load 3.5-4.3) | 9.65 ms | 15.40 ms | 17.72 ms | 92.3 % | 10.0 ms | 16.76 ms |
| Widescreen off, HUD centered, 60 fps on | 5.97 ms | 9.63 ms | 11.34 ms | 57.7 % | — | 10.41 ms |
| 16:9 + Edges, 60 fps **off** | 4.93 ms | 6.39 ms | 7.21 ms | 38.3 % | — | 7.22 ms |

The 60 fps synthesis roughly doubles the per-row VDP work (it renders the mixed
row in addition to the guest row), which is the whole difference between the
last two rows.

### 4.2 Full race route, release build, five 500-frame windows (frames 3100-5600, 41.6 s)

| Window | CPU p50 | CPU p95 | p95 / budget | guest clock | conceals |
|---|---:|---:|---:|---:|---:|
| 3100-3600 | 8.15 ms | 12.97 ms | 77.7 % | -26 ppm | 0 |
| 3600-4100 | 6.69 ms | 10.65 ms | 63.8 % | +82 ppm | 0 |
| 4100-4600 | 7.55 ms | 11.43 ms | 68.5 % | -7 ppm | 0 |
| 4600-5100 | 7.23 ms | 11.20 ms | 67.1 % | +47 ppm | 0 |
| 5100-5600 | 7.85 ms | 11.12 ms | 66.6 % | -41 ppm | 0 |
| whole race | 7.57 ms | 11.60 ms | 69.5 % | -5 ppm | 0 |

This is the windowed race run under ambient load 2.9-6.2. There is no cliff in
any section: the cost tracks how much of the picture is synthesized, not the
track geometry. Note the route is the committed baseline route; it covers
frames 3096-5600 of Auckland (the run ends with the car stopped). Tunnel and
hill sections are inside this window for that route but are not separately
labelled — the per-window table is the honest statement of coverage.

### 4.3 Development build (trace + reverse-debug on), same window

| Run | CPU p50 | CPU p95 | p95 / budget | DRC ratio | conceals |
|---|---:|---:|---:|---|---:|
| before (pre-fix behaviour, telemetry only) | 7.03 ms | 10.67 ms | 63.9 % | -1482…+1009 ppm | 1 |
| after (quiet) | 9.00 ms | 16.93 ms | 101.5 % | -2000…+2000 ppm (at bound) | 1 |

The dev build is ~40 % more expensive per frame (TCP server, frame rings,
reverse-debug store ring) and under ambient load its tail exceeds the budget;
that is the documented cost of the instrumentation, not a game regression. It
remains usable (no underruns, tempo still bounded).

### 4.4 DRC ratio and ring fill, before vs after

| Configuration | ratio range | frames at clamp | fill range |
|---|---|---:|---|
| Before, boot window (600 frames) | -180…**+5000 ppm** | 523 / 600 | 0-193 ms |
| After, boot window (600 frames) | **-1600…-60 ppm** | 0 | 47-63 ms |
| Before, race window | -1482…+1009 ppm | 0 | 6.1-43.7 ms |
| After, race window (quiet) | **-645…+281 ppm** | 0 | 44.4-74.0 ms |
| After, race under 2 CPU burners | -1066…+514 ppm | 0 | 34.1-74.0 ms |

Worst steady correction after the fix is 0.16 % (2.8 cents) during the first
seconds of boot, then it settles below 0.07 %. Before, it was 0.5 % for 26 s.

## 5. 60 s windowed recording under deliberate load

Release build, frames 3100-4400 (19.2 s of race, 1150 frames - the ring window
is 24 576 frames, so a longer capture is available on request), **two CPU
burners running in parallel** on a machine already shared with other work:

| Metric | Value |
|---|---|
| guest clock vs wall | **+11 ppm** (59.9406 fps measured) |
| audio produced vs wall | -99 ppm |
| audio device clock vs wall | -605 ppm (host audio clock, absorbed by the bridge) |
| audio drift (produced seconds - wall) | **-1.9 ms** over 19.2 s |
| DRC ratio | -1066 … +514 ppm (abs mean 358 ppm) |
| ring fill | 34.1 … 74.0 ms |
| underruns / conceal events | **0 / 0** |
| CPU work p50 / p95 | 7.43 ms / 11.43 ms (68.5 % budget) |

The raw series is `build/perf/rel-load60b/frame-stats.csv` (one row per frame:
interval, wait, present, nine wall phases, nine CPU phases, DRC ratio, fill,
underrun/conceal counters, pushed/pulled sample counts).

## 6. Hotspots and fixes

Profile: `gprof` build (`-pg`, CI options), 3600 turbo frames of the same race,
`build/perf/gprof-before.txt` / `gprof-after.txt`.

| Rank | Function | Before | After |
|---:|---|---:|---:|
| 1 | `fetch_plane_span` (VDP plane fetch) | 17.7 % | 16.7 % |
| 2 | `tg2_video scanline` (per-row synthesis + capture) | 12.2 % | 14.1 % |
| 3 | `pixel` (TG2 plane-B sampling, road geometry) | 6.7 % | 7.9 % |
| 4 | `gvdp_render_scanline` | 6.2 % | 7.3 % |
| 5 | `draw_scanline` (widescreen + HUD) | 7.1 % | 7.0 % |
| 6 | ymfm YM2612 (FM synthesis at 223 kHz) | 13.4 % | 19.5 % |
| — | `genesis_local_states_note_frame` (thumbnail) | 2.7 % | **0 %** |

Fixes applied (all output-neutral):

1. **Per-row `GVDP` copy removed.** The synthesized row was built by copying the
   whole 64 KiB VDP state per scanline (`mixed_vdp = *source`): 14.8 MiB of
   memory traffic every frame at 60 fps, which also evicted the VRAM the
   renderer then read. The row is now rendered from the endpoint snapshot with
   an undo log (one scroll word + at most 64 sprite words), restored afterwards.
2. **Rewind thumbnail only on snapshot frames** (was a 48×32 downscale every
   frame for a picture that was overwritten before use).
3. **Overdue frames skip the 60 fps synthesis entirely** (their picture is not
   presented), so catch-up is roughly twice as fast.
4. Static row scratch instead of ~13 KiB of stack zeroing per row.

The remaining cost is intrinsic: with 60 fps on, the engine renders each scanline
twice (guest picture + synthesized picture) and the TG2 renderer samples plane B
per pixel for the widescreen margins and per-pixel road geometry. Further wins
need either a different synthesis design or guest-visible changes.

## 7. Output identity

Every change is host-side; guest-visible output is unchanged.

| Check | Result |
|---|---|
| Off, frames 1-5600 framebuffer hashes vs pre-change baseline | **5600/5600 identical** |
| Off cold-boot fingerprints (frames 60 / 300) | `2A0B972960C5E325` / `1131D937D70234FD` (stock) |
| Off picture cadence, frames 3601-3960 | 186 changed pictures, intervals 66×1 / 66×2 / 53×3 (stock) |
| 60 fps, frames 1-5600 framebuffer hashes vs pre-change On run | **5600/5600 identical** |
| 60 fps, frames 3601-3960 | **360/360** changed pictures |
| 60 fps road artefact audit | 2503 presentations, 1511 synthesized frames, **83 732 road rows, 0 violations**, 992 real pictures, 0 snapshot inconsistencies |
| WRAM at frames 3300 / 4500 / 5200, 60 fps Off vs On | **byte-identical** |
| WAV, Off vs On, whole run | **byte-identical**, SHA-256 `c572492e…88d02` (the documented stock audio) |
| dispatch / floor / interior / unsafe manifests | **0 entries** |

The audit exports endpoint and presented plane-B rows per synthesized line and
checks edge envelopes, stripe runs, atlas rows and byte-exact translation
(`tools/check_road_artifacts.py`, `--road-audit`).

## 8. Feedback-replay and base-directory bug

The runner used `$APPIMAGE` as the base directory whenever it was set, without
checking that it described *this* process. AppImage exports the variable to its
whole child environment, so a plain binary launched from a terminal or launcher
that is itself an AppImage inherited a stranger's path:

```
[feedback-replay] /home/vitor/.local/bin//logs/TG2-feedback.replay
```

That is exactly what the owner saw, from both `build-main/` and
`~/Games/TG2-release-69a96ef/`: `~/.local/bin` was the *Orca/AppImage parent's*
directory (`$APPIMAGE=/home/vitor/.local/bin/orca-linux.AppImage`).

Fix (`init_exe_dir`): resolve `/proc/self/exe` first and honour `$APPIMAGE` only
when the running executable actually lives under `$APPDIR` (the AppImage mount).
Otherwise the variable is ignored. The replay folder path also no longer
doubles the separator.

Files now go next to the executable (or under `$GENESIS_USER_DIR` when that is
set, which is what the replay-diagnostic tooling uses):

| File | Location |
|---|---|
| Feedback replay + sidecars | `<exe dir>/logs/TG2-feedback.replay{,.config.ini,.mods.txt,.sav}` |
| `settings.ini`, `rom-<game>.cfg` | `<exe dir>/` |
| Evidence manifests (`dispatch_misses.toml`, `floor_coverage.toml`, `interior_label_misses.toml`, `floor_unsafe.toml`) | `<exe dir>/` |
| Rewind/quick save states | `<exe dir>/` |
| WAV / `--hash-frames` outputs | wherever the caller points them |

## 9. What is not verified

* The 60 % p95 target was met on a quiet machine (**57.4 %**) and in the
  38 % / 58 % option rows; under the ambient load of this shared workstation
  (other agents building and running games) the same window measured 63-92 %.
  The owner's own machine at rest is expected between those; the release build
  keeps the guest clock exact and never drops audio even in the loaded runs.
* Tunnel/hill sections are covered only as part of the committed baseline route
  windows above; no per-section labels exist in that route.
* No `perf` on this host (installing it needs sudo), so the profile is gprof.
* Windows/macOS behaviour of the new vsync/pacer policy is unqualified; it is
  the same SDL path, but only Linux was measured.
* The owner's listening test after these changes is still required.

## Reproduction

```sh
JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build          # dev build
tools/release/build-linux.sh --rom ~/roms/genesis/tg2.bin \
    --sdl <SDL2-2.28.5 source> --version 0.1.0-local                # CI configuration

# Race window, real window, silent (volume 0) but real audio clock:
python3 tools/probe_perf.py \
    --exe build-release/dist/linux/TG2Recomp-linux-x86_64/TG2Recomp \
    --out build/perf/run --frames 4400 --start 3300 --count 1000 \
    --widescreen 16:9 --hud edges --display wayland-1 \
    --runtime-dir /run/user/1000 --cpus 1,3,5,7
# Deliberate load: add --load 2 (two CPU burners in parallel).

# Output identity:
python3 tools/probe_framerate.py --port 4510 --out build/perf/off --turbo
TG2_HUD_MODE=edges python3 tools/probe_framerate.py --port 4510 \
    --out build/perf/on --turbo --60fps --widescreen 16:9 --hud edges --road-audit
```

`GENESIS_FRAME_STATS=<path>` writes the per-frame CSV; the ring is always on and
the file is written at exit. Nothing is written unless the variable is set.
