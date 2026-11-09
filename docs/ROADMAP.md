# Roadmap

Everything planned after v0.1.0, in one place. `STATUS.md` says what works
today; this file says what comes next. Each item has a short entry in the
table and a section below with the owner's requirements. Items with a task
spec link to it in `docs/tasks/`.

Rules that apply to every item:

- Every enhancement is an **option**. With it off, the picture, sound and
  input stay byte-identical to stock (Off-mode hashes: frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD`).
- Use the game's own assets, made better. Never assets from other games or
  other versions of Top Gear 2.
- When an owner request is added or settled, update this file, not `STATUS.md`.

## Overview

The owner's stated order for the visual work is high-resolution rendering
first, then NTSC + scanlines. The other groups have no set order.

| Group | Item | Summary | Spec |
|---|---|---|---|
| Pending from v0.1.0 | [Merge the task 26 playtest fixes](#merge-the-task-26-playtest-fixes) | RACE SOUND page, P2 Start out of the box and `[DUAL-DBG]` log noise are fixed on a branch that never reached `main` or v0.1.0. | [26](tasks/26-owner-playtest-e586c00.md) |
| Pending from v0.1.0 | [Real-device checks](#real-device-checks) | Play Windows, Intel macOS and the Steam Deck (controller only) on real hardware; finish the Apple Silicon check. | |
| Pending from v0.1.0 | [Quiver Launcher listing](#quiver-launcher-listing) | The owner submits the project now that v0.1.0 exists. | |
| Visual | [High-resolution rendering](#high-resolution-rendering) | Races above 224 lines: road re-rasterised from the game's per-line state, most detailed sprite LOD, clean background, sharp HUD. **First in the visual queue.** | |
| Visual | [NTSC filter and scanlines](#ntsc-filter-and-scanlines) | Blargg composite filter (`md_ntsc`) and *Animal Well*-style scanlines, with presets. **Second in the visual queue.** | |
| Visual | [HD menus, fonts and HUD pack](#hd-menus-fonts-and-hud-pack) | Optional replacement pack of faithful HD redraws, keyed by the original tiles. | |
| Visual | [Gradient skies](#gradient-skies) | SNES-like vertical sky gradients derived from each track's own sky colour, weather and time of day. | |
| Visual | [Widescreen on the other screens](#widescreen-on-the-other-screens) | Track intro, menus, shop and results extended to widescreen. Deferred by the owner to the final phase. | [17](tasks/17-widescreen-menu-screens.md) |
| Visual | [Arbitrary car colours](#arbitrary-car-colours) | HSL picker replacing the game's car-colour page, not limited to the Genesis palette. | |
| Gameplay | [Analog control](#analog-control) | Proportional steering injected into the game's steering routine; triggers only if partial throttle makes sense. | |
| Gameplay | [Cheats page](#cheats-page) | Pick any of the 64 races and set money/upgrades from the Esc menu, through the game's own password path. | |
| Save states | [Car setup screen](#save-states-on-the-car-setup-screen) | Save and load on the setup screen, on a new game and between races. | [27](tasks/27-setup-screen-quickstate.md) |
| Save states | [Live 2P race after a load](#live-2p-race-after-a-load) | Show a loaded split-screen race resuming live, not under the game's PAUSE. | |
| Audio | [Clean FM and separate volumes](#clean-fm-and-separate-volumes) | Optional YM3438-style FM without the ladder distortion, plus Music and SFX volume sliders. | |
| Audio | [Better engine and nitro PCM](#better-engine-and-nitro-pcm) | Band-limited resampling of the original PCM instead of the DAC's sample-and-hold. | |
| Audio | [Auckland music re-attacks](#auckland-music-re-attacks) | Channels 1–2 re-attack some notes differently from the owner's VGM reference. | |
| Platforms | [Android](#android) | A future release target. Not started. | |

Out of scope (owner): save states on the password screen.

## Pending from v0.1.0

### Merge the task 26 playtest fixes

Task 26 fixed the owner's e586c00 playtest bugs on
`origin/vittau/tg2-playtest-fix` (last commit 2026-11-07), but the branch
was never merged, so v0.1.0 ships without them:

- `0ae5b7d`, `f7eff64`: the RACE SOUND page is built from the session choice
  and keeps a recorded choice (the page was empty, then garbled);
- `c04a251`: two players are usable out of the box (engine patch
  `0020-game-default-players.patch`; P2 could not press Start);
- `a1fa4cb`: drops the `[DUAL-DBG]` telemetry from the release log;
- `tools/verify_sound_page.py`.

The feedback-replay divergence from the task spec has no commit on the
branch. Merge `main` into the branch, rebuild, rerun its probes and the
Off-mode hashes, check that main's RACE SOUND page still has the bug before
claiming the fix, then merge. Patch number 0020 is still free on `main`.

### Real-device checks

Windows, Intel macOS and the Steam Deck (Gamescope, controller only) only
have CI headless smoke tests; nobody has played them. Apple Silicon macOS
(27.2) starts and plays into the menus after the quarantine step; the
launcher ROM pick and a full race still need a playtest there (unsigned
`.app`; Gatekeeper first-run steps are in `RELEASING.md`). Until these pass,
the README calls those builds release candidates.

### Quiver Launcher listing

The owner submits the project to Quiver now that v0.1.0 exists, so Quiver
can review it. Window screenshot for the form:
`~/Pictures/tg2-quiver-screenshot.png` (outside git).

## Visual

### High-resolution rendering

*Owner request, 2026-11-07.*

Render races above 224p in our renderer. This would also give the
"Internal resolution" option a real meaning; today it is a no-op for TG2.
- **Road:** redraw the road from the game's own per-line parameters (curve,
  hill, scale and stripe phase) at N× resolution, instead of upscaling the
  224-line raster. Sub-line interpolation also helps the 60 fps frames.
- **Sprite LOD:** the game picks smaller, lower-detail sprite variants with
  distance (trees, signs, cars). Map each object's LOD set, then always draw the
  most detailed variant, scaled to the on-screen size with good filtering, at
  the higher render resolution, with sub-pixel positions.
- **Background and HUD:** scale the background layers cleanly; keep the HUD
  sharp.

It uses the same assets, only better, which fits the owner's rule on foreign
assets.

First steps: map the LOD tables (pattern sets per object and distance
thresholds), and find which per-line road state is enough to re-rasterise.

### NTSC filter and scanlines

*Owner request, 2026-11-07.*

A Blargg NTSC composite filter and scanlines as presentation options. Blargg
has a Genesis-specific variant, `md_ntsc`, besides `snes_ntsc`. Reference:
https://github.com/vittau/modern-tyrian (`docs/CRT.md`, `src/ntsc.c`,
`src/crt_filter.c`, and regression captures in `test/regress/modern-crt-*`).
It is a scalar C99 port of `snes_ntsc` 0.2.2 (via Deadly Dave): composite
preset, RGB555-keyed kernel tables (about 16 MiB, built lazily), 3 input
columns → 7 output columns, burst phase advanced per presented frame (smooth-
motion frames too), half-row scanlines, and Off / Scanlines / NTSC / both. The filter
needs no palette. The per-colour kernel table is only a speed-up, since the
filter is linear. Because later enhancements (gradient skies, HSL car colours,
high-resolution rendering) put arbitrary colours in the presented frame, the
filter must accept any colour. Choose between RGB555-keyed tables, as in
modern-tyrian (slight gradient quantisation, mostly hidden by the composite
blur), and direct per-pixel filtering on the CPU or in a GPU shader (exact
colour, higher cost). Don't key the tables on the Genesis 512-colour palette. Precomputing at startup is
cheap for RGB555 (about 16 MiB, a fraction of a second). Finer keys grow fast:
565 is about 32 MiB, 666 about 128 MiB, and full 888 about 8 GiB, which is not
feasible. For exact full colour, use the filter's linearity: a pixel's kernel is
r·K_R + g·K_G + b·K_B, so three base kernels plus a few multiply-adds per tap
(SIMD) replace the per-colour table. Blargg's gamma and hue adjustments are
not linear and must be applied separately. Plan: start with RGB555 like
modern-tyrian, measure banding on the gradient skies, and switch to the
three-kernel path if needed.
- **Owner's queue and taste (2026-11-07):** the queue after 0.1.0 is
  high-resolution rendering first, then NTSC + scanlines. Use Blargg's filter
  for NTSC. For scanlines, the owner likes the look of *Animal Well*. A
  community shader reproduces it:
  https://godotshaders.com/shader/animal-well-inspired-crt-effect/ . Study its
  effect (scanline profile, brightness compensation, any mask, bloom or
  curvature) and reimplement it in our presentation path. Check the shader's
  licence before copying any code, and prefer an original implementation of the
  same look.
- Run it on the final presented frame: after widescreen composition and the
  overscan crop, and for the 60 fps synthesized frames too. Then scale to the
  window, with scanlines matched to the output resolution.
- Presets (composite / S-Video / RGB) and scanline strength. Off stays
  byte-identical.
- It conflicts with [high-resolution rendering](#high-resolution-rendering), which aims at the opposite
  look, so make them mutually exclusive or order them clearly.
- Check the license before vendoring: Blargg's libraries are LGPL 2.1, and
  static linking in a PolyForm-NC project needs care. Also measure the CPU cost
  on the 3500U and on the Deck.

### HD menus, fonts and HUD pack

*Owner request, 2026-11-07; a later extension of high-resolution rendering.*

Redraw the menus, fonts and HUD art in
high resolution. Do it as a data-driven replacement pack keyed by the
original tile/pattern content (like Dolphin or RT64 texture packs), so the
game logic is untouched, missing entries fall back to the original art, and
the pack is optional. The redraws must be faithful HD versions of the
originals, not new designs. It pairs with [widescreen on the other screens](#widescreen-on-the-other-screens). Acceptance test (owner):
downsampling each HD asset back to the original size must give art very close
to the original tile. A tool scores every pack entry: box-filter downsample,
quantise to the Genesis 9-bit palette, then compare per pixel against the
original, with a threshold. Entries that fail are rejected. This is the same
idea as the car-colour test: the enhancement must reproduce the stock asset. Before
publishing a pack, decide how to distribute it: it is a derivative of the
game's copyrighted art, so it is a riskier thing to host than code. Make it an option; at 1× with it off, the output stays byte-identical.

### Gradient skies

*Owner request, 2026-11-06.*

Race skies
with a vertical gradient similar to the SNES version's look, not limited to the
Genesis palette. Draw it ourselves in the game-owned renderer; copy no SNES
assets. Derive it from the game's own sky colour per track, weather and time of
day: night, fog, rain and snow need their own ramps. Anchor it to the moving
horizon on hills, and handle tunnels, flashes and split screen. Make it an
option; with it off, the picture stays byte-identical. A worker should first
answer how the sky is drawn today: the backdrop colour or background-layer
tiles, and whether raster palette changes already occur.

### Widescreen on the other screens

*Owner request, 2026-11-06: scheduled for the final phase.*

Widescreen for **every** extendable non-race screen: the track intro with its
scrolling scenery, menus, shop and results. Spec:
[task 17](tasks/17-widescreen-menu-screens.md). Today these screens are shown
in their original width, centred.

### Arbitrary car colours

*Owner request, 2026-11-06.*

An HSL picker that **replaces the game's own car-colour page** in the
pre-race menu. It is in-game and drawn in the game's menu style, not in the Esc
overlay. It is not limited to the Genesis 512-colour palette. Like the BOTH
row on the SOUND page, the page is host-owned: hook the colour page, draw
H/S/L rows and a live preview with the game's font and glyph tiles, and read
the pad there. With the option off, the stock page and its fixed colours stay
byte-identical. Recolour at
render time in our renderer; the simulation and RAM are untouched, and with it
off the picture stays byte-identical. First find out:
- which palette line and entries the player car's body uses;
- whether those entries are shared with opponents, the HUD car icon or the
  scenery.

Recolour only the player car's sprite pieces, using the sprite capture,
shifting hue and saturation and scaling lightness to keep the shading. Cover
P1 and P2 in split screen, the HUD car icon, and the menu, shop and results
car images. Persist the colours per player in `settings.ini`.
Acceptance test for the shading logic (owner): each of the game's stock car
colours must be reproducible with the HSL picker. For each stock colour, find
the H/S/L setting that best matches all of the car's shade entries, and
report the per-entry error after Genesis 9-bit quantisation. The target is
exact, or at most one 9-bit step per channel. This forces the shading model
to be fitted from the stock ramps rather than invented.

## Gameplay

### Analog control

*Owner request, 2026-11-07.*

Proportional steering from an analog stick, with optional analog throttle and
brake on the triggers, similar to Cannonball (the OutRun recomp). Top Gear 2
only reads a digital pad, so there are two levels:
- Quick (rejected by the owner): pulse LEFT/RIGHT with a duty cycle
  proportional to the stick.
- Proper (**owner's choice, 2026-11-07**): find the routine that turns LEFT/RIGHT into the car's steering
  delta, and inject a scaled value from the stick there. Add a deadzone,
  a response curve and a sensitivity option.

Treat the triggers the same way only if the throttle model makes partial input
meaningful. Then check feel and lap times against the D-pad, cover 2P, and keep
it an option. With it off, input stays byte-identical. First steps: map the
steering and throttle code in RAM and ROM, and see how Cannonball maps its
wheel.

### Cheats page

*Owner request, 2026-11-07.*

An easy "Cheats" page in the in-game menu (Esc): pick the circuit (any of the
64 races) and set the money (and the car upgrades, if cheap). Preferred
mechanism: build the state through the game's own password path. The codec is
reversed (`docs/PASSWORDS.md`, `tools/tg2_password.py`), so the game loads a
consistent championship state as if a password had been typed. Apply it at a
safe point (menu or between races), never mid-race. The corrected password
codec supports all level-3 parts and up to $1,023,000 per player (the checksum
is 15-bit, not capped at 255). Passwords start at country slot 1; they have no
field for races 2–4. `stage` is difficulty. Using a cheat
changes nothing in stock behaviour; with no cheat applied, output stays
byte-identical.

## Save states

### Save states on the car setup screen

*Owner request, 2026-11-09.* A save on the setup screen is refused on a new
game (`SAVE UNAVAILABLE HERE`) and, between races, deferred to the start of the
next race (patch 0024). The screen is reached by a jump-table dispatch that the
resume path can't follow, so its own frame loop can't simply be declared as a
boundary: that was tried, and loads fell back to the main menu. The full plan
and acceptance are in [task 27](tasks/27-setup-screen-quickstate.md).

### Live 2P race after a load

The quickstate matrix saves and loads a 2P split-screen race, but the scripted
boot leaves the game's own PAUSE overlay up and TCP `set_input` does not clear
it, so the loaded picture is a correct *paused* race. Show a full unpaused 2P
race after a fresh-process load (`VALIDATION.md`, end of "Quickstate resume
continues the guest's callers").

## Audio

### Clean FM and separate volumes

*Owner request, 2026-11-06.* A small optional audio task. It adds a "clean FM"
option (ymfm YM3438 variant, no ladder distortion; the default stays the stock
YM2612 sound) plus separate **Music volume** and **SFX volume** sliders in the
in-game Esc menu, next to the existing master Volume, in every sound mode.
Default 100% stays byte-identical. Classify by source: the Z80 music driver is
music; the 68k FM/PSG engine and the race Z80 SFX image are SFX.

### Better engine and nitro PCM

The engine and nitro **are** PCM (correction from task 20): a 6.6 kHz DAC
player in the race Z80 SFX image (ROM `$0701F6`); the 68k FM part is only a
drone. The owner's "better version of the same asset" fits here: band-limited
resampling of the original PCM instead of the DAC's sample-and-hold. Rejected:
engine samples from other games or versions.

### Auckland music re-attacks

The logic match of the music against the owner's VGM rips is 89.7–99.5%. The
open divergence is Auckland, channels 1–2, where some notes are re-attacked
differently (`AUDIO.md` §11).

## Platforms

### Android

*Owner request, 2026-11-07.* A future release target beyond Windows, Linux and
macOS. Not started. Until then, avoid choices that would block an Android build
(SDL setup, file paths, ROM import, touch/controller input, packaging).
