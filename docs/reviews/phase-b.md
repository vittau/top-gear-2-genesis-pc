# Phase B organisation and regression evidence

Implemented on `vittau/review-phase-b`, based on untouched `34c43b1`.
Local host: macOS arm64, Homebrew SDL2. No CI, release, tag, merge or engine
submodule pin change is part of this work.

## Regression tool and untouched baseline

`tools/regression.py` replays `game/baseline-route.json` using the engine's
exact-frame input script, four isolated settings directories (Off/On ×
SFX/MUSIC), 89 frame samples per case at frames 60..5340 in steps of 60,
and streaming SHA-256 of each complete WAV. It checks all four execution
manifests, requires zero entries and removes WAVs even on failure/timeout.
Logs, actual hashes and manifest counts remain under the ignored output path.
Python 3.11+ is required for capture; importing the boot-hash helper does not
require tomllib. SDL dummy/software works on this Mac; `--video-driver`
allows an offscreen driver where available.

```sh
flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh
flock ~/.cache/tg2-heavy.lock /opt/homebrew/bin/python3.14 tools/regression.py --record --out build/phase-b/base
flock ~/.cache/tg2-heavy.lock /opt/homebrew/bin/python3.14 tools/regression.py --out build/phase-b/final-dev
```

Off explicitly disables widescreen, race 60 fps and the overscan crop; On
uses fixed 16:9, race 60 fps and the default crop. Both use centered HUD,
100% faders and native scale 1, matching the Phase A matrix.

The committed golden is `tools/regression-golden.json` (hashes and framebuffer
dimensions only). It was actually recorded from the untouched game/engine
sources at `34c43b1`, before any game change. `build/phase-b/verify-phase-a.py`
compared it to Phase A's original summary: **all 356 frame samples and all
four WAV hashes are identical**, including every value in Phase A's report
table. Stock boot/title remain `60=2A0B972960C5E325`,
`300=1131D937D70234FD`; SFX WAV SHA-256 remains
`1d0ab92b32b7f6ba7ac3e63e42f9c0fdfb8d8dff4dbfdbc20b02220faf7442a6`,
MUSIC remains `431338f523a9b0d54d1145b38c5a28657b712b9b23b0ca0ae312b15e2486b343`.
The optional `--uncapped` uses the engine's full runtime measurement path,
retaining rendering and audio while skipping host pacing. `--scale 2..4`
requires its own golden path so it cannot replace the canonical 1× golden
accidentally. An attempted engine `--benchmark` shortcut changed WAV output;
it was rejected rather than updating the golden.

| Case | Frame 3300 | Frame 3600 | Frame 4500 |
| --- | --- | --- | --- |
| off-sfx | A963A0F0F13938F3 | F0FE14786186F4EF | 3CFEED8F6CC6EACC |
| off-music | 5E97D0EC79AA383D | F625EB3DCBF36595 | 9B4D7BC9E902D29B |
| on-sfx | 0CA730442D5DD893 | B61E997D1F5AB9FE | B65BBFCD95F04FB5 |
| on-music | 57F9593D892B8CF9 | 459A09B583349F9C | 02B428F12DCEC6F9 |

All seven focused tools that used to duplicate those boot/title literals now
read the single golden through `regression.boot_hashes()`.

Release evidence manifests are opt-in in the engine. An initial release
capture stopped because its manifest files were absent; the tool now passes
`--debug` explicitly in both profiles so evidence collection is consistent.
The repeated untouched trace-OFF run passes the same golden with all counts
zero (`build/phase-b/base-release-capture.log`, exit 0). No TCP is needed:
input scripting, framebuffer hashes and WAV capture are available in release.

## Guest memory and race predicates

`tg2_memory.h` owns the wrapped 64 KiB big-endian word reader, RAM 16/32-bit
readers, and bounded ROM/RAM 16/32-bit readers. It preserves the old address
masking, wrap and unmapped-zero behavior. The engine's real `glue_peek*`
bus API remains in the native control-menu implementation, where bus reads
already have one engine-owned definition.

`tg2_race.h` owns three explicitly different predicates, approved by the
coordinator without behavior changes:

- `tg2_race_audio_policy_frozen`: the exact former low-word `$4714` check,
  regardless of pause, phase or player count.
- `tg2_race_tick_active`: the former simulation predicate, accepting `$4714`
  or `$49CC`, with the original pause/phase/1P guards.
- `tg2_race_picture`: the original live-row VDP/name-table/raster eligibility,
  which must follow the displayed picture rather than the CPU's next scene.

