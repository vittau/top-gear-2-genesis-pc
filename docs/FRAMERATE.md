# Race presentation rate: measurement and 60 fps option

ROM: Top Gear 2 USA, CRC32 `BD3074D2`. Every address below was checked against
the private ROM with `tools/disasm_tg2.py` (Capstone 68000 mode) and against
native runtime snapshots from the scripted baseline route. Generated C was read,
never edited.

**Result.** The default-on "60 fps races" option presents a race at **60 pictures/s** (was
31 distinct framebuffers/s, 20 completed picture builds/s) with the game clock,
lap index and AI cadence untouched. With the option off the build is
byte-identical to the stock port: all 5600 per-frame framebuffer hashes of the
baseline route match, including frame 60 `2A0B972960C5E325` and frame 300
`1131D937D70234FD`. With it on, the picture updates on all 360 V-ints of the
measured race window (road, H-scroll, sprite table, cars, HUD). Physics matches
the stock port exactly for the first ~220 V-ints of the sampled race and stays
within 0.037 % of track position over 30 s; see
[Physics fidelity](#physics-fidelity-what-matches-and-what-does-not) for the
numbers and the reason.

## Stock measurement (Phase A)

`python3 tools/probe_framerate.py` drives the committed baseline input route at
exact wall frames through the runner's input-script interface (one owned PID,
TCP port 4410, private evidence under `build/fps/`). It records per-frame
framebuffer hashes, RAM and VRAM snapshots, six screenshots and a whole-run WAV.

Frames 3600-3960 (six seconds of steady racing at 60 Hz):

| Measurement | Stock |
|---|---:|
| Distinct framebuffers | 186/360 → **31/s** |
| Changed-picture intervals | 66 × 1, 66 × 2, 53 × 3 V-ints |
| Completed picture builds (`$FF23B4`) | 120/360 → **20/s** |
| Primary raster pointer swaps (`$FF231E`) | 120 |
| VRAM sprite-attribute changes (`$BE00`) | 120 |
| VRAM H-scroll changes (`$B800`) | 99 |
| Race V-int counter (`$FF238C`) | +1 on all 360 |
| Race clock (`$FF23B8`) | +`$D555` on all 360 |

So the race produces a complete new picture one V-int in three, while the V-int
handler keeps running its physics at a full 60 Hz. The rate is set by CPU cost,
not by an alternate-frame design: one picture build needs between two and three
frames of emulated 68K time, and the render-ready handshake quantises the
latency to whole V-ints.

### Main-loop and V-int structure

* `$0065EE` calls the picture build `$0067B6`, spins at `$0065F2` until byte
  `$FF2424` is cleared by the V-int handler, and repeats while the exit flag is
  zero.
* `$0067B6` prepares one picture: `$006804` calls `$0088A2` (view position),
  `$00680A` calls `$00E170` (state snapshot), `$00681E..$006846` copy the player
  state used by the picture into the record's `+$70..+$86` snapshot block,
  `$006890` calls `$00F522` (HUD sprites), `$00689E..$0068BE` build road and
  scenery (`$007FA8`, `$008402`, `$0084E6`, `$007A10`), then `$006982` sets
  `$FF2424=1` and `$006990` increments `$FF23B4`.
* `$0088A2` is the only writer of the view position in a steady race:
  `$0088C4` copies the physical position `+0` (`$FF18CA`) into the view
  position `+8` (`$FF18D2`), `$0088CA` copies `+4` into `+$C`, and
  `$0088CE..$0088EE` resolve the track-segment table base into `$FF1996` /
  `$FF199A`. The copy is skipped while player state `+$1A` is 2.
* V-int `$004714` increments the generic handshake `$FF01C6` (`$004742`), the
  race counter `$FF238C` (`$004748`) and `$FF2425` (`$00474C`), latches
  `$FF2426`, then tests `$FF2424` (`$004762`). Ready: `$004768` calls `$004A24`
  to submit the queued VDP work and `$00476C` clears the flag. Not ready: the
  deferred block `$004774..$0047C0` runs instead - pending palette upload
  `$FF23C5`, `$0012F0`, `$005218`, the queued VRAM block upload `$0052C2`
  (gated by `$FF23C4`) and the deferred VRAM block work `$00E4A0`.
* `$00E4A0` is the game's idle-time VRAM uploader: it tests `$FF168E`, advances
  `$FF233A`, and on alternating calls uploads the block mask in `$FF238E` or
  `$FF2392` in six DMA chunks to VRAM `$9320`/`$9340`.
