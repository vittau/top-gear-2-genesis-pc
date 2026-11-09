# Project status (2026-11-06)

Overall estimate: about **88%** of the goal, which is a native Top Gear 2
on Windows, Linux/Steam Deck and macOS, with widescreen and true 60 fps,
plus music and SFX together. Everything below has been verified headlessly.
The owner has played two short sessions (Linux, Ryzen 5 3500U).

## On `main`

| Area | State | Docs |
|---|---|---|
| Native 4:3 baseline | Boot → menus → full 4-lap race → results/shop/next race; 2P split-screen; 33.7-min soak, plus a 43.7-min soak with all options on (16:9 + Edges + 60 fps + Hide overscan, 13 races, SP stable). 0 dispatch misses. | `BRINGUP.md`, `VALIDATION.md` |
| All 64 races | Password codec reversed (`PASSWORDS.md`, `tools/tg2_password.py`). All 16 countries raced for 62 s in Off and 16:9+Edges, 0 manifest entries; rain, night, fog and snow covered. Task 25 drove the last 19 races (index selected from the ROM table on the setup screen) to the finish: 64/64. Nitro = C button. | `VALIDATION.md` |
| Widescreen | Adaptive / 16:9 / 21:9 race renderer: road, background, sprites in the margins. HUD Centered or Edges. Off is byte-identical to stock. | `WIDESCREEN.md` |
| Widescreen fixes from playtests | Black bands on downhills, the top-window line, tunnel margins (now follow the walls), and the motion-only flicker in 60 fps synthesized frames. Full-presented-frame margin audit: 1019 → 0. | `WIDESCREEN.md` |
| Hide overscan | Default On: crops the 8 top and 16 bottom empty race lines (the top band's stock red marks go with them), so the picture fills the window. Menus, results and split-screen keep their full height. | `WIDESCREEN.md` |
| 60 fps | Stock simulation plus host-only interpolation. Identical WRAM over 16000 frames; 60 pictures/s; no road artefacts; adds 50 ms display latency. | `FRAMERATE.md` |
| Music + SFX (BOTH) | A third RACE SOUND value, **BOTH**, in the game's own SOUND menu. Stock MUSIC and SFX WAVs are byte-identical to stock. Limitation: a shared-chip mix, so music notes can be stolen by SFX; a clean second virtual chip is future work. | `AUDIO.md` |
| Performance + audio pacing | Release build at 16:9+Edges+60 fps uses p95 60.5% of the frame budget on a Ryzen 5 3500U. Guest clock is exact (late frames repay their tick; overdue frames drop 60 fps synthesis, never guest time). Music is sequenced by a free-running Z80 program, so tempo follows guest time: under two CPU burners, -6.8 ms audio drift per 60 s, 0 underruns. DRC bounded to ±0.2%. Logs/settings/saves now go next to the executable (they used to go to `~/.local/bin`). Engine patches 0004-0006. | `PERFORMANCE.md` |
| Real-device audio (owner bug) | Root cause: every host hitch was concealed and then became permanent latency, until the ring cap cut audio in bursts (delays, then pops). Fix: a cushioned, latency-bounded DRC (100 ms target, 250 ms ring, ±0.5%, latency bound 160 ms, quick resume). Measured on a PipeWire null-sink recording: 4×3-min races at 0 pops, dropouts and underruns. Needs the owner's listening confirmation. | `PERFORMANCE.md` §10 |
| BOTH fix + music tempo | BOTH is now session-owned host state (it engages on every route, persisted as `[mods.racesound]`), and its text uses the game's own menu font. Exact audio sample clock (patch 0008; it was -402 ppm). Tempo-stable slow-integral DRC (patch 0009): speed swings 1233 → 37 ppm/s. Reference pipeline: headless Genesis Plus GX renderer (`tools/gpgx_render.c`). A/B files in `~/Music/tg2-ab/`. | `AUDIO.md` §6-7, §11-12 |
| Music tempo (owner bug) | Root cause: the port re-armed the YM2612 timer B on every `$27` reload instead of letting it run free (patch 0010). Title theme went from -6.99% ±2% to +0.194% flat. **Owner confirmed 2026-11-06: music speed is great.** All 4 owner VGM rips align at +0.194%, and Genesis Plus GX agrees with the port to 0.02%, so the residual is the rips' own time base. Logic match vs the VGMs: 89.7–99.5% (open item: Auckland ch1-2 re-attacks). | `AUDIO.md` §11 |
| Race band crop + HUD Edges fix (owner request) | Hide overscan (default On) now crops the race's empty 8 top / 16 bottom lines: 256×200 Off, 356×200 16:9, 467×200 21:9. A per-frame guard crops only single-player race pictures whose bands are empty. Menus and split screen are unchanged. Engine patch 0012 (`present_window`). HUD Edges map/marker split fixed (the HUD moves to sprites on frames 3409–3585). 16 tracks, 181 race pictures checked; margin audits 0; Off hashes unchanged. | `WIDESCREEN.md` |
| Quit from the menu (owner request) | The in-game menu (Esc / Back+RB) has a **Quit game** row (two presses) that exits through the normal window-close path, so settings are saved. Meant for controller-only play on Steam Deck. Engine patch 0013. Compiles; needs a hands-on check in the next play build. | |
| Options | Widescreen / 60 fps / HUD / Hide overscan in the launcher and the in-game overlay (gamepad: Back+RB), persisted in `settings.ini [mods.*]`. | `RELEASING.md` |
| CI | `build.yml`: Linux (glibc ≤ 2.35, Deck), Windows x64, macOS universal2. The ROM comes from the private repo via deploy key; artifacts are gated against ROM or generated C. | `RELEASING.md` |
| Release packaging | macOS `TG2Recomp.app` (universal2; installed in Applications it imports the picked ROM into Application Support, portable it finds the ROM beside the `.app`), single-file Linux `TG2Recomp-x86_64.AppImage` plus tarball, Windows zip. `v*` tags build a **draft** release with SHA256SUMS. Validated on CI run 42222837085: every platform smoke-ran 600 frames with the ROM auto-detected. | `RELEASING.md` |
| ROM | Auto-detected by CRC next to the executable, whatever the file name. An installed macOS app also searches Application Support, where it imports the ROM picked in the launcher (engine patch 0019). | `BRINGUP.md` |

Engine changes live as patches in `patches/segagenesisrecomp/`. The
submodule pin is upstream `dd520f1`.

## Priority: first playable release (owner, 2026-11-06)

The owner's priority is a first release (v0.1.0) that is playable and has no
major bugs. Release path:

1. **Done (313ae46):** BOTH via two chips and a second Z80 core (task 20b):
   music, engine, nitro and impacts all play.
2. **Done (tasks 22, 24, 25):** release qualification, 64/64 races driven to the
   finish with the release defaults (docs/VALIDATION.md). The tier-3 floor seeds,
   the weather margin smear, cross-session quickstates (patch 0018) and the
   skipped scene init at `$650C` (core-0004 exact stack delta) are fixed. Not
   driven live: a 2P race.
   **In progress (task 26, `tg2-playtest-fix`):** owner playtest of e586c00.
   RACE SOUND page empty and then garbled; P2 cannot press Start (P2 device 0
   by default); the feedback replay diverges at execution 0; `[DUAL-DBG]` log
   noise. After it merges: a play build for the owner, then step 4.
3. Task 21 (crop + HUD Edges fix) merged 2026-11-06. README screenshots refreshed without bands (2026-11-07).
4. CI `platforms=all` dry run → owner playtest of the candidate, **including on his Steam Deck** (the AppImage from the dry-run artifacts; controller only, Game Mode) → tag
   `v0.1.0` with the owner's go-ahead → the owner publishes the draft and
   submits to Quiver.

Release bugs from owner playtests (2026-11-07):
- **Fixed:** with BOTH persisted in `settings.ini`, the music was silent from
  boot (patch 0011 released the Z80 from BUSREQ while routing, so the music
  mailbox could be read mid-write). BUSREQ now halts the Z80 in BOTH too;
  `tools/verify_both_boot.py` boots BOTH/MUSIC/SFX from a clean settings dir and
  requires the title/menu music to correlate >= 0.99 (0.9952 both vs music).
- **Fixed (task 22):** the tier-3 floor ran `$00E46C` / `$00445A` in real play
  (discovery seeds).
- **Fixed (task 22):** rain/snow particles smeared into long lines across the
  widescreen margins.
- **Fixed (task 24, 33f4c5e):** from Greece onward a scene-init continuation at
  `$650C` was skipped (the stack delta missed `add.w (sp)+,d0`, so a plain
  RTS read as a jump target). Patch `core-0004`, `tools/check_stack_delta.py`.
- **Fixed (3a92c4f):** "Internal resolution" did nothing visible for TG2,
  because the game renders through its own `GameVideo` at native resolution.
  Patch 0017 hides the row; high-resolution rendering may bring it back.
- **Fixed (2e42151):** with the HUD at edges, the overtake popup ("18TH"
  rising over the car) was carried to the right edge with the right cluster.
  Only the cluster columns move now.
- **Fixed (task 25):** loading a save state in a race froze it at "GO!" in a
  fresh process (picture static, guest clock still running). Cause: the save
  interrupted an arbitrary instruction and TG2 has no shared WaitForVint park,
  so the loader restored the CPU inside the new process's boot chain. Engine
  patch 0018 + `game/tg2_spec.c` now park quickstates at a declared per-frame
  boundary and resume the game fiber at that boundary; races and the title/main
  menu resume live, screens without a declared loop refuse the save with a
  clear message. Same-process rewind still works.
- **Fixed (2026-11-07, owner playtest on macOS):** a race loaded from a save
  state ended and went back to the main menu instead of the results and the
  next race, even when the player qualified. Cause: the load restarted the race
  loop with a reset stack, and when it returned the engine fell back to the
  top-level loop (`$001E18`, title) instead of the race's caller (`$001E82`,
  results, qualification and race index + 1). Engine patch 0021 keeps the
  restored stack and continues the guest's return addresses; `$001E82` and
  `$001E1E` are seeded entries. Evidence in VALIDATION.md, "Quickstate resume
  continues the guest's callers".
