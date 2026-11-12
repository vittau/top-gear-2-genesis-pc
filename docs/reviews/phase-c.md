# Phase C patch-stack maintenance

Branch `vittau/review-phase-c`, based on `131d47a`. No CI, merge, fork or
submodule-pin change. Work continues after the C2 checkpoint below.

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