* `$00490A..$004912` tests `$FF238C` parity; the even-V-int call `$004922` is
  palette fading (`$00665A`), not physics. `$00496A` calls `$00DB02` on every
  race V-int, outside the parity branch, and `$0049AC` restores `$004714` as
  the next V-int target.

The VDP is set up with register 5 = `$5F` (sprite attribute table `$BE00`),
register 13 = `$2E` (H-scroll table `$B800`), plane A `$C000`, plane B `$E000`.

### Where per-tick deltas are applied

All of this runs in the V-int path, once per race V-int, so it is already a
60 Hz simulation:

* `$00DB02` reads VDP status bit 0 into `$FF186C` (PAL/NTSC), polls pads
  (`$00D7A6`) and dispatches race state. Active racing follows `$00DF36`:
  `$00E146` advances the race phase counter `$FF1866`, `$00D98A` advances
  opponents, `$00CD76`/`$00CD84` update the players.
* Per-player chain `$00CD84`: `$00CDEA` effect timers, `$00D4C6` integrates the
  physical position (speed `+$C2`, `5/6` NTSC scaling at `$00D4DE..$00D4E8`),
  `$00CE18` derives surface/steering flags from the view position, `$00D644`
  derives segment/slope/curvature, `$00DA82` further track state, `$00CE5A`,
  and `$00CF7A` computes speed from slope `+$16`.
* `$00D644` reads `+8` and calls `$00D65E`, which turns the position into a
  segment index and interpolation weights and returns them in D4/D5/D6; the
  caller stores them in `+$12`/`+$16`/`+$14`.
* Opponents are 12-byte records at `$FF053C`; `$00D98A..$00DA80` advances them
  every V-int with the same `$D555/65536` NTSC scaling.
* `$00DF40` adds `$0000D555` to `$FF23B8` (50 clock ticks per second, 16.16).
  Player lap index `+$CA` (`$FF1994`) advances at `$00DAB2..$00DAB8`.
* `$0048EC..$0048FE` calls the sound-driver veneers `$070010`/`$07001C` once
  per race V-int; the engine tone/pitch path (`$0254B8..$0256BE`) runs from
  the `$00DB02` tail.
* `$00DEF6` is a bounded view follower (`+$FA0` per call, clamped to `+0`),
  called from `$00DEAE`. It is not called during steady racing - the measured
  `+8` staircase proves the main loop is the only writer there.

### Why the game is slow: the view position feeds physics

The player update samples the *view* position `+8`, not the physical position:

```
$00CE18  move.l $8(a4),d7     -> surface/steering flags
$00D644  move.l $8(a4),d0     -> $00D65E -> +$12/+$14/+$16 (segment/slope/curve)
$00DA82  move.l $8(a4),d0     -> further track state
$00CF7A  ... +$16 ...         -> slope acceleration in the speed model
```

Measured stock `+8` staircase (900 sampled frames, 3600-3960 and 4000-4500):
308 updates, gaps 242 × 3 and 64 × 2 V-ints (period 2.92 on average), always
written with the physical position of the previous frame. Between updates the
IRQ physics keeps sampling the same, stale terrain position.