- **Open (owner, 2026-11-07): visible save-state feedback.** Saving gives no
  feedback the player can see: `host_state_notice` only rewrites the window
  title for 5 s ("Top Gear 2 - State saved"), which fullscreen, the Steam Deck
  and a hidden title bar never show. Draw the notice in the game picture,
  top left, e.g. "STATE SAVED TO SLOT 1" (and the load/refusal messages the
  same way).
- Added for the owner (patch 0016): P freezes the frame without the game's
  PAUSE screen and pauses audio output (screenshot mode); P or Esc resumes.

Deferred until after 0.1.0: the clean FM option and music/SFX volumes, task
17 (widescreen menus), and the Auckland music re-attack divergence.

**Enhancement idea for after 0.1.0 (owner, 2026-11-06): gradient skies.** Race skies
with a vertical gradient similar to the SNES version's look, not limited to the
Genesis palette. Draw it ourselves in the game-owned renderer; copy no SNES
assets. Derive it from the game's own sky colour per track, weather and time of
day: night, fog, rain and snow need their own ramps. Anchor it to the moving
horizon on hills, and handle tunnels, flashes and split screen. Make it an
option; with it off, the picture stays byte-identical. A worker should first
answer how the sky is drawn today: the backdrop colour or background-layer
tiles, and whether raster palette changes already occur.

