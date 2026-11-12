# Phase A cleanup verification

Branch: `vittau/review-phase-a`, based on `1550a7312d1ef12b2662fd4248dcd4430b5842ad`.
Development host: macOS arm64, Homebrew SDL2, native Release build with trace/reverse-debug enabled.
No CI, tags, release, merge, engine fork, or submodule pin changes.

## Changes and inspection results

- Launcher choices now report their registry name and description. RACE SOUND reports label `RACE SOUND`, the stock/music/effects/Both explanation, and `Sound effects`, `Music`, `Both` choices. HUD reports its own HUD text.
- Both volume features now report `enabled=1`, `option_count=1`; their existing integer descriptors report labels `Music volume` / `SFX volume`, range 0–100, step 5, default/current 100. This was a real launcher defect: `launcher_imgui.cpp` iterates `feature.option_count` before calling `feature_option_get`, so the prior zero hid the descriptors. This is verified from the compiled code path, without a visible launcher session.
- Development builds default to three jobs and use the documented outer-wrapper convention: `flock ~/.cache/tg2-heavy.lock tools/build-linux.sh`. The script does not acquire this lock internally, so callers following AGENTS.md cannot deadlock on a nested lock. Linux/macOS release shell builders also default to three jobs; CI supplies explicit `--jobs` values, unchanged. The Windows PowerShell default remains eight because its CI call uses that default and this task explicitly preserves CI behavior.
- Python is the sole patch applicator; the shell entry point execs it. Its worktree-local stamp includes patch names/content, all three pins, and resulting engine/core/UI tree hashes, including untracked file contents. A mismatch snapshots all dirty targets before any reset/clean, restores the pins, and applies all 45 patches in sorted order (42 engine, two core, one UI). Recovery commits use the consuming repository's configured identity. Clean application does not require an author configuration.
- Removed the specified write-only audio/actor/row fields and unused menu macros; kept raw handler offsets. Removed unused CHOICE/INT status strings, retired probe controls, the obsolete FM-model probe, and duplicate layout defaults.
- The recompiler initializes the layout to zero, defaults the four omitted address keys to zero, and leaves the absent level-mode array empty (`recompiler/src/game_config.c`, layout parsing). All 35 regenerated C files have identical SHA-256 hashes.
- `tg2_options_apply_env()` already applies HUD/overscan overrides before rendering; the scanline getters now just return that state and are private. The unused HUD-region line argument and the redundant presentation-scale wrapper are gone.
- Every current platform builds the same executable target, which unconditionally calls `recomp_target_launcher_ui`; that helper unconditionally defines `RECOMP_LAUNCHER`. Removed the unreachable no-launcher branches.
- Inspected all four tags (`v0.1.0-rc1`, `v0.1.0`, `v0.2.0`, `v0.3.0`): none writes `tg2.ini` or offers the withdrawn clean-audio options. Some tags contain the migration reader and retired-section filtering, which are what this cleanup removes; the actual old settings format/options never shipped in a tag.
- Only bit 0 of the captured high-resolution row flags is consumed by tools; retained `TG2_ROW_ROAD` and removed the unused classifications. The separate NX road-audit flags are unchanged.
- Removed the vacuous aggregate actor-anchor statistic and its aggregate gate: it subtracted the expression just assigned to the same fields. Kept Python's sampled anchor checks and the existing position, palette, priority, floor and native-row checks.
- Updated the audio status, high-resolution comments, and documentation of patch 0017 as superseded for TG2 by 0050. The patch itself remains.

All explicitly retained diagnostics and bring-up tools remain: stepped actor sizing, actors-off, CONTROL and top-row captures, chip dump, SFX PCM trace, tcp_probe, z80_disasm, tg2_nitro_probe, tg2_password_break, test_app_paths and probe_options. The phase B+ refactors and BOTH rewrite were not performed.

## Untouched baseline and final comparison

Before source edits, initialized the pinned recursive submodules and actually applied the complete engine/core/UI stack with the old Python applicator. Built with:

```sh
flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh
```

Exit 0; log `build/phase-a/baseline-build.log`. The initial final build exits 0; log `build/phase-a/final-build.log`. Review subsequently removed the internal lock from the shell wrapper; see the follow-up verification below. An intermediate compile identified one remaining presentation-scale call in actors; it was updated before the successful build and final captures.