This is the reason a pure "run the main program faster" change cannot work:
with a picture every V-int the same `$0088A2` copy would run every V-int, the
terrain sampling would lose its 2-3 V-int lag, and the vehicle dynamics would
change. The earlier research build measured exactly that: race clock identical,
but at frame 5200 the player was 509143 units ahead and 16 % faster. See
[the rejected experiment](#records-the-rejected-headroom-only-experiment).

## Chosen technique

Two independent parts, both race-only, both inert when the option is off:

1. **Main-program headroom** (`GameSpec.main_cpu_divisor`): while the live
   V-int target is the race handler and the palette fade has finished and the
   countdown is over and the race is single-player, main-program instruction
   cost is divided by 8. Interrupt, DMA, raster, chip and sound-driver clocks
   are untouched by the engine contract. One picture build then needs ~0.36
   frame, so a complete picture is ready on every V-int and `$004A24` submits
   one per frame.
2. **Stock-schedule view position for physics**: the adapter keeps
   `s_phys_view`, refreshed every third V-int (`$FF238C % 3 == 0`) with the
   physical position, and runs the IRQ routines that sample `+8`
   (`$00CD84`, `$00CE18`, `$00D644`, `$00DA82`) with that value temporarily in
   `+8`. The picture build keeps the fresh, per-frame value, so the road,
   scenery, cars and HUD move every frame while the physics sees the stock
   terrain sampling.

The hooks are audited `game_hook` sites in `game/game.toml`; each returns 0
(stock execution) when the option is off, when the race is not active, or while
a guest split-stack adjustment is pending. The adapter also runs the handler's
deferred VRAM block work (`$00E4A0`, `$0052C2`) after the picture submission on
the two V-ints in three that the stock build leaves free, so the faster picture
rate does not starve it.

Nothing in the video renderer, widescreen path, generated C, or the engine was
changed for this.

## Results

Frames 3600-3960, 360 transitions, same scripted route:

| | Off (stock) | 60 fps option |
|---|---:|---:|
| Distinct framebuffers | 186 (31/s) | **360 (60/s)** |
| Changed-picture intervals | 66×1, 66×2, 53×3 | 359 × 1 |
| Completed picture builds (`$FF23B4`) | 120 (20/s) | **360 (60/s)** |
| Primary raster pointer swaps | 120 | **360** |
| VRAM sprite-attribute changes | 120 | **360** |
| VRAM H-scroll changes | 99 | 250 |
| Race V-int advances | 360 | 360 |
| Race-clock increments of `$D555` | 360 | 360 |
| Dispatch / floor / interior / unsafe entries | 0/0/0/0 | 0/0/0/0 |

Some H-scroll values legitimately repeat on straight sections; the sprite
table, the raster pointer and the completion counter all advance on every
frame. Six consecutive PNGs (`build/fps/frames-60fps/frame-3600.png` ..
`frame-3605.png`, sha256 in `hashes.txt`) are all different, and their pixel
diffs cover the whole frame (HUD, opponents, car, road).

Route-wide framebuffer hashes (`--hash-frames 1`, all 5600 frames):

* Off vs the stock capture: **0 differing frames**.
* On vs Off: frames 1-3095 identical (logos, title, menus, race start,
  countdown), differences start at frame 3096 - the V-int on which the option
  engages after the countdown - and continue through the race. Menus are
  unaffected.

Cold-boot fingerprints with the option on are still `2A0B972960C5E325`
(frame 60) and `1131D937D70234FD` (frame 300).

### Physics fidelity: what matches and what does not

Same scripted inputs, matching wall frames; `clk` is `$FF23B8` (16.16 ticks),
`pos` is `$FF18CA` (raw units), `spd` is `$FF18D8` (raw units):

| Wall frame | clk Off = On | pos Off | pos On | Δpos | spd Off | spd On |
|---:|---:|---:|---:|---:|---:|---:|
| 3300 | yes | 8565652 | 8565652 | 0 | 3964 | 3964 |
| 3600 | yes | 9480462 | 9480462 | 0 | 2707 | 2707 |
| 3960 | yes | 10544214 | 10544214 | 0 | 3131 | 3131 |
| 4500 | yes | 11839452 | 11840960 | +1508 (+0.013 %) | 3448 | 3453 |
| 5200 | yes | 14021393 | 14016243 | -5150 (-0.037 %) | 4294 | 4267 |

Across the 364 captured samples the race clock and lap index match **exactly**
(the clock is IRQ-driven and the IRQ cadence is unchanged) and 362 of 364
positions match exactly. A second capture covers frames 5000-5600 (the end of
the route; both runs brake to a stop at frame 5400 with speed 0):

| Wall frame | pos Off | pos On | Δpos | Δpos % | spd Off | spd On |
|---:|---:|---:|---:|---:|---:|---:|
| 5000 | 13390570 | 13392418 | +1848 | +0.014 % | 4942 | 4942 |
| 5100 | 13697722 | 13695916 | −1806 | −0.013 % | 3395 | 3343 |
| 5200 | 14021393 | 14016243 | −5150 | −0.037 % | 4294 | 4267 |
| 5300 | 14221170 | 14216551 | −4619 | −0.033 % | 1042 | 897 |
| 5350 | 14246382 | 14236557 | −9825 | −0.069 % | 183 | 102 |
| 5400-5600 (stopped) | 14247474 | 14236942 | −10532 | −0.074 % | 0 | 0 |

The race clock and lap index are identical at every one of these samples too.

Why any divergence at all: the stock view-position schedule is an artefact of
the port being CPU-bound - its gaps are 2 or 3 V-ints and drift inside the
frame, so the value physics samples on a given V-int can be one frame older or
newer than a fixed 3-V-int schedule produces. Reproducing that exact pattern
would mean reproducing the stock CPU stall pattern, which is the thing the
option removes. The fixed schedule keeps the mean lag and the mean update rate,
so speed, terrain response and AI behaviour stay within 0.037 % of position at
30 s and 0.074 % at the end of the captured route, instead of the 3.6 % / 16 %
drift of the headroom-only experiment.

### Audio and music tempo

* Both captures have identical WAV format and length: stereo, 16-bit,
  223721 Hz, 20899200 stereo frames (93.416 s). The Z80/FM/PSG clock and the
  per-V-int sound-driver calls are untouched.
* The two WAVs are **sample-identical for the first 51.627 s** (wall frame
  3098, i.e. exactly until the option engages); 55.3 % of all samples are
  identical. During the race the engine note follows the (slightly different)
  measured speed and the main loop issues its sound writes once per frame, so
  the mixed waveform changes even though the music clock does not.
* Onset-envelope cross-correlation between the two captures peaks at **0 ms
  lag in every 8 s window** of the race, so there is no tempo drift.

## Records: the rejected headroom-only experiment

The first attempt (commit `31aa802`) used divisor 64 with no view-position
gate. It produced 60 pictures/s but drifted: at frame 5200 position +509143
(3.6 %) and speed +16 %, because the `$0088C4` copy ran every V-int and removed
the 2-3 V-int terrain-sampling lag described above. That result is why the
option now ships with the view gate, and why the gate is the part of the
implementation that carries the "same feel" requirement.

An earlier unrestricted variant also had to be rejected for a different reason:
a picture ready on every V-int keeps the handler on the `$004768` submission
branch, so the deferred block (`$004774..$0047C0`) never ran. Outside racing
that starves the palette upload path `$FF23C5` and leaves the fade at its first
step. The current gate therefore only engages after the palette fade has
finished (`$FF22FA == 0`); fades, countdown and menus keep stock timing.

## Option surface

Default **on**. The player surface is the shared `settings.ini` next to the
executable, edited by the launcher's Mods page or by the in-game recomp-ui
overlay (F1/Esc, or Back+RB on a controller):

```ini
[mods.race60]
enabled = 1
```

`TG2_RACE_60FPS=0|1` remains a probe-only override and is never persisted. The
choice is latched at each race start, so toggling it in the overlay during a
race leaves that race untouched and applies from the next one.
`TG2_RACE60_DIVISOR=<n>` is likewise a research control for the headroom amount
(default 8; 8 and 64 measured identically).

## Reproduction

```sh
JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build
# With [mods.race60] enabled = 0 in build/settings.ini:
python3 tools/probe_framerate.py --port 4450 --out build/fps/result-off
# With [mods.race60] enabled = 1 (the shipping default):
python3 tools/probe_framerate.py --port 4450 --out build/fps/result-on
python3 tools/compare_framerate.py build/fps/result-off build/fps/result-on \
  --out build/fps/comparison.json
```

Each probe run exits 0 after 5600 frames. `summary.json` holds the cadence
counters, `ram-*.ram`/`vram-*.vram` the per-frame state, `stderr.log` the
per-frame framebuffer hashes, and `audio.wav` the whole-run audio.

## Limitations

* Physics is not bit-identical over long runs: position is exact for the first
  ~220 V-ints of the captured race, then diverges to 0.037 % at frame 5200
  (30 s) and 0.074 % at frame 5400 (where both runs have stopped). The cause is
  the drift-prone stock view-position schedule explained above; a fixed
  schedule cannot reproduce it exactly. The race clock, lap index and AI
  cadence are exact at every sample, and speed tracks stock within 0.6 %.
* A full lap was not measured: the committed route covers ~40 s of one track
  and ends with the car stopped. Lap-time equality within one frame is
  therefore argued from exact clock identity plus the bounded position error,
  not measured.
* Two-player races keep stock timing (the option disengages when `$FF189E` is
  non-zero), because only the single-player record layout was audited.
* Fades, countdown, menus, the finish sequence and other tracks are
  unqualified; the option only engages in the measured race state.
* With the option on, the sound of the race changes (engine pitch follows the
  slightly different speed; main-loop sound writes happen at 60 Hz instead of
  20 Hz). Music tempo is unchanged.
* Presentation latency: the picture is built from the physical position of the
  same frame, where stock draws from a position one to three frames old.