**Enhancement idea for after 0.1.0 (owner, 2026-11-07): NTSC filter and scanlines.**
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
- It conflicts with high-resolution rendering, which aims at the opposite
  look, so make them mutually exclusive or order them clearly.
- Check the license before vendoring: Blargg's libraries are LGPL 2.1, and
  static linking in a PolyForm-NC project needs care. Also measure the CPU cost
  on the 3500U and on the Deck.

**Enhancement idea for after 0.1.0 (owner, 2026-11-07): high-resolution rendering.**
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
Later extension (owner, 2026-11-07): redraw the menus, fonts and HUD art in
high resolution. Do it as a data-driven replacement pack keyed by the
original tile/pattern content (like Dolphin or RT64 texture packs), so the
game logic is untouched, missing entries fall back to the original art, and
the pack is optional. The redraws must be faithful HD versions of the
originals, not new designs. It pairs with task 17 (widescreen menus). Acceptance test (owner):
downsampling each HD asset back to the original size must give art very close
to the original tile. A tool scores every pack entry: box-filter downsample,
quantise to the Genesis 9-bit palette, then compare per pixel against the
original, with a threshold. Entries that fail are rejected. This is the same
idea as the car-colour test: the enhancement must reproduce the stock asset. Before
publishing a pack, decide how to distribute it: it is a derivative of the
game's copyrighted art, so it is a riskier thing to host than code. Make it an option; at 1× with it off, the output stays byte-identical.
First steps: map the LOD tables (pattern sets per object and distance
thresholds), and find which per-line road state is enough to re-rasterise.

