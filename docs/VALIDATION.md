# Full-game qualification ledger

The 60 fps rows below describe the **superseded CPU-headroom design**. The
current presentation-only implementation and its exact per-V-int replay,
full-race, cadence and audio comparisons are documented in
[FRAMERATE.md](FRAMERATE.md#qualification). Historical trajectory/lap-time
divergence below must not be read as a current limitation. The subsequent
road-atlas correction has a regression check over every synthesized baseline
frame: maximum edge-envelope and stripe-count violations are both zero; see
[road topology qualification](FRAMERATE.md#road-topology-continuous-geometry-versus-discrete-atlas-state).

Scope: does the native port play the real game, and do the presentation options
change what the game does? Every entry below was produced headlessly (SDL dummy
or offscreen video, dummy audio, TCP port 4470 for sections 1/4/5 and 4490 for
the all-track coverage, one runtime at a time) by controller input only: no RAM
writes, no save states, no generated-code edits. The task-25 coverage extension
is the one deliberate exception: it selects a later race of an already-loaded
country by writing the game's own selection words, grounded in the ROM (see
"Coverage: 64 of 64").

| Artifact | What |
|---|---|
| `tools/tg2_runner.py` | minimal runner client: launch, TCP commands, one-round-trip `step()`, race-state decode |
| `tools/tg2_race_driver.py` | closed-loop driver: boot, race, finish, post-race, next race; writes `trace.csv`, `route.json`, `laps.json`, `summary.json` |
| `tools/tg2_replay_route.py` | exact-wall-frame replay of a recorded route in any presentation mode |
| `tools/tg2_controls_probe.py` | in-race A/C/off-road probe with screenshots |
| `tools/tg2_password.py` | password codec reverse-engineered from the ROM (see `docs/PASSWORDS.md`) |
| `tools/tg2_password_ui.py` | types a password through the game's ENTER PASSWORD screen, verifying each symbol in WRAM |
| `tools/tg2_coverage.py` | one coverage cell: password → track → 62 s of driving → evidence |
| `tools/tg2_coverage_batch.py` | the 16-track × 2-mode matrix, one process per cell |
| `tools/tg2_reach_races.py` | the 19 races a password cannot name, one process per race (setup-screen index selection) |
| `tools/tg2_state_matrix.py` | quickstate save → fresh-process load matrix (race modes, menus, rewind) |
| `tools/tg2_margin_audit.py` | widescreen seam statistics + per-run contact sheets |
| `tools/tg2_nitro_compare.py` | same-route nitro A/B speed measurement |
| `tools/tg2_active_lines.py` | password route into a track, captures countdown/nitro/pause/cruise, reports which scanlines carry content |
| `tools/check_active_lines.py` | classifies every row of a capture as picture / stock window band / empty |
| `tools/summarize_active_lines.py` | active-line evidence table across runs, re-measuring every capture |
| `tools/verify_hud_map.py` | HUD Edges map-vs-marker alignment: native and Edges captures of the same route frames, bounding boxes compared |
| `tools/tg2_hud_diag.py` | per-scanline raster state + exact-frame VRAM dumps for HUD investigations |
| `tools/verify_crop_evidence.py` | re-reads a crop evidence tree (sizes, bands, stock parity, menus, audits) without launching the game |

Driver mechanics (why the comparison is trustworthy):

* One TCP round trip per control tick carries `set_input` + the WRAM block +
  `frame_info`. The runner services the batch in the single per-frame poll that
  runs before the simulation step, so the control delay is exactly one frame
  with no TCP jitter.
* Two Off runs of the closed-loop driver produced **identical lap times to four
  decimals and the same finish frame** (see the repeat row), and the 16:9 run
  reproduced the Off run exactly. A difference between modes is therefore caused
  by the option, not by scheduling noise.
* The controller reads the player lateral position (`$FF18CE`, clamp ±288 at
  `$FF1690`/`$FF1694`) and its derivative; throttle is B. The first 300 frames
  after "GO" are run without throttle so the field clears and traffic does not
  randomise the drive.

## 1. Full race — track 1 (Australasia / Auckland, 1.6 miles, 4 laps)

Wall-clock frames run at 60 Hz; the race clock (`$FF23B8`) is 16.16 ticks at
50 Hz, so `seconds = ticks / 65536 / 50`. "Run-up" is the grid-to-line segment;
the four timed laps follow.

| Mode | Evidence | Run-up | Lap 1 | Lap 2 | Lap 3 | Lap 4 | Race total | Manifests |
|---|---|---:|---:|---:|---:|---:|---:|---|
| Off | `build/qual/rt-off-1/` | 12.4333 | 39.8664 | 42.9997 | 37.7998 | 44.8531 | **177.95 s** | 0/0/0/0 |
| Off (repeat) | `build/qual/rt-off-2/` | 12.4333 | 39.8664 | 42.9997 | 37.7998 | 44.8531 | **177.95 s** (identical) | 0/0/0/0 |
| Widescreen 16:9 | `build/qual/rt-ws169/` | 12.4333 | 39.8664 | 42.9997 | 37.7998 | 44.8531 | **177.95 s** (identical to Off) | 0/0/0/0 |
| 16:9 + 60 fps | `build/qual/rt-fps60/` | 12.3999 | 39.8998 | 44.8664 | 44.4997 | 40.4731 | **182.14 s** (4th-line crossing) | 0/0/0/0 |

Results screen reached in every run ("RACE RESULTS" with all 20 finishers and
the player's TIME column; `build/qual/race-post1/race1-post-02.png` shows the
screen, `race1-post-03.png` the championship table, `race1-post-04.png` the
return to setup, `race1-post-05.png` the next track intro, `race1-post-06.png`
the shop). Post-race flow (results → championship table → setup → next track
intro → shop → next race) was driven automatically in
`build/qual/progress1/` (two consecutive races: Auckland then Ayers Rock).

**Lap-time deltas.** Off vs Off, Off vs 16:9: 0.0000 s on every lap, same finish
frame. Off vs 16:9+60 fps: lap 1 +0.033 s (0.08 %), race total +4.19 s (2.35 %).
The first-lap match is the honest physics signal; the later-lap spread is the
documented 60 fps view-position schedule (`docs/FRAMERATE.md`) feeding a
reactive driver, which steers differently once the trajectory separates, plus
traffic. The race clock itself is IRQ-driven and identical in both modes.

**Same-route replay.** Replaying one recorded route frame-exactly with
`tools/tg2_replay_route.py` (`build/qual/pipe-replay-off`, `pipe-replay-16:9`,
`pipe-replay-16:9-60`): Off and 16:9 give identical lap times
(52.3830 / 55.2663 / 52.9330 / 23.3165 s); 60 fps gives 45.3997 / 59.5330 /
53.1997 / 26.0332 s for the same input frames, total 192.12 s vs 192.38 s
(+0.14 %). That route ends with the car crawling off-road (it does not complete
lap 4 cleanly), so it is used only as a same-input physics comparison, not as a
finish claim.

## 2. All 16 tracks (password route)

For the corrected screen alphabet, original country gate, full 15-bit checksum,
part-field map, and complete rain/snow table, see [PASSWORDS.md](PASSWORDS.md).
Geneva has no visible precipitation; its `$44` descriptor does not have the
weather-enable bit. Munich snow has a new native capture.

Every track is reached through the game's own **ENTER PASSWORD** screen. The
encoding was reversed from the ROM (`docs/PASSWORDS.md`); the generator is
`tools/tg2_password.py` and the UI driver `tools/tg2_password_ui.py`. Nothing
writes guest RAM: the tools only type symbols, verify them against the live
buffer at `$FF2570`, and then drive with controller input.

Per-track run (`tools/tg2_coverage.py`, `tools/tg2_coverage_batch.py`):

1. boot → main menu → `DOWN`×3 → `CONTINUE` → `PASSWORDS`;
2. type the 16-symbol password for the country (each symbol checked in RAM);
3. `END` → game-setup screen → `RACE` → intro panel (country, track, length,
   laps, weather icon, clock) → pre-race shop → race;
4. drive **62 s of race time** with the closed-loop controller (throttle `B`,
   steering from `$FF18CE`), a screenshot every 600 frames.

"Pass" below means: the password was accepted by the game, the intro panel
named a track, the race clock ran for >= 62 s of driving (race clock delta =
wall-frame delta), the car reached racing speed, and all four runtime
manifests stayed empty.

| # | Country / track | Weather / lighting | Laps | Off | 16:9 + HUD Edges | Manifests (both modes) |
|---:|---|---|---:|---|---|---|
| 0 | Australasia / Auckland | sun, 5:43 AM | 4 | pass, 62.18 s | pass, 62.20 s | 0/0/0/0 |
| 1 | Britain / Loch Ness | overcast (grey sky) | 5 | pass, 62.15 s | pass, 62.13 s | 0/0/0/0 |
| 2 | Canada / Banff | sun + cloud, 7:30 AM | 5 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 3 | Egypt / Abu Simbel | sun, 4:43 AM | 5 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 4 | France / Bordeaux | sun, 3:30 AM | 5 | pass, 62.17 s | pass, 62.13 s | 0/0/0/0 |
| 5 | Germany / Bavaria | **rain** (visible streaks) | 5 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 6 | Greece / Athens | **night** (dark palette, lamps) | 5 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 7 | India / Amber Port | sun, 9:43 AM | 5 | pass, 62.15 s | pass, 62.13 s | 0/0/0/0 |
| 8 | Ireland / Dublin | overcast, 1:10 PM | 5 | pass, 62.20 s | pass, 62.20 s | 0/0/0/0 |
| 9 | Italy / Florence | sun, 11:30 AM | 4 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 10 | Japan / Hiroshima | sun, 2:43 PM | 5 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 11 | Scandinavia / Copenhagen | dusk, 5:40 PM | 4 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 12 | South America / Chile | dusk, 9:30 PM | 5 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 13 | Spain / Andalucia | overcast, 3:30 PM | 5 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 14 | Switzerland / Geneva | bright, no precipitation (flags $44) | 4 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
| 15 | America (picker: U.S.A.) / Las Vegas | **night** (dark palette, city lights) | 4 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |

Evidence per cell, `build/qual/cov/cNN-<mode>/`:

| Artifact | What |
|---|---|
| `intro-0/1/2.png` | the intro panel (country, track, length, laps, weather icon, clock) |
| `race-start.png`, `race-<frame>.png` (×6), `race-end.png` | live race, 398×224 in widescreen, 256×224 Off |
| `trace.csv` | per-sample frame, race clock, lap, speed, lateral position, pad |
| `summary.json` | result, 62 s timings, manifests, password record, shot list |
| `dispatch_misses.toml`, `floor_coverage.toml`, `interior_label_misses.toml`, `floor_unsafe.toml` | runtime manifests, all **0 entries** |

Fastest sample speeds per track (raw player speed, ~5000 is ~120 MPH) ranged
from 4 962 to 6 665; every run crossed the start line and drove at racing
speed for the whole window.

### Widescreen margin audit

`tools/tg2_margin_audit.py --cov build/qual/cov --out build/qual/margin-audit`
measures the step between the last native column and the first generated
margin column against the frame's own column-step distribution, and writes a
4-frame contact sheet per run.

* 64 widescreen frames audited (4 per track), **0 seam outliers**; no seam
  step exceeded `max(3 × the frame's p99 column step, 8 × its median)`, and
  the few high ratios are HUD cells or scenery legitimately starting in the
  margin (e.g. the minimap at the right edge and roadside objects).
* Visual review of all 16 sheets (`build/qual/margin-audit/cNN-ws169-edges-sheet.png`):
  no wrapped road (the road never reappears as a second band in a margin), no
  missing scenery (roadside objects, skylines, rain and city lights continue
  into both margins), no seam at the native/margin boundary. HUD Edges places
  the speed/speedometer gauge at the left edge and the lap counter + minimap
  at the right edge, as designed.
* The centre banners (`16TH`, `NOW`, `LOSER`, `LAP 1 LEFT`) come from the game
  itself: the same strings appear in Off mode (e.g.
  `build/qual/cov/c02-off/race-9267.png` shows `LOSER`), so they are not a HUD
  duplication.
* Not checked here: sprite pop-in/out at the margin edges from one frame to
  the next (the coverage runs take screenshots every 600 frames, not dense
  sequences).

### Notes on the weather / lighting column

The intro panel's clock is flavour text, not the lighting source: Athens shows
a sun icon and 10:43 AM yet renders as a night race, and Bordeaux shows
3:30 AM yet renders in daylight. Weather (rain) and lighting (night palette)
are separate per-track properties; the column above records what the race
frame actually shows. Rain was confirmed by the persistent streak overlay on
Bavaria (`build/qual/cov/c05-off/race-11110.png`).

### Old route (kept for history)

The championship still needs a top-ten finish to advance, and the COUNTRY
SELECTION picker requires the password for the selected index (the screen's
demand value at `$FF2570+$24` must be <= the password's country). Both routes
work now that the codec is known; the PASSWORD row is simpler because it
passes `-1` and accepts any country. The pre-filled string that the old entry
below reports as rejected is the fresh-game password (`country = 0`), so it is
rejected for any picker index above 0 — that is the gate, not a broken string.

* Championship progression: `build/qual/progress1/`, `build/qual/soak-60/`
  (Auckland then Ayers Rock, the latter a night race).
* COUNTRY SELECTION navigation: `build/qual/country-nav3/`,
  `build/qual/country-britain/`.

## 3. Rain, night, nitro, crash, pit

| Scenario | Status | Evidence |
|---|---|---|
| Night race | **passed** | Athens (`build/qual/cov/c06-off/race-*.png`) and Las Vegas (`build/qual/cov/c15-*/race-*.png`) render with the night palette (dark sky, street lights, lit city). Ayers Rock from the championship route is also a night race (`build/qual/soak-60/race2-post-01.png`). |
| Rain race | **passed** | Germany / Bavaria is a rain race: a persistent streak overlay covers the whole frame in every captured shot, e.g. `build/qual/cov/c05-off/race-11110.png` and `build/qual/cov/c05-ws169-edges/race-*.png`. |
| Nitro | **passed (input, tank and speed)** | Input is the `C` button; see the measurement below |
| Collision / off-road | **passed (off-road), partial (contact)** | `tools/tg2_controls_probe.py` off-road phase: lateral hits the -287 clamp and speed collapses 5615 -> 3571 (`build/qual/controls2/throttle+LEFT-*.png`). On-road instantaneous drops in the same log (e.g. 5544 -> 3475 at frame 4410, lateral -11.7) are consistent with car contact but no contact frame was isolated |
| Pit stop | **not present** | no pit lane, pit prompt, tyre or fuel state in the HUD or in the player record |

### Nitro

* **Input.** `C`. The remapped-control byte `$FF18FA` sets bit 4 for raw pad
  bit 5 (`$00D80A..$00D872`); the CONTROL screen's TYPE 1 preset labels that
  button NITRO (`build/qual/shop-255/shop.png`). `A` and `C` are *not*
  interchangeable: `A` is the brake (bit 2, `$00D320` subtracts 0x30 from the
  target speed) and `C` is the nitro (bit 4, `$00E0BA`).
* **Tank.** Byte counter at `$FF18CA+$2D4` (read as the word 0x0600 = 1536 at
  the race start). Each activation decrements the high byte by one, i.e. six
  charges per race: 1536 -> 1280 -> 1024 ... (`0x0600`, `0x0500`, `0x0400`).
  No purchase is needed.
* **Controlled speed measurement** (`tools/tg2_nitro_compare.py`,
  `build/qual/nitro/compare/nitro-compare.json`): one closed-loop route is
  recorded, then replayed twice from the race start with exactly the same pad
  sequence; the second replay ORs `C` into the pads of a 90-frame window.
  Both replays report the same race clock at every marker, so the difference
  is the button alone:

  | Frames after GO | speed, no nitro | speed, nitro | tank |
  |---:|---:|---:|---|
  | 899 (press) | 3180 | 3216 | 1536 -> 1280 |
  | 915 | 3334 | 3532 | 1280 |
  | 930 | 3406 | 3696 | 1280 |
  | 959 | 3727 | 4509 | 1280 |
  | 990 | 4009 | **5207** | 1280 |
  | 1050 | 4199 | 3263 (crashed at the higher speed) | 1280 |

  +1 198 raw speed units (+30 %) at the same clock; the nitro replay then
  meets traffic the plain replay has not reached yet.
* Coverage runs with `--nitro` (`build/qual/cov/c08-off`, `c08-ws169-edges`,
  `c00-ws169-edges`) record the same tank drop and speed rise in
  `summary.json` under `nitro`.

## Physics: Off vs 16:9 vs 60 fps at matched frames

From the closed-loop traces (`build/qual/rt-off-1/trace.csv` vs
`build/qual/rt-fps60/trace.csv`), matched within 3 wall frames:

| Frame | Race clock Off = 60 fps | pos Off | pos 60 fps | Δpos | speed Off / 60 |
|---:|---|---:|---:|---:|---|
| 3600 | identical | 8 674 894 | 8 674 894 | 0 (0.0000 %) | 4230 / 4230 |
| 4400 | identical | 12 104 164 | 12 103 253 | −911 (0.0075 %) | 5334 / 5334 |
| 6000 | identical | 18 123 682 | 18 122 618 | −1064 (0.0059 %) | 4650 / 4649 |
| 6800 | identical | 21 048 159 | 21 042 344 | −5815 (0.0276 %) | 4530 / 4421 |
| 8000 | identical | 25 924 043 | 25 770 773 | −153 270 (0.59 %) | 5204 / 4242 |

The race clock is identical at **every** sample (the clock is IRQ-driven and the
60 fps option does not touch it). Position tracks the stock port to 0.03 % for
the first ~55 s and then separates because the car meets traffic/grass at
different points; that is the documented view-schedule difference plus a
reactive driver, not a clock or rule change.

## 4. Two-player split-screen

**Passed** with `tools/tg2_split_screen.py` (`build/qual/split-2p-race/`),
run in 16:9 with `TG2_RACE_60FPS=1`.

How it is reached: the main menu's first row is a mode toggle ("1P GAME" ->
"2P GAME") driven by START; the 2P setup then shows **two** panels and waits for
pad port 1. The TCP `set_input` command only drives port 0, so this run uses the
runner's input script with `PLAYER 2` directives for the menu, the second panel
and player 2's throttle, and monitors the result over TCP.

| Check | Result | Evidence |
|---|---|---|
| Two-player race flag | `$FF189E` = 1 for 1287 sampled race frames | `build/qual/split-2p-race/summary.json` |
| Split-screen renders | live race, player 1 98 MPH, player 2 88 MPH, both LAP 1/4 | `build/qual/split-2p-race/shot-6499.png` |
| Stays 4:3 | split-screen content occupies **x 71..326 = 256 px** centred in the 398-px 16:9 frame; a 1P 16:9 race frame spans the full 0..397 | pixel-column measure of `shot-6499.png` vs `build/qual/rt-ws169/finish.png` |
| 60 fps does not engage | 258/360 and 245/360 distinct framebuffers in two 6-s moving windows (~42/s, i.e. two stock-rate panels) versus 360/360 for 1P with the option on | `build/qual/split-2p-race/stderr.log` |

A stray START during the countdown pauses the game (the 2P countdown is reached
after the menu presses), so the tool exposes `--unpause-at`; the exported frame
in the screenshots above is unpaused.

## 5. Long-run soak (16:9 + 60 fps)

`python3 tools/tg2_soak.py --port 4470 --out build/qual/soak-33 --widescreen
16:9 --60fps --minutes 33 --launch-delay 300 --periodic-shots`
(`build/qual/soak-33/summary.json`).

| Measurement | Result |
|---|---|
| Wall time | **2021 s (33.7 min)**, one process, one port |
| Races started / completed | 10 / 7 (each Ayers Rock failure restarts the championship from the menu) |
| Frames simulated | finish of the last race at wall frame 121 127 |
| Exit | 0, clean shutdown (`[rewind] shutdown`), no watchdog exit |
| Stack pointer (`A7`) | 153 samples every 600 frames: **min = max = `$FFFFFA`** — no drift |
| Manifests | dispatch 0, floor 0, interior 0, unsafe 0 |
| Screenshots | 233 PNGs under `build/qual/soak-33/` |

Race-by-race lap times (seconds; the last short entry in some races is the
finish crossing that also increments the lap counter):

| # | Frames | Track (laps) | Lap times |
|---:|---|---|---|
| 1 | 3063-13585 | Auckland | 39.60, 39.20, 39.20, 43.03 |
| 2 | 15067-31049 | Ayers Rock (night) | 54.53, 54.47, 50.90, 54.50, 39.83 |
| 3 | 38717-49291 | Auckland | 40.50, 38.60, 40.00, 44.70 |
| 4 | 56959-67675 | Auckland | 40.77, 41.00, 41.40, 42.00 |
| 5 | 75343-85869 | Auckland | 41.57, 37.80, 41.10, 40.91 |
| 6 | 87447-104607 | Ayers Rock | 52.50, 54.17, 56.13, 53.07, 58.73 |
| 7 | 106225-121127 | Ayers Rock | 61.67, 57.93, 60.30, 56.59 |

## Reproduce

```sh
JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build

# full race, one presentation mode per run (real-time, deterministic control)
python3 tools/tg2_race_driver.py --port 4470 --out build/qual/rt-off     --skip-post --launch-delay 300 --widescreen off
python3 tools/tg2_race_driver.py --port 4470 --out build/qual/rt-ws169     --skip-post --launch-delay 300 --widescreen 16:9
python3 tools/tg2_race_driver.py --port 4470 --out build/qual/rt-fps60     --skip-post --launch-delay 300 --widescreen 16:9 --60fps

# post-race flow (results, table, setup, next intro, shop, next race)
python3 tools/tg2_race_driver.py --port 4470 --out build/qual/progress1 \
    --races 2 --periodic-shots --post-frames 3000

# same-route replay, any mode
python3 tools/tg2_replay_route.py --route build/qual/rt-off/route-race.json \
    --out build/qual/replay-ws169 --widescreen 16:9

# controls / off-road probe and split-screen
python3 tools/tg2_controls_probe.py --port 4470 --out build/qual/controls2 --turbo
python3 tools/tg2_split_screen.py --port 4470 --out build/qual/split-2p-race \
    --widescreen 16:9 --60fps --press-count 4 --unpause-at 3700

# 30-minute soak
python3 tools/tg2_soak.py --port 4470 --out build/qual/soak-32 \
    --widescreen 16:9 --60fps --minutes 32 --launch-delay 300 --periodic-shots

# all 16 tracks by password, both presentation modes (this task)
python3 tools/tg2_coverage_batch.py --port 4490 --out build/qual/cov \
    --modes off,ws169-edges --seconds 62
# one cell on its own: country 5 = Germany / Bavaria (rain)
python3 tools/tg2_coverage.py --port 4490 --out build/qual/cov/c05-off \
    --country 5 --mode off --seconds 62
# widescreen seam audit + contact sheets
python3 tools/tg2_margin_audit.py --cov build/qual/cov --out build/qual/margin-audit
# nitro controlled comparison
python3 tools/tg2_nitro_compare.py --port 4490 --out build/qual/nitro/compare \
    --country 0 --window-at 900 --window 90
# password round-trip
python3 tools/tg2_password.py decode "KVC2 2HQG CJL2 Y4%T"

# task 25: quickstate save -> fresh-process load matrix
python3 tools/tg2_state_matrix.py --out build/qual/qa-state-matrix
# task 25: the 19 races a password cannot select
python3 tools/tg2_reach_races.py --out build/qual/qa-reach
```

## Manifests

Every run copies the runtime manifests next to its evidence. All runs in this
ledger report `dispatch_misses.toml`, `floor_coverage.toml`,
`interior_label_misses.toml` and `floor_unsafe.toml` with **0 entries**; no new
discovery seeds were needed, so `game/game.toml` is unchanged by this task.

## Gaps / follow-ups

* The `stage` field is DIFFICULTY, not a race slot (see the task-22 section),
  so a password cannot name a country's races 2..4. Task 25 reached them by
  writing the selected index on the game-setup screen
  (`tools/tg2_reach_races.py`); every race in the game is now driven to the
  finish.
* The coverage runs take a screenshot every 600 frames, so per-frame sprite
  pop-in/out at the widescreen edges was not measured; only still-frame
  margin continuity (section 2) and the visible absence of wrapped/missing
  scenery were checked.
* The 60 fps option was not part of this task (another task owns it); all
  coverage runs are stock rate, so the 60 fps physics parity notes above still
  apply.
* The open-loop replay of a *reactive* route diverges once the car touches the
  grass; the deterministic comparison that is valid today is same-mode
  repeatability (exact) and same-script Off/16:9 (exact). A tuned feed-forward
  route would make the 60 fps same-script comparison exact as well.

## All-options soak (main c13967c+, 2026-11-06 overnight)

`TG2_HUD_MODE=edges TG2_HIDE_OVERSCAN=1 tools/tg2_soak.py --minutes 40 --widescreen 16:9 --60fps --periodic-shots`
on the dev build of main, with every overnight fix merged: renderer fixes,
Hide overscan, BOTH audio code present but not selected, exact guest clock.

| Metric | Result |
|---|---|
| Wall time | 2621.6 s (43.7 min), `result: finished`, exit 0 |
| Races started | 13 (Auckland / Ayers Rock alternating; 4- and 5-lap races completed) |
| Stack pointer | 199 samples, min `$FFFFA4`, max `$FFFFFA` (no drift) |
| Manifests | dispatch 0 / floor 0 / interior 0 / unsafe 0 |
| Evidence | `build-main/soak-all-on/` (private) |

## Task 22 — v0.1.0 release qualification (default options)

Run with the release defaults: widescreen Adaptive (16:9 canvas), 60 fps races
On, HUD Centered, Hide overscan On, the stock RACE SOUND default. One runtime at
a time, TCP port 4610, SDL offscreen video and dummy audio, uncapped (turbo)
guest where the tool allows it, every heavy step under
`flock ~/.cache/tg2-heavy.lock`.

### Race structure: 64 races, 16 countries x 4; `stage` is DIFFICULTY

This contradicts the assumption in the task (and in the earlier "gaps" note
above) that a password `stage` value reaches a country's later races. It does
not. The facts, all from the ROM and confirmed at runtime:

* The race table at ROM `$01B8E8` has **64 entries**, four per country. Entry
  *i* = `country = i >> 2`, `slot = i & 3`. Each entry is a 0xAE-byte record;
  byte 0..1 is the index, byte 7 the lap count and bytes 8..9 the track length
  as ASCII digits (`"16"` = 1.6 miles), matching the intro panel.
* `$FF16BE` is the selected race index. The intro panel and the race itself are
  loaded from `table[$FF16BE]` (stored to `$FF241C` at `$001E5E`); the password
  loader sets it to `country << 2` (`move.w $28(a0),d0; lsl.w #2` at
  `$023B54`), i.e. the country's **first** race.
* The password packer drops the low two bits when it prints a password:
  `lsr.w #2` then `andi.w #$f` at `$023A12..$023A18` reads `$FF16BE >> 2` as the
  4-bit country. A password therefore only ever resumes at a country's start,
  which matches the game handing out a password between countries.
* The 2-bit `stage` field is the **DIFFICULTY** level. The menu's DIFFICULTY
  page leaves its value through `move.w $6(a4),-$5fe8(a3)` at `$01ED4E`
  (`$FF2420`); the packer reads `$FF2420 & 3` into `stage` at `$023A2C`; the
  loader writes `stage` back to `$FF2420` at `$023B60`. The page shows the
  three labels **AMATEUR / PROFESSIONAL / CHAMPIONSHIP**, and `stage = 0/1/2`
  loads with the same country, the same race descriptor and a byte-identical
  intro panel and race picture (checked for country 0 slots 0..2: descriptor
  `0x01b9e8`, same Auckland panel, same first race frame).
* The only way to reach a country's races 2..4 is to finish the previous race
  in the top ten. `tools/tg2_progress.py` does exactly that with a generated
  password that carries money plus full upgrades; the race index is read back
  before every race (`0 -> 1 -> 2 -> 3` for country 0), and the four intro
  panels are Auckland / Ayers Rock / Canterbury Plains / Sydney.

The coverage table below therefore names races by country and slot, not by
`stage`. `stage = 0` (AMATEUR) was used for the progression runs.

### Coverage: 64 of 64 races driven to the finish (default options)

Every run below is `tools/tg2_progress.py` on the release defaults (16:9
canvas, 60 fps races, HUD Centered, Hide overscan On, stock RACE SOUND),
uncapped guest, TCP 4610, one runtime at a time, under the heavy lock. Each
country starts from a generated password that carries money and full upgrades
(the fixture uses 150k with every part at max; the checksum is 15-bit, not capped at 255), then races in order; the
race index is read back before every race. A race is "passed" when it reached
the finish (the clock froze with speed 0).

The first pass reached 45 of 64 races the same way and stopped at a country's
top-ten gate. The 19 remaining races were then qualified one process per race:
the password still names the country, and on the game-setup screen the run
writes the race index `$FF16BE` and the matching descriptor from the ROM table
`$01B8E8 + index*4` to `$FF241C` (grounded in the password loader at
`$023B54` and the top-level copy at `$001E5E`; see `docs/RAM_MAP.md`). The
intro panel then names the requested slot's own track and the HUD shows its
own lap count, so the cell is the race it claims to be:
`tools/tg2_reach_races.py` (`build/qual/qa-reach/`). No other guest write is
made; the driving is controller input only. Result cells marked
"race-index override" come from those per-race runs; all other cells are the
original country progression runs.

Manifests (dispatch / floor coverage / interior labels / floor unsafe) are the
counts from that run. The country-progression batch ran before the discovery
fix below, so Egypt and Australasia show the floor miss there. The per-race
runs confirm the open `0x00650C` interior-label miss is track-specific: it
appears in the races that actually execute that scene-init block (1/1) and is
absent in the others (0/0).

| Country | Race | Track | Length | Laps | Descriptor | Result | Splits | Manifests | Evidence |
|---|---:|---|---:|---:|---|---|---|---|---|
| Australasia | 1 | Auckland | 1.6 mi | 4 | 0x01b9e8 | passed | 5 | 0/2/0/0 | `build/qual/qa-prog/c00` |
| Australasia | 2 | Ayers Rock | 1.2 mi | 5 | 0x01ba96 | passed | 6 | 0/2/0/0 | `build/qual/qa-prog/c00` |
| Australasia | 3 | Canterbury Plains | 1.5 mi | 4 | 0x01bb44 | passed | 5 | 0/2/0/0 | `build/qual/qa-prog/c00` |
| Australasia | 4 | Sydney | 3.2 mi | 3 | 0x01bbf2 | passed | 4 | 0/2/0/0 | `build/qual/qa-prog/c00` |
| Britain | 1 | Loch Ness | 1.7 mi | 5 | 0x01bca0 | passed | 6 | 0/0/0/0 | `build/qual/qa-prog/c01` |
| Britain | 2 | London | 2.0 mi | 4 | 0x01bd4e | passed | 5 | 0/0/0/0 | `build/qual/qa-prog/c01` |
| Britain | 3 | Sheffield | 2.4 mi | 4 | 0x01bdfc | passed | 5 | 0/0/0/0 | `build/qual/qa-prog/c01` |
| Britain | 4 | Stonehenge | 2.5 mi | 4 | 0x01beaa | passed | 5 | 0/0/0/0 | `build/qual/qa-prog/c01` |
| Canada | 1 | Banff | 1.4 mi | 5 | 0x01bf58 | passed | 6 | 0/0/0/0 | `build/qual/qa-prog/c02` |
| Canada | 2 | Niagara | 2.7 mi | 3 | 0x01c006 | passed | 4 | 0/0/0/0 | `build/qual/qa-prog/c02` |
| Canada | 3 | Toronto | 2.8 mi | 3 | 0x01c0b4 | passed | 4 | 0/0/0/0 | `build/qual/qa-prog/c02` |
| Canada | 4 | Vancouver | 2.7 mi | 4 | 0x01c162 | passed (race-index override) | 5 | 0/0/0/0 | `build/qual/qa-reach/c02-s4` |
| Egypt | 1 | Abu Simbel | 0.7 mi | 8 | 0x01c210 | passed | 9 | 0/2/0/0 | `build/qual/qa-prog/c03` |
| Egypt | 2 | Aswan | 0.9 mi | 7 | 0x01c2be | passed (race-index override) | 8 | 0/0/0/0 | `build/qual/qa-reach/c03-s2` |
| Egypt | 3 | Cairo | 1.1 mi | 5 | 0x01c36c | passed (race-index override) | 6 | 0/0/0/0 | `build/qual/qa-reach/c03-s3` |
| Egypt | 4 | Hush Sitton | 1.6 mi | 5 | 0x01c41a | passed (race-index override) | 6 | 0/0/0/0 | `build/qual/qa-reach/c03-s4` |
| France | 1 | Bordeaux | 1.1 mi | 5 | 0x01c4c8 | passed | 6 | 0/0/0/0 | `build/qual/qa-prog/c04` |
| France | 2 | Monaco | 1.9 mi | 5 | 0x01c576 | passed | 6 | 0/0/0/0 | `build/qual/qa-prog/c04` |
| France | 3 | Nice | 2.3 mi | 4 | 0x01c624 | passed | 5 | 0/0/0/0 | `build/qual/qa-prog/c04` |
| France | 4 | Paris | 2.6 mi | 3 | 0x01c6d2 | passed | 4 | 0/0/0/0 | `build/qual/qa-prog/c04` |
| Germany | 1 | Bavaria | 1.2 mi | 5 | 0x01c780 | passed | 6 | 0/0/0/0 | `build/qual/qa-prog/c05` |
| Germany | 2 | Cologne | 2.0 mi | 4 | 0x01c82e | passed | 5 | 0/0/0/0 | `build/qual/qa-prog/c05` |
| Germany | 3 | Frankfurt | 1.6 mi | 4 | 0x01c8dc | passed | 5 | 0/0/0/0 | `build/qual/qa-prog/c05` |
| Germany | 4 | Munich | 2.8 mi | 3 | 0x01c98a | passed | 4 | 0/0/0/0 | `build/qual/qa-prog/c05` |
| Greece | 1 | Athens | 1.0 mi | 7 | 0x01ca38 | passed | 8 | 0/0/1/1 | `build/qual/qa-prog/c06` |
| Greece | 2 | Meteora | 2.5 mi | 4 | 0x01cae6 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c06` |
| Greece | 3 | Mykanos | 2.6 mi | 4 | 0x01cb94 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c06` |
| Greece | 4 | Santorini | 2.5 mi | 4 | 0x01cc42 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c06` |
| India | 1 | Amber Port | 0.9 mi | 8 | 0x01ccf0 | passed | 9 | 0/0/1/1 | `build/qual/qa-prog/c07` |
| India | 2 | Bombay | 1.4 mi | 5 | 0x01cd9e | passed (race-index override) | 6 | 0/0/1/1 | `build/qual/qa-reach/c07-s2` |
| India | 3 | Delhi | 2.1 mi | 4 | 0x01ce4c | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c07-s3` |
| India | 4 | Taj Mahal | 2.4 mi | 4 | 0x01cefa | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c07-s4` |
| Ireland | 1 | Dublin | 1.5 mi | 5 | 0x01cfa8 | passed | 6 | 0/0/1/1 | `build/qual/qa-prog/c08` |
| Ireland | 2 | Galway | 1.3 mi | 5 | 0x01d056 | passed | 6 | 0/0/1/1 | `build/qual/qa-prog/c08` |
| Ireland | 3 | Killarney | 1.8 mi | 4 | 0x01d104 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c08` |
| Ireland | 4 | Limerick | 1.8 mi | 4 | 0x01d1b2 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c08` |
| Italy | 1 | Florence | 1.6 mi | 4 | 0x01d260 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c09` |
| Italy | 2 | Pisa | 2.3 mi | 4 | 0x01d30e | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c09` |
| Italy | 3 | Rome | 2.5 mi | 4 | 0x01d3bc | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c09` |
| Italy | 4 | Sicily | 2.3 mi | 4 | 0x01d46a | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c09-s4` |
| Japan | 1 | Hiroshima | 1.9 mi | 5 | 0x01d518 | passed | 6 | 0/0/1/1 | `build/qual/qa-prog/c10` |
| Japan | 2 | Kyoto | 2.8 mi | 3 | 0x01d5c6 | passed | 4 | 0/0/1/1 | `build/qual/qa-prog/c10` |
| Japan | 3 | Tokyo | 3.0 mi | 3 | 0x01d674 | passed | 4 | 0/0/1/1 | `build/qual/qa-prog/c10` |
| Japan | 4 | Yokohama | 2.6 mi | 4 | 0x01d722 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c10` |
| Scandinavia | 1 | Copenhagen | 1.5 mi | 4 | 0x01d7d0 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c11` |
| Scandinavia | 2 | Helsinki | 1.7 mi | 5 | 0x01d87e | passed | 7 | 0/0/1/1 | `build/qual/qa-prog/c11` |
| Scandinavia | 3 | Reykjavik | 2.1 mi | 4 | 0x01d92c | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c11-s3` |
| Scandinavia | 4 | Stockholm | 2.1 mi | 4 | 0x01d9da | passed (race-index override) | 5 | 0/0/0/0 | `build/qual/qa-reach/c11-s4` |
| South America | 1 | Chile | 1.6 mi | 5 | 0x01da88 | passed | 6 | 0/0/1/1 | `build/qual/qa-prog/c12` |
| South America | 2 | Mexico | 2.3 mi | 4 | 0x01db36 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c12` |
| South America | 3 | Peru | 2.6 mi | 4 | 0x01dbe4 | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c12-s3` |
| South America | 4 | Brazil | 2.5 mi | 4 | 0x01dc92 | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c12-s4` |
| Spain | 1 | Andalusia | 0.9 mi | 7 | 0x01dd40 | passed | 8 | 0/0/1/1 | `build/qual/qa-prog/c13` |
| Spain | 2 | Barcelona | 1.2 mi | 6 | 0x01ddee | passed | 7 | 0/0/1/1 | `build/qual/qa-prog/c13` |
| Spain | 3 | Madrid | 2.4 mi | 4 | 0x01de9c | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c13-s3` |
| Spain | 4 | Seville | 2.2 mi | 4 | 0x01df4a | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c13-s4` |
| Switzerland | 1 | Geneva | 1.6 mi | 4 | 0x01dff8 | passed | 5 | 0/0/0/0 | `build/qual/qa-prog/c14` |
| Switzerland | 2 | Grindelwald | 1.8 mi | 5 | 0x01e0a6 | passed (race-index override) | 6 | 0/0/1/1 | `build/qual/qa-reach/c14-s2` |
| Switzerland | 3 | Lucerne | 2.2 mi | 4 | 0x01e154 | passed (race-index override) | 5 | 0/0/0/0 | `build/qual/qa-reach/c14-s3` |
| Switzerland | 4 | Zurich | 2.9 mi | 4 | 0x01e202 | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c14-s4` |
| U.S.A. | 1 | Las Vegas | 2.2 mi | 4 | 0x01e2b0 | passed | 5 | 0/0/1/1 | `build/qual/qa-prog/c15` |
| U.S.A. | 2 | Los Angeles | 2.2 mi | 5 | 0x01e35e | passed | 6 | 0/0/1/1 | `build/qual/qa-prog/c15` |
| U.S.A. | 3 | New York | 2.7 mi | 4 | 0x01e40c | passed (race-index override) | 5 | 0/0/1/1 | `build/qual/qa-reach/c15-s3` |
| U.S.A. | 4 | San Francisco | 2.5 mi | 4 | 0x01e4ba | passed (race-index override) | 5 | 0/0/0/0 | `build/qual/qa-reach/c15-s4` |

Evidence per country progression: `build/qual/qa-prog/cNN/` (trace.csv,
route.json, summary.json, intro panels, a screenshot every 900 frames, finish
frame). Evidence per index-override race: `build/qual/qa-reach/cNN-sN/` (same
artifacts, one process per race; `batch.json` summarises all 19).
Post-fix re-runs: `build/qual/qa-fixcheck/c00` (Auckland + Ayers Rock, all
manifests 0) and `build/qual/qa-650c-fix/cNN` (task 24: Greece, India, Italy,
Japan, Spain, Switzerland, race 1 each, all manifests 0/0/0/0). The `0/0/1/1`
cells above predate task 24; that 1 is the `0x00650C` miss, now fixed.

### Bug list (severity, reproduction, state)

1. **BLOCKER, fixed — tier-3 floor ran `0x00E46C` / `0x00445A`.**
   The owner's release playtest (session 3, frames 12900/13069) and our own
   batch runs (Australasia race 2 Ayers Rock, frame 19289; Egypt race 1)
   reached the interpreter floor. Both addresses are real ROM code: the
   small-object animator registered with `MOVE.L #$E46C,$C(A4)` at `$003D40`
   (the sibling of the already-seeded `$00E436` at `$003CE8`) and the
   `$00445A` PRNG step it calls. The object table lives in RAM (`$FF2736`),
   so static scanning cannot see the callback. Fixed by seeding both in
   `game/driver.discovery.toml`; the generated C now contains
   `func_00E46C` and the dispatcher entry. Verified on the exact track: a
   post-fix 2-race Australasia run reports 0/0/0/0.
2. **MAJOR, fixed (task 24, engine core patch `core-0004`) — interior-label
   dispatch at `0x00650C`, the scene-init continuation skipped.**
   `interior_label_misses.toml` and `floor_unsafe.toml` listed `0x00650C` in
   nine country runs (Greece onward), first at race 1 frame ~8585. `$650C` is
   not an entry point: it is the fall-through continuation after the three
   setup `bsr`s at `$6500..$6508`, and `0x000650C` never appears in the ROM as
   data. The value could only come from the return slot those `bsr`s push, and
   the dispatcher was the plain `rts` at `$754A` at the end of `$7336`. Cause:
   the split-function stack counter (`_sp_popped`) credited only the
   MOVE/MOVEA/MOVEM/PEA and `ADDQ/SUBQ #n,SP` forms, so `add.w (sp)+,d0` at
   `$740C` moved the guest stack without the counter noticing; sixteen
   iterations of func `$7336`'s sprite loop left the delta at -32 and the RTS
   was read as "the guest pushed a jump target", dispatching `$650C` instead
   of returning to it. Fixed in the engine with one exact stack-delta rule for
   every mnemonic (see "Task 24" below). The repro now reports 0/0/0/0, and so
   do Greece, India, Italy, Japan, Spain and Switzerland with `--races 1`.
3. **MAJOR, fixed — rain/snow particles smear across the widescreen margins.**
   In every rain/snow race a particle that landed on the old 256-px edge was
   continued by `plane_a_margins()` as a full-width one-line streak in both
   margins (`build/qual/qa-prog/c04/c4-r4-start.png`,
   `.../c05/c5-r4-start.png`). Plane A carries both the raster-positioned
   tunnel wall and the weather overlay; the fix only continues an edge that
   an opaque plane-A run of >= 8 texels owns, so a 1-2 texel particle keeps
   the plane-B continuation. Before/after:
   `build/qual/qa-weather-after/c04-full/c4-r4-start.png` (night rain) and
   `.../c05-full/c5-r4-start.png` (blizzard). The margin audit exports
   `pa_run`/`pa_extend`; `tools/check_margin_artifacts.py` now fails on a
   short-run extension. Two full rain/snow races: 1168 + 1167 frames audited,
   `plane_a_short_extension` 0, all violation classes 0, `passed: true`.
   Weather particles still do not populate the margins themselves (the margin
   fill composites plane B); that is a separate enhancement, not a streak.
4. **MAJOR, fixed (task 25) — a quickstate loaded in a fresh process froze the
   race picture.** Save at the GO frame in France, then: same process, run 120
   frames, load, hold throttle -> 8 distinct pictures, speed 5144, clock
   advances (rewind works). Fresh process, boot 600 frames, load the same file,
   hold throttle -> 1 distinct picture, clock advances to 27197274, speed 4540:
   the guest ran and RAM changed but the picture never updated. Cause: TG2 has
   no shared WaitForVint park (it spins on its own hardware flags inside each
   screen's loop) and set neither `resume_main_loop_pc` nor `save_resume_pc`, so
   the save was taken mid-instruction and the loader restored the CPU inside the
   new process's boot chain. Fixed with a declared per-frame boundary plus an
   explicit resume PC; see "Task 25 — cross-session quickstates" below.
   Evidence: `build/qual/qa-state`, `build/qual/qa-state-matrix`,
   `tools/tg2_state_freeze.py`, `tools/tg2_state_matrix.py`.
5. **MINOR, known — BOTH still lacks the engine/nitro PCM** (needs a second
   Z80 core, task 20b). Checked here for noise: reference below.

### Release-config smoke and stock identity

* Release-profile build (`-DGEN_ENABLE_TRACE=OFF -DSONIC_REVERSE_DEBUG=OFF`,
  Release, no IPO) in `build-rel/`.
* `tools/tg2_release_smoke.py`: the executable and the ROM (renamed
  `fixture-cartridge.dat`, detected by CRC) in a scratch directory, SDL dummy
  drivers, a controller-only input script that boots to a 1P race; exit 0,
  `input_script: loaded`, race picture captured
  (`build/qual/qa-release-smoke2/run/race-4.png`, `race-5.png`).
* With every presentation option off (`TG2_RACE_60FPS=0
  TG2_HIDE_OVERSCAN=0`, widescreen off): frame 60 `2A0B972960C5E325`, frame
  300 `1131D937D70234FD`, 0 manifests (`tools/verify_widescreen.py --modes
  off`, `build/qual/qa-ws-off`). Re-checked after merging origin/main at
  `2e42151` (engine patches 0015/0016 + HUD popup fix).

### Sound modes (one race each, 40 s capture)

`tools/tg2_both_route.py --mode {music,sfx,both} --widescreen 16:9 --60fps`,
then `tools/audio_glitch_detect.py` on each `race.wav`:

| Mode | Pops | digital-silence dropouts | DC-hold runs | envelope collapses |
|---|---:|---:|---:|---:|
| MUSIC | 0 | 0 | 9 | 400 |
| SFX | 0 | 0 | 0 | 0 |
| BOTH | 0 | 0 | 0 | 49 |

Zero pops and zero digital-silence dropouts in all three. The MUSIC
DC-hold/envelope counts are the PSG square wave's identical samples and the
music's own note envelopes on an offline capture (the detector's 2 ms hold
and 20 dB collapse tests were designed against a device capture of steady
music); BOTH has neither. Device-side confirmation still needs the owner's
speakers (the same detector, `--device` capture).

### Two-player split screen

Not re-qualified as a full race this round. `tools/tg2_split_race.py` reaches
the 2P race (`$FF189E` = 1, the race clock runs from frame ~3507) and drives
player 1 closed-loop, but the scripted boot's last START lands just after GO
and pauses the countdown, so the full-race attempt stops at the pause. The
previous live 2P evidence (`build/qual/split-2p-race/`, section 4 above) still
stands: two panels, both cars racing, 4:3 content, 60 fps disengaged. A full
2P race remains open for the owner's playtest.

### Save states under BOTH

The 0014 second Z80 core serialises with the state. Re-checked with
`TG2_RACE_SOUND=both` on the merged build: save at GO, run, load in the same
process, hold throttle -> 8 distinct pictures, speed 5144, race clock still
advancing, 0/0/0/0 manifests (`build/qual/qa-state-both/summary.json`). The
second Z80 does not break rewind; the cross-process freeze below is the same
one as with the stock sound.

### Merge note

Qualified again after merging `origin/main` at `3a92c4f` (engine patches
0014 BOTH second Z80, 0015 icon, 0016 photo-freeze hotkey, 0017 internal
resolution hidden; HUD-overtake popup fix): engine patches reset and
re-applied, rebuilt with JOBS=3 under the heavy lock, stock Off hashes
re-checked (`build/qual/qa-ws-off2`).

## Task 25 — cross-session quickstates

### What was frozen

Top Gear 2 has no single game-mode word and no shared WaitForVint routine: every
screen spins on its own hardware flag (`tst/move+cmp` loops in the menu code,
the picture-ready byte `$FF2424` in the race loop) and the game fiber yields
from the scanline scheduler. The engine's host-snapshot path parks a save at a
`WaitForVint` whose caller reports `state_at_boundary()`; TG2 never reaches that
park, so the legacy save interrupted an arbitrary instruction. Loading such a
file in a fresh process restored CPU and RAM but the C call chain was still the
boot/title chain: the guest clock and RAM advanced while the picture stayed on
"GO!" (docs/VALIDATION.md, task-22 bug 4).

### Mechanism (engine patch 0018, game adapter)

* Engine patch 0018 adds `glue_state_boundary(site)`: a game hook can offer a
  per-frame instruction as a host-snapshot boundary. A queued save parks the
  game fiber there *before* the instruction, so the snapshot is taken at a
  repeatable loop point with the guest stack intact; the guest resumes in place
  afterwards. It also adds `GameSpec.state_resume_pc`, consulted after the
  adapter's `state_load(apply)` has prepared it, which names the PC the game
  fiber restarts at.
* `game/tg2_spec.c` saves a four-word host payload (magic, version, boundary
  site), approves the race loop and the title/menu loops, and maps the saved
  site to the same address on load. `tools/apply-engine-patches.sh` applies the
  patch; a build id rejects states from another build before touching RAM.
* The reference port for this project (RocketKnightAdventuresRecomp) leaves
  `resume_main_loop_pc` at 0 with no host payload, so it has the same gap;
  there was nothing to copy from it.
* `game/game.toml` seeds those loop tops as in-function entries
  (`$0065F2` race picture-ready loop, `$001E18` top-level loop, `$001E9D8`
  title START spin, `$001EBF6` main-menu page loop). The recompiler splits each
  into a callable entry without changing its host body; the generated code path
  is a tail transfer where a branch was, and the stock Off framebuffer hashes
  prove the game still behaves identically.

| Screen | Boundary instruction | Resume PC | Verified |
|---|---|---|---|
| Race (1P and 2P) | `$0065F2` picture-ready wait, once per frame | `$0065F2` | live, pixel-identical to the saved frame |
| Title | `$001E9D8` START spin | `$001E9D8` | live, pixel-identical, START still advances |
| Main menu | `$001EBF6` page draw/input loop | `$001EBF6` | live, pixel-identical, START still advances |
| Password entry / game setup | no declared loop top | — | save **refused** ("Save unavailable in the current game mode", no file written) |
| Any other screen | no declared loop top | — | save refused, nothing freezes |

A state file from another build, a damaged file, or an old-format file is
rejected with a clear message before any guest state is touched. The in-process
path (rewind, F-keys within one session) uses the same boundary and payload.

### Quickstate matrix (release defaults, one runtime at a time)

`tools/tg2_state_matrix.py --out build/qual/qa-state-matrix`: each case saves
through the same runner entry point the overlay/F-key path uses, then loads the
file in a **second process** that boots 600 frames first. "Live" means the
picture changed, the race clock advanced, and the manifests stayed empty.

| Case | Options at save | Distinct pictures / 420 frames | Clock delta | Speed | Manifests | Evidence |
|---|---|---:|---:|---|---|---|
| `race-off` | 4:3, stock rate | 8 | +24 794 302 | 82 → 3803 | 0/0/0/0 | `build/qual/qa-state-matrix/race-off` |
| `race-60fps` | 16:9 + 60 fps | 8 | +24 794 302 | 82 → 3709 | 0/0/0/0 | `build/qual/qa-state-matrix/race-60fps` |
| `race-ws169` | 16:9, stock rate | 8 | +24 794 302 | 82 → 3709 | 0/0/0/0 | `build/qual/qa-state-matrix/race-ws169` |
| `race-both` | 16:9 + 60 fps, RACE SOUND BOTH | 8 | +24 794 302 | 82 → 3803 | 0/0/0/0 | `build/qual/qa-state-matrix/race-both` |
| `race-mid` | 16:9 + 60 fps, 240 frames into the race | 8 | +24 794 302 | 4270 → 3274 (throttle only) | 0/0/0/0 | `build/qual/qa-state-matrix/race-mid` |
| `rewind` | same process save → run → load | 8 | +24 794 302 | 82 → 3709 | 0/0/0/0 | `build/qual/qa-state-matrix/rewind` |
| `menu-title` | title screen | static (pixel-identical) | — | — | 0/0/0/0 | `build/qual/qa-state-matrix/menu-title` |
| `menu-main` | main menu | static (pixel-identical) | — | — | 0/0/0/0 | `build/qual/qa-state-matrix/menu-main` |
| `menu-password` | password entry | save refused | — | — | — | `build/qual/qa-state-matrix/menu-password` |
| `menu-setup` | game setup | save refused | — | — | — | `build/qual/qa-state-matrix/menu-setup` |
| `race-2p` | 2P split screen, 16:9 + 60 fps | resumed paused (pixel-identical) | — | — | 0/0/0/0 | `build/qual/qa-state-matrix/race-2p` |

The loaded menu frame is the saved frame: both menu cases compare the saving
process's screenshot with the loading process's first frame (0.0 % differing
pixels). The original freeze reproduction (`tools/tg2_state_freeze.py`,
`build/qual/qa-state-fix1`) now ends the fresh process on exactly the
same-process values — 8 distinct pictures, speed 5144, clock 27251887 — where
the pre-fix run gave 2 pictures and a diverged clock. The matrix also re-runs
the same-process load for the stock sound (`rewind`), so rewind still works.

The earlier freeze reproduction (`tools/tg2_state_freeze.py`,
`build/qual/qa-state-fix1`) now reports **8 distinct pictures in the fresh
process** (was 1-2), identical speed and clock to the same-process load; the
same check on the clean rebuild from `tools/apply-engine-patches.sh --reset`
(`build/qual/qa-state-fix2`) gives speed 5144 and clock 26978822 in both
processes.

### Quickstate resume continues the guest's callers (2026-11-07)

Owner report (macOS, release build): a quickstate saved and loaded during race
3 of a country, finished in 2nd place, went back to the main menu after the
race instead of the results and race 4. Reproduced on a dev build with the
owner's own `native_save_1.bin`: after the finish the log printed
`resume loop returned at $0065F2; continuing at dispatcher $001E18`, no results
screen appeared and the race index stayed at 2.

The real guest stack in a normal race (`get_registers` + WRAM, no state
loaded) holds one return address: `$001E82` at `$FFFFFA`, pushed by
`jsr $64C2` at `$001E7C` in the top-level loop. `$001E82` runs the post-race
flow: `jsr $2301E` (results), the qualification test at `$20A62`, then
`$FF16BE + 1` and `bra $1E52` (next race). The title and main-menu boundaries
sit one level down as well, below `jsr $1E764` at `$001E18` (return `$001E1E`).
The loader reset A7 to the initial SSP and, when the resumed loop returned,
called the dispatcher `$001E18`, which starts over at the title.

Engine patch 0021 resumes a game boundary inside the restored frame (A7 kept)
and, when the loop returns, pops each guest return address that follows a
JSR/BSR and continues it. `game/game.toml` seeds `$001E82` and `$001E1E`
(both checked as the instruction after the call in the raw ROM).

| Case (dev build, dummy video/audio, one runtime at a time) | Before | After |
|---|---|---|
| Owner's race-3 state, autopilot finishes 10th | menu, race index 2, no results | `continuing guest caller $001E82`, race 4 starts (index 3) |
| Owner's race-3 state, autopilot finishes 12th | — | "YOU HAVE FAILED TO QUALIFY", then the title (stock behaviour) |
| Title state (`$01E9D8`), fresh process, START → menu → START row | — | `continuing guest caller $001E1E`, race reached |
| Main-menu state (`$01EBF6`), fresh process, START row | — | `continuing guest caller $001E1E`, race reached |

All four manifests are empty in every loaded run. Stock identity is unchanged:
`tools/probe_run.py --widescreen off --frames 360` gives frame 60
`2A0B972960C5E325` and frame 300 `1131D937D70234FD`.

The F-key slots are the same mechanism: Shift+F1..F9 saves into
`native_save_N.bin`, F1..F9 loads it, both through `runner_save_state_file` /
`runner_load_state_file`, the entry points the matrix drives directly.

Stock identity: with every presentation option off, frame 60
`2A0B972960C5E325` and frame 300 `1131D937D70234FD` are unchanged
(`tools/verify_widescreen.py --modes off`, `build/qual/qa-ws-off3`), and all
four manifests stay empty.

2P: the scripted boot reaches the split-screen race and saves at `$0065F2`;
`$FF189E` is 1 before and after the fresh-process load, the loaded picture is
pixel-identical to the saved one (0.0 %), and the manifests stay empty. That
boot leaves the game's own PAUSE overlay up (the known task-22 scripted-boot
pause) and TCP `set_input` does not clear it, so the resumed 2P picture is the
correct paused race rather than a live one; a full unpaused 2P race is still
the open item from the 2P section above.