Raw-ROM disassembly: `$471C` writes `$49CC` to `$FF01EC`, `$49AC` restores
`$4714`, and `$49BA` returns from interrupt. With the default engine,
`own_deliver_vint` sets `s_in_vblank_service=1` and executes the handler
atomically; frame-pre audio cannot run inside that interval. An untouched
base run dumped every boundary 2600–3400: 801 samples, 67 menu targets and
734 `$4714`, zero `$49CC`; all four manifests were empty. Dumps were read
individually and deleted; scalar evidence is `build/phase-b/vector/summary.json`.
The opt-in `GENESIS_INTERLEAVE_IRQ` path explicitly allows handler yields,
so it could expose `$49CC` at frame-pre. Its narrower audio behavior is a
known preserved limitation, not fixed in this cleanup. Unifying the three
checks would change routing/eligibility, so they deliberately remain distinct.

## Interfaces, options and renderer modules

Game-to-game audio declarations now live in `tg2_audio.h`; option callbacks
and mod-provider declarations live in `tg2_options.h`. Audio chip routing,
Z80 access enums, mixer volume and sound-frame declarations come from their
real engine headers. New patch `0056-runtime-ui-header.patch` adds only the
missing runtime-overlay visibility header and includes it in its engine
implementation; the existing patch stack is not reorganised.

Runtime rows are generated in their original order/sections from the option
registry: keys, labels, choices, defaults, ranges and step sizes are unchanged.
The coordinator approved keeping the richer registry volume descriptions in
both surfaces, then explicitly accepted the existing software-footer clipping
as outside Phase B. Real headless presented screenshots were captured for
both the untouched base and final build, at the actual default 597×448 window
and at 1280×800 (software drawable, not a physical Deck). Both Music and SFX
already clip at both sizes. The footer pixels are byte-identical before/after
in all four comparisons: only the common leading text fits. Evidence:
`build/phase-b/overlay-{base,final}/{music,sfx}-{default,deck}.png` and
`build/phase-b/overlay-comparison.json`. No screenshot is committed and no
recomp-ui patch was added.

The complete returned description strings change as follows (launcher text
is unchanged):

| Row | Previous overlay description | Registry wording now used by both |
| --- | --- | --- |
| Music volume | Music level, as a percentage of the stock mix. Only the cartridge's music driver follows it; the engine, nitro and effects have their own slider. 100% is the stock level. | Music level, as a percentage of the stock mix. Only the cartridge's music driver is affected; engine, nitro and effect sounds keep their own slider. 100% is the stock level. |
| SFX volume | Sound-effects level, as a percentage of the stock mix: the 68K FM/PSG engine and the race Z80 sample player. 100% is the stock level. | Sound-effects level, as a percentage of the stock mix: the 68K FM/PSG engine and the race Z80 sample player (engine, nitro, impacts). Music keeps its own slider. 100% is the stock level. |

The renderer is split into canvas/options, scene/SAT capture, world/HUD,
raster composition, interpolation/presentation, and TCP diagnostics. Its
private implementation header shares value types and the necessary internal
symbols, namespaced `tg2v_`; file-local helpers stay static. The public
`GameVideo` adapter remains in `tg2_video.c`. Mechanical token comparison
confirms all 59 extracted function bodies are unchanged apart from internal
symbol qualification (`build/phase-b/split-comparison.json`).

## Release diagnostics and version source

Trace-only builds retain the password trace, TCP game commands, headless
overlay driver, CONTROL/top-row captures, margin/road audits, native reference
dumps, filter masks and actor evidence/trace/aggregate statistics. Release
compilation excludes those bodies/buffers. Functional actor projection,
promotion/culling, native-art coverage and the stepped/actors-off controls
remain. Game hook sites in `game.toml` are unchanged.

The CMake project declaration is the numeric version source. The three shell
builders, Windows builder, payload numeric fallback and three CI version
calculations read `tools/release/project_version.py`. Current numeric version
and plist fallback remain `0.3.0`; the CI suffix remains `-g<7-digit SHA>`.
Artifact name constants and the Windows resource template are untouched.
Only non-trigger workflow lines changed. Exact expressions:

```sh
TG2_VERSION=$(python3 tools/release/project_version.py)-g$(git rev-parse --short=7 HEAD)
```

```powershell
$version = (python tools/release/project_version.py)
if ($LASTEXITCODE) { throw 'Reading project version failed' }
"TG2_VERSION=$version-g$short" | Out-File -FilePath $env:GITHUB_ENV -Append -Encoding utf8
```

