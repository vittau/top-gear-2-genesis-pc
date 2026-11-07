# Project status (2026-11-06)

Overall estimate: about **88%** of the goal, which is a native Top Gear 2
on Windows, Linux/Steam Deck and macOS, with widescreen and true 60 fps,
plus music and SFX together. Everything below has been verified headlessly.
The owner has played two short sessions (Linux, Ryzen 5 3500U).

## On `main`

| Area | State | Docs |
|---|---|---|
| Native 4:3 baseline | Boot → menus → full 4-lap race → results/shop/next race; 2P split-screen; 33.7-min soak, plus a 43.7-min soak with all options on (16:9 + Edges + 60 fps + Hide overscan, 13 races, SP stable). 0 dispatch misses. | `BRINGUP.md`, `VALIDATION.md` |
| All 16 tracks | Password codec reversed (`PASSWORDS.md`, `tools/tg2_password.py`). All 16 countries raced for 62 s in Off and 16:9+Edges, 0 manifest entries; rain, night, fog and snow covered. Nitro = C button. | `VALIDATION.md` |
| Widescreen | Adaptive / 16:9 / 21:9 race renderer: road, background, sprites in the margins. HUD Centered or Edges. Off is byte-identical to stock. | `WIDESCREEN.md` |
| Widescreen fixes from playtests | Black bands on downhills, the top-window line, tunnel margins (now follow the walls), and the motion-only flicker in 60 fps synthesized frames. Full-presented-frame margin audit: 1019 → 0. | `WIDESCREEN.md` |
| Hide overscan | New option, default On: blanks the stock red marks in the top band, in every mode. | `WIDESCREEN.md` |
| 60 fps | Stock simulation plus host-only interpolation. Identical WRAM over 16000 frames; 60 pictures/s; no road artefacts; adds 50 ms display latency. | `FRAMERATE.md` |
| Music + SFX (BOTH) | A third RACE SOUND value, **BOTH**, in the game's own SOUND menu. Stock MUSIC and SFX WAVs are byte-identical to stock. Limitation: a shared-chip mix, so music notes can be stolen by SFX; a clean second virtual chip is future work. | `AUDIO.md` |
| Performance + audio pacing | Release build at 16:9+Edges+60 fps uses p95 60.5% of the frame budget on a Ryzen 5 3500U. Guest clock is exact (late frames repay their tick; overdue frames drop 60 fps synthesis, never guest time). Music is sequenced by a free-running Z80 program, so tempo follows guest time: under two CPU burners, -6.8 ms audio drift per 60 s, 0 underruns. DRC bounded to ±0.2%. Logs/settings/saves now go next to the executable (they used to go to `~/.local/bin`). Engine patches 0004-0006. | `PERFORMANCE.md` |
| Real-device audio (owner bug) | Root cause: every host hitch was concealed and then became permanent latency, until the ring cap cut audio in bursts (delays, then pops). Fix: a cushioned, latency-bounded DRC (100 ms target, 250 ms ring, ±0.5%, latency bound 160 ms, quick resume). Measured on a PipeWire null-sink recording: 4×3-min races at 0 pops, dropouts and underruns. Needs the owner's listening confirmation. | `PERFORMANCE.md` §10 |
| BOTH fix + music tempo | BOTH is now session-owned host state (it engages on every route, persisted as `[mods.racesound]`), and its text uses the game's own menu font. Exact audio sample clock (patch 0008; it was -402 ppm). Tempo-stable slow-integral DRC (patch 0009): speed swings 1233 → 37 ppm/s. Reference pipeline: headless Genesis Plus GX renderer (`tools/gpgx_render.c`). A/B files in `~/Music/tg2-ab/`. | `AUDIO.md` §6-7, §11-12 |
| Music tempo (owner bug) | Root cause: the port re-armed the YM2612 timer B on every `$27` reload instead of letting it run free (patch 0010). Title theme went from -6.99% ±2% to +0.194% flat. **Owner confirmed 2026-11-06: music speed is great.** All 4 owner VGM rips align at +0.194%, and Genesis Plus GX agrees with the port to 0.02%, so the residual is the rips' own time base. Logic match vs the VGMs: 89.7–99.5% (open item: Auckland ch1-2 re-attacks). | `AUDIO.md` §11 |
| Options | Widescreen / 60 fps / HUD / Hide overscan in the launcher and the in-game overlay (gamepad: Back+RB), persisted in `settings.ini [mods.*]`. | `RELEASING.md` |
| CI | `build.yml`: Linux (glibc ≤ 2.35, Deck), Windows x64, macOS universal2. The ROM comes from the private repo via deploy key; artifacts are gated against ROM or generated C. | `RELEASING.md` |
| Release packaging | macOS `TG2Recomp.app` (universal2; finds the ROM beside the `.app`), single-file Linux `TG2Recomp-x86_64.AppImage` plus tarball, Windows zip. `v*` tags build a **draft** release with SHA256SUMS. Validated on CI run 42222837085: every platform smoke-ran 600 frames with the ROM auto-detected. | `RELEASING.md` |
| ROM | Auto-detected by CRC next to the executable, whatever the file name. | `BRINGUP.md` |

Engine changes live as patches in `patches/segagenesisrecomp/`. The
submodule pin is upstream `dd520f1`.

## Priority: first playable release (owner, 2026-11-06)

The owner's priority is a first release (v0.1.0) that is playable and has no
major bugs. Release path:

1. **Blocker:** BOTH via the second chip (task 20). If it can't be made clean
   in time, hide BOTH for 0.1.0 instead of shipping noise.
2. **Release qualification** (after task 20): reach every race of every
   country via passwords, including each country's still-unvisited second race,
   and 2-player. Run the release build with the default options. Gate on
   no crashes, empty manifests and no audio glitches.
3. Task 21 (crop the black bands + HUD Edges map split) ships only if it
   merges clean before the release candidate. It doesn't block.
4. CI `platforms=all` dry run → owner playtest of the candidate → tag
   `v0.1.0` with the owner's go-ahead → the owner publishes the draft and
   submits to Quiver.

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
| 21 Crop race black bands + HUD Edges map split (owner request) | `tg2-race-crop` | The owner chose to crop the 8 top / 16 bottom black lines of races when Hide overscan is On. Also fixes the HUD Edges map/marker split. |
| 20b BOTH: second Z80 core for the race SFX image | `tg2-both-dualchip` | Dual-chip BOTH merged: music on chip A, 68k FM on chip B; no shared-chip noise; page re-entry fixed. Missing: the engine and nitro PCM, which run on a Z80 SFX image that needs its own Z80 core. Prototype reverted (the upload side effects stopped both drivers). Resumes when a worker slot frees. If it isn't clean by the release candidate, BOTH ships labelled as missing car sounds, or is hidden. |

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
  macOS (unsigned `.app`; Gatekeeper first-run steps are in RELEASING.md).
- Each country's second championship race is still unvisited (it needs
  progression).
- Quiver Launcher listing: the owner submits the project after the first real release (v0.1.0) exists, so
  Quiver can review it. Window screenshot for the form: `~/Pictures/tg2-quiver-screenshot.png` (outside git).
- First public release: the owner decides when to make the repo public.
  Done on 2026-11-06: history rewritten to the noreply e-mail, PolyForm NC license, public README; the repo is now public. `vittau/top-gear-2-private-inputs` must stay private forever.

## For playtests

Release-config build: `~/Games/TG2-play-c27839b/` (ROM next to the binary),
or download the latest `build.yml` artifact. Dev build:
`build-main/TG2Recomp ~/roms/genesis/tg2.bin`.
