# Race timing investigation

ROM: Top Gear 2 USA, CRC32 `BD3074D2`. Addresses below were checked against
the private ROM with `tools/disasm_tg2.py` (Capstone 68000 mode), then against
native runtime snapshots. Generated C was read, never edited.

## Stock measurement

`python3 tools/probe_framerate.py` runs the baseline input route at exact
wall frames through the runner's input-script interface. It owns one PID,
uses TCP port 4410, and writes private evidence to `build/fps/stock/`.
This avoids the older probe's TCP input scheduling jitter. The route's
button presses are unchanged; screenshot/audio TCP actions are replaced
with deterministic capture directives and a whole-run WAV capture.

Frames 3600–3960 give 360 consecutive frame transitions (six seconds at
60 Hz). The framebuffer changes on **186/360 transitions: 31 pictures/s**.
Consecutive changed-picture intervals: **66 × 1, 66 × 2, 53 × 3 V-ints**.
The picture is sometimes partially updated; a distinct framebuffer does
not establish that a complete road/car/HUD composition was produced.

The main-loop completion counter `$FF23B4` advances **120** times, and the
primary raster pointer `$FF231E` changes **120** times: **20 completed
picture builds/s**, one every three V-ints in this window. The main-loop
marker `$FF1838` advances by two on those same 120 transitions. Conversely,
race V-int counter `$FF238C` advances by exactly one on **all 360**
transitions, and the race clock `$FF23B8` advances by `$D555` on all 360.
The player position and speed also advance between repeated pictures.
This is variable presentation lag, not an alternate-frame physics cap.

Cold boot hashes match the supplied stock fingerprints: frame 60
`2A0B972960C5E325`, frame 300 `1131D937D70234FD`. The 5600-frame capture
exits 0 with zero dispatch misses, floor entries, interior misses and unsafe
floor entries. The build command was
`JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build` (exit 0).

## ROM timing paths

* `$002082` waits for the word `$FF01C6` to differ from D0. This is the
  generic boot/scene VBlank handshake, not the active race's render gate.
* Race entry/init is `$006500..0065EE`; the active race loop calls
  `$0067B6` from `$0065EE`, spins at `$0065F2` on byte `$FF2424`, then
  repeats through `$006602..006606` while the exit flag is zero.
* `$0067B6` prepares presentation: `$0088A2` copies current player position
  into the view position, `$00E170` snapshots player/opponent state,
  `$00F522` prepares HUD sprites, `$007F90/$008414/$008548/$0079D6` build
  road/scenery lists, and `$00977C` handles player-view object projection.
  `$006982` sets byte `$FF2424=1`; `$006990` increments `$FF23B4`.
* V-int `$004714` temporarily installs `$0049CC` as a reentrant IRQ target,
  increments the generic handshake at `$004742`, the race counter at
  `$004748`, and the adjacent byte `$FF2425` at `$00474C`. It copies the
  render-ready/counter word to `$FF2426`. If a new picture is ready,
  `$004768` calls `$004A24` to submit queued VDP work and `$00476C` clears
  the ready byte. Otherwise it services pending presentation work at
  `$004774..0047C0`. `$004898` loads the active road raster pointer into A5.
* `$00490A..004912` tests `$FF238C` parity. The even-V-int call at
  `$004922` is `$00665A`, **palette fading**, not the physics update.
  `$00668A` increments the fade step, `$00673C` moves RGB channels toward
  their targets; `$006728` ends the fade phase. Some effects have their
  own parity tests, e.g. skid sound selection `$00D608..00D63C`.
* `$00496A` calls `$00DB02` every full race V-int, outside the parity
  branch. `$0049AC` restores `$004714` as the next full V-int target.
  `$0049CC` merely services raster setup if the previous V-int overruns;
  it does not advance the physics clock. No such lost ticks occur in the
  measured stock window.

## Physics, clock and audio deltas

* `$00DB02` reads VDP status bit 0 into `$FF186C` (PAL/NTSC timing
  selection), polls pads through `$00D7A6`, and handles race/pause state.
