# Phase C patch-stack maintenance

Branch `vittau/review-phase-c`, based on `131d47a`. No CI, merge, fork or
submodule-pin change. The final branch is pushed for review; it is not merged.

## Baseline and consolidation

The 47-patch base builds and passes `tools/regression.py --uncapped`: exit 0,
356 framebuffer hashes and four WAV hashes match the committed golden; all
four manifest counts are zero (`build/phase-c/baseline.log`).

C1 imports 47 local commits, one per patch, and exports with contiguous target
numbering. The unedited round trip preserves **47/47 patch payloads byte for
byte**; filenames become contiguous subject-derived names. A Git-dir cache
retains unchanged imported mail after format-patch generation; new/rebased
commits use canonical format-patch. Headerless historical diffs have no message,
so their descriptive filenames supply the initial local commit subjects.
Evidence: `c1-import.log`, `c1-export.log`, `c1-roundtrip.json` under
`build/phase-c/`. This workflow is documented in the patch README.

C2 consolidates 47 patches into 16 area patches. The early and late GameSpec
hooks remain separate to respect runtime/diagnostics dependencies; quickstate
boundaries and notices are combined because old 0024 needs 0023's helpers and
the axis probe needs its dev menu probes. The early icon hook precedes macOS
path policy. Reordering/squashing needed no conflict resolution and changes no
file bytes. All proposed areas otherwise remain separate.

| Target | Step 0 and C2 identical stamped tree hash | Identical normalized content tree |
| --- | --- | --- |
| engine | `ec6893be9c7ac0d03a3ba75e3c144d182d07adbcd9a257eec617c5bf367ee29b` | `f81e86b5ebca5e6c3ecadcd6ff1de1d41f7d6647` |
| core | `e743384da7d768fee358440df0c03ebd177c92dab7fc0e4cadc449e2a6812cc5` | `1379a30192dc0a780d77a7177e6f5c3d279c6b59` |
| ui | `0fd81811755d52cc493692ec7a2a5a135be8db4686b56dd7421c5ae2d2e3ed8e` | `0c1312022ca99bd78115b4cd7946e0589020b41f` |

The stamp hash includes the pinned HEAD and working-tree/untracked state;
normalized Git content trees additionally allow comparison while the files
are committed on local maintenance branches (the nested core gitlink is
normalized to its recorded pin and its content checked separately). C2 normal
application restores pinned HEADs, so **both** forms match Step 0 exactly.
No regression run was needed for this byte-identical C2 commit.

### New stack

| New patch | Reason |
| --- | --- |
| `0001-preserve-irq-register-effects.patch` | Keep guest ISR register changes, including raster pointers, when returning to native code. |
| `0002-detect-cartridge-content-beside-the-executable.patch` | Find the required ROM by content before opening the launcher; users need no fixed filename. |
| `0003-expose-game-presentation-and-menu-hooks.patch` | Let the game own settings, native video geometry, app identity and player defaults without embedding game policy in the runner. |
| `0004-resolve-executable-and-application-data-paths.patch` | Anchor assets, cartridge lookup and writable user data to the actual image or macOS bundle rather than inherited launcher state. |
| `0005-keep-exact-guest-timing-and-runtime-telemetry.patch` | Repay late ticks without retiming simulation and measure full runtime work independently of host VSync. |
| `0006-stabilize-device-drift-and-chip-sample-clocks.patch` | Preserve chip clock remainders and timer phase while correcting device drift without modulating music tempo. |
| `0007-route-independent-sound-writers-and-live-source-gains.patch` | Support separate music and effects chips and Z80 programs; fader changes ramp gain without rerouting running drivers. |
| `0008-save-quickstates-at-guest-boundaries-and-present-feedback.patch` | Resume the saved guest callers and keep requests queued for a safe boundary; show results without changing hashed game pixels. |
| `0009-integrate-runtime-menu-and-controller-input.patch` | Provide clean menu dismissal, photo freeze and quit, retain slot hotkeys and expose additive triggers plus dev axis probes. |
| `0010-bound-linear-picture-sampling-and-record-capture-geometry.patch` | Filter only the active picture and export sampler metadata so diagnostic captures explain output scaling. |
| `0011-follow-device-aspect-and-gamescope-window-policy.patch` | Start adaptive windows at the desktop aspect and controller-only Gamescope sessions at the panel dimensions. |
| `0012-make-replay-and-execution-diagnostics-opt-in.patch` | Migrate the old diagnostics default and let release users enable replay/evidence for bug reports without normal-play files. |
| `0013-expose-game-scale-vocabulary-and-runtime-menu-layout.patch` | Use the game render-scale choices and host menu layout after the complete runtime settings surface has been assembled. |
| `0014-declare-runtime-overlay-visibility.patch` | Expose the host visibility query through a public C header instead of game-side copied prototypes. |
| `core-0001-dispatch-pushed-rts-targets-with-exact-stack-deltas.patch` | Account every guest stack adjustment before choosing a normal return or a computed tail dispatch. |
| `ui-0001-apply-runtime-layout-policy-and-wrap-help-footers.patch` | Share explicit section policy across both menu backends and reserve measured software help height above settings rows. |

