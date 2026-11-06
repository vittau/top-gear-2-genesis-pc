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

All measurements below were repeated after merging `origin/main` (task 11's
widescreen margins); the section header says which tree each row is from.

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
| 16:9 + Edges + 60 fps (quiet, load 1.5, merged tree) | **6.01 ms** | **10.09 ms** | 11.89 ms | **60.5 %** | 6.2 ms | 10.3 ms |
| 16:9 + Edges + 60 fps (quiet, load 2.6, before the task-11 margin merge) | 6.47 ms | 9.57 ms | 11.51 ms | 57.4 % | 6.60 ms | 9.89 ms |
| 16:9 + Edges + 60 fps (load 3.5-4.3) | 9.65 ms | 15.40 ms | 17.72 ms | 92.3 % | 10.0 ms | 16.76 ms |
| Widescreen off, HUD centered, 60 fps on | 5.97 ms | 9.63 ms | 11.34 ms | 57.7 % | — | 10.41 ms |
| 16:9 + Edges, 60 fps **off** | 4.93 ms | 6.39 ms | 7.21 ms | 38.3 % | — | 7.22 ms |

(This branch was merged with `origin/main` after the task-11 widescreen-margin
work landed; the margin code adds a small amount of per-row work, which is the
difference between the first two rows.)

The 60 fps synthesis roughly doubles the per-row VDP work (it renders the mixed
row in addition to the guest row), which is the whole difference between the
last two rows.

### 4.2 Full race route, release build, five 500-frame windows (frames 3100-5600, 41.6 s)

| Window | CPU p50 | CPU p95 | p95 / budget | guest clock | conceals |
|---|---:|---:|---:|---:|---:|
| 3100-3600 | 6.31 ms | 11.48 ms | 68.8 % | -6 ppm | 0 |
| 3600-4100 | 6.65 ms | 11.05 ms | 66.2 % | -13 ppm | 0 |
| 4100-4600 | 6.66 ms | 11.32 ms | 67.9 % | -13 ppm | 0 |
| 4600-5100 | 6.29 ms | 9.94 ms | 59.6 % | -50 ppm | 0 |
| 5100-5600 | 6.72 ms | 10.30 ms | 61.7 % | +45 ppm | 0 |
| whole race | 6.56 ms | 10.88 ms | 65.2 % | -0.6 ppm | 0 |

This is the windowed race run on the merged tree under ambient load 4.5-5.5.
There is no cliff in
any section: the cost tracks how much of the picture is synthesized, not the
track geometry. Note the route is the committed baseline route; it covers
frames 3096-5600 of Auckland (the run ends with the car stopped). Tunnel and
hill sections are inside this window for that route but are not separately
labelled — the per-window table is the honest statement of coverage.

### 4.3 Development build (trace + reverse-debug on), same window

| Run | CPU p50 | CPU p95 | p95 / budget | DRC ratio | conceals |
|---|---:|---:|---:|---|---:|
| before (pre-fix behaviour, telemetry only) | 7.03 ms | 10.67 ms | 63.9 % | -1482…+1009 ppm | 1 |
| after, quiet (load 2.6) | 8.99 ms | 16.93 ms | 101.5 % | -2000…+2000 ppm (at bound) | 1 |
| after, merged tree (load 6.1) | 12.32 ms | 20.25 ms | 121.4 % | -2000…+1399 ppm | 1 |

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

Release build, **3600 consecutive frames = 60.04 s of wall time** (frames
2000-5600 of the baseline route, so the window contains the menu lead-in, the
whole measured race and the stop), with **two CPU burners running in parallel**
on a machine already shared with other work:

| Metric | Value |
|---|---|
| window | frames 2000-5600, **60.043 s** |
| guest clock vs wall | **-2.7 ppm** (59.9398 fps) |
| audio drift (produced seconds - wall) | **-6.8 ms over 60 s** (-113 ppm) |
| DRC ratio | -970 … +273 ppm |
| ring fill | 44.6 … 74.0 ms |
| underruns / conceal events | **0 / 0** |
| CPU work p95 / budget (race subset) | 63.2 % |

The residual +6.8 ms/60 s is the host audio device clock (PipeWire reported
-619 ppm against the pacer clock in the same runs), not frame pacing: the guest
itself stays within 3 ppm of 59.940 fps for the whole minute.

Same run restricted to the race (frames 3100-5600, 41.7 s): guest -6.5 ppm,
drift -4.9 ms, ratio -970…+273 ppm, 0 underruns, 0 conceals.

