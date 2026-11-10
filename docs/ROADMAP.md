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

## Current plan (owner, 2026-11-10)

The owner picked the first items to work on, in this order:

1. **NTSC filter and scanlines** — [task 28](tasks/28-ntsc-scanlines.md).
   **Paused by the owner on 2026-11-09** before any code was written (the
   Blargg LGPL question is open too). Branch `vittau/tg2-ntsc-scanlines` has
   no commits.
2. **High-resolution rendering** — design (task 29), S1/S2 (task 31) and
   S3 (task 33) are complete and merged. The owner approved S3's visuals and
   requested a Linux draft for his Steam Deck. Address its new playtest
   feedback first; [S4/task 34](tasks/34-highres-s4.md) is prepared, not started.
   S3/S4 implementation is restricted to Opus, Fable or Sol.
3. **Clean FM, separate volumes and better engine/nitro PCM** —
   [task 30](tasks/30-clean-fm-and-pcm.md): finished Music/SFX faders remain;
   the owner rejected Clean FM and Clean engine samples after listening and
   they were removed. Do not reintroduce them as unfinished release work.

No worker remains active at the session checkpoint. See
[CONTINUATION.md](CONTINUATION.md) for source/build revisions, draft assets,
validation evidence, retained worktrees and next-session decisions. Keep at
most two supervised workers and serialize heavy steps with the shared lock.

Shared rules fixed up front, kept while NTSC is paused so it can resume
without rework: NTSC runs at native source resolution and is mutually
exclusive with a render scale above 1×; scanlines run at output resolution
and also apply to a high-resolution frame; both stages accept any RGB colour.
Engine patch numbers are reserved per task (28: 0028–0032, high-res:
0033–0039, 30: 0040–0044).

The other groups have no set order.

## Overview

