# Project status (2026-11-11)

**Next coordinator:** start with [CONTINUATION.md](CONTINUATION.md).
S3 is merged and visually approved; the Linux-only Steam Deck draft is ready.
The owner uses the extracted tar.gz and reported it worked well, with a
regression: Linear Filter still works in the main menu but has no visible
effect during gameplay. [Task 35](tasks/35-linear-filter-highres.md) and the
unified runtime menu ([task 36](tasks/36-unify-runtime-menu-groups.md)) are
reviewed, merged in `87e926b`, and in the new
[Deck draft](https://github.com/vittau/top-gear-2-genesis-pc/releases/tag/untagged-250db4e89d9b27e23c8f).
Linux build/glibc/smoke gates pass. The owner approved the local macOS
filter/menu playtest (“Está tudo certo”). Linear On adds about 4.51 ms CPU
locally at 4×; latest-fix Deck performance still needs measurement.
His report of intermittent missing instruments in race-menu music is fixed
([task 37](tasks/37-intermittent-race-menu-instruments.md)): with BOTH saved,
the boot diverted four bytes of the music driver's octave table to the second
Z80. Merged into `main`; the owner listened and approved it.
Detailed sprites [S4/task 34](tasks/34-highres-s4.md) were owner-approved and
merged in `a8041a2`. Smooth growth [task 39](tasks/39-highres-continuous-actor-size.md)
was owner-approved (“Está ótimo”) and is now the default on
`vittau/tg2-highres-continuous`; stepped remains an internal comparison only.
The same branch now promotes Ayers Rock's ordinary `$96` rock ladder and
has a bounded first-race inventory of the other 13 countries. Actor and stock
regressions pass; the separate Ayers night-road stripe audit fails even with
actors disabled and remains unresolved. See HIGHRES §§14.8/15 and task 39's
handoff for the ready 4×/60-fps play scripts. Poles remain native (task 38).

**v0.1.0 is out** (published 2026-11-08, tag on `f1cb093`; release notes in
`release/v0.1.0.md`). It is a native Top Gear 2 for Windows, Linux/Steam Deck
and macOS, with widescreen, true 60 fps, music and SFX together, save states
and controller-only play. It has been played on Linux (Ryzen 5 3500U) and
macOS (Apple Silicon). The owner also played an older Linux tarball on the
Steam Deck; the latest aspect/logging fixes and S3 still need his Deck test.
Windows and Intel macOS have CI headless smoke evidence only.

Where to look:

- **This file:** what works on `main` today and its known limitations.
- **[ROADMAP.md](ROADMAP.md):** every planned item and owner request after
  v0.1.0. Add new ideas there, not here.
- **[tasks/README.md](tasks/README.md):** index of the task specs and their state.
- **[VALIDATION.md](VALIDATION.md):** the evidence behind every claim below.

## On `main`

| Area | State | Docs |
|---|---|---|
| Native 4:3 baseline | Boot → menus → full 4-lap race → results/shop/next race; 2P split-screen; 33.7-min soak, plus a 43.7-min soak with all options on (16:9 + Edges + 60 fps + Hide overscan, 13 races, SP stable). 0 dispatch misses. | `BRINGUP.md`, `VALIDATION.md` |
| All 64 races | Password codec reversed (`PASSWORDS.md`, `tools/tg2_password.py`). All 16 countries raced for 62 s in Off and 16:9+Edges, 0 manifest entries; rain, night, fog and snow covered. Task 25 drove the last 19 races (index selected from the ROM table on the setup screen) to the finish: 64/64. Nitro = C button. | `VALIDATION.md` |
| Widescreen | Adaptive / 16:9 / 21:9 race renderer: road, background, sprites in the margins. HUD Centered or Edges. Off is byte-identical to stock. | `WIDESCREEN.md` |
| High-resolution S3/S4 | Road/background and detailed actors at 2×/3×/4×, default 1×, restart required. S3/S4 approved and merged; owner-approved continuous growth is now default on the task 39 branch, including Ayers Rock rocks. Other unpromoted country kinds are inventoried; HUD/effects/poles retain native detail. | `HIGHRES.md` §§13–15, `CONTINUATION.md` |
| Widescreen fixes from playtests | Black bands on downhills, the top-window line, tunnel margins (now follow the walls), and the motion-only flicker in 60 fps synthesized frames. Full-presented-frame margin audit: 1019 → 0. | `WIDESCREEN.md` |
| Hide overscan | Default On: crops the 8 top and 16 bottom empty race lines (the top band's stock red marks go with them), so the picture fills the window. Menus, results and split-screen keep their full height. | `WIDESCREEN.md` |
| 60 fps | Stock simulation plus host-only interpolation. Identical WRAM over 16000 frames; 60 pictures/s; no road artefacts; adds 50 ms display latency. | `FRAMERATE.md` |
| Music + SFX (BOTH) | A third RACE SOUND value, **BOTH**, in the game's own SOUND menu. Stock MUSIC and SFX WAVs are byte-identical to stock. Music on virtual chip A, the 68K engine and the race SFX PCM on chip B with a second Z80 core (patch 0014), so music and SFX no longer steal each other's channels. | `AUDIO.md` |
| Performance + audio pacing | Release build at 16:9+Edges+60 fps uses p95 60.5% of the frame budget on a Ryzen 5 3500U. Guest clock is exact (late frames repay their tick; overdue frames drop 60 fps synthesis, never guest time). Music is sequenced by a free-running Z80 program, so tempo follows guest time: under two CPU burners, -6.8 ms audio drift per 60 s, 0 underruns. DRC bounded to ±0.2%. Logs/settings/saves now go next to the executable (they used to go to `~/.local/bin`). Engine patches 0004-0006. | `PERFORMANCE.md` |
| Real-device audio (owner bug) | Root cause: every host hitch was concealed and then became permanent latency, until the ring cap cut audio in bursts (delays, then pops). Fix: a cushioned, latency-bounded DRC (100 ms target, 250 ms ring, ±0.5%, latency bound 160 ms, quick resume). Measured on a PipeWire null-sink recording: 4×3-min races at 0 pops, dropouts and underruns. Needs the owner's listening confirmation. | `PERFORMANCE.md` §10 |
| BOTH fix + music tempo | BOTH is now session-owned host state (it engages on every route, persisted as `[mods.racesound]`), and its text uses the game's own menu font. Exact audio sample clock (patch 0008; it was -402 ppm). Tempo-stable slow-integral DRC (patch 0009): speed swings 1233 → 37 ppm/s. Reference pipeline: headless Genesis Plus GX renderer (`tools/gpgx_render.c`). A/B files in `~/Music/tg2-ab/`. | `AUDIO.md` §6-7, §11-12 |
| Music tempo (owner bug) | Root cause: the port re-armed the YM2612 timer B on every `$27` reload instead of letting it run free (patch 0010). Title theme went from -6.99% ±2% to +0.194% flat. **Owner confirmed 2026-11-06: music speed is great.** All 4 owner VGM rips align at +0.194%, and Genesis Plus GX agrees with the port to 0.02%, so the residual is the rips' own time base. Logic match vs the VGMs: 89.7–99.5% (open item: Auckland ch1-2 re-attacks). | `AUDIO.md` §11 |
| Race band crop + HUD Edges fix (owner request) | Hide overscan (default On) now crops the race's empty 8 top / 16 bottom lines: 256×200 Off, 356×200 16:9, 467×200 21:9. A per-frame guard crops only single-player race pictures whose bands are empty. Menus and split screen are unchanged. Engine patch 0012 (`present_window`). HUD Edges map/marker split fixed (the HUD moves to sprites on frames 3409–3585). 16 tracks, 181 race pictures checked; margin audits 0; Off hashes unchanged. | `WIDESCREEN.md` |
| Quit from the menu (owner request) | The in-game menu (Esc / Back+RB) has a **Quit game** row (two presses) that exits through the normal window-close path, so settings are saved. Meant for controller-only play on Steam Deck. Engine patch 0013. Compiles; needs a hands-on check in the next play build. | |
| Options | Widescreen / 60 fps / HUD / Hide overscan in the launcher and the in-game overlay (gamepad: Back+RB), persisted in `settings.ini [mods.*]`. | `RELEASING.md` |
| CI | `build.yml`: Linux (glibc ≤ 2.35, Deck), Windows x64, macOS universal2. The ROM comes from the private repo via deploy key; artifacts are gated against ROM or generated C. | `RELEASING.md` |
| Release packaging | macOS `TG2Recomp.app` (universal2; installed in Applications it imports the picked ROM into Application Support, portable it finds the ROM beside the `.app`), single-file Linux `TG2Recomp-x86_64.AppImage` plus tarball, Windows zip. `v*` tags build a **draft** release with SHA256SUMS. Validated on CI run 42222837085: every platform smoke-ran 600 frames with the ROM auto-detected. | `RELEASING.md` |
| Save states | Shift+F1–F9 save; F1–F6 and F9 load (F7 is the state browser, F8 rewind); also from the Esc menu. States survive a restart and resume live in races, on the title and on the main menu; after a load the race flow continues to results and the next race. Notices in the picture (`STATE SAVED TO SLOT 1`...). A save between races is written at the next race start; the password and new-game setup screens refuse it. Engine patches 0018, 0021–0024, 0027. | `VALIDATION.md` |
| Task 26 playtest fixes (after v0.1.0) | RACE SOUND page builds from the session choice (no black first open, no garbling), player 2 live out of the box (patch 0020), recorded BOTH survives a feedback replay, no `[DUAL-DBG]` log noise. Merged 2026-11-09; not in the v0.1.0 binaries. | `VALIDATION.md` |
| Deck feedback: device aspect | Adaptive follows the actual output: a gamescope/Steam Deck session starts borderless fullscreen at the panel size, and a windowed start takes the desktop's aspect instead of a fixed 16:9. A 16:10 panel now fills with a 320×200 race picture (1280×800) instead of a letterboxed 16:9 one; fixed aspects and Widescreen Off still letterbox as chosen. Engine patches 0045. Needs a real Deck run. | `WIDESCREEN.md`, `VALIDATION.md` |
| Deck feedback: no logs in normal use | The feedback replay (Diagnostics) is off by default; a release-profile session writes nothing at all next to the executable. `--debug` turns the replay and the runtime evidence on for one launch, and a **Diagnostics (bug report)** row in the Esc menu (plus the launcher Mods page) persists the same choice for the next launch. Pre-existing `settings.ini` files migrate to version 2 with diagnostics off. Engine patches 0046–0049. | `README.md`, `VALIDATION.md` |
| ROM | Auto-detected by CRC next to the executable, whatever the file name. An installed macOS app also searches Application Support, where it imports the ROM picked in the launcher (engine patch 0019). | `BRINGUP.md` |

Engine changes live as patches in `patches/segagenesisrecomp/`. The
submodule pin is upstream `dd520f1`.

## Known limitations

- Windows and Intel macOS lack real-device playtests. The new Linux S3 draft
  still needs the owner's Steam Deck performance, controller and visual check.
- Full N× + 60-fps qualification is S6; live scale switching is S7. The S4
  review branch replaces S3's same-colour mask ambiguity with explicit
  coverage; poles remain native, with their visible mismatch mapped in task 38.
- Menus, the shop and the results screens are shown in their original width,
  centred.
- Save states are refused on the password and setup screens, and deferred to
  the next race start between races.
- A loaded 2P race has only been shown resuming under the game's PAUSE.
- 60 fps adds 50 ms of display latency (owner has not said whether that is
  acceptable on a controller).

## For playtests

Current Deck test: [draft deck-s3-20261110](https://github.com/vittau/top-gear-2-genesis-pc/releases/tag/untagged-fb40acbd6ff0b4a9d90d),
target `a205759`, Linux-only [green CI](https://github.com/vittau/top-gear-2-genesis-pc/actions/runs/42842299392).
Use the tar.gz folder layout the owner already uses. Its binary and AppImage
need glibc 2.34 (within the ≤2.35 target), pass 600-frame smoke tests, and
contain no ROM/generated C/debug payloads. The draft is not published.

Stable release: v0.1.0. Dev build:
`build-main/TG2Recomp ~/roms/genesis/tg2.bin`.

## History: the road to v0.1.0

Kept as a record. Statuses below are as they were written (2026-11-06/07);
anything still open has moved to [ROADMAP.md](ROADMAP.md).

### Priority: first playable release (owner, 2026-11-06)

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
- **Fixed (patches 0022, 0023):** saving gave no feedback the player could
  see (only the window title). Notices are now drawn in the picture, top
  left, e.g. "STATE SAVED TO SLOT 1", plus the load and refusal messages.
- Added for the owner (patch 0016): P freezes the frame without the game's
  PAUSE screen and pauses audio output (screenshot mode); P or Esc resumes.

### Last in-progress table (2026-11-06)

| Task | Worktree | State |
|---|---|---|
| 20b BOTH: second Z80 core for the race SFX image | `tg2-both-dualchip` | **Done.** Patch 0014 runs a second Z80 core (own 8 KB RAM/bank/BUSREQ/reset) only in BOTH; the 68K upload and the PCM command ports are routed to it, so the music driver is untouched. Chip B = 68K engine + SFX PCM, matching SOUND EFFECTS at corr 0.9947; engine, nitro (cmd 4) and impacts (cmd 2/5/7) present; BOTH mix = A+B exactly; 0 pops/dropouts offline and on the null sink; p95 68.9%. |

### Questions for the owner (2026-11-06)

0. ~~CI minutes~~ Resolved 2026-11-06: the repo is now **public** (unlimited Actions minutes on standard runners). The CI budget policy stays: manual (Linux by default) or `v*` tags only.

1. Is the 50 ms display latency of 60 fps acceptable on the controller?
2. Does BOTH sound acceptable on real speakers? Music notes can be stolen
   by SFX. If not, the next step is a second virtual sound chip just for
   SFX.
3. ~~Is the music tempo steady now?~~ Answered 2026-11-06: no, it's broken (pops, dropouts). See task 15.
4. Previously: Play `~/Games/TG2-play-c27839b/TG2Recomp`, a release-config build of main with every overnight fix.

### Other notes

- Task 22 found that the password `stage` field is the **difficulty**, not a race selector. The game has 64 races (16 countries × 4); task 25 qualified the last 19 by selecting the race index on the game-setup screen, so **all 64 races are driven to the finish**.
- Quiver Launcher listing: the owner submits the project after the first real release (v0.1.0) exists, so
  Quiver can review it. Window screenshot for the form: `~/Pictures/tg2-quiver-screenshot.png` (outside git).
- First public release: the owner decides when to make the repo public.
  Done on 2026-11-06: history rewritten to the noreply e-mail, PolyForm NC license, public README; the repo is now public. `vittau/top-gear-2-private-inputs` must stay private forever.