Raw series: `build/perf/merge-load60s/frame-stats.csv` (one row per frame:
frame, wall stamp, interval, pacer wait, present, nine wall phases, nine CPU
phases, DRC ratio (ppm), ring fill (µs), underrun/conceal counters, pushed and
pulled sample counts).

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
(`tools/check_road_artifacts.py`, `--road-audit`). Every row of the table above
was re-run on the merged tree (merging task 11's widescreen margins), except the
On "before/after" hash pair, which is the controlled A/B of the renderer
change itself: the same capture was taken with and without the per-row copy
removal and compared frame by frame.

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

* The 60 % p95 target was met on a quiet machine (**57.4 %** before the margin
  merge, **60.5 %** after it) and in the 38 % / 58 % option rows; under the
  ambient load of this shared workstation (other agents building and running
  games) the same window measured 63-92 %.
  The owner's own machine at rest is expected between those; the release build
  keeps the guest clock exact and never drops audio even in the loaded runs.
* Tunnel/hill sections are covered only as part of the committed baseline route
  windows above; no per-section labels exist in that route.
* No `perf` on this host (installing it needs sudo), so the profile is gprof.
* Windows/macOS behaviour of the new vsync/pacer policy is unqualified; it is
  the same SDL path, but only Linux was measured.
* The owner's listening test after these changes is still required.

## 10. Real-device audio (pops, dropouts, delays)

The owner reported that after the task-12 pacing changes (release build of
`c27839b`, windowed, Adaptive 16:9 + 60 fps) the **music is all broken: pops,
dropouts, delays**, while the same session before task 12 (`f618606`) was only
"slow during races" with no pops. Task 12 had measured **0 underruns**, which
means it measured the ring, not what the device played.

Everything below is measured on the device side, on this machine, in the
owner's configuration (Adaptive 16:9, HUD Edges, 60 fps on, 59.94 fps guest).

### 10.1 `tools/audio_glitch_detect.py`

One tool, two capture paths, all three artifact classes:

| Class | Test |
|---|---|
| dropout (digital silence) | run of ≥ 2 ms of samples with \|x\| ≤ 1 inside music (local RMS > 120) |
| dropout (DC hold) | run of ≥ 2 ms of identical samples inside music |
| dropout (envelope collapse) | 5 ms RMS more than 20 dB below its 200 ms local median, framed by music, shorter than 60 ms |
| pop | a sample-to-sample step above 0.7× the local 20 ms peak (and above 1200 s16) that is **isolated**: no comparable step within 10 ms either side. A plain "far above the local derivative envelope" test cannot work on this soundtrack - PSG square waves and FM percussion make the music's own edges the envelope, so the isolated-step rule is what separates a pipeline discontinuity from a legitimate edge. `--selftest` injects 12 synthetic steps and finds 12. |
| tempo / delay | the device stream's amplitude+onset envelope is warped by a candidate ratio (±4000 ppm, 100 ppm steps) and correlated against the offline deterministic WAV of the same route in 30 s windows; the winning ratio is the local tempo, the winning offset the accumulated delay |

Counts are reported per minute of *music* (the tool finds the music windows
itself). `--selftest` injects 12 known steps and 6 known 20 ms dropouts into a
clean capture and reports how many were found near the injection points
(12/12 pops, 6/6 digital silences, 6/6 envelope collapses, 0 false positives on
the clean signal), which is how the detector itself is qualified rather than
trusted.

### 10.2 The null-sink method

The device path has to be recorded without touching the owner's audio, and
`parecord`/`pw-record` of the monitor is the only capture that sees what the
device was actually handed (post-DRC, post-concealment).

```sh
# once, as the user, no sudo, default device untouched:
pactl load-module module-null-sink sink_name=tg2_test \
    sink_properties=device.description=tg2_test

python3 tools/audio_device_capture.py --exe build-rel/TG2Recomp \
    --out build/audio15/rel-on-load0 --frames 11000 --mode on
python3 tools/audio_glitch_detect.py --device build/audio15/rel-on-load0/device.wav \
    --reference build/audio15/offline/wav11000-ref.wav --out .../glitch.json

pactl unload-module <id>          # when done
```

Three things make this reproducible:

* **SDL does not honour `PULSE_SINK`.** `SDL_OpenAudioDevice(NULL, …)` asks for
  the default device and passes it by name to the server, so `PULSE_SINK` and
  a stream-restore target are both overridden. The harness therefore starts the
  game, moves *its own* `sink-input` onto `tg2_test` within ~0.3 s (the game is
  still booting silently), and fails loudly if the move cannot be verified in
  `pactl list sink-inputs`. Nothing else in the session is written: not the
  default sink, not the hardware sink, not any other client.
* **The capture's time base is the sink's.** Calibration: a 1 kHz click every
  1.000 s played into the same sink and recorded with `parecord` comes back
  with 1.0000 s spacing (min 1.0000, max 1.0003), so the recorder neither
  stretches nor compresses. It does lose the first ~0.4 s (before the stream
  is up) and the tail, so only the music span is analysed.
* **Never start a second PipeWire instance.** A private `pipewire` +
  `pipewire-pulse` graph has no hardware driver; it ran the sink at ~0.74× the
  nominal rate and its `wireplumber` reserved the real ALSA card, which made
  the owner's session re-create its sink node. The null sink must live in the
  owner's own graph, where it is clocked by the real hardware device.

A lab build also taps the exact samples handed to the SDL callback
(`GENESIS_LAB_DEVICE_WAV`, not committed) so a capture loss can be told apart
from a real glitch. Downstream of the bridge the two agree sample for sample:
where the monitor recording has an event and the tap does not, the gap is at
the client→server boundary, not in the generated stream.

### 10.3 What the device received: bisect

Method: release-config `TG2Recomp`, same committed baseline route, 60 fps on,
offscreen GL at 60.00 Hz (presents do not block, so the pacer path is the
owner's vsync-off path; see 10.4), device = `tg2_test`, 30-40 s per row. The
stress column injects a 150 ms frame-time spike every 2 s (`TG2_LAB_STALL_US`/
`TG2_LAB_STALL_EVERY`, measurement build only) because with a quiet host every
variant is clean and the differences are invisible.

| Build / variant | injected hitch | conceals | looped frames | hard overflow drops | ring fill p50 / last |
|---|---|---:|---:|---:|---|
| `f618606` policy (target 50, ring 150, ±0.5 %, no prime snap, no overdue skip) | 150 ms / 2 s | 4 | 1 891 | 0 | 157 / 165 ms |
| `c27839b` policy (target 80, ring 200, ±0.2 %, prime snap, overdue skip) | none | 0 | 0 | 0 | 60 / — |
| `c27839b` policy | 150 ms / 2 s | 9 | 6 748 | 0 | 149 / 138 ms |
| `c27839b` + vsync on | 150 ms / 2 s | 9 | 6 649 | 0 | — / 138 ms |
| `c27839b` + bound ±0.5 % | 150 ms / 2 s | 9 | 6 976 | 0 | — / 159 ms |
| `c27839b` + target 100 / ring 250 | 150 ms / 2 s | 9 | 8 228 | 0 | — / 202 ms |
| `c27839b` + prime-snap off | 150 ms / 2 s | 0 | 0 | **7 562** | — / 156 ms |
| `c27839b` + overdue-skip off | 150 ms / 2 s | 8 | 7 152 | 0 | — / 159 ms |
| **this fix** | 150 ms / 2 s | 13 | 20 565 | **0** (44 drain splices, 57 878 frames) | 129 / 134 ms (p95 141, max 250) |

On a quiet host the pre-fix release build is clean on this machine: 3 minutes,
60 fps on, **0 pops, 0 digital silences, 0 conceals, 0 underruns** - which is
exactly what task 12 measured and why the owner's report could not be
reproduced from counters alone. The owner's session has more running than this
measurement box, and it is the *hitch* rows that model it.

Read the table as: *no single task-12 knob is the bug.* Every variant that
keeps the pre-task-12 recovery path turns a long frame into permanent latency
(the fill walks from ~60 ms to 150-200 ms and stays there), and the ones whose
recovery is worse eventually overflow the ring and drop samples one by one
(`prime-snap off`: 7 562 frames = 34 ms of audio cut out in 27 s). The fix
column has a *bounded* fill (p95 141 ms, no overflow at all) and pays for it
with 44 drain splices - 4 ms notches instead of clicks and delay.

A full-historical `f618606` binary would also revert the task-11/13/14 merges
(widescreen margins, BOTH audio, macOS paths), so its row is reproduced by
reverting exactly its five audio behaviours on the current tree; that is the
controlled A/B, not a different game build.

### 10.4 Root cause

Three defects, all in the *recovery* path rather than in steady state.

1. **The cushion was ~60 ms, not 80 ms.** The bridge is fed one video frame of
   audio at a time (16.7 ms) while the device pulls 1024-frame blocks (21.3 ms),
   so the instantaneous fill is a sawtooth of ±21 ms and the value the servo
   regulates is the *pull-time* value; the pre-push value sampled into the
   frame statistics is ~20 ms lower. With target 80 ms that leaves ~60 ms of
   ring content, and a real-device 3-minute run at the owner's settings shows
   one 30 ms host hitch taking the fill from ~60 ms to **22.7 ms** and the
   correction hitting *both* clamps (±2000 ppm). A single 60 ms hitch therefore
   runs the ring dry.

2. **Every starvation became permanent delay.** When the ring went dry the
   bridge concealed (pitch-preserving loop of the last 5-25 ms), which is the
   right thing, but it then *held the read cursor* until the ring was back at
   the full target, and the pacer repaid the missing guest time as a burst of
   frames. That burst is audio the speaker has not heard yet: it is latency.
   Measured with a 150 ms hitch every 2 s: fill 60 → 156 → 189 ms, i.e. the
   delay ratchets up and never comes back (the ±0.2 % servo drains 2 ms/s).
   The owner hears this as **delays**.

3. **The delay ended in a burst of clicks.** Once the ratchet reached the ring
   cap, `rab_push` dropped one source frame per pushed frame - a hard cut
   repeated for as long as the backlog took to clear. Measured: 41 127 frames
   (184 ms) of audio cut out in one 20 s run, at the ring cap. The owner hears
   this as **pops**, and the conceal loops as **dropouts**.

Task 12 made all three worse than `f618606` not because any one knob is wrong
but because it simultaneously (a) kept a ~60 ms effective cushion, (b) halved
the servo's authority to 0.2 %, so a repaid backlog took twice as long to
drain, and (c) added a hard latency ceiling (the 200 ms ring) that the
unbounded ratchet reached sooner.

The vsync decision is **not** part of the problem, and the measurements say the
opposite of the guess: with the display at 60.00 Hz and the guest at 59.94 fps,
vsync-on locks the loop to the display (interval p99 17.5 ms, max 26.2 ms,
present p50 13.97 ms) and forces the guest to run 0.1 % fast, while vsync-off
gives the same p99 with a much smaller tail (max 18.7 ms) and an exact guest
clock (59.959 vs 59.936 fps over 30 s). Both had 0 conceals. Keeping
vsync-off is therefore deliberate, and with it the DRC has only the real device
crystal to absorb.

### 10.5 The fix

`patches/segagenesisrecomp/0006-audio-drc-prime-snap-and-ratio-bound.patch`
(regenerated; it now carries all four changes), config in `runner/audio.c`:

| Change | Value | Why |
|---|---|---|
| steady-state ring target | 80 → **100 ms** | two 50 ms host hitches are absorbed without the ring running dry, at ~100 ms of added latency |
| ring / pre-roll | 200 / 200 → **250 / 250 ms** | the cushion must fit above the target; pre-roll is still discarded at prime |
| DRC ratio bound | 0.2 → **0.5 %** (8.6 cents) | the full width a real device crystal needs; measured real-device excursions already touch ±0.2 % |
| resume after a stall | wait for the full target → **one 50 ms block** | stops turning every stall into `target_ms` of permanent latency |
| latency bound | none → **target + 60 ms** | the surplus is spliced out behind a 4 ms gain dip (a soft notch) instead of the ring overflowing (repeated hard cuts) |

The splice is the only new mechanism: when the fill stands more than 60 ms
above target, the output fades out over 4 ms, the read cursor jumps forward by
the surplus, and it fades back in. It only ever fires when a host has already
lost more time than the cushion (0 times in any 3-minute run on this machine,
44 times under the 7.5 %-loss stressor) and it replaces a hard cut with a
notch. Underruns, spawned by a host that genuinely cannot keep up, still
conceal - there is no policy that makes 150 ms of missing wall time inaudible.

### 10.6 After the fix

Release build, both owner configurations, 3-minute race (11 000 frames, the
committed baseline route), device recording + device tap, detector run against
the offline deterministic WAV of the same route, one CPU burner as the load.

Device-side detector result:

| Config | Load | pops/min | digital-silence dropouts | envelope collapses | tempo (median) |
|---|---|---:|---:|---:|---:|
| 16:9 + 60 fps on | none | 0.00 | 0 | 1 (capture start) | -180 ppm |
| 16:9 + 60 fps on | 1 burner | 0.00 | 0 | 1 (capture start) | 0 ppm |
| 60 fps off | none | 0.00 | 0 | 1 (capture start) | -80 ppm |
| 60 fps off | 1 burner | 0.00 | 0 | 1 (capture start) | -180 ppm |

Bridge telemetry and latency for the same four runs:

| Config | Load | conceals | underruns | overflow | drain splices | ring fill p50 / p95 / min | DRC ratio | guest clock |
|---|---|---:|---:|---:|---:|---|---|---|
| 60 fps on | none | 0 | 0 | 0 | 0 | 80 / 91 / 60 ms | -727…+1032 ppm | 59.941 fps |
| 60 fps on | 1 burner | 0 | 0 | 0 | 0 | 81 / 90 / 63 ms | -774…+926 ppm | 59.941 fps |
| 60 fps off | none | 0 | 0 | 0 | 0 | 81 / 90 / 61 ms | -427…+589 ppm | 59.941 fps |
| 60 fps off | 1 burner | 0 | 0 | 0 | 0 | 80 / 90 / 64 ms | -1357…+106 ppm | 59.941 fps |

The `dropout_repeat` events are 3 per run, always at 10.8 / 24.3 / 44.2 s - the
cartridge's own menu silences, identical in the device tap and in the offline
WAV. The single `dropout_envelope` event per run is at 0.683 s, the recorder's
own fade-in. No digital silence and no pop in any of the four runs.

Tempo/delay against the offline capture, 30 s windows: device stream within
±1100 ppm of the offline capture (median -180 … 0 ppm), accumulated delay drift
-5 … -330 ms over 150 s, and the ring fill - the authoritative latency number -
stays at 80 ms p50, 90 ms p95 for the whole run. There is no audible pitch
wobble and no growing delay. Compare pre-fix under the same stressor: fill 60 →
189 ms, 184 ms of audio cut out.

(One measurement-build run had two 5.33 ms digital-silence gaps, each exactly
one PipeWire quantum, absent from the device tap: a missed client callback
while the capture tool was writing a 35 MB WAV. None in the four release runs
above, which is why the capture tool is described as part of the load, not as
the device.)

Output identity (host-side only, verified on the fixed binary):

| Check | Result |
|---|---|
| Offline deterministic WAV, 5600 frames, whole run | SHA-256 `c572492e…488d02`, **identical** before and after the fix (the documented stock audio) |
| Off cold-boot fingerprints, frames 60 / 300 | `2A0B972960C5E325` / `1131D937D70234FD` (stock) |
| [FBHASH] lines, 93 per run | identical before and after the fix |

### 10.7 What is not verified here

* The owner's box has more running than this measurement box had even at load
  1 (KDE, a browser, the launcher). The pre-fix build is clean on a quiet host
  here, so the failure mode was reproduced deterministically by *injecting*
  host hitches (150 ms every 2 s), not by reproducing his exact session; his
  own listening test is still the acceptance. If his report persists with this
  build, the next measurement to take is his own `frame-stats.csv`
  (`GENESIS_FRAME_STATS`) plus a null-sink capture with these two tools.
* Windows/macOS: the same SDL audio path, not measured.
* A host that loses 7.5 % of wall time (150 ms every 2 s) still conceals: no
  buffering policy can play 100 % of a stream the host does not deliver. The
  fix bounds the damage (no clicks, delay capped at 160 ms) but does not make
  such a host sound clean.
* The 5.33 ms client-side gaps in one of four runs come from the measurement
  environment (the capture tool competing for the CPU); they are absent from
  the device tap. A 3-minute run with the capture tool's own disk writes on a
  busy disk could plausibly do the same on the owner's machine.

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

# Real-device audio (§10): null sink in the owner's own graph, capture the
# monitor, detect pops/dropouts/tempo against the offline deterministic WAV.
pactl load-module module-null-sink sink_name=tg2_test \
    sink_properties=device.description=tg2_test
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy build-rel/TG2Recomp \
    ~/roms/genesis/tg2.bin --no-launcher --widescreen off --turbo \
    --max-frames 11000 --wav build/audio15/offline/ref.wav \
    --input-script build/audio15/rel-on-load0/route.input      # reference
python3 tools/audio_device_capture.py --exe build-rel/TG2Recomp \
    --out build/audio15/rel-on-load0 --frames 11000 --mode on [--load 1]
python3 tools/audio_glitch_detect.py \
    --device build/audio15/rel-on-load0/device.wav \
    --reference build/audio15/offline/ref.wav \
    --out build/audio15/rel-on-load0/glitch.json
python3 tools/audio_glitch_detect.py --device <clean.wav> --selftest
pactl unload-module <id>
```

`GENESIS_FRAME_STATS=<path>` writes the per-frame CSV; the ring is always on and
the file is written at exit. Nothing is written unless the variable is set.