**Enhancement idea for after 0.1.0 (owner, 2026-11-07): cheats in the menu.**
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

**Enhancement idea for after 0.1.0 (owner, 2026-11-07): analog control.**
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

**Enhancement idea for after 0.1.0 (owner, 2026-11-06): arbitrary car colours.**
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

## Still in progress

| Task | Worktree | State |
|---|---|---|
| 20b BOTH: second Z80 core for the race SFX image | `tg2-both-dualchip` | **Done.** Patch 0014 runs a second Z80 core (own 8 KB RAM/bank/BUSREQ/reset) only in BOTH; the 68K upload and the PCM command ports are routed to it, so the music driver is untouched. Chip B = 68K engine + SFX PCM, matching SOUND EFFECTS at corr 0.9947; engine, nitro (cmd 4) and impacts (cmd 2/5/7) present; BOTH mix = A+B exactly; 0 pops/dropouts offline and on the null sink; p95 68.9%. |

## Questions for the owner (queued for 09:00)

0. ~~CI minutes~~ Resolved 2026-11-06: the repo is now **public** (unlimited Actions minutes on standard runners). The CI budget policy stays: manual (Linux by default) or `v*` tags only.

1. Is the 50 ms display latency of 60 fps acceptable on the controller?
2. Does BOTH sound acceptable on real speakers? Music notes can be stolen
   by SFX. If not, the next step is a second virtual sound chip just for
   SFX.
3. ~~Is the music tempo steady now?~~ Answered 2026-11-06: no, it's broken (pops, dropouts). See task 15.
4. Previously: Play `~/Games/TG2-play-c27839b/TG2Recomp`, a release-config build of main with every overnight fix.

## Open items

- **Final phase (deferred by the owner):** widescreen for *every* extendable non-race screen (track intro with scrolling scenery, menus, shop, results...). Spec: `docs/tasks/17-widescreen-menu-screens.md`.

- **Approved for after BOTH merges (owner, 2026-11-06):** a small optional audio task. It adds a "clean FM" option
  (ymfm YM3438 variant, no ladder distortion; default stays the stock YM2612 sound) plus separate
  **Music volume** and **SFX volume** sliders in the in-game Esc menu, next to the existing master Volume,
  in every sound mode (owner request). Default 100% stays byte-identical. Classify by source: the Z80
  music driver is music. The 68k FM/PSG engine and the race Z80 SFX image are SFX.
  Rejected: engine samples from other games or versions. Correction from task 20: the engine and
  nitro **are** PCM, a 6.6 kHz DAC player in the race Z80 SFX image (ROM `$0701F6`). The 68k FM
  part is only a drone. So the owner's "better version of the same asset" fits here: band-limited
  resampling of the original PCM instead of the DAC's sample-and-hold. That is post-0.1.0 too. Rejected: replacing the engine sound with samples from other games or versions. The
  engine sound is a 68k FM effect, not a PCM sample.
- Real-device checks: Steam Deck (Gamescope, controller only), Windows,
  Intel macOS. Apple Silicon macOS (27.2) starts and plays into the menus
  after the quarantine step; the launcher ROM pick and a full race still need
  a playtest there (unsigned `.app`; Gatekeeper first-run steps are in
  RELEASING.md).
- Task 22 found that the password `stage` field is the **difficulty**, not a race selector. The game has 64 races (16 countries × 4); task 25 qualified the last 19 by selecting the race index on the game-setup screen, so **all 64 races are driven to the finish**.
- Quiver Launcher listing: the owner submits the project after the first real release (v0.1.0) exists, so
  Quiver can review it. Window screenshot for the form: `~/Pictures/tg2-quiver-screenshot.png` (outside git).
- First public release: the owner decides when to make the repo public.
  Done on 2026-11-06: history rewritten to the noreply e-mail, PolyForm NC license, public README; the repo is now public. `vittau/top-gear-2-private-inputs` must stay private forever.

## For playtests

Release-config build: `~/Games/TG2-play-c27839b/` (ROM next to the binary),
or download the latest `build.yml` artifact. Dev build:
`build-main/TG2Recomp ~/roms/genesis/tg2.bin`.