### Old → new mapping

| Historical patch | New patch |
| --- | --- |
| `0001` | `0001-preserve-irq-register-effects.patch` |
| `0002` | `0002-detect-cartridge-content-beside-the-executable.patch` |
| `0003` | `0003-expose-game-presentation-and-menu-hooks.patch` |
| `0004` | `0004-resolve-executable-and-application-data-paths.patch` |
| `0005` | `0005-keep-exact-guest-timing-and-runtime-telemetry.patch` |
| `0006` | `0006-stabilize-device-drift-and-chip-sample-clocks.patch` |
| `0007` | `0004-resolve-executable-and-application-data-paths.patch` |
| `0008` | `0006-stabilize-device-drift-and-chip-sample-clocks.patch` |
| `0009` | `0006-stabilize-device-drift-and-chip-sample-clocks.patch` |
| `0010` | `0006-stabilize-device-drift-and-chip-sample-clocks.patch` |
| `0011` | `0007-route-independent-sound-writers-and-live-source-gains.patch` |
| `0012` | `0003-expose-game-presentation-and-menu-hooks.patch` |
| `0013` | `0009-integrate-runtime-menu-and-controller-input.patch` |
| `0014` | `0007-route-independent-sound-writers-and-live-source-gains.patch` |
| `0015` | `0003-expose-game-presentation-and-menu-hooks.patch` |
| `0016` | `0009-integrate-runtime-menu-and-controller-input.patch` |
| `0017` | `0003-expose-game-presentation-and-menu-hooks.patch` |
| `0018` | `0008-save-quickstates-at-guest-boundaries-and-present-feedback.patch` |
| `0019` | `0004-resolve-executable-and-application-data-paths.patch` |
| `0020` | `0003-expose-game-presentation-and-menu-hooks.patch` |
| `0021` | `0008-save-quickstates-at-guest-boundaries-and-present-feedback.patch` |
| `0022` | `0009-integrate-runtime-menu-and-controller-input.patch` |
| `0023` | `0008-save-quickstates-at-guest-boundaries-and-present-feedback.patch` |
| `0024` | `0008-save-quickstates-at-guest-boundaries-and-present-feedback.patch` |
| `0025` | `0010-bound-linear-picture-sampling-and-record-capture-geometry.patch` |
| `0026` | `0004-resolve-executable-and-application-data-paths.patch` |
| `0027` | `0009-integrate-runtime-menu-and-controller-input.patch` |
| `0033` | `0003-expose-game-presentation-and-menu-hooks.patch` |
| `0035` | `0003-expose-game-presentation-and-menu-hooks.patch` |
| `0040` | `0007-route-independent-sound-writers-and-live-source-gains.patch` |
| `0042` | `0007-route-independent-sound-writers-and-live-source-gains.patch` |
| `0045` | `0011-follow-device-aspect-and-gamescope-window-policy.patch` |
| `0046` | `0012-make-replay-and-execution-diagnostics-opt-in.patch` |
| `0047` | `0012-make-replay-and-execution-diagnostics-opt-in.patch` |
| `0048` | `0012-make-replay-and-execution-diagnostics-opt-in.patch` |
| `0049` | `0012-make-replay-and-execution-diagnostics-opt-in.patch` |
| `0050` | `0013-expose-game-scale-vocabulary-and-runtime-menu-layout.patch` |
| `0051` | `0013-expose-game-scale-vocabulary-and-runtime-menu-layout.patch` |
| `0052` | `0010-bound-linear-picture-sampling-and-record-capture-geometry.patch` |
| `0053` | `0005-keep-exact-guest-timing-and-runtime-telemetry.patch` |
| `0054` | `0009-integrate-runtime-menu-and-controller-input.patch` |
| `0055` | `0009-integrate-runtime-menu-and-controller-input.patch` |
| `0056` | `0014-declare-runtime-overlay-visibility.patch` |
| `core-0003` | `core-0001-dispatch-pushed-rts-targets-with-exact-stack-deltas.patch` |
| `core-0004` | `core-0001-dispatch-pushed-rts-targets-with-exact-stack-deltas.patch` |
| `ui-0001` | `ui-0001-apply-runtime-layout-policy-and-wrap-help-footers.patch` |
| `ui-0002` | `ui-0001-apply-runtime-layout-policy-and-wrap-help-footers.patch` |