## Task 24 — the skipped scene-init call at `$650C`

### Ground truth (raw ROM, `tools/disasm_tg2.py`)

* `$64C2` is the race scene init. It is called with `jsr $64c2.l` from
  `$001E7C` (return `$001E82`, the attract/new-race driver that walks the
  64-entry race table at `$01B8E8`) and from `$001FDE` (the 1P race path).
* Its first three calls are `bsr.w $754C`, `bsr.w $8B32` and `bsr.w $7336` at
  `$6500/$6504/$6508`. `$650C` is the instruction after them (`jsr $2520`,
  `jsr $2628`, `jsr $F7FA`). Those three callees have no other caller in the
  ROM, so the continuation is only reachable as the fall-through of `$6508`.
* `0x000650C` appears nowhere in the 1 MB ROM as data, and no `bra`/`bsr`/
  `jmp`/`jsr` in the ROM targets it. A "missing entry point" reading is
  therefore wrong: the value can only come from the return slot that the
  `bsr.w $7336` at `$6508` pushes, i.e. the plain `rts` at `$754A` at the end
  of func `$7336`.
* `$754A` closes a loop over the sprite list (`$7524..$7546`) whose body calls
  `$8AC4`/`$8AD2`, and earlier in the same function `move.w d0,-(sp)` at
  `$73FE` is paired with `add.w (sp)+,d0` at `$740C`.