| Group | Item | Summary | Spec |
|---|---|---|---|
| Pending from v0.1.0 | [Steam Deck feedback](#steam-deck-feedback-owner-playtest-2026-11-09) | Picture 16:9 instead of 16:10; logs written in normal use. Fixed on `main` (task 32); needs a real Deck run. | [32](tasks/32-deck-aspect-and-quiet-logs.md) |
| Pending from v0.1.0 | [Real-device checks](#real-device-checks) | Play Windows, Intel macOS and the Steam Deck (controller only) on real hardware; finish the Apple Silicon check. | |
| Pending from v0.1.0 | [Quiver Launcher listing](#quiver-launcher-listing) | Submitted by the owner on 2026-11-08; waiting for a Quiver maintainer to verify it. | |
| Visual | [High-resolution rendering](#high-resolution-rendering) | Races above 224 lines: road re-rasterised from the game's per-line state, most detailed sprite LOD, clean background, sharp HUD. **Priority 2.** | [29](tasks/29-highres-design.md) |
| Visual | [NTSC filter and scanlines](#ntsc-filter-and-scanlines) | Blargg composite filter (`md_ntsc`) and *Animal Well*-style scanlines, with presets. **Paused (owner, 2026-11-09).** | [28](tasks/28-ntsc-scanlines.md) |
| Visual | [HD menus, fonts and HUD pack](#hd-menus-fonts-and-hud-pack) | Optional replacement pack of faithful HD redraws, keyed by the original tiles. | |
| Visual | [Gradient skies](#gradient-skies) | SNES-like vertical sky gradients derived from each track's own sky colour, weather and time of day. | |
| Visual | [Widescreen on the other screens](#widescreen-on-the-other-screens) | Track intro, menus, shop and results extended to widescreen. Deferred by the owner to the final phase. | [17](tasks/17-widescreen-menu-screens.md) |
| Visual | [Arbitrary car colours](#arbitrary-car-colours) | HSL picker replacing the game's car-colour page, not limited to the Genesis palette. | |
| Gameplay | [Analog control](#analog-control) | Proportional steering injected into the game's steering routine; triggers only if partial throttle makes sense. | |
| Gameplay | [Cheats page](#cheats-page) | Pick any of the 64 races and set money/upgrades from the Esc menu, through the game's own password path. | |
| Save states | [Car setup screen](#save-states-on-the-car-setup-screen) | Save and load on the setup screen, on a new game and between races. | [27](tasks/27-setup-screen-quickstate.md) |
| Save states | [Live 2P race after a load](#live-2p-race-after-a-load) | Show a loaded split-screen race resuming live, not under the game's PAUSE. | |
| Audio | [Separate Music and SFX volumes](#separate-music-and-sfx-volumes) | **Done (task 30).** Two live-switchable faders in every sound mode, byte-identical at 100 %. | [30](tasks/30-clean-fm-and-pcm.md) |
| Audio | [Clean FM (rejected)](#clean-fm-rejected) | **Rejected by the owner after listening (2026-11-09):** the YM3438 core was inaudible to him. Built, measured, removed. | [30](tasks/30-clean-fm-and-pcm.md) |
| Audio | [Better engine and nitro PCM (rejected)](#better-engine-and-nitro-pcm-rejected) | **Rejected by the owner after listening (2026-11-09):** the reconstruction sounded muffled (6.6 kHz samples have nothing above 3.3 kHz). Built, measured, removed. | [30](tasks/30-clean-fm-and-pcm.md) |
| Audio | [Auckland music re-attacks](#auckland-music-re-attacks) | Channels 1–2 re-attack some notes differently from the owner's VGM reference. | |
| Platforms | [Android](#android) | A future release target. Not started. | |

Out of scope (owner): save states on the password screen.

## Pending from v0.1.0

### Steam Deck feedback (owner playtest, 2026-11-09)

The owner played on a Steam Deck: it worked well, but the picture was 16:9
instead of the panel's 16:10, and a ~1.4 MB file was written to `logs/` (the
feedback replay, on by default). Fixed on `main` by
[task 32](tasks/32-deck-aspect-and-quiet-logs.md): Adaptive follows the
device's output, the game starts fullscreen under Gamescope, and diagnostics
are opt-in (`--debug` or the Diagnostics row). Still needs a run on the
owner's Deck.

### Real-device checks

Windows, Intel macOS and the Steam Deck (Gamescope, controller only) only
have CI headless smoke tests; nobody has played them. Apple Silicon macOS
(27.2) starts and plays into the menus after the quarantine step; the
launcher ROM pick and a full race still need a playtest there (unsigned
`.app`; Gatekeeper first-run steps are in `RELEASING.md`). Until these pass,
the README calls those builds release candidates.

### Quiver Launcher listing

Submitted by the owner on 2026-11-08, after v0.1.0 was published. It is
waiting for a Quiver maintainer to verify it; nothing to do on our side until
they reply. The window screenshot used in the form is
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

S3's road rasteriser is accepted and merged. Next, finish the partially
mapped per-type LOD ladders and capture actor metadata for S4; see
[task 34](tasks/34-highres-s4.md). Start with any fresh S3/Deck defect the
owner reports. Detailed scope and remaining boundaries are in HIGHRES §13.

Design and ground truth: [docs/HIGHRES.md](HIGHRES.md) (task 29). It maps the
per-line road state, the atlas geometry and palette banks, and the sprite LOD
tables, then proposes the architecture, the engine seam (patch 0033) and the
step-by-step plan with per-step acceptance. The owner decided its §9 questions
on 2026-11-09 (smooth road edges, integer-N× HUD, always the most detailed
sprite variant, the engine's "Internal resolution" row as the control, 1×
default, road + background first as an experimental option, 2P later).

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
- **Owner's queue and taste (2026-11-07; order superseded on 2026-11-09, see
  "Current plan"):** the queue after 0.1.0 was high-resolution rendering
  first, then NTSC + scanlines. Use Blargg's filter
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

### Separate Music and SFX volumes

*Owner request, 2026-11-06.* **Implemented in task 30** (`docs/AUDIO.md` §13).
Music volume and SFX volume faders in the in-game Audio section under the master
Volume and on the launcher's Mods page, in every sound mode. Writes are
classified by source: the resident Z80 music driver is music; the 68K FM/PSG
engine and the race Z80 SFX image are sound effects (the game tells the mixer
when the first core runs the race image instead of the driver). At 100 % every
stock MUSIC/SFX/BOTH capture and the 4:3 frame hashes are byte-identical. The
faders switch live (a one-frame gain ramp; the fader never touches chip routing)
and `tools/tg2_live_toggle_probe.py` covers the menu, the pre-race screens, the
countdown, the race start and mid-race in all three modes, plus a cold start and
a mid-race RACE SOUND switch.

### Clean FM (rejected)

*Owner request, 2026-11-06; rejected 2026-11-09.* A "Clean FM" option (ymfm's
YM3438 core, no ladder distortion) was built and measured: it removed the
ladder's DC offset and harmonic distortion (`AUDIO.md` §13.5) while leaving
every pitch, note and tempo bit-identical (log-spectrum correlation 0.9999
against the stock chip). The owner heard no improvement, so the option and its
engine patch (0041) were removed.

### Better engine and nitro PCM (rejected)

The engine and nitro **are** PCM (correction from task 20): a 6.6 kHz DAC
player in the race Z80 SFX image (ROM `$0701F6`). A "Clean engine samples"
option reconstructed that stream band-limited (95-tap Kaiser sinc at 3.3 kHz)
instead of the chip's sample-and-hold. Measured on the model: images at
6.6k/13.2k/19.8k dropped from -26 to -60 dBc. **Rejected by the owner after
listening (2026-11-09):** it sounded muffled rather than more detailed - a
6.6 kHz stream has nothing above 3.3 kHz to recover - and, worse, the option
also rewrote the *music* driver's own DAC stream (the driver streams the DAC
channel continuously; 170,063 reconstructed writes in 40 s of menu music), which
muffled the music. Option and patch removed; the stock DAC is kept.

### Auckland music re-attacks

The logic match of the music against the owner's VGM rips is 89.7–99.5%. The
open divergence is Auckland, channels 1–2, where some notes are re-attacked
differently (`AUDIO.md` §11).

## Platforms

### Android

*Owner request, 2026-11-07.* A future release target beyond Windows, Linux and
macOS. Not started. Until then, avoid choices that would block an Android build
(SDL setup, file paths, ROM import, touch/controller input, packaging).