## Dead-code cleanup

Separate commits after the byte-identical consolidation remove the unused
`hide_internal_resolution` field and runtime-row guard, then the four retired
A/B switches. Game code sets no resolution-hiding field, so the row path is
unchanged. Removing `classic_servo` retains the normal DRC law. The mixer keeps
sorting, Z80 writes and PSG remainders exactly as when all retired switches
were unset; worker and serial drains keep their former default behavior.

This command returns **1, no matches**, on the applied final sources:

```sh
rg -n 'hide_internal_resolution|classic_servo|GENESIS_AUDIO_DRC_CLASSIC|GENESIS_MIXER_RESET_LEFTOVER|GENESIS_AUDIO_MUTE_Z80|GENESIS_AUDIO_NO_SORT' segagenesisrecomp/runner game tools
```

No game/tool reads or sets them. The only remaining non-review documentation
mention is the explicitly historical DRC A/B result in `docs/AUDIO.md`; its
runnable comparison now uses a preserved pre-task-18 executable, rather than
asking a current binary to honor a deleted switch. Historical patch numbers
in that document and the other validation ledgers were not rewritten.

Kept and checked in source: `GENESIS_AUDIO_CHIPDUMP` in `runner/audio.c`,
`GENESIS_AUDIO_SFXPCM_TRACE` in `game/tg2_audio_both.c`,
`GENESIS_APP_PATHS_TEST` in `runner/app_paths.h`, and
`runner_debug_virtual_axis` in `runner/main.c`. The UI patch is unchanged after
consolidation, including the footer wrapping and the axis probe's input path.
These diagnostics were preserved by source inspection; their individual
capture probes were not rerun for this task.

## Game-owned application data name

`GameSpec.data_directory_name` is optional. The game sets it to exactly
`TG2Recomp`; the shared macOS helper takes this value, using `GenesisRecomp`
only if another game leaves the field empty. Directory creation and placement
policy are unchanged. The core's game-specific RTS example was also reworded
as a generic comment, without altering generator code.

`rg -n -i 'tg2|top gear' segagenesisrecomp` returns **1, no matches** on the
applied source tree (normal ignored build outputs and Git internals excluded).
There are no remaining game-name exceptions in the engine or its core source.
The parent and nested-core recorded pins remain:

| Target | Unchanged pin |
| --- | --- |
| engine | `dd520f1f975a80b080cddc569f3f49035f054101` |
| core | `03ba2787da829369bbc2d958621b10330885c8f8` |
| UI | `839a6f98c3014e7586ac942a66395ddaa6fc5bc5` |

`tools/test_app_paths.py` still passes its 17 bundle/location cases. The new
`tools/test_app_path_policy.py` extracts the actual runner initialization
functions and compiles each platform branch, including `app_paths.h`, with
mocked platform/filesystem APIs. It does not reproduce the selection algorithm
in Python. Before and after outputs are byte-identical (`cmp` exit 0):

