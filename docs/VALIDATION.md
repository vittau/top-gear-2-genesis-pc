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
or offscreen video, dummy audio, TCP port 4470, one runtime at a time) by
controller input only: no RAM writes, no save states, no generated-code edits.

| Artifact | What |
|---|---|
| `tools/tg2_runner.py` | minimal runner client: launch, TCP commands, one-round-trip `step()`, race-state decode |
| `tools/tg2_race_driver.py` | closed-loop driver: boot, race, finish, post-race, next race; writes `trace.csv`, `route.json`, `laps.json`, `summary.json` |
| `tools/tg2_replay_route.py` | exact-wall-frame replay of a recorded route in any presentation mode |
| `tools/tg2_controls_probe.py` | in-race A/C/off-road probe with screenshots |

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

## 2. Further tracks

Two routes to other countries exist; neither was usable for coverage in this
build:

* **Championship progression** — needs a top-ten finish (below).
* **CONTINUE → COUNTRY SELECTION** — a direct country picker (main menu:
  `START`, `DOWN`×3, `START`, `DOWN`, `RIGHT`, `START`; the picker lives behind
  the same `CONTINUE` row as `PASSWORD`). Picking a country then opens
  **ENTER PASSWORD** for that level, and the pre-filled string is rejected
  ("INVALID PASSWORD", `build/qual/password-accept2/pw-C.png`). The password
  encoding is not reversed, so the picker cannot start a race yet.

Evidence for the navigation and the gate: `build/qual/country-nav3/`
(`after-start.png` is the picker), `build/qual/country-britain/`
(`country-1-selected.png` selects Britain), `build/qual/password-accept2/`
(`pw-C.png`, invalid password).

| Track | How reached | Evidence |
|---|---|---|
| Auckland, Australasia (1.6 mi, 4 laps, 5:43 AM) | race 1 | `build/qual/progress1/after-start-1800.png` |
| Ayers Rock, Australasia (1.2 mi, 5 laps, 9:15 PM) | race 2, **night race** | intro `build/qual/progress1/race1-post-05.png`; the finished night race: `build/qual/soak-60/race2-post-01.png` (dark palette, LAP 5/5) and `build/qual/soak-60/race-3060.png` |
| championship track 3+ | not reached | every attempt ended on the Ayers Rock qualification gate; the soak restarts the championship from the menu (evidence: `build/qual/soak-33/raceN-start.png`) |

A race must be **qualified** (roughly top ten) to advance; finishing 14th on
Ayers Rock ended the championship and returned the game to the main menu. The
soak tool therefore restarts the championship from the menu after a failed
qualification, which is also what makes a 30-minute continuous session possible.

**Rain**: no rain race was reached. Weather is a per-track property shown on the
track intro panel (sun icon on Auckland and Ayers Rock); only those two tracks
were reached before the championship ended, so rain remains untested.

Attempts to widen coverage failed: the main menu's DIFFICULTY row was stepped
three clicks left (`--difficulty-steps -3`,
`build/qual/progress-easy/race2-post-02.png`) and three clicks right
(`build/qual/progress-easy2/race2-post-02.png`); both Ayers Rock races finished
17th, so either the row was not actually changed or it does not affect the AI,
and it was left at its default.

## 3. Rain, night, nitro, crash, pit

| Scenario | Status | Evidence |
|---|---|---|
| Night race | **passed** | Ayers Rock runs at 9:15 PM with the night palette: `build/qual/soak-60/race2-post-01.png`, `build/qual/soak-60/race-3060.png` |
| Rain race | **untested** | not reached |
| Nitro | **not found** | `build/qual/controls2/phases.json`: A is the brake (speed 4387 -> 945 in 2 s, median 1000 while every other window accelerates), C produced no boost outside the normal acceleration curve (median 6400 vs 5999 in the following window) and no nitro gauge/timer exists in the player record or HUD. No nitro input was identified. |
| Collision / off-road | **passed (off-road), partial (contact)** | `tools/tg2_controls_probe.py` off-road phase: lateral hits the -287 clamp and speed collapses 5615 -> 3571 (`build/qual/controls2/throttle+LEFT-*.png`). On-road instantaneous drops in the same log (e.g. 5544 -> 3475 at frame 4410, lateral -11.7) are consistent with car contact but no contact frame was isolated |
| Pit stop | **not present** | no pit lane, pit prompt, tyre or fuel state in the HUD or in the player record |

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
```

## Manifests

Every run copies the runtime manifests next to its evidence. All runs in this
ledger report `dispatch_misses.toml`, `floor_coverage.toml`,
`interior_label_misses.toml` and `floor_unsafe.toml` with **0 entries**; no new
discovery seeds were needed, so `game/game.toml` is unchanged by this task.

## Gaps / follow-ups

* Only two of the sixteen championship tracks were reached (Auckland and Ayers
  Rock), not the three further tracks the task asked for. Advancing needs a
  top-ten finish; the reactive driver is not fast enough on Ayers Rock's tighter
  layout (~52-56 s laps, 14th-17th) even though it qualifies on Auckland
  (3rd-4th). A faster lane-keeping controller, a working difficulty setting, or
  reversing the password encoding is the way to the rest.
* Rain remains untested for the same reason (weather is per track).
* No nitro input was found (see section 3).
* The open-loop replay of a *reactive* route diverges once the car touches the
  grass; the deterministic comparison that is valid today is same-mode
  repeatability (exact) and same-script Off/16:9 (exact). A tuned feed-forward
  route would make the 60 fps same-script comparison exact as well.