Parser, numeric fallback and rendered plist checks pass locally, as do shell
syntax checks. `build/phase-b/check-version.py` renders the base and current
plist templates for `0.3.0` and `0.3.0-g1234567`: both are byte-identical. It
also checks all four artifact-name constants and the unchanged Windows icon
resource template (that template has no numeric version fields). Evidence:
`build/phase-b/version-artifacts.json`. The embedded runtime version remains
`0.3.0`. The literal search
`rg -n '0\.3\.0' CMakeLists.txt .github/workflows/build.yml tools/release`
returns just `CMakeLists.txt:9:project(TopGear2Recomp VERSION 0.3.0 LANGUAGES C CXX)`.
Windows PowerShell and the workflow expressions are unverified
in their native environment/CI; no CI was run.

## Completion evidence

All builds and captures below used the machine-wide heavy lock, at most
three build jobs and one runtime at a time. WAVs were streamed and removed;
no WAV remains under `build/phase-b`. No ROM, dump, generated C or capture is
committed.

The local trace-OFF profile was configured directly, without invoking release
packaging:

```sh
flock ~/.cache/tg2-heavy.lock cmake -S . -B build/phase-b/release -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DTG2_ROM="$HOME/roms/genesis/tg2.bin" \
  -DGEN_ENABLE_TRACE=OFF -DSONIC_REVERSE_DEBUG=OFF -DGENESIS_NATIVE_IPO=ON \
  -DCMAKE_DISABLE_FIND_PACKAGE_Freetype=ON
flock ~/.cache/tg2-heavy.lock cmake --build build/phase-b/release --target TG2Recomp -j3
```

This tests the release compile flags with the same host Homebrew SDL2 as the
base; it is not a bundled-SDL or distribution-qualified release artifact.

| Check | Result / exit | Evidence under `build/phase-b/` |
| --- | --- | --- |
| Untouched base development build and `--record` | 0; 356 frame hashes, four WAV hashes, all manifest counts zero | `base-build.log`, `base-capture.log`, `base/` |
| Golden vs all Phase A recorded values | 0; 356/356 + 4/4 identical | `verify-phase-a.py` |
| Untouched base trace-OFF build and default comparison | 0; same canonical golden | `base-release.log` (build), `base-release-capture.log` (corrected capture) |
| Shared-reader/header/registry/trace-gating intermediate | 0; same canonical golden | `shared-game.log` |
| Post-split development build and default comparison | 0; same canonical golden | `final.log` (build), `finish-checks.log`, `final-dev/` |
| Trace-OFF build and default comparison | 0; same canonical golden | `finish-checks.log`, `final-release/` |
| Full runtime `--uncapped` base release, final release, final rebuilt development | 0 for each; same canonical golden | `extra-uncapped.log`, `{base,final-release,final-dev}-uncapped/` |
| Additional trace-OFF 2× base/final matrix | 0; 356 frame hashes + four WAV hashes identical | `2x-golden.json` (ignored), `{base,final}-release-2x/` |
| Regenerated C, same profile compared with base | 35/35 identical in development and 35/35 in release | `generated-comparison.json` |
| Manifest entries in every successful matrix case | dispatch, floor, interior labels and unsafe floor all zero | per-case `manifest-counts.json` and TOMLs |
| Extracted video function bodies | 0; 59/59 identical after internal name qualification | `split-comparison.json` |
| Deliberately changed expected hash | comparison returns 1 with unified diff; test exits 0 | `test-comparator.py` |
| Patch applicator check, Python compilation and shell syntax | 0 | `tools/apply-engine-patches.py --check`, listed source scripts |

The final tool invocation against the committed golden was:

```sh
flock ~/.cache/tg2-heavy.lock /opt/homebrew/bin/python3.14 tools/regression.py \
  --out build/phase-b/final-dev-uncapped --uncapped
```

Exit **0**: all 356 frame hashes and four WAV hashes match, all manifest
counts zero. The same optional uncapped path was first verified against the
untouched release base. The canonical golden was never changed to absorb a
difference. Release symbol inspection finds no password trace, TCP game
handlers, native reference/model buffers, top-row snapshots, actor audit or
reference-pass flag. macOS `size` reports release `__DATA` decreasing from
36,126,720 to 32,423,936 bytes (3,702,784 bytes removed).

### Focused probes and limits

