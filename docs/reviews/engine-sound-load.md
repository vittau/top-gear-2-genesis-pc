# Engine sound after loading a race quickstate

Owner report: with **RACE SOUND = BOTH**, save a quickstate during a race, go
back to the game's menus, then load that state — the race resumes but the car's
engine sound is missing; other sound effects play. Pre-existing, not introduced
by the phase-D review.

Conclusion: the quickstate *file* carried only the canonical virtual sound chip.
BOTH runs the race SFX on a second virtual YM2612 + SN76489 pair (chip B), so a
state loaded by a process that was not already running that race restored the
68K/Z80 machine into a pair of **idle** effects chips. Every sound that keys
itself during the race still played; the engine sound — started once by race
init (`$025418`) and kept alive by channel/envelope state inside the chip — did
not. Patch `0015` puts chip B into the quickstate; the resumed race's effects
layer now matches the uninterrupted race. Stock SOUND EFFECTS was never
affected (it uses chip 0, which was always in the format).

## 1. Reproduction

Deterministic, headless, no TCP server, one process at a time, under the shared
machine lock. Two input scripts over the standard baseline route
(`game/baseline-route.json`):

```
save.input : <route> HOLD B / WAIT 240 / SAVE_STATE race.state / WAIT 200 / RELEASE / EXIT
load.input : WAIT 600 / LOAD_STATE race.state / HOLD B / WAIT 200 / RELEASE / EXIT
```