The ignored `build/phase-a/capture.py` converts `game/baseline-route.json` into an exact-frame input script, captures 5,400 frames per case, hashes every 60 frames, and records full stock WAVs. Both baseline and final capture commands run under the shared heavy lock and exit 0. Off means widescreen, race 60 fps, overscan crop and other presentation options off, native scale 1. On means fixed 16:9, race 60 fps and the default overscan crop on, centered HUD, native scale 1. Each is tested in SFX and MUSIC modes.

**All 356/356 framebuffer hashes match** (89 in each of four cases). The off cases retain golden boot/title hashes `60=2A0B972960C5E325`, `300=1131D937D70234FD`. Representative race hashes, identical before/after:

| Case | Frame 3300 | Frame 3600 | Frame 4500 |
|---|---|---|---|
| Off, SFX | A963A0F0F13938F3 | F0FE14786186F4EF | 3CFEED8F6CC6EACC |
| Off, MUSIC | 5E97D0EC79AA383D | F625EB3DCBF36595 | 9B4D7BC9E902D29B |
| On, SFX | 0CA730442D5DD893 | B61E997D1F5AB9FE | B65BBFCD95F04FB5 |
| On, MUSIC | 57F9593D892B8CF9 | 459A09B583349F9C | 02B428F12DCEC6F9 |

All four WAV SHA-256 comparisons match; presentation settings do not change either mode's audio:

- SFX, Off and On: `1d0ab92b32b7f6ba7ac3e63e42f9c0fdfb8d8dff4dbfdbc20b02220faf7442a6`.
- MUSIC, Off and On: `431338f523a9b0d54d1145b38c5a28657b712b9b23b0ca0ae312b15e2486b343`.

Actual manifests in each isolated capture directory report **zero dispatch misses, floor coverage, interior-label misses and unsafe-floor entries**, baseline and final (32 manifests checked). Complete sampled hashes, WAV hashes and counts are in `build/phase-a/{baseline,final}/summary.json`; the automated comparison is `build/phase-a/comparison.json`. WAVs remain ignored; no generated C, ROM, state or capture is committed.

## Patch-application checks

All four required scenarios pass against the real pinned submodules:

1. Missing/old-format stamp rebuilds the full stack; `apply-fresh.log`.
2. A second run is a no-op; `apply-second.log`.
3. After preserving the tree, manual `git checkout -- .` in the engine is detected and the full stack is restored; `apply-checkout.log`.
4. Synthetic tracked edits plus untracked files in **each** engine/core/UI tree are preserved in its own `refs/keep/...` commit before reset. Verified both file contents with `git show` and the restored tree hashes; `apply-dirty.log`, `apply-verification.json`.

A disposable local three-target Git fixture additionally proves clean first application without any Git author configuration and second-run idempotence; `apply-clean-no-author.log`. `tools/apply-engine-patches.py --check`, Python compilation and shell syntax checks exit 0. An initial verification-harness ref-token parsing error was corrected; it was not an applicator failure.

## Probe results

All runs use the shared heavy lock and one headless runtime at a time. Python
commands use the ignored `build/phase-a/venv` (NumPy/Pillow); logs and exact argv
are in `build/phase-a/probe-results-final.json` and `probe-*.log`.

| Probe | Invocation / scope | Exit |
|---|---|---|
| `check_highres.py` | `g1 --out build/phase-a/g1`, all nine boot configurations | 0 |
| `highres_probe.py` | `--out build/phase-a/highres --samples 2 --seconds 8`, actual password-driven race | 0 |
| `check_highres.py` | `drive --out build/phase-a/actors --scale 2 --frames 360 --min-frames 300 --actors --skip-road-audit --race60` | 0 |
| `tg2_live_toggle_probe.py` | Main exercised through `build/phase-a/live-streamed.py`, MUSIC and SFX, both faders, race-sound toggles and cold start; 8/8 checks | 0 |
| `probe_framerate.py` | `build/phase-a/fps-dummy.py build/phase-a/fps-final-turbo`, native 16:9/60 fps, 60 measured moving frames, full road audit | 0 |
| `check_road_artifacts.py` | Full successful turbo audit, standalone repeat | 0 |

The actor run checks 15,777 promoted actors with zero aggregate position,
palette, priority or floor errors; its sampled actor/native-row checks and
margin audit pass. Native-audit failures described below are not hidden by
this actor-only invocation; no analytic NX road qualification is claimed.