### Root cause (engine, not a game seed)

The engine tracks a path-local guest stack delta (`_sp_popped`, carried into
split-function tails through `g_split_sp_popped`). An RTS whose total is
negative is interpreted as "the guest pushed a jump target"
(`MOVE.L #target,-(SP); RTS`) and its stack top is dispatched instead of
returning to the native caller (patch `core-0003`). That interpretation needs
an *exact* delta, but only the MOVE/MOVEA/MOVEM/PEA forms and `ADDQ/SUBQ #n,SP`
credited it.

`add.w (sp)+,d0` at `$740C` pops two bytes the counter never saw, so each pass
of func `$7336`'s sprite loop leaked -2. Sixteen passes left `_sp_popped` at
-32 at the RTS in `$754A`, which then popped the `$650C` return slot and
dispatched it. `$650C` is interior to func `$64C2`, so the runner recorded an
interior-label miss, the floor capsule ran `$650C..$6656` and could not return
to the live frame (`exit_pc $007F18`, `expected_ret $001E82`), and the dispatch
was declined. `$650C..$6656` is the countdown/presentation path of every race,
so from Greece onward (the tracks whose sprite loop runs 16+ times) it was
skipped for the rest of the session.

### Fix

* Engine patch `core-0004-exact-stack-delta.patch` (`external/m68k-recomp-core`)
  replaces the per-mnemonic accounting with one `stack_delta_bytes()` rule used
  by both the `has_sp_adjust` pre-scan and the single emission point: `(A7)+`
  releases 4 bytes for a long / 2 otherwise, `-(A7)` allocates the same, plus
  PEA, `ADDQ/SUBQ #n,SP` and MOVEM; control flow is excluded because it owns its
  return slot explicitly. Pre-scan and emission can no longer disagree.