* Active racing follows `$00DF36`: `$00E146` advances the race phase
  counter, `$00D98A` advances opponents, `$00CD84/$00CD76` update players.
  Object callbacks at `$00E418`, collision tests `$0091B0/$0093E4`,
  positions/rank and finish tests are also reached from this IRQ path.
* Player speed is word +`$0E` in the record at `$FF18CA` (`$FF18D8`).
  `$00CF7A..00D43A` computes acceleration, drag, braking and gear changes;
  +`$C2` (`$FF198C`) is the speed used for position integration.
  `$00D4C6..00D4F2` adds that value to longword +`$00` (`$FF18CA`),
  multiplying by 5/6 on NTSC at `$00D4DE..00D4E8`. Position +`$08`
  (`$FF18D2`) is the view/track sample position copied by `$0088C4`.
  HUD speed conversion is `$00F5F8..00F614`, using 3/128 and the selected
  MPH/KPH factor. Halving these deltas would incorrectly slow the game.
* Opponents are 12-byte records at `$FF053C`, count-minus-one at `$FF217E`.
  `$00D98A..00DA80` updates them every race IRQ. `$00DA10..00DA20` adds
  their speed to their track position, with NTSC `$D555/65536` scaling.
* `$00DF40` adds `$0000D555` to `$FF23B8` on NTSC, while `$00DF4A`
  increments the high word on PAL. This is a 16.16 race clock with
  **50 clock ticks per second**, not a count of main-loop iterations.
  `$00E284/$00E2D8/$00E30A` store its high word into finish-order records.
  Player lap index +`$CA` (`$FF1994`) is advanced at `$00DAB2..00DAB8`.
* Per-player effect timers +`$2A0`/`$2A6` decrement in `$00CDEA..00CE16`,
  and nitro/cooldown timers at +`$BA`/`$2EA` decrement in `$00E082..00E0AE`.
  These stay in the IRQ path. Global countdown byte `$FF23C2` decrements
  at `$00DE42`, setting the next 60/30-frame countdown stage at
  `$00DE04/$00DE0C`.
* `$0048EC..0048FE` calls sound-driver veneers `$070010/$07001C` once per
  full race V-int. The tail of `$00DB02` also reaches `$0254B8`
  (with live player/view values), whose pitch setup
  divides engine-rate values at `$025564/$0255F4` and calls `$025694`.
  `$0256BE` submits the pitch through `$070028`; effect requests use
  `$0250E2/$025114`. The sound-driver clocks and native IRQ cadence must
  remain untouched; accelerating every guest instruction is unsuitable.

## Enhancement experiment

The first candidate is race-only **main-program CPU headroom**, through
the engine's existing `GameSpec.main_cpu_divisor` contract. It reduces
main-program budget consumption while preserving IRQ debt, DMA stalls,
native raster/chip clocks and the game's real render-ready wait. It does
not halve physics deltas or alter the parity branch. Qualification results
and the final decision follow below.

### Result: 60 pictures/s, rejected for gameplay drift

The qualified **measurement**, not a qualified feature, is
`build/fps/active-race/`. Headroom divides main CPU instruction costs by 64
only while the V-int target is `$004714`, fade phase `$FF22FA` is zero,
and race phase `$FF1866` is nonnegative. Interrupt/DMA clocks remain native.

| Frames 3600–3960, 360 transitions | Stock | Headroom experiment |
|---|---:|---:|
| Distinct framebuffer transitions | 186 (31/s) | 360 (60/s) |
| Completed picture builds | 120 (20/s) | 360 (60/s) |
| Primary raster-pointer swaps | 120 | 360 |
| VRAM sprite-table changes | 120 | 360 |
| VRAM H-scroll changes | 99 | 250 |
| Race V-int advances | 360 | 360 |
| Race-clock increments of `$D555` | 360 | 360 |
| Dispatch / floor / interior / unsafe entries | 0 / 0 / 0 / 0 | 0 / 0 / 0 / 0 |

Some scroll values legitimately repeat on straight sections. The completion
counter, raster swaps and sprite data demonstrate a complete new game
picture build on every frame in the experimental window. Six consecutive
PNGs are `build/fps/active-race/frame-3600.png` through `frame-3605.png`;
each has a different framebuffer hash, recorded in `stderr.log`.