The live harness changes only test execution: it uses the engine's existing
`--measure-runtime 9000 --runtime-uncapped` mode with SDL dummy and invokes the
existing glitch detector on bounded, overlapping blocks aligned to its sample
blocks. RMS and exact waveform comparisons still stream the original WAVs.
This avoids the original detector helper's whole-WAV allocation; production
audio and the checked-in probe implementation are unchanged. Its eight cases
pass, with zero detected pops and cold-start half-volume ratios of 0.500.
All four accumulated live manifests contain zero entries across ten sessions
and 71,450 frames. WAV hashes are recorded in `live-wav-hashes.json`; files
over 100 MB were then
deleted. BOTH-mode live toggles and owner listening were not repeated.

Initial probe attempts used an isolated user directory without its own
`debug.ini`, which redirected the TCP lookup; fixed the test environment to
use the worktree's build directory. This Homebrew SDL cannot initialize the
probe's `offscreen` driver. The final native probe uses its intended `--turbo`
mode through an ignored wrapper that substitutes only `SDL_VIDEODRIVER=dummy`;
no renderer/engine code was changed to accommodate the host.

A paced fallback initially returned 1 from the optional native audit because
frames 5501–5503 had no audit files, despite zero geometry/pixel violations.
The base's paced capture passed, and all 5,600 framebuffer hashes plus the WAV
hash matched that initial final capture; audit payloads near the gap match,
while endpoint-frame metadata reflects the skipped history entries. Another
paced repeat skipped different frames, demonstrating why this is unsuitable
for deterministic qualification: the existing `genesis_frame_overdue()` guard
skips presentation synthesis/audit work on host lateness. The final comparison
therefore uses the probe's intended turbo path for both unchanged base game
sources and final sources, against the same fully applied engine. Supplemental
base build exits 0. Both base and final turbo producer runs exit 0, and the
standalone road checker exits 0: 2,503 contiguous audit frames, 1,511 synthesized
frames, 83,732 tested road lines, no missing frames and every violation count
zero. All 2,503 base/final audit files match byte for byte, as do **all 5,600
per-frame framebuffer hashes**, the sampled RAM/VRAM, and the full WAV
(SHA-256 `c5c5d9ced414d61e25220853fd3c7d93756d12bdd5036b46fd16240471a3962a`).
See `native-audit-baseline-comparison.json`, `native-turbo-comparison.log`,
`probe-fps-final-turbo.log` and `probe-road-final.log`. The temporary baseline
source checkout was restored to HEAD, and the qualified final executable was
restored and compared with its saved copy before the final turbo run. There
is no unresolved picture/sound difference or final probe failure. After
comparison, bulk native road exports and per-frame RAM/VRAM dumps were removed;
`native-audit-file-hashes.json` retains all 2,503 qualified audit hashes, and the
summaries, comparison results, scripts, logs and selected screenshots remain.

Verified scope is local development behavior, metadata, patch safety and the
listed directed checks. Linux/Windows execution, release packaging, real
controllers, Deck performance and a visible launcher/playtest were not run.


## Source commits

- `e65b3a4` — Preserve submodule edits and verify applied patch trees.
- `71088d5` — Default local builds to three jobs and lock development builds.
- `487b422` — Fix launcher metadata and retire unshipped option compatibility.
- `9c292b8` — Remove write-only renderer state and retired probe controls.
- `a2c9c7a` — Refresh audio and high-resolution option documentation.
- `8331ace` — Allow clean patch application without a Git author configuration.
- `cb622ff` — Historical internal-lock note, superseded by the review follow-up below.

## Review follow-up: outer build lock

Removed the development builder's internal `flock` and restored the existing
AGENTS.md/documentation convention. The default remains `JOBS=3`. This avoids
a child waiting forever on the same lock already held by the caller; no game,
engine, generated source, or CI behavior changes.

Verification: `bash -n tools/build-linux.sh` and
`flock ~/.cache/tg2-heavy.lock tools/build-linux.sh`; build evidence is in
`build/phase-a/review-outer-lock-build.log`. Both commands exit 0; the wrapped
build completes without nesting the lock and uses the default three jobs.
No framebuffer/audio recapture is needed for this shell-only fix.