* No game seed, no in-function label, no generated-C edit. In this ROM exactly
  one instruction's accounting changes (`$740C`, in the buggy function);
  `tools/check_stack_delta.py` reports 1902 accounted instructions and, after
  the fix, 0 mismatches across the whole generated program.
* Residual gap, unchanged and honest: a *genuine* `MOVE.L #target,-(SP); RTS`
  whose target is an interior address still needs in-function dispatch codegen.
  TG2 has no such site (the Duff's-device tables at `$7B08/$7CE4/$7E78` point at
  their own seeded entries), so the miss is gone, not hidden.

### Evidence

| Check | Before | After |
|---|---|---|
| `tg2_progress --country 6 --races 1` manifests | 1/1 interior+unsafe at frame 8585 | `build/qual/qa-650c-fix/c06` 0/0/0/0 |
| Greece/India/Italy/Japan/Spain, race 1 each | 0/0/1/1 each (task 22 batch) | 0/0/0/0 each (`qa-650c-fix/c06,c07,c09,c10,c13`) |
| Switzerland, race 1 | 0/0/0/0 in the task 22 batch (its sprite count never reached the drift) | 0/0/0/0 (`qa-650c-fix/c14`) |
| floor-capsule executed PCs (`executed-pcs.txt`) | contains `$650C,$6512,$6518,$651E..$6594`, `$2520..$25FC`, `$F702..$F7FA` | none of them |
| race 1 start frame (Greece) | 9057 | 8997 |
| Off-mode frame 60 / 300 | `2A0B972960C5E325` / `1131D937D70234FD` | unchanged (`qa-ws-off-650c`) |