The `save` process never leaves the race; the `load` process is a *fresh*
process sitting at the title/menus (i.e. the state matrix's "load from menu"),
which is exactly the owner's situation after going back to the menus. Both
captures stop at the same guest frame, so their last 200 frames cover the same
race time.

```sh
# reference (uninterrupted race) and resumed capture, BOTH mode
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy SDL_RENDER_DRIVER=software \
GENESIS_AUDIO_CHIPDUMP=build/exp-engine/w200/save/chip TG2_RACE_SOUND=both \
GENESIS_USER_DIR=$PWD/build/exp-engine/w200/save/ \
  build/TG2Recomp ~/roms/genesis/tg2.bin --no-launcher --widescreen off \
  --input-script build/exp-engine/hash/save.input --max-frames 8000 \
  --wav build/exp-engine/w200/save/run.wav --turbo --fresh-evidence
# ... same for load.input / --max-frames 2000 into .../load/
```

`GENESIS_AUDIO_CHIPDUMP` writes `<prefix>A.wav` (music chip) and
`<prefix>B.wav` (effects chip), which is what makes the two layers measurable
separately. `tools/regression.py` now performs exactly this pair of runs.

## 2. Root cause, with evidence

### 2.1 The state file

`runner_save_state_file()` writes, in order: glue state, 68K work RAM,
`machine_save_state()` (VDP + bus + both Z80 cores + clocks), then
`ym2612_save_state()` and `psg_save_state()`. The two virtual chips live in the
audio mixer, not in the machine image, so those two calls are the only carrier
for their registers. Both wrote **chip 0 only**:

```c
/* ym2612_ymfm.cpp, before patch 0015 */
/* Only the canonical chip 0 is in the state format; the second chip is
 * re-synced from the next frame of 68K writes after a load. */
```

That assumption is wrong for anything sustained. A driver that resumes in the
middle of an effect re-sends frequency/volume writes and PCM data, but it does
not re-send the key-on that started the effect, nor the envelope, LFO, phase,
pan and DAC state that the resuming driver assumes is already loaded.

### 2.2 What the resumed race actually did

Measured on the pre-fix build, BOTH, load-from-menu, 400 frames of the race
starting at the resume point, compared against the uninterrupted reference at
the same guest frames (`build/exp-engine/wavcmp.py`, per-chip dumps):

| Layer | reference RMS | resumed RMS | ratio | sample correlation |
|---|---:|---:|---:|---:|
| chip A (music) | 1481.48 | 1481.37 | 0.99992 | — |
| **chip B (race SFX)** | **1443.25** | **594.91** | **0.41** | **0.0016** |
| main mix (A+B) | 2029.20 | 1635.78 | 0.81 | 0.67 |

In quiet windows the resumed chip B output was a *constant* 380.0 RMS — the
documented idle-YM2612 DC bias (AUDIO.md §10), i.e. the chip was silent and
unfed. Loud windows were 0.5–0.8 of the reference: the one-shot FM effects that
key themselves. Chip A matched to 0.008 %, before and after the fix, so the
music layer was never involved.

**The machine itself resumed correctly.** `GENESIS_AUDIO_WRITEDUMP` over the
same frames gives an identical writer histogram — the 68K SFX engine and the
second Z80 PCM player emit the same writes at the same guest frames:

| Writer | reference | resumed |
|---|---:|---:|
| `$0CB2` (music driver) | 7854 | 7854 |
| `$068E` / `$067F` (SFX PCM data / `$2A` select) | 4322 / 4322 | 4282 / 4282 |
| `$0C4F`/`$0C4C` (music driver) | 1555 / 1555 | 1555 / 1555 |
| `$FFFF` (68K FM engine) | 420 | 420 |
| `$04B7`/`$04CF`/`$04DB` (PCM sample start) | 20 / 20 / 20 | 21 / 21 / 21 |

and the streamed DAC data values are identical, sample for sample (shifted by
one sample, the resume boundary). `GENESIS_AUDIO_SFXPCM_TRACE` likewise reports
the same engine-loop/gear/nitro/impact commands. So this was never a routing,
upload or command problem — only the chip's own state was missing.

### 2.3 Single-session proof that it is the chip state

Same build, same state file, same host options, two ways to load it:

| Case | chip B RMS (resumed / reference) | ratio |
|---|---:|---:|
| **rewind** (save, race 300 frames, load in the *same* process) | 1395.27 / 1393.82 | **1.001** |
| **load from menu** (fresh process at the menus) | 594.91 / 1443.25 | 0.41 |

The machine image is identical in both; the only difference is whether the chip
models already held the race's state. That is the defect, and it is exactly what
the code comment above admitted.

### 2.4 Stock SOUND EFFECTS is not affected

Same experiment in SFX mode (single chip, chip 0, which was always saved):
RMS 1393.12 / 1443.15 = **0.965** with the engine sound present. The residual is
the same sub-frame/DC difference the music chip shows; nothing is missing.

## 3. Fix

Engine patch
[`0015-save-the-both-effects-chip-in-quickstates-and-rewinds.patch`](../../patches/segagenesisrecomp/0015-save-the-both-effects-chip-in-quickstates-and-rewinds.patch)
(new row in the patch README):

* `ym2612_save_state`/`psg_save_state` write **chip 0 exactly as before**, then
  chip 1 as an **optional, tagged, length-prefixed trailer**
  (`"1YM1"`/`"1PS1"` + version, then the same layout chip 0 uses). The loaders
  look for the tag; when it is absent they rewind the stream and leave chip 1
  untouched, which is precisely the old behaviour. Nothing is reinterpreted: an
  old file's PSG section can never be read as a chip-1 YM blob.
* The host state container (`runner/host_state.h`) validates sections 1–3 by
  size as before, and lets sections 4/5 (YM, PSG) be *shorter* than this build
  writes, because the readers themselves validate their bytes. A corrupt or
  truncated payload therefore still fails in the staged read; only a
  legitimate older layout is accepted.
* Rollback snapshots (`ym2612_rb_save/rb_load`, `psg_rb_save/rb_load`) carry
  chip 1 too, in the same shape, so a rewind inside BOTH restores the effects
  chip instead of leaving it at the moment being rewound away from. A
  chip-0-only image still loads.
* No game-side change was needed, and no generated C was touched.

Compatibility was verified both ways. Using the owner's own state
(`~/.cache/tg2-evidence/native_save_2.bin`, copied, original untouched,
`GRHOST2`, build `tg2-0.1.0-bd3074d2-state1`, sections
`16/94/65536/98880/833/52`) and a state written by the base build with the same
script:

| Load of an old-format state | base build | fixed build |
|---|---|---|
| BOTH: whole-run WAV SHA-256 | `d85ede09…0cfb2` | `d85ede09…0cfb2` (**identical**) |
| BOTH: frame hashes | — | identical |
| SFX: whole-run WAV SHA-256 | `8a7874f5…08e9` | `8a7874f5…08e9` (**identical**) |
| SFX: frame hashes | — | identical |
| base-build-saved state, BOTH | `8bfcdc23…0fc6` | `8bfcdc23…0fc6` (identical) |
| base-build-saved state, SFX | `335d1be2…86ec` | `335d1be2…86ec` (identical) |

So an old quickstate loads exactly as it did before — chip 1 left alone, i.e.
the engine sound still missing in BOTH from such a file until it is re-saved —
while a state saved by the fixed build restores chip 1. Both files loaded with
exit 0 in both modes, with sane pictures and audio.

Rewind/rollback: `GENESIS_RB_PROBE=120:8 GENESIS_RB_SELFTEST=3000` over a BOTH
race reports every pass `OK`, the section self-test reports
`fm len=1674 flip@8 … restored=1 OK` and `psg len=112 … OK` (chip 0 + tag +
chip 1), and the rewind ring initialises with the larger snapshot
(`60 snapshots … snapshot size 167670 bytes`).

Applied with `tools/apply-engine-patches.py --as-commits` → commit → `--export`
(the usual maintenance flow); the patch carries the repository's commit
identity. The submodule pin is unchanged and no engine branch was pushed.

## 4. Verification

### 4.1 The resumed effects layer now matches the uninterrupted race

BOTH, load-from-menu, after the fix:

| Measurement (same method as §2.2) | before | after |
|---|---:|---:|
| chip B RMS ratio, 400-frame window | 0.41 | 0.97–1.00 |
| chip B per-20-frame RMS ratios, first 3.3 s | 0.2–0.6 | **0.98–1.03 (10/10 windows)** |
| chip B sample correlation, 2 s after the resume | 0.0016 | 0.94 |
| chip A max sample difference, 400 frames | — | **0 (sample-exact)** |
| chip B idle-window output | constant 380 (silent) | live programme |

The remaining `0.97` on the *whole-window* RMS is a DC term: per-window ratios
at 20-frame resolution are 1.00 (±3 %), and chip A is sample-identical, so the
music clock, the frame split and the sample counts are exact.

### 4.2 Coverage across modes and load contexts

Every case below is save-then-load with the same scripts; "effects layer" is
chip B in BOTH and the whole capture in the single-chip modes.

| Case | Result |
|---|---|
| BOTH, load from the menus (fresh process) | effects RMS ratio 1.00, 10/10 windows inside ±20 % |
| BOTH, load during a *different* race (route finishes race 1, starts race 2, then loads race 1's state) | effects RMS ratio 1.00, 10/10 windows |
| BOTH, load in the same process (rewind 300 frames) | engine sound present (chip B 1.001 of the reference) |
| SOUND EFFECTS, load from the menus | ratio 1.00, 10/10 windows (stock path; was never affected) |
| MUSIC, load from the menus | main WAV **sample-identical** to the uninterrupted race at a one-frame offset (correlation 1.000000 over 200 frames, equal RMS, `diff_rms` 0.0), and the stock game plays no engine sound in MUSIC: the run's `GENESIS_AUDIO_SFXPCM_TRACE` file is never created because the 68K SFX engine issues no PCM command at all |

### 4.3 New regression case

`tools/regression.py` gained `off-load-both` and `off-load-sfx`: a save run and
a fresh-process load run per case, both stopped 200 frames after the save/resume
point, compared by `tools/tg2_state_audio.py` (20-frame RMS windows of the
effects layer; alignment-free, because the resume boundary sits between frame
flushes). The case **raises before comparing goldens** if the layer is missing
or mismatched, then records the frame hashes of the resumed run, both WAV
SHA-256s and the measured ratios in `tools/regression-golden.json`.

Old code (patch stack without 0015, same scripts, `build-pre/TG2Recomp`):

```
off-load-both: resumed chipB does not match the uninterrupted race:
  rms 1564.2 vs 930.9 (ratio 0.6), windows inside 0/10
  [0.608, 0.301, 0.247, 0.785, 0.631, 0.667, 0.729, 0.604, 0.289, 0.29]
  -> exit 1
off-load-sfx : 13 frames, mix RMS 1567.0/1564.2 (ratio 1.0), windows 10/10
  -> exit 0
```

After the fix, with the same scripts and binary layout:

```
off-load-both: 13 frames, chipB RMS 1567.5/1564.2 (ratio 1.0), windows 10/10
off-load-sfx : 13 frames, mix   RMS 1567.0/1564.2 (ratio 1.0), windows 10/10
```

So the BOTH case fails on the old code and passes on the fix, while the stock
SOUND EFFECTS case passes on both — exactly the reported scope — and it also
pins that stock path against future regressions.

### 4.4 Existing goldens unchanged

`tools/regression.py --uncapped --record` against the pre-existing
`tools/regression-golden.json`:

* the ten original entries (784 frame hashes, ten WAV hashes, sixteen SOUND-page
  screenshot hashes) are byte-identical — the new file only adds the two load
  cases;
* every manifest (`dispatch_misses`, `floor_coverage`,
  `interior_label_misses`, `floor_unsafe`) is zero in every run, including the
  new save/load runs;
* the documented BOTH WAV SHA-256 `171df2ef…d72f97` still appears for
  `off-both`, `on-both` and both live-race cases, and MUSIC/SFX keep
  `431338f5…`/`1d0ab92b…`;
* re-run after the compatibility rewrite of patch 0015, in the dev build
  (`build/reg-verify-dev2`) and in the trace-OFF release build
  (`build/reg-verify-rel2`): both print
  `PASS: all frame, WAV and SOUND-page screenshot hashes match; all manifest counts zero.`
  and exit 0, with the recorded golden unchanged. The chip-1 payload lives in
  the state *file* and in the mixer, so no golden byte moved.

(Full command list and exit codes in §6.)

## 5. Unverified / known residuals

* **Real hardware and ears.** Everything here is measured on per-chip WAV
  captures and register/write dumps; the owner still has to listen to it.
* **Linux, Windows, Steam Deck and CI.** Only this Apple-silicon development
  build was exercised; no CI run was dispatched (per `AGENTS.md`).
* **Longer resumes drift slightly, in both modes.** Beyond roughly 5 s after the
  resume the resumed race and the uninterrupted one stop being sample-identical
  (per-20-frame ratios 0.8–1.1 on individual windows) while the level stays
  within 10 %. The frame-picture hashes show the same thing: the resumed run
  matches the reference only sporadically a few seconds in. That is a
  pre-existing property of resuming the simulation (nothing in this change can
  influence the 68K), it also happens in stock SOUND EFFECTS, and the new
  regression therefore asserts the first 3.3 s of the effects layer with a
  ±20 % per-window / ±10 % whole-window tolerance rather than exact bytes.
* The `YmTimerState` status model used for 68K/second-core YM reads
  (`genesis_bus.c`, `s_ym68k`) is host state and is still not part of the
  quickstate. It is a plausible contributor to the small residual above; it was
  left alone because it is not needed to restore the engine sound and changing
  the machine-image layout is a separate decision.
* **Old quickstates keep their old behaviour.** They load (bit-identical audio
  and pictures to the base build), but chip 1 is not in the file, so the engine
  sound from such a state is still missing in BOTH until it is re-saved. The
  owner's existing slot 1/2 saves are in this class. Reconstructing the
  effects chip on the fly would mean re-running race init's sound start, which
  is a behaviour change and was not attempted here.

## 6. Commands and exit codes

All builds and captures under the shared lock, ≤3 build jobs, one runtime
instance at a time.

| # | Command | Exit |
|---|---|---:|
| 1 | `git submodule update --init --recursive` | 0 |
| 2 | `flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh` (base build, no 0015) | 0 |
| 3 | reference/load captures for `both` (pre-fix), `sfx`, `rewind`, with `GENESIS_AUDIO_CHIPDUMP` | 0 |
| 4 | `flock … tools/build-linux.sh` after adding the patch (applied 0015) | 0 |
| 5 | reference/load captures for `both` (fixed) | 0 |
| 6 | `python3 tools/apply-engine-patches.py --as-commits` / commit / `--export` | 0 |
| 7 | `flock … python3 tools/regression.py --out build/reg-dev --record --uncapped` (record; ten old entries identical) | 0 |
| 8 | `flock … tools/build-linux.sh … build-pre` with 0015 moved aside (16 patches) | 0 |
| 9 | new load case against `build-pre/TG2Recomp` | 1 (`off-load-both`, expected) |
| 10 | `flock … tools/build-linux.sh` (restores the 17-patch stack) and the trace-OFF release configure/build into `build-rel` | 0 / 0 |
| 11 | `flock … python3 tools/regression.py --out build/reg-verify-dev --uncapped` | `dev=0` |
| 12 | `flock … python3 tools/regression.py --exe build-rel/TG2Recomp --out build/reg-verify-rel --uncapped` | `rel=0` |
| 13 | owner state, copied: load with the base build and with the fixed build, BOTH and SFX; WAVs and frame hashes compared (4 runs each) | 0 / identical |
| 14 | base-build-saved state: same four loads | 0 / identical |
| 15 | `GENESIS_RB_PROBE=120:8 GENESIS_RB_SELFTEST=3000` over a BOTH race | 0, all passes OK |
| 16 | rebuild dev + release after the compatibility rewrite, repeat 11–12 | `dev=0`, `rel=0` |
| 17 | `python3 -m py_compile tools/regression.py tools/tg2_state_audio.py` | 0 |
| 18 | `git diff --check` | 0 |

Evidence directories (not committed): `build/exp-engine/` (reproduction captures
and analysis scripts), `build/reg-dev/` (golden run logs and manifests). WAVs
over 100 MB were deleted after their numbers were extracted; captures are never
committed.

## 7. Files changed

* `patches/segagenesisrecomp/0015-save-the-both-effects-chip-in-quickstates-and-rewinds.patch`
  and its `README.md` row (engine: `runner/audio/ym2612_ymfm.cpp`,
  `runner/audio/sn76489.c`, their headers, `runner/host_state.h`).
* `tools/regression.py` (new load-from-menu cases, `route_lines()` split,
  `file_sha256`), `tools/regression-golden.json` (two new entries),
  `tools/tg2_state_audio.py` (new streaming comparison tool).
* `docs/AUDIO.md` (§8 save states and §10 limitations: chip 1 is an optional
  trailer, rewinds carry it, old states keep their behaviour),
  `docs/CONTINUATION.md` (evidence list).