Exact-clock comparisons at matching wall frames, using the same scripted
inputs (speed and position are raw guest units):

| Wall frame | Race clock, Off = On (16.16 ticks) | Position Off | Position On | Speed Off | Speed On |
|---:|---:|---:|---:|---:|---:|
| 3300 | 11250278 | 8565652 | 8565652 | 3964 | 3964 |
| 3600 | 27634178 | 9480462 | 9479531 | 2707 | 2687 |
| 3960 | 47294858 | 10544214 | 10504301 | 3131 | 2989 |
| 4500 | 76785878 | 11839452 | 12178304 | 3448 | 3313 |
| 5200 | 115014978 | 14021393 | 14530536 | 4294 | 3584 |

All **364 captured clock/V-int/lap-index samples match exactly**, exceeding
the one-clock-frame requirement for elapsed clock. That does **not** prove
equal lap completion time: speed/position diverge, and this route does not
complete a lap. At frame 5200 the speed difference is 710 raw units and
position difference is 509143, so this candidate fails the same-feel goal.

The reason is visible in the ROM: `$0088C4` refreshes +8(A4) in the main
loop, but IRQ routine `$00D644/$00D65E` reads it to derive track gradient
and curvature into +`$12/$14/$16`. Speed calculation `$00D30E..00D31E`
then uses +`$16` for slope acceleration. Main-loop view snapshots therefore
feed physics; keeping only the IRQ *count* unchanged is insufficient.
`$0091B0` also reaches collision responses which can rewrite +`$C2/$0E`
at `$00922E/$009234`. A first-divergence trace separating terrain effects
from subsequent collisions remains necessary; the table alone does not
attribute every speed change to one of them.

Whole-run WAVs have identical duration/format (20899200 stereo frames,
223721 Hz, 16-bit, 93.415 seconds) and different PCM content, consistent
with changed engine pitch/vehicle events. Music tempo has **not** been
independently qualified by waveform/sequence analysis or listening; equal
sample counts only establish audio duration. No Z80/FM/PSG timing was
modified by the experiment.

An earlier unrestricted attempt (`build/fps/headroom-active/`) was also
rejected: it advances race startup by two V-ints and remains black. Its
ready picture on every V-int continuously takes `$004768`'s submission
branch, bypassing pending palette consumption at `$004774..004788`;
`$FF23C5` stays set and the fade remains at its first step. The successful
60-picture experiment deliberately leaves fade/countdown at stock timing.
Two earlier captures, `headroom/` and `headroom64/`, exercised inactive
hooks and are not enhancement evidence. The pinned engine declares
`handle_arg` and `on_post_reset` but has no callers for them; initialization
therefore belongs in the game's entry wrapper.

### Delivery boundary and reproduction

**Partial research delivery. No player-facing 60 fps option is qualified.**
Normal builds omit the experiment entirely. To reproduce it intentionally:

```sh
cmake -S . -B build -DTG2_TIMING_EXPERIMENT=ON
cmake --build build --target TG2Recomp -j8
TG2_RACE_HEADROOM=0 python3 tools/probe_framerate.py --out build/fps/off
TG2_RACE_HEADROOM=1 python3 tools/probe_framerate.py --out build/fps/on
python3 tools/compare_framerate.py build/fps/off build/fps/on \
  --out build/fps/comparison.json
```

The CMake option and environment switch are research controls, not an
advertised gameplay feature. Default is Off; setting the environment alone
does nothing in a normal build. No renderer, widescreen, generated C or
engine source was changed. The safe deliverable is the deterministic
measurement/comparison tooling and verified timing map; the headroom
prototype is retained behind a default-off build gate for further study.

A safe complete implementation needs presentation state detached from
the physics-facing +8(A4)/terrain/collision snapshots, or interpolation
of road/scenery/sprite/HUD presentation while the original main/IRQ
schedule stays intact. This work intentionally does not enter the video
renderer being developed in parallel. Doubling the entire logic rate or
blindly halving deltas is ruled out by the measured 60 Hz physics path.
All-track, finish/fade-out, full-lap and sound-tempo qualification remain
open. The measured window holds B continuously; speed itself varies with
terrain and collisions, so it is a constant-input run, not a speed-locked
laboratory test.
