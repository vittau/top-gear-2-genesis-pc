# Engine, core and UI patches

The parent repository pins remain upstream commits. These 16 area patches apply
in place in sorted order: numbered files target `segagenesisrecomp/`, `core-*`
its nested `external/m68k-recomp-core/`, and `ui-*` targets `recomp-ui/`.
No submodule branch is pushed and no submodule pin is changed.

## Applied order

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

## Historical number mapping

Historical findings retain their original numbers; use this table instead of
rewriting those documents. The withdrawn 0041 patch has no input or replacement.
The early GameSpec hooks and final scale/layout hooks are separate because the
latter depend on the completed runtime settings/diagnostics surface. Quickstate
boundaries, requests and presented notices share one area: old 0024 consumes
the notice helpers from 0023, and the runtime axis probe consumes its dev menu
probes. Early icon hooks precede application paths so the macOS icon guard has
its declaration. All other proposed areas remain separate.

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

## Safe normal application

`tools/apply-engine-patches.py` is the sole implementation. The `.sh` and `.ps1`
entry points delegate to it. A worktree-local Git-directory stamp contains the
stack bytes/names, all three pins, HEAD/tracked diffs and untracked contents.
Only a matching stack and matching trees is a no-op. Missing/stale stamps,
manual checkout or edits cause a full rebuild; `--reset` forces it and `--check`
is read-only. Before any reset/clean, all dirty target trees (including untracked
files) are snapshotted with a private index into printed `refs/keep/...` commits;
core is saved before its parent engine. Recover with `git show <ref>:<path>`.
Ignored build outputs are retained. Normal application detaches at each pin,
preserving local maintenance branch histories.

## Local maintenance (no forks or submodule pin changes)

`python3 tools/apply-engine-patches.py --as-commits` snapshots dirty targets
first, preserves any previous local maintenance branch, restores the parent
repo's pins and creates local `tg2/patches` branches in engine/core/UI, with
one commit per patch. Supplied mail subjects/bodies are retained; legacy bare
diffs without a Subject use their descriptive filename as the initial subject.
Edit and commit/rebase on these local branches; never push them.

`python3 tools/apply-engine-patches.py --export` exports the committed local
histories using `git format-patch`, numbers each target contiguously (`0001`,
`core-0001`, `ui-0001`), and removes stale patch files. Dirty source edits must
be committed first. For an unchanged imported commit, a worktree-local Git-dir
cache preserves its original mail bytes after generating its format-patch;
new/amended/squashed commits use canonical format-patch output. Thus an unedited
round trip preserves all patch bytes, while legacy filenames can change to
the contiguous subject-derived names. `--branch NAME` selects another local
maintenance branch in both modes.

Export before running a normal build: normal application detaches back to the
recorded pins and reapplies the files in place, without moving local maintenance
branches. Phase A snapshots, tracked/untracked tree stamps, read-only `--check`,
and the single Python implementation behind shell/PowerShell entry points remain.