| Case | Executable/search root | Data root | ROM library |
| --- | --- | --- | --- |
| macOS installed app | `/Applications/` | `/Users/player/Library/Application Support/TG2Recomp/` | 1 |
| macOS writable portable app | `/Games/` | `/Games/` | 0 |
| macOS read-only portable app | `/Games/` | `/Users/player/Library/Application Support/TG2Recomp/` | 1 |
| macOS loose executable | `/Games/` | `/Games/` | 0 |
| Linux loose executable | `/games/` | `/games/` | 0 |
| Linux valid AppImage | `/games/` | `/games/` | 0 |
| Linux inherited unrelated AppImage | `/games/` | `/games/` | 0 |
| Linux argv fallback | `/fallback/` | `/fallback/` | 0 |
| Windows executable | `C:\Games\` | `C:\Games\` | 0 |

Thus settings/save/cartridge roots and the existing filenames derived from
these roots stay identical. The existing `GENESIS_USER_DIR` override and asset
lookup code were not changed. Evidence is `build/phase-c/paths-before.json`,
`paths-after.json` and `paths-final.json`; the archived pre-change runner
sources used for the before run are in `build/phase-c/path-before/`.

## Commands and results

All commands below completed with **exit 0**, except the two absence greps
above, whose expected exit is 1. Build/regression shell scripts use `set -eu`,
so their exit includes every listed subcommand. Every build used the shared
heavy lock, at most three jobs; captures were headless, sequential, and their
WAVs streamed into SHA-256 and deleted by the official tool.

| Command | Evidence/result |
| --- | --- |
| `flock ~/.cache/tg2-heavy.lock sh build/phase-c/baseline.sh` | `baseline.log`: `JOBS=3 tools/build-linux.sh`, then `/opt/homebrew/bin/python3.14 tools/regression.py --out build/phase-c/baseline --uncapped`; golden passes |
| `python3 tools/apply-engine-patches.py --as-commits`, then `--export` on original stack | `c1-import.log`, `c1-export.log`, `c1-roundtrip.json`; 47/47 raw payloads identical, legacy names become contiguous |
| `python3 build/phase-c/group.py`, then applicator `--export` and default apply | `group.log`, `c2-export.log`, `c2-apply.log`; 16 patches; Step 0/C2 tree hashes equal as shown above |
| `flock ~/.cache/tg2-heavy.lock sh build/phase-c/c3-check.sh` | `c3-check.log`: dev and trace-OFF release builds and full golden comparisons pass |
| `python3 tools/test_app_path_policy.py --runner build/phase-c/path-before` | nine before path-policy cases pass |
| `python3 tools/test_app_path_policy.py` | nine after/final cases pass |
| `cmp build/phase-c/paths-before.json build/phase-c/paths-after.json` (also `paths-final.json`) | byte-identical outputs |
| `python3 tools/test_app_paths.py` | 17 cases pass |
| `flock ~/.cache/tg2-heavy.lock sh build/phase-c/c4-check.sh` | `c4-check.log`: final dev/release builds and golden comparisons pass |
| `python3 build/phase-c/check-applicator.py` | `c5-check.log`, `c5-checks.json`; all recovery/round-trip checks below pass |
| `python3 tools/apply-engine-patches.py --repo "$PWD" --check` | final stamp and all three trees match |
| `python3 -m py_compile tools/apply-engine-patches.py tools/test_app_path_policy.py` | syntax passes |
| `bash -n tools/apply-engine-patches.sh` | syntax passes |
| `git diff --check` | no whitespace errors |

The C3 script configures its new local release build with:

```sh
cmake -S . -B build/phase-c/release -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -DTG2_ROM="$HOME/roms/genesis/tg2.bin" -DGEN_ENABLE_TRACE=OFF \
  -DSONIC_REVERSE_DEBUG=OFF -DGENESIS_NATIVE_IPO=ON \
  -DCMAKE_DISABLE_FIND_PACKAGE_Freetype=ON
cmake --build build/phase-c/release --target TG2Recomp -j3
/opt/homebrew/bin/python3.14 tools/regression.py \
  --exe build/phase-c/release/TG2Recomp --out build/phase-c/c3-release --uncapped