The Phase A NumPy/Pillow venv was reused. `check_highres.py g1` and controls
run through the ignored `run-directed.py` wrapper; it only selects SDL dummy
for this Mac. `verify_hud.py` runs through `run-hud-uncapped.py`, substituting
full-runtime uncapped pacing for its historical turbo launch. Overscan is
explicitly off for the historical HUD/widescreen probes.

| Probe | Scope | Exit |
| --- | --- | --- |
| `check_highres.py g1 --out build/phase-b/g1` | All nine boot configurations, canonical hashes and empty manifests | 0 |
| `test_tg2_controls.py --out build/phase-b/controls` | Fresh-install synthetic P1/P2 triggers, native carousel/pages, race input bits, boot gates and manifests | 0 |
| `verify_widescreen.py --modes off --out build/phase-b/ws --end-frame 5400` | Actual stock route and captures, canonical boot/title, manifests | 0 |
| `verify_hud.py --record-baseline` against saved base | Two baseline capture runs; all manifests empty | 0 |
| `verify_hud.py` against final | All eight capture runs exit 0 with empty manifests; ownership checker rejects frame 3300 | 1 |
| Same full HUD check against saved untouched base | Identical ownership assertion at frame 3300 | 1 |
| HUD base/final artifact comparison | All **174/174** artifacts identical: 58 PNGs, 116 RAM/VRAM dumps | 0 |
| All seven touched probe `--help`/imports, plus Python compilation | Includes `analyze_top_band`, `verify_crop_evidence`, `compare_framerate` | 0 each |

The HUD checker failure is explicitly not claimed as a passing HUD ownership
qualification. Under the uncapped wrapper, its TCP-based ownership check rejects
frame 3300 on both executables; the base and final captures themselves are
byte-identical (`hud-artifact-comparison.json`). The exact commands were:

```sh
py=/Users/vitor/orca/workspaces/top-gear-2-genesis-pc/review-phase-a/build/phase-a/venv/bin/python
flock ~/.cache/tg2-heavy.lock "$py" build/phase-b/run-hud-uncapped.py \
  --out build/phase-b/hud
flock ~/.cache/tg2-heavy.lock "$py" build/phase-b/run-hud-uncapped.py \
  --exe build/phase-b/base-dev-exe --out build/phase-b/hud-base
```

Both return **1** at `tools/verify_hud.py:164`:

```text
assert len(mask) > 500, (frame, 'HUD ownership missing')
AssertionError: (3300, 'HUD ownership missing')
```
 Normal paced full HUD
qualification and the three historical artifact-verifier datasets were not
recreated. Detailed logs are `probe-{g1,controls,ws-final,hud-base,hud-final,hud-base-full}.log`;
CLI/import results are `probe-help-final.json`. An initial widescreen invocation
ended before the last committed route action and was rejected before launch;
the final invocation uses frame 5400. An initial saved-base HUD capture used
the wrong manifest directory; the wrapper was corrected and both base and
final captures were repeated.

Verified scope is local macOS source/build behavior and the exact comparisons
above. Linux/Windows/Deck execution, hardware ImGui presentation, real
controllers, distribution packaging and CI are not qualified by this phase.
The owner-approved pre-existing software-footer clipping and opt-in
interleaved-IRQ audio limitation remain; no BOTH rewrite or patch-stack
restructuring was performed.

### Source commits and branch

Branch pushed to origin: `vittau/review-phase-b`.

- `139f19c` — deterministic regression tool, single golden and probe readers.
- `f663f78` — release version derived from the CMake project declaration.
- `959958a` — explicit release evidence and isolated additional scale checks.
- `5919455` — shared game interfaces/readers, option descriptors and trace guards.
- `8e89678` — focused video modules and private implementation header.
- `5bc2885` — native reference pass/scratch excluded in release.
- `bd66a89` — initial optional uncapped experiment, superseded below.
- `e79c78d` — runtime placement metadata in the option registry.
- `b579e43` — full-runtime uncapped capture, retaining WAV generation.

The final documentation commit records this evidence; no source change follows
the successful final comparisons. On resuming after the usage-limit interruption,
the saved logs showed that the release build and final development/release runs
had completed successfully before shutdown. A fresh read-only artifact audit
confirmed all four normal/uncapped 1× result files match the committed golden,
all manifest counts are zero, both sets of 35 generated C hashes remain equal
to their base profiles, all eight overlay PNG dimensions are correct and all
four stored footer comparisons are identical. No runtime or WAV remained; the
patch-applicator check also returns 0. These completed runs were not repeated.