Every post-fix run reached the finish: Greece Athens 8 laps, India Amber Fort
9, Italy Florence 5, Japan Hiroshima 6, Spain Andalusia 8, Switzerland Geneva
5 (`summary.json` in each directory). The three `jsr` targets that only the
`$650C` block calls ($2520, $2628, $F7FA) no longer appear in the floor's
executed-PC set, i.e. the continuation now runs as native code inside
`func_0064C2` instead of being handed to the interpreter and discarded.

Race-start capture diff (same frame, 356x200): 27 pixels in a 13x6 HUD area
(`c6-r1-start.png`, before vs after) — the countdown/presentation path now
completes; the boot menus are pixel-identical, which also shows the runs are
frame-aligned up to the race.

Regression check: `python3 tools/check_stack_delta.py` re-derives every
instruction's stack delta from the ROM with capstone and fails on a missing or
wrong `_sp_popped` line. Removing the `$740C` accounting line from a copy of the
generated tree makes it report exactly
`$00740C add.w (a7)+, d0: expected delta +2, generated +0` (exit 1).

## Quickstate feedback and the menu-dismiss input leak (2026-11-07)

Owner report on macOS: choosing "Save state" in the in-game (Esc) menu with
Enter wrote no file, and there was no visible confirmation of a save or load.

Cause 1 — the key that accepts the menu row also reached the game. The owner's
feedback replay (`TG2-feedback.replay`) writes `W` at frame 14690 and the very
next input line is `I 14690 80`: Genesis START (0x80), which the owner never
pressed for the game. `input_set_gameplay_blocked(0)` ran on the frame Enter
closed the menu, and `SDL_GetKeyboardState` still reported Enter (= START).

Fix: engine patch 0022 latches every button and pad button held at the moment
gameplay capture ends and suppresses it until released.

Cause 2 — the only feedback was the window title, invisible in fullscreen and
on a Deck. Engine patch 0023 draws a 2.5 s notice at the top-left of the
presented picture (`STATE SAVED TO SLOT N`, `STATE LOADED FROM SLOT N`,
`SAVING STATE...`, `SAVE UNAVAILABLE HERE`, `LOAD REJECTED...`), using the
in-game menu's own 5x7 glyph cell and its light text colour over a dim panel.
It is presentation only: the guest framebuffer, `--hash-frames`, replays and
the normal `screenshot` capture are unchanged; `screenshot` with
`"presented":1` captures the composited window.

Evidence (`tools/tg2_state_notice_probe.py`, dev build, TCP-driven real menu):

| Check | Before 0022 | After 0022 + 0023 |
|---|---|---|
| pad mask on the frame Enter closed the menu (`pad`) | 128 (START) | 0 |
| pad mask on the frame the pad's A closed the menu (virtual controller) | 16 (B) | 0 |
| state written by the menu save row in a race | yes (see note) | yes, `native_save_1.bin`, 165 523 B |
| notice in the presented picture | none (title only) | `docs/images/state-notice-4x3-save.png`, `docs/images/state-notice-4x3-load.png` (full set in `build/evidence/state-notice/final-4x3/`) |
| same notice, 16:9 | — | `docs/images/state-notice-16x9-save.png`, `docs/images/state-notice-16x9-load.png` (full set in `build/evidence/state-notice/final-16x9/`) |
| notice absent from the guest frame | — | `final-4x3/save-guest.png` (256x200, no overlay) |
| save refused on a screen with no boundary (password entry) | title only | `SAVE UNAVAILABLE HERE` (`final-4x3/refusal.png`) |
| load of an empty slot | title only | `LOAD REJECTED: SLOT 1` (`final-4x3/load-rejected.png`) |
| Off-mode frame 60 / 300 | — | `2A0B972960C5E325` / `1131D937D70234FD` (unchanged) |
| manifests (`tools/tg2_runner.manifest_counts`) | — | 0 / 0 / 0 / 0 |

Note: the leaked START does reach the race, but on this build the game's PAUSE
screen still runs the race loop's boundary (`$65F2`), so a save requested while
paused does complete. The refusal *is* reproducible on a screen without a
resume site (password entry), and the owner's no-file session is consistent
with that refusal path; the notice now makes any such outcome visible instead
of silent.

## Quickstate lost between races (owner report, 2026-11-07)

The owner finished race 3, saved to slot 1 at the start of race 4 through the
in-game menu, and later loaded slot 1 to find the old race-3 state: the save was
never written (`native_save_1.bin` kept its 17:10 mtime). The feedback replay
(`save-lost-r4/TG2-feedback.replay`) shows `W` at frame 20130 with a zero pad
(the menu-dismiss input leak of patch 0022 is fixed), nine START taps between
frames 19558 and 19905 after the finish, and two more START taps after the save
before race 4 starts. That places the save on one of the **inter-race flow
screens** (race results, championship table, car/gear setup, next-track intro,
shop). Those screens have no repeatable instruction the host can resume in
place, so `glue_state_boundary` never parked and the queued save was dropped
after the engine's 120-frame timeout; the only feedback was the window title.

Measured with `tools/tg2_postrace_save_probe.py` (finishes a race, then saves on
every screen of the flow):

| Screen | Before | After patch 0024 |
|---|---|---|
| race (running) | written | written |
| finish banner | written | written |
| race results | **refused** | queued, written at the next race start |
| championship table | **refused** | queued, written at the next race start |
| car/gear setup | **refused** | queued, written at the next race start |
| next-track intro | **refused** | queued, written at the next race start |
| shop (gears) | **refused** | queued, written at the next race start |
| next race countdown | — | written |
| race 2 (running) | written | written |

Adding the screens' own one-frame waits as boundaries was tried first and
rejected: the saves land, but a load of such a state bails out of the race flow
to the main menu. The screens' loops are reached by dispatch rather than a
JSR/BSR chain, so after the resumed loop returns the engine cannot follow the
guest callers (`floor_unsafe`: `$001E6A ... capsule exit_pc != native loose-A7
return`); the resumed intro panel returns to the title menu
(`build/evidence/resume-5/loadcheck2/step1.png`). A quickstate that misbehaves
on load is worse than a visible refusal, so the sites were not kept.

On the owner's build (patches 0022+0023, before 0024) the refusal *was* drawn
in the picture: `SAVING STATE...` immediately, then `SAVE UNAVAILABLE HERE` two
seconds later (`docs/images/state-notice-refusal-owner-build.png`, reproduced on
the pre-0024 binary by asking for a save on the password screen). The save was
still lost, which is what this report fixes.

Patch 0024 instead keeps the request queued for up to 15 s of gameplay and
takes it at the next boundary the game actually reaches. Pressing START to
begin the next race parks it at the race loop, so the file holds the start of
that race — the moment the menu row already promises ("the next completed
gameplay tick") and what a player saving between races wants. The queue is
visible as `SAVING AT NEXT BOUNDARY...` (`docs/images/state-notice-interrace-save.png`);
if no boundary appears the request is refused with `SAVE UNAVAILABLE HERE`. A
later save request replaces the queued one, and a save whose temporary file
cannot be opened now reports `SAVE FAILED: CANNOT WRITE STATE` instead of being
dropped in silence.

Loading such a file resumes the race and it runs to its end
(`tools/tg2_postrace_resume_probe.py --until-countdown`): the saved state is
parked at `$0065F2` (race loop), and in a fresh process it completes five laps
and the finish (`build/evidence/resume-countdown/summary.json`,
`docs/images/state-notice-interrace-resume.png`).

## Task 26 merged after v0.1.0 (2026-11-09)

The task 26 fixes (`origin/vittau/tg2-playtest-fix`, 2026-11-07) were never
merged, so v0.1.0 shipped without them. Merged into `main` on 2026-11-09 after
the checks below, on macOS arm64 (dev build `tools/build-linux.sh`, dummy
video/audio, one runtime at a time). The owner-settings runs use a copy of the
owner's installed macOS `settings.ini` (RACE SOUND = BOTH, HUD edges, 60 fps,
Adaptive widescreen), since the original Linux session directory is not on
this machine.