```

C3 dev uses `JOBS=3 tools/build-linux.sh` and the official regression with
`--out build/phase-c/c3-dev --uncapped`. C4 repeats that dev build and regression
with `--out build/phase-c/c4-dev --uncapped`, then rebuilds the existing
trace-OFF `build/phase-b/release` directory with `cmake --build ... --target
TG2Recomp -j3` and compares with `--exe build/phase-b/release/TG2Recomp --out
build/phase-c/c4-release --uncapped`. Using the same release output directory
also makes the generated layout file's absolute-path comment comparable.

Each of the baseline, C3 dev/release and final C4 dev/release comparisons
matches all **356 framebuffer hashes and four WAV hashes** against
`tools/regression-golden.json`. This includes options off/default on, SFX/MUSIC,
boot/title frames 60 and 300, and race frames. SFX WAV SHA-256 is
`1d0ab92b32b7f6ba7ac3e63e42f9c0fdfb8d8dff4dbfdbc20b02220faf7442a6`;
MUSIC is `431338f523a9b0d54d1145b38c5a28657b712b9b23b0ca0ae312b15e2486b343`.
All four cases in every run have zero `dispatch_misses`, `floor_coverage`,
`interior_label_misses` and `floor_unsafe` counts.

The final **35/35 generated C SHA-256s in each configuration** equal the
accepted base lists from Phase B (`generated-base.json` and
`generated-release-base.json` under `build/phase-b/`), verified by dictionary
equality against freshly hashed files. Final lists are
`build/phase-c/generated-dev-final.json` and `generated-release-final.json`.
The C3 release in its new directory differs only in the generated layout
file's first-line absolute output-path comment; final same-directory comparison
is exact, including that comment. No generated C was edited or committed.

## Applicator safety and round trip

Final checks force a fresh apply, verify the next run is a no-op, then run
`git checkout -- .` in the engine: the altered tree is detected and the full
stack restored. A deliberate tracked edit plus an untracked sentinel is then
made in **each** target. The reset restores the final trees, while new
`refs/keep/` snapshots contain both sentinel payloads (verified with `git show`).
Finally `--as-commits` followed by `--export` preserves all **16 filenames and
16 payloads byte-for-byte**; normal apply restores pinned HEADs and exact final
trees. Local branch histories are retained and never pushed. The final stamp
hashes are:

| Target | Final stamp tree hash |
| --- | --- |
| engine | `777d2394d59d24eb7abcc6a4cccdd96a86d081dcd4d3bb06af323da28fd5614b` |
| core | `b671bd33718bd4c3b56d7f7f06fb77833339f3c89f0e143e4abdba6bdb42dab1` |
| UI | `0fd81811755d52cc493692ec7a2a5a135be8db4686b56dd7421c5ae2d2e3ed8e` |

The Windows release entry remains the same PowerShell invocation:
`& python "$repo/tools/apply-engine-patches.py" --repo $repo`, followed by
its existing `$LASTEXITCODE` check. It contains no patch-name assumptions;
Python enumerates the new engine/core/UI prefixes. Its arguments were exercised
locally with `--repo`, and Python plus the shell entry point passed syntax
checks. The unchanged PowerShell statement was reviewed statically; no
PowerShell parser or Windows execution was available.

## Commits and verification limits

Implementation commits on `vittau/review-phase-c`:

- `45457a2` — local commit/export maintenance modes.
- `5e2e003` — byte-identical 47-to-16 consolidation (separate checkpoint).
- `5897a72` — unused resolution-hiding field removed.
- `dd59ed7` — unused audio A/B paths removed.
- `81489f5` — game-owned data name and cross-platform path-policy check.

This report and the final maintenance notes are committed separately after
those changes. Only the parent branch is pushed; parent submodule gitlinks
match `131d47a`, with all runtime changes represented as patch files.

Verified on this macOS host: local dev/release builds, deterministic picture
and audio captures, native compiled path-policy mocks for all three platforms,
patch application/recovery/export, generated C and manifest checks. Not
verified: actual Linux/Windows/Steam Deck runtime or packaging, real Windows
PowerShell execution, CI, and interactive/physical audio devices. No workflow,
CI dispatch, tag, merge, release or upstream-submodule push was performed.
