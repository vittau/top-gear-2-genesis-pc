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
| 14 | Switzerland / Geneva | bright, snow | 4 | pass, 62.13 s | pass, 62.13 s | 0/0/0/0 |
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
python3 tools/tg2_password.py decode "KUC2 2HQG CJL2 Y4%T"
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
(the checksum allows 150k with every part at max), then races in order; the
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
manifests 0) and `c06` (Greece race 1, still the open 0x00650C miss).

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
2. **MAJOR, open (engine) — interior-label dispatch at `0x00650C`.**
   `interior_label_misses.toml` and `floor_unsafe.toml` list `0x00650C` in
   nine country runs (Greece onward), first at race 1 frame ~8593. The game
   dispatches into the middle of the scene-init block that starts at
   `$64C2` (the pushed target is `$650C`, which is the fall-through
   continuation after three `bsr`s). The recompiler has no in-function label
   there, so the floor capsule runs it and cannot return (`exit_pc $007F18`,
   `expected_ret $001E82`, "capsule exit_pc != native loose-A7 return"); the
   call is skipped for the session. It needs in-function dispatch codegen in
   the engine, not a game seed (seeding would split the parent). Reproduced
   after the merge: `tools/tg2_progress.py --country 6 --races 1`.
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