| Check | `main` before the merge | Merged branch |
|---|---|---|
| `tools/verify_sound_page.py` (open, cycle, re-open the RACE SOUND page in every mode; fresh dir and owner settings) | **fail**: with BOTH the first open is black (palette 3 black on all five visit-0 pictures), later BOTH opens differ from each other, and the MUSIC/SFX pages differ from stock | **pass**: every picture has text and palette 3; MUSIC/SFX pixel-identical to stock, every BOTH open identical |
| Player map at startup, fresh directory | P2 off (`device = 0`) | `p2=keyboard+gamepad` (patch 0020) |
| Player map with a saved `settings.ini` whose P2 is `device = 0` | P2 off | P2 off (the saved device wins) |
| `[DUAL-DBG]` string in the binary | present | absent |
| Off-mode hashes (`tools/probe_run.py --widescreen off --frames 360`) | — | frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD` (unchanged) |
| `tools/tg2_release_smoke.py` (decoy-named ROM, controller-only boot to a 1P race) | — | passed, race pictures captured |
| Manifests (every run above) | — | 0 / 0 / 0 / 0 |

Not re-checked here: the feedback-replay divergence fix (`tg2_options.c`,
a recorded BOTH no longer collapses to MUSIC on replay), which needs the
owner's replay file from the original session.

## Task 31 — high-resolution rendering S1/S2 (branch `vittau/tg2-highres-s1-s2`)

Steps S1 (compact per-row capture + render-scale skeleton) and S2 (engine seam
for a taller presented picture, patch 0033) from `docs/HIGHRES.md` §8. Scale
default 1; `TG2_HIGHRES_SCALE` is the capture-only override and the temporary
S2 test provider needs `TG2_HIGHRES_TEST_PROVIDER=1`. All runs on this Mac
(macOS arm64, development build from `tools/build-linux.sh`), dummy video and
audio, one runtime instance at a time; the only windowed run is the last row.

| Check | Command | Result |
|---|---|---|
| G1, scale 1 and scale 2 (builder stub), `off` | `python3 tools/check_highres.py g1` | frames 60/300 `2A0B972960C5E325` / `1131D937D70234FD`; the whole 60..360 series identical between scales |
| G1, `16:9`, scale 1 vs 2 | same | whole hash series identical (the 16:9 boot canvas has its own hashes, as `docs/FRAMERATE.md` already notes) |
| G1, 60 fps on, scale 1 vs 2 | same | both canonical hashes retained |
| G1, test provider enabled on menus | same | identical to stock; the provider declines non-race pictures |
| G2, all four manifests | every run above | 0 / 0 / 0 / 0 |
| S1 capture vs live rows | `python3 tools/check_highres.py capture` | 3 pictures, 203 fresh rows each, 0 mismatches; 51–74 road rows; 34–42 µs/picture, 168–209 ns/row (two sessions) |
| S1/S2 byte identity across a race | `python3 tools/check_highres.py route` | scale 1 vs scale 2 (builder stub): identical framebuffer hash on every sampled frame of the 5600-frame baseline route, `off` and `16:9`, manifests empty |
| S2 test picture, `off` / `16:9` | `python3 tools/check_highres.py s2` | 256×400 and 712×400 (1× is 256×200 / 356×200); scale 2 with no builder is pixel-identical to 1×; menus keep the stock canvas and are byte-identical (title digest; 320×224 off, 398×224 in 16:9) and the password screen stays 256×224 |
| S2 2P split-screen stays native | `python3 tools/check_highres.py split` | `$FF189E != 0` on 3,185 sampled frames; geometry 224 lines × 398 wide throughout; all 7,901 framebuffer hashes identical with the test provider off and on; manifests empty |
| S2 windowed | `python3 tools/check_highres.py s2 --windowed --only 169-scale2-test` | cocoa window presents the 2× picture; captured, then closed |
| G3 stock widescreen | `python3 tools/verify_widescreen.py` | passes in off / 16:9 / 21:9 at scale 1 |

Evidence: `build/highres-check/` (summaries, per-row samples, PNGs) and
`build/ws/`. Not verified: any real N× geometry (S3), a 2P race at N×, an
interlaced picture (unreachable in this game), Deck-class cost.

## Task 32 — device aspect and quiet logs (2026-11-09)

Two pieces of Steam Deck feedback: the picture was 16:9 on the Deck's 16:10
panel, and a normal session left ~1.4 MB in `logs/`. Engine patches 0045–0049.
All runs on this Mac (macOS arm64, development build from
`tools/build-linux.sh`, SDL dummy video/audio unless a row says "cocoa"), one
runtime instance at a time, under the shared build lock. Evidence under
`build/evidence/task32/` (gitignored).

| Check | Command | Result |
|---|---|---|
| Off-mode hashes unchanged | `python3 tools/probe_run.py --widescreen off --frames 360 --port 4440` | frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`; `w=320 h=224` |
| All four manifests empty (dev build) | every run here | 0 / 0 / 0 / 0 |
| Adaptive, 16:10 output 1280×800 | `python3 tools/tg2_aspect_probe.py --race --port 4454` (`video_configure`) | output 1280×800 (1.600) → picture 320×200 (1.600): fills the panel; presented capture 1280×800 |
| Adaptive, 16:9 output 1280×720 | same | output 1280×720 (1.778) → picture 356×200 (1.780) |
| Adaptive, 4:3 output 1024×768 | same | output 1024×768 (1.333) → picture 320×200 (1.600): SDL letterboxes; the 320-pixel minimum is unchanged |
| Fixed 16:9 on the same three outputs | same | picture 356×200 in every case, letterboxed inside 16:10 and 4:3 as chosen |
| Adaptive, title screen vs race picture (dummy) | `build/evidence/task32/aspect-dummy-title.json`, `aspect-dummy-race.json` | title 358×224 / 398×224 / 320×224 (fit, 16:10 / 16:9 / 4:3); race 320×200 / 356×200 / 320×200 |
| Windowed start on a real 16:10 panel (cocoa) | `SDL_AUDIODRIVER=dummy build/TG2Recomp … --widescreen fit --max-frames 90 --turbo` | display 1408×881 (1.598) → window 716×448 (1.598, adaptive, windowed) → output 716×448, picture 358×224 (1.598) |
| Borderless fullscreen, Adaptive (cocoa) | same with `fullscreen = 1` in settings.ini, 150 frames | output 1408×881 (1.598) → picture 358×224 (1.598) (3 of 4 runs; one run caught macOS's menu-bar-strip transition at 1408×818, and the picture followed it at 386×224, 1.723) |
| Borderless fullscreen, fixed 16:9 (cocoa) | same with `--widescreen 16:9` | output 1408×881 (1.598) → picture 398×224 (1.777): letterbox bars top/bottom |
| Gamescope session detection (dummy) | `SteamDeck=1 SDL_VIDEODRIVER=dummy … --widescreen fit` | `[VIDEO] gamescope/Steam Deck session: starting borderless fullscreen`; window 597×448 (dummy's 1024×768 desktop, adaptive) and output = the whole desktop; on the Deck's 1280×800 output the same code gives a 320×200 picture |
| Release-profile session writes nothing | `build-rel/TG2Recomp --no-launcher --max-frames 300` (release profile: `GEN_ENABLE_TRACE=OFF`, `SONIC_REVERSE_DEBUG=OFF`), ROM beside the exe under a decoy name | exit 0; directory diff before/after: **no files created or changed** — no `logs/`, no `.toml`, no `settings.ini` |
| Release-profile with `--debug` | same with `--debug` | `logs/TG2-feedback.replay` + `.config.ini` + `.mods.txt` + `.sav` and the four manifests, nothing else |
| Old settings.ini migrates to off | release profile, `[mods.diagnostics] enabled = 1`, no `[meta]` | `[config] migrating settings.ini: diagnostics are now opt-in`; file rewritten with `[meta] settings_version = 2` and `[mods.diagnostics] enabled = 0`; no `logs/` |
| Esc-menu toggle (real runtime menu, dev build) | `key`/`ui_open`/`ui_rows` probes on `Mods` | row `Diagnostics (bug report)` Off → On; closing the menu saved `settings_version = 2`, `enabled = 1`; the next launch without `--debug` wrote `logs/TG2-feedback.replay` |
| Release smoke | `python3 tools/tg2_release_smoke.py --exe build-rel/TG2Recomp --work build/qual/release-smoke` | `passed: true`, exit 0, route loaded, five race pictures (356×200 / 398×224, 15–96 % non-black); no `logs/` in the run directory |

File audit, release profile, normal session: **nothing** beyond the executable
and the ROM. Created only on demand or failure: `settings.ini` (first save from
the launcher/menu, or the one-time migration), `native_save_N.bin` (quickstate
the player saves), `crash-report`/`last_error.log` (only when the game actually
crashes), and — with diagnostics on — `logs/TG2-feedback.replay*` plus the four
evidence `.toml` files.

Not verified here: a real Steam Deck / gamescope session (window size, panel
mode, scaled output), the Deck's 1280×800 panel through an actual compositor,
and controller-only operation of the new Diagnostics row on the device.

## Task 33 — high-resolution rendering S3 (branch `vittau/tg2-highres-s3`)

**S3 complete:** implementation and local technical qualification passed, and
the owner approved the straight, curve, hill, rain and tunnel visual comparisons
on 2026-11-10 ("Está ótimo"). No release or merge into main was performed.

Merged-state requalification on macOS arm64 (Apple A18 Pro, 8 GiB), trace
development build, SDL dummy video/audio, one runtime at a time, all builds
and heavy checks under `flock ~/.cache/tg2-heavy.lock`, builds at `JOBS=3`.
The real-launcher test uses a hidden cocoa window; it restores settings.

The atlas-run renderer fits continuous road bands within 1.5 native pixels
and analytically covers road, border and lane boundaries. Sprites, HUD, sky
and plane-A effects retain integer-N× nearest content. Internal resolution
offers experimental 1×–4×, defaults to 1× and applies next launch.

Review fixes: keep row/picture serials at the same width (the 16-bit row tag
disabled smoothing after 65,535 pictures), cap 3× at 4095 whole output
columns, keep Off at the actual H32 256×N width,
keep wide native menus/2P out of N× expansion, correct wrapped option
navigation, compare actual 1× versus 4× in 2P, fail
missing manifests, and measure stripe centres from final pixels while
distinguishing white border/stripe palette collisions. Patch 0050 correctly
leaves `choice_values` NULL: the Esc callbacks map indices 0–3 to scales 1–4;
the launcher receives the actual scale values.

| Check | Command / evidence | Result |
|---|---|---|
| Patch reset + build | `tools/apply-engine-patches.sh --reset`; `JOBS=3 flock ~/.cache/tg2-heavy.lock tools/build-linux.sh ~/roms/genesis/tg2.bin build` | exit 0, upstream submodule pins unchanged |
| G1, Off/1× and 60 fps boot | `tools/check_highres.py g1` | exit 0; frames 60/300 `2A0B972960C5E325` / `1131D937D70234FD` |
| G2 | four manifests after every qualification runtime | 0 / 0 / 0 / 0, absent manifests fail |
| G3, 1× widescreen | `tools/verify_widescreen.py` | exit 0; Off/16:9/21:9, RAM/VRAM/native centre identical at 600/1350/2800/3300/4501 |
| G3, 1× 60 fps | `tools/probe_framerate.py` Off and `--60fps`, then `tools/compare_framerate.py` | exits 0; 186/360 stock versus 360/360 changed pictures, no scalar RAM mismatches, identical WAV SHA-256 |
| Exact-frame downscale, 1×–4× | `tools/check_highres.py s3` | exit 0; max mean 0.316/255, at most 0.060% of pixels >64; mean tolerance 2.5, fraction tolerance 2% |
| N× road + margins, Auckland 2× | `tools/check_highres.py drive --scale 2 --frames 3200` | exit 0; 3,638 pictures / 451,686 output road rows, 51,150 stripe rows, centre error ≤0.500 output px; all violations 0 |
| N× road + margins, Auckland 3× | `tools/check_highres.py drive --scale 3 --frames 3200` | exit 0; 3,641 pictures / 690,066 output road rows, 86,467 stripe rows, centre error ≤0.496 output px; all violations 0 |
| N× road + margins, Auckland 4× | `tools/check_highres.py drive --scale 4 --frames 3200` | exit 0; 3,641 pictures / 911,412 output road rows, 119,389 stripe rows, centre error ≤0.496 output px; all violations 0 |
| Moving straight/curve/hill captures, bavaria-rain, 2×/3×/4× | `tools/check_highres.py drive --track bavaria-rain --scale N --frames 1500 --min-frames 1000` | exits 0; 1,939–1,946 pictures per scale; road, stripe-centre and margin violations 0; paired native/N× downscale passes |
| Moving straight/curve/hill captures, canada, 2×/3×/4× | `tools/check_highres.py drive --track canada --scale N --frames 1500 --min-frames 1000` | exits 0; 1,939–1,948 pictures per scale; road, stripe-centre and margin violations 0; paired native/N× downscale passes |
| Options, Esc | `tools/check_highres.py option` | exit 0; settings 1/2/3/4 report the same scale, invalid 8 → 1×; real Esc row cycles to 4× and persists it |
| Options, launcher | `tools/check_highres.py launcher` | exit 0; real hidden launcher persists 2→3→4→1, labels and experimental note captured |
| 2P stays native, menus unchanged | `tools/check_highres.py split`; G1 + widescreen captures | exit 0; 7,902 exact 1×/4× hashes, always 398×224, including the menu flow |
| Wide native menus/2P, 32:9, 1× versus 2× | `build/s3-wide-menu-after/summary.json`; `build/s3-wide-2p/split2p/split-summary.json` | exits 0; menu hashes identical (four differed before the fix), 7,901 2P/menu hash pairs identical, always 796×224 |
| 3× adaptive width cap and mode changes | `tools/check_highres.py cap` | exit 0; extreme adaptive canvas 4095×600, Off 768×600, fixed 16:9 1068×600; paired Off downscale mean 0.411, 0.107% pixels >64 |
| Long-session freshness | `tools/check_highres_serial.py` | exit 0 through 131,074 captures and reset; the same fixture rejects the inherited implementation with expected SIGABRT (-6) |

| Scale | Builder µs / frame, without audit | Full CPU work µs / frame, mean / p95 |
|---|---:|---:|
| 2× | 802.6 | 7478.8 / 9092 (910 sampled frames) |
| 3× | 1067.1 | 7642.6 / 10216 (910 sampled frames) |
| 4× | 1396.0 | 7072.8 / 8787 (910 sampled frames) |

Cost command: `tools/check_highres.py drive --scale N --frames 900
--shot-every 10000 --no-audit`. These runs use realtime audio and record all
thread-CPU phases; full CPU work subtracts only the pacer CPU wait. Neither
SDL/vsync blocking time nor audit/dump work is presented as rendering cost.
Whole-frame values include variable guest work from separate closed-loop
runs; isolated builder timings provide the comparison of S3 scale cost.

Evidence: `build/s3-reverify/final-summary.json` and its command/qualification
logs; per-track `drive-summary.json`, `trace.json`, paired PNG/PPM captures;
`s3/s3-summary.json`, `ws/summary.json`, `fps/comparison.json`, option/launcher
summaries and hidden-launcher PNGs. The raw `.nxroad` and large margin CSVs
were removed after their verdicts, as required by the resource rules.

Curated comparisons inspected: `docs/images/highres-straight.png`,
`highres-curve.png`, `highres-hill.png`, `highres-rain.png`,
`highres-tunnel.png`. Both halves were verified byte-for-byte against the
same-frame 1× canvas and 2× capture; provenance and frames are in HIGHRES §13.3.
Auckland supplies the tunnel case; Bavaria supplies rain and Canada a distinct
winter atlas. No gaps, fan duplicates or striped tearing were seen in the
reviewed examples; the automated checks cover the longer sequences above.

Initial centre-audit trials failed for incomplete palette classification:
white borders and winter snow shared the lane colour. The framerate comparer
also required a streaming SHA-256 compatible with Python 3.9. Targeted tests
then exposed real wide-native and Off-width defects; both were fixed and
rerun to exit 0. Earlier failure logs and command histories remain under
`build/s3-reverify/`. Valid 1× and 16:9 race checks were retained when later
changes affected only audit measurement or separately tested native-width
paths.

The coordinator relayed the owner's reduced validation strategy after the
existing matrix completed: keep valid results, use short directed checks per
scale and one long audit at the largest effective scale, and cover weather/
tunnel at one scale unless a scale-specific defect appears. The tables above
state the coverage actually produced, including the earlier long Auckland
2×/3×/4× runs; no further long matrix was repeated. HIGHRES §13.4 gives the
reduced reproduction pattern. Moving paired downscales across the nine runs
had maximum mean error 0.426 and maximum fraction >64 of 0.112%.

Not verified: GPU/Steam Deck/release cost, full N× + 60 fps composition (S6),
live switching (S7), or NTSC exclusion (option not yet implemented). Tunnel-opening artwork and detailed weather sampling are
plane-A composition in S5; the S3 nearest plane-A path and margins are tested.
The colour terrain mask can confuse an overlay pixel matching its underlying
plane-B colour; S4/S5 need explicit coverage masks. See HIGHRES §13.5.

The S3 worker made no CI, tag, release, audio implementation change or main
merge during qualification. After the owner's visual approval, the coordinator
merged S3 and built the Linux draft below.

## S3 merge and Steam Deck draft (2026-11-10)

Owner-approved S3 was merged into `main` as
`a2057597b29de1542a0dbc8d21a7aed9a80c918e`. The only merge conflict was the
HIGHRES documentation's S3 completion line; the approved high-resolution
implementation and patches were retained. The existing main audio-option
removals were retained too.

Coordinator command `gh workflow run build.yml --ref main -f platforms=linux
-f dry_run=false` exited 0 and created
[run 42842299392](https://github.com/vittau/top-gear-2-genesis-pc/actions/runs/42842299392).
Linux and independent Linux verification both succeeded; Windows/macOS and
the full-matrix release job were skipped. Tarball/AppImage content checks
passed; both downloaded payloads need glibc 2.34 (≤2.35 gate) and smoke-ran
600 frames with the ROM auto-detected, exit 0, no true dispatch misses.

`gh run download`, local streamed checksum comparison and
`tools/release/verify_artifact.py` all exited 0. BUILD-INFO identifies game
`a205759`, engine `dd520f1f975a`, version `0.1.0-ga205759`, Release profile,
TCP and reverse-debug disabled. The tarball SHA-256 is
`37ae02c929a223ad6300a1d7243f196864a902f390b1415a9006347ab6434618`;
AppImage is `e5ea30e405cd798869a34f467a5f2cbf9fa7832b91f1e15d653a5ef33945e825`.

`gh release create deck-s3-20261110 --draft --prerelease --latest=false
--target a2057597b29de1542a0dbc8d21a7aed9a80c918e` (with the tarball,
AppImage, SHA256SUMS and handwritten notes) exited 0. A subsequent metadata
read confirmed all three uploaded assets/digests, the exact source target,
and `isDraft=true`. [Draft URL](https://github.com/vittau/top-gear-2-genesis-pc/releases/tag/untagged-fb40acbd6ff0b4a9d90d).
No `v*` tag or published release was created.

The owner clarified he uses the **extracted tar.gz** on his Deck. This
draft's real-device result is still pending; CI does not establish Deck GPU,
gamepad or pacing behaviour. See CONTINUATION.md for the next coordinator.

## Tasks 35/36 — S3 native-art Linear Filter and runtime menu groups

Worker branch `vittau/tg2-linear-filter-s3`, current-main base, pinned SDL2
2.28.5 and hidden Cocoa/Metal. Investigation proved a correct 1:1 final sampler
at 4× / 1280×800; the coordinator then approved game-owned native RGB filtering
with the existing On toggle. Off retains 55/55 pre-fix samples at both 2×/4×.
The fixed 4× final race changes 124,690 pixels while all 256,928 uncovered road
pixels remain exact; real in-race toggle output matches saved On. 2× and
fractional 4× keep identical same-frame guest RAM. Stock hashes remain
`60=2A0B972960C5E325`, `300=1131D937D70234FD`, all four manifests empty.

Directed Auckland/rain/60-fps underlay and margin audits cover 4,027 pictures
and 1,016,488 measured sub-rows, zero violations, worst stripe centre 0.4961
pixel. The 2P 32:9 pair retains all 4,500 hashes at 796×224. No full S3 matrix
was repeated. The old unfiltered-reference check and a local poller shutdown
race are documented with their valid retained evidence, not reported as clean
script exits. See [Linear Filter](LINEAR_FILTER.md) for exact scope and limits.

Runtime UI has exactly VIDEO, AUDIO, SYSTEM, MODS, SAVE STATES in that order;
all 20 original rows remain, visited with an SDL virtual controller at 1280×800.
Filter/scale/Music/SFX changes save and reopen correctly. Details and captures:
[RUNTIME_MENU.md](RUNTIME_MENU.md), `build/linear-s3/menu-after/`. Local evidence
is qualified; new Deck candidate and owner acceptance remain coordinator work.
No workflow, tag, release or old draft source identity was changed.

### Portable applicator and no-pacing cost follow-up

The Python Windows path now routes `ui-*` correctly and shares the idempotence
stamp with the shell twin. Real sequential application of 43 patches on pristine
pinned fixture clones, second application, relative `--repo`, and shell/Python
stamp interoperability all pass (exit 0); pins unchanged, no Windows CI run.

One 4× / 1280×800 paired no-audit/no-dump run samples the same baseline route
and 360 CPU frames (3000–3359). Mean CPU is Off 1.882 ms / On 6.392 ms
(**+4.511 ms**); composition+crop CPU adds 4.367 ms. Patch 0053 prevents the
profiling-only uncapped mode from restoring simulated software VSync. Sampled
pacer waits are all zero, both probes exit 0, all manifests empty. A final stock
smoke retains the two canonical hashes. Method, auxiliary builder wall timing,
startup/polling limitations and device-performance boundaries are documented
in [LINEAR_FILTER.md](LINEAR_FILTER.md#follow-up-portable-patch-application-and-isolated-local-cost).


## Deck follow-up merge and draft: Linear Filter + menu (2026-11-10)

Coordinator reviewed the worker's presentation/menu evidence and requested
portable patch-application and no-pacing CPU-cost follow-ups; both passed
(185660b/8a6936e). Actual Windows execution is not claimed. Filter/menu work
was merged in `87e926b12db46a6f4aec7326d14ab470b1a4875f`.

Manual Linux-only [CI 42898689826](https://github.com/vittau/top-gear-2-genesis-pc/actions/runs/42898689826)
passed build and independent downloaded-artifact verification. Tarball and
AppImage content gates passed, required glibc is 2.34 (≤2.35), and each ran
600 frames with ROM discovery and exit 0. Windows/macOS were skipped.
`gh run download`, streamed checksum comparison and local verify_artifact.py
also exited 0; BUILD-INFO identifies version `0.1.0-g87e926b` and exact game
revision, unchanged engine pin, Release profile, TCP/reverse-debug disabled.

[Draft deck-filter-menu-20261110](https://github.com/vittau/top-gear-2-genesis-pc/releases/tag/untagged-250db4e89d9b27e23c8f)
was created with tar.gz, AppImage and SHA256SUMS; metadata confirms draft +
prerelease, exact source target and all three assets uploaded. Tarball SHA-256:
`5fe2a14e2f952fd1d50990f353734c1a2a0dcf92f595be65b117a5172954ee56`;
AppImage: `91bc3f3f4dde4bfd73bb2453494b79ece822df57a22e22390af36373b0339bae`.
The previous draft remains unchanged; no v* tag or published release was made.

This is a new source-labelled candidate for the owner's extracted-folder Deck
installation. Local Off/On CPU means at 4×1280×800 were 1.882/6.392 ms
(+4.511 ms, short controlled dev-build sample); no Deck performance or new
owner visual acceptance is claimed. The target retest covers filter effect
in races, frame pacing/audio, menu VIDEO/AUDIO/SYSTEM/MODS/SAVE STATES, and
saved preferences. S4 remains unstarted.


## Owner local acceptance: filter and menus

The owner manually tested the current macOS binary containing the merged
filter/menu changes and said “Está tudo certo.” This approves tasks 35/36
locally; it does not supply performance measurements for the latest Linux
binary on the Deck. After the manual session closed, the worker build's four
execution manifests were checked and each had 0 entries.

He separately reported intermittent missing instruments in race-menu music,
then explicitly asked to save the filter/menu work and defer the instrument
question to another session. Task 37 records the report and known revision/
configuration facts without asserting a diagnosis. No audio code was changed
or new audio runtime/capture/worker started in response.

## Task 37 — missing instruments in race-menu music (2026-11-10)

Report reproduced and root-caused: with `[mods.racesound] mode = both` in
`settings.ini`, `z80_route()` diverted the four Z80 bytes `$A0025E..$A00261` to
the second core during the *boot* music-driver upload. Those offsets are also
entries `$37..$3A` of the driver's note → octave table at `$0227` (octave 4,
G..A♯), so those four note indices played four octaves low — the line vanished.
See [AUDIO.md](AUDIO.md#the-command-ports-and-the-music-drivers-block-table-task-37)
for the tables, Z80 disassembly and the mechanism.

Fix (`game/tg2_audio_both.c`): the command ports are routed only while the
second core actually holds the race SFX image (its `C3 10 04` entry, read from
guest state), so the boot upload, a cold reset and a quickstate load all land on
the first core unless a race has uploaded its own image.

Evidence, all headless (SDL dummy, one runtime at a time, controller/input-script
only apart from one labelled diagnostic RAM poke), fixed build on Linux:

| Check | Result |
|---|---|
| First-core Z80 RAM `$25E..$261` after persisted-BOTH boot | `20 20 20 20` (= ROM/MUSIC/SFX); was `00 00 00 00` |
| Second core at boot | 0 non-zero bytes; was the four `$20` bytes |
| chip A vs MUSIC, title / main menu / 1P setup / track intro / shop | corr **1.000000**, max sample difference **0** (was 0.973–0.997) |
| chip A vs MUSIC, race 2000–4500 | 0.995298 (was 0.988310); note stream identical |
| note-write register diff vs MUSIC | 0 pitch differences (was 24: `$A5=$04` vs `$24`, note `$37`, FM ch 2) |
| `GENESIS_AUDIO_SFXPCM_TRACE` BOTH vs SOUND EFFECTS, throttle route | byte-identical, 465 commands |
| chip B (BOTH) vs SOUND EFFECTS, race | 0.999980, RMS 1459.0 both (engine/nitro audible on chip B) |
| Stock MUSIC / SFX whole-run WAV MD5 vs a `main` d57cffa build | `117d0e45…bdb6` / `e55d0e0b…1e3b`, identical |
| Frame hashes every 60 frames (stock modes) | 66 lines each, `diff` empty; frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD` |
| Manifests over every capture (8 runs) | 0 / 0 / 0 / 0 |

Regression test: `tools/verify_both_driver_image.py` (exit 0 on the fixed
build). Not verified: the owner listening to the fixed build, Deck audio, and a
quickstate saved in an affected session, which keeps the corrupted driver bytes
until the next boot re-uploads the driver.

Post-fix re-run of the existing boot regression: `tools/verify_both_boot.py`
reports BOTH vs MUSIC, BOTH vs SFX and MUSIC vs SFX all **1.000000** on its
400–900 window (the same window that recorded 0.995227 before), exit 0. A
mid-race BOTH quickstate saved at frame 3004 and loaded back in the same process
keeps the driver table equal to ROM and keeps issuing SFX commands (174 before
the save, 610 after the load), so the command-port predicate agrees with the
machine image after a state load. A cold reset restores the pre-boot machine
(both cores' RAM zeroed), which the predicate treats as "no image resident"; a
second race re-runs the same `$0700C8` upload that was verified here.

## Deck draft: race-menu music fix (task 37, 2026-11-10)

Owner-approved task 37 was merged into `main` (`f540b21`, docs `8f2bd53`).
Coordinator command `gh workflow run build.yml --ref main -f platforms=linux
-f dry_run=false` exited 0 and created
[run 42911855879](https://github.com/vittau/top-gear-2-genesis-pc/actions/runs/42911855879):
Linux build and independent Linux verification succeeded (payload gate PASS,
highest glibc symbol 2.34 ≤ 2.35, 600-frame headless smoke with ROM discovery);
Windows/macOS and the release job were skipped. `gh run download`, local
checksum check and `tools/release/verify_artifact.py` exited 0. BUILD-INFO:
version `0.1.0-g8f2bd53`, game `8f2bd53`, engine `dd520f1f975a`, Release, TCP
and reverse-debug disabled.

[Draft deck-instruments-20261110](https://github.com/vittau/top-gear-2-genesis-pc/releases/tag/untagged-8c70f39421b827e442b5)
(draft + prerelease, target `8f2bd53`) carries only the tarball the owner uses
on the Deck plus `SHA256SUMS`. Tarball SHA-256:
`03d41406b7907911e0e404787dec96dbb7c699e8292ad10900d782cc5e2a93a2`.
No `v*` tag or published release was created; earlier drafts are unchanged.
Deck listening of the fix is pending.


## Task 34 — detailed sprites at N× (S4, 2026-11-11)

Implemented and locally qualified on `vittau/tg2-highres-s4`; **owner visual
acceptance pending**. Development host: macOS arm64, SDL dummy headless,
shared heavy lock, max 3 build jobs, one runtime at a time. No CI, tags,
releases, engine/pin changes or ROM-derived git artifacts. Implementation and
selection/coverage details: HIGHRES §§14.3–14.7.

| Check / command family (all prefixed by the shared `flock`) | Exit / evidence |
|---|---|
| `env JOBS=3 tools/build-linux.sh` | 0; `build/s4/build-boundaries.log` |
| `check_highres.py g1 --out build/s4/last-gates` | 0; 9 configs; Off `60=2A0B972960C5E325`, `300=1131D937D70234FD` |
| `verify_widescreen.py --out build/s4/g3-ws-qualified`, scale 1 / 60 fps Off | 0; Off/16:9/21:9, 5,600 frames each; canonical RAM/centre identical at all five frames; real margin sprites and adaptive widths pass |
| `probe_framerate.py` / `--60fps`, `compare_framerate.py` | 0/0/0; 186 vs 360 changed pictures; 0 sampled RAM-field mismatches; identical WAV SHA-256 `c5c5d9ced414d61e25220853fd3c7d93756d12bdd5036b46fd16240471a3962a` |
| `check_highres.py split --mode 32:9 --scale 4` | 0; native 2P geometry/hash sequence identical |
| `check_highres.py cap` | 0; native menus, capped 3×, Off/fixed-aspect transitions |
| Final Auckland 4× `drive --actors --frames 3200` | Runtime 0; road/margin/actor gates pass; original tool 1 was only the independent-box false positive described below; same-pixel corrected `sprite-pairs` recheck 0 |
| Canada 3× / 1,800 frames; Bavaria rain 4× / 900 | 0/0; final drive, road/margin/actor gates and pair rechecks pass |
| Directed Auckland tunnel 2× / 2,000 frames | 0; actual tunnel/road plus near opponent case captured |
| Linear On 2× / 300; combined 60-fps 2× / 180 | 0/0; corresponding reference filtering, strict position and row-replay gates pass |
| Stepped/continuous review pair | 0; same frame 221, identical guest RAM SHA-256 `b433c123c7612b0138bd1e9c368b693a41c4b0c16b83fcbef0268d20f4f3f88f` |

All four execution manifests have 0 entries in every qualified run.
The largest-scale long audit measured 3,301 pictures / 812,488 road rows /
161,582 stripe centres, maximum centre error 0.5 output pixel, zero road or
margin violations. Other scales use directed checks, not another full matrix.
The long audit was repeated only while fixing actual culling/reference
bookkeeping defects; the final photometric-check correction reused captures.

| Track | Promoted actors (every frame) | Untabulated/model fallbacks | Native final-SAT guards | Fully guest-culled kept native |
|---|---:|---:|---:|---:|
| Auckland | 52,156 | 0 | 14 | 13,516 |
| Canada | 25,077 | 0 | 6 | 5,264 |
| Bavaria rain | 11,852 | 0 | 15 | 1,257 |

Across 89,085 promoted actors: max floor error 0; independent guest-piece,
palette and priority mismatches 0; analytic drawn-anchor error 0, ≤2.1e-8
output pixel after JSON serialization. The native-row opacity/index/priority
replay audit has 0 mismatches. Sampled native-pole overlap exercises both
orders: Canada 520 output pixels blocked / 604 painted in front; rain 570 /
233. Fully culled actors are not resurrected by larger artwork.

The old S3 whole-image limit rejected a snowy-tree Canada picture (mean
3.211/255) despite the expected internal snow-detail change. S4 preserves the
original global and individual patch numbers, checks unchanged pixels with
the same S3 limits, and bounds padded connected silhouette/occlusion groups
by distance (64/80/96 maximum-channel mean, strictest member for overlaps).
The original 4× checker also assigned a nearby car's detail to a far sign's
box: individual patch 114.25, but combined visible group ≤52.9121. Its sole
failure is resolved by `sprite-pairs` on the exact same 25 pairs (exit 0), not
by hiding a picture or relaxing the unchanged-region tolerance. Final Canada
group mean ≤56.0711; unchanged-pixel mean ≤0.3066. HIGHRES §14.6 records the
scope and expected antialias/detail differences; visual acceptance remains
required.

Incremental CPU, fixed [3000,3900) route, 900 frames, 1280×800, full audio and
rendering, no audits/dumps/pacer work, `TG2_ACTORS=0` → On:

| Scale | Whole-frame mean Off → On | Incremental mean | On p95 |
|---|---:|---:|---:|
| 2× | 1.4031 → 1.6596 ms | 0.2565 ms | 1.883 ms |
| 4× | 1.8841 → 2.2672 ms | 0.3831 ms | 2.594 ms |

These are development-host CPU measurements, not Deck/GPU figures. The
settings file was restored after temporary Linear On/Off checks. Comparison
helpers stream RAM/VRAM fields and WAV hashes.

Additional resolved boundary: with stock 1×, 60 fps Off and Hide overscan On,
blanking row 0 could skip scene selection, leaving margin snapshots empty.
Selecting the same displayed SAT before overscan now passes the complete G3
repeat. Batched actor diagnostics also retain the controller's existing
poll cadence. No guest simulation, culling or memory was changed.

Ignored evidence: `build/s4/{qualified-summary.json,worker-report.md}`;
`final-commands.json`, `boundaries-commands.json`, `cost-commands.json`,
`pair-commands.json`; per-track folders named in those ledgers. Six review
pictures in `build/s4/review/`: `01-far.png`, `02-middle.png`,
`03-near-car.png`, `04-near-tree.png`, `05-pole-rain.png`, `06-tunnel.png`;
plus `stepped-continuous.png` and `pole-occlusion.png`. `pictures.json` maps
sources and model data. No captures were committed.

Remaining: owner S4 visual acceptance; native poles (visible mismatch mapped
at his request in task 38); S5 HUD/weather/tunnel-opening artwork; full N×
temporal qualification S6; live switching S7; other-country/platform and
Deck/GPU qualification. No runtime remains running.

## Task 39 — continuous actor growth (2026-11-11)

Local development evidence on macOS arm64, branch
`vittau/tg2-highres-continuous`; all builds/heavy work used the shared lock,
at most 3 build jobs and one headless runtime. S4 was approved/merged before
this task; owner review of the new motion/default policy remains pending.
The owner explicitly allowed approximate height agreement with the original
hand-drawn ladder; continuity is the criterion. HIGHRES §15 has the design.

| Final gate | Evidence/result |
|---|---|
| ROM/runtime diagnosis | 13,445 interpolated and 12,621 table projections agree with the raw instructions; `$FF17E0` is always the integer row scale, 12,474 interpolated D4 values differ from it |
| Motion traces | Auckland/Canada/Bavaria rain, 1,200 controller frames each, 4×/60 fps On; 44,505 matched visible frame pairs /1,721 band crossings; 0 residuals above 0.1%, max 0.000034% |
| Size change before→after | Cars 42.86→11.82%, trees 75.00→24.52%, signs 100→17.80%, barrels 100→25.46%; new changes follow physical projection, without a band-size term |
| 4× all-frame actors | Auckland 23,521; Canada 9,308; rain 8,977; floor/SAT/anchor/palette/priority errors 0 |
| Native sprite-row replay | 528,766 rows in the 4× runs, mismatches 0; directed Linear On 2× adds 6,314 actors /71,318 rows, also 0 |
| Occlusion | Rain native poles block 1,361 sampled output pixels /10 actor pixels draw over poles; clip/guest-cull/SAT guards retained |
| Changed/unchanged regions | Union of native and new silhouettes; continuous near/middle/far group limits 80/80/96, stepped 64/80/96. Qualified Canada group max 65.7263; outside mean max 0.3652 (4×), 0.8637 (2× Linear On), within unchanged S3 limits |
| Stock G1 | 9 configurations, exit 0; Off frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD` |
| Native boundaries | 32:9 2P native identity and cap/Off/16:9 transitions, exit 0 |
| Manifests | All four empty in every runtime run, including the original image-threshold failure |
| Video | 20 s /60 fps /2848×840, 1,200 exact synchronized pictures per side; ending RAM SHA-256 identical |

The initial Canada audit **returned 1** at group mean 69.8417 against the
old near limit 64: the projected near car is 1.116× as large, increasing area
24.6%. This is the intended silhouette change. Its pictures and failing
summary are retained in `build/task39/audit/canada/`. After declaring the
continuous near tolerance 80, the qualified repeat returns 0. No region or
metric was removed; unchanged-region limits, independent position/attribute
gates and the scalar projection gate were preserved. The first MP4 combine
also returned 8 because this ffmpeg lacks `drawtext`; raster captions plus
the supported overlay filter resolve it (exit 0).

CPU: fixed [3000,3900), 900 frames, 1280×800, 60-fps races On, full rendering
and audio, no audit/dump/pacer work. Original S4→new means are 2×
2.5311→2.7323 ms (+0.2012 ms), 4× 3.1509→3.4553 ms (+0.3044 ms, new mean
of two runs). New 4× means vary from 3.0133 to 3.8973 ms. Within-branch
stepped→continuous pairs give +0.0242 ms at 2× and +0.5897/−0.1856 ms at 4×
in opposite orders. These observations do not resolve a precise 4× increment
and are not Deck/GPU measurements; raw CPU/layout phase data remain available.

Ignored report: `build/task39/{worker-report.md,qualified-summary.json}`;
command ledgers `commands.json`, `followup-commands.json`,
`video-commands.json`, `cost-repeat-commands.json`, `cost-s4-commands.json`;
`rom-evidence.json`, `growth-new-final.json`, `growth-stepped.json`,
`growth-before.json`, `video-identity.json`, `video-probe.json`. The MP4 is
`build/task39/video/stepped-vs-continuous-4x-60.mp4`; bulk PNGs were deleted.
`build/task39/play-continuous.sh` launches the ready branch build, saved
scale 4 and race 60 fps On, with continuous selected internally.

No CI, tags, releases, ROM-derived git artifacts, generated C edits, engine
changes or submodule pin changes. Native poles/special pieces, stock spawn/
culling and player/HUD/menus/2P remain in scope exactly as before. Default
continuous, all-country coverage, S6 and real-platform performance await
their respective owner review/qualification.

### Task 39 approved default / Ayers Rock / bounded survey follow-up

Owner approved the continuous motion (“Está ótimo”). `b151a25` makes it the
N× default; only `TG2_ACTOR_SIZE=stepped` selects the old size policy.
Targeted build, G1 and a 300-frame default 4×/60-fps actor drive exit 0,
stock hashes unchanged, four manifests empty. No new full-matrix repeat.

Ayers Rock (country 0, slot 2, index 1, descriptor `$01BA96`) was captured
through the documented setup-only track selector. Rocks are ordinary kind
`$96`, record `$FF8E08`, model 0 32×16 through model 10 2×1; missing allowlist
entry caused fallback 1. `dce0c67` adds only that kind. A 900-frame 4×/60-fps
run has 4,333 rock presentations with no rock fallbacks; 4,015 matched size
pairs /154 band changes, max residual 0.000032%. All actor floor/SAT/anchor/
palette/priority/native-row replay errors are 0. Short Auckland/Canada/rain
regressions exit 0 (5,652 /3,832 /4,893 promoted actors, zero invariants).

**Retained failure:** the full Ayers drive exits 1 on road stripe-count and
centre checks (44,789 /31,138), while geometry/gap/hole/outlier checks and
actor checks pass. The fixed-input, 121-picture actor-disabled baseline also
exits 1 on stripe/centre (6,057 /3,990); both settings end with identical
RAM SHA-256 `b6caf537b95f1b1ea15f61889bad4acdfb884521637908dbd16b5dfc019c1849`.
Raw audit flags differ with sprite removal, so no bit-identical-road claim
is made. This is an unresolved night-road diagnostic independent of rock
sizing, not a passed/waived all-road qualification. No road code changed.

The other 13 countries each have one selected 900-moving-frame first-race
1× capture: 11,700 frames /79,487 mapper calls, selected runs exit 0 and all
four manifests empty. Password/race-index assertions verify entry; immobile
paused attempts are excluded. HIGHRES §14.8 gives per-kind counts. R1-only
unknown ordinary kinds `$81/$93/$97/$A1/$A2/$A3/$A4` remain unpromoted;
poles/specials stay native. Snapshot-based model-0 screening finds no R2–R4;
N× SAT/culling R5–R7 are not measurable by this 1× inventory. This is not
coverage of all four races or every late-race kind.

Ignored evidence: `build/task39-followup/{default-commands.json,rock-commands.json,
country-summary.json,country-table.md,rock-growth.json,road-baseline.json,
road-baseline-comparison.json,worker-report.md}`; per-country evidence under
`countries/`, initial/resumed valid capture directory named in each summary.
Ready build uses saved scale 4 and 60 fps On. Scripts:
`build/task39/play-continuous.sh`, `build/task39-followup/play-ayers-rock.sh`.
No visible runtime was launched, no CI/tags/releases/engine or pin changes.
