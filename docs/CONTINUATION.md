# Coordinator continuation — S3 accepted, Steam Deck playtest, then S4

**Ordinary-kind extension (2026-11-11):** after the owner confirmed smooth
Ayers rocks (“Sim”), task 39 merged in `9f8345a`. On new branch
`vittau/tg2-highres-more-kinds`, all seven remaining ordinary kinds
`$81/$93/$97/$A1/$A2/$A3/$A4` pass ROM/asset checks and directed 4×/60-fps
actor qualification. `$81` uses slot identity for its lateral motion.
Stock G1 and original-track regressions pass; no Ayers road diagnostic was
run or changed. Read task 39's newest extension handoff and HIGHRES §14.9;
report `build/more-kinds/worker-report.md`. Play directly with
`build/more-kinds/play.sh [egypt|italy|chile|las-vegas]`, saved 4×/60 fps On.
Owner review of this new seven-kind extension remains separate from his
already accepted continuous/rock work.

**Task 39 approved follow-up (2026-11-11):** owner played continuous and said
“Está ótimo”. `b151a25` makes it default; `dce0c67` promotes the ordinary
Ayers Rock `$96` rock ladder. On the same continuous branch, stock/default
and short Auckland/Canada/rain actor gates pass. A bounded 900-moving-frame
1× inventory of the remaining 13 countries is in HIGHRES §14.8; no other
new kind was fixed. The full Ayers drive still returns 1 on a night-road
lane/centre diagnostic that also fails with actors disabled; actor invariants
and road geometry checks pass, and this separate road issue remains open.
Read task 39's latest handoff and `build/task39-followup/worker-report.md`.
Play default: `build/task39/play-continuous.sh`; direct Ayers checkpoint:
`build/task39-followup/play-ayers-rock.sh`, both saved 4× /60 fps On.

**S4 continuation (2026-11-11):** Fable completed the LOD evidence/checkpoint;
Sol continued the implementation on `vittau/tg2-highres-s4`. Local technical
qualification is complete; owner visual acceptance is pending. Read task 34's
current handoff and HIGHRES §14, with the full ignored report at
`build/s4/worker-report.md`. The operator highlighted the native pole detail
mismatch in picture 05; [task 38](tasks/38-highres-poles.md) explicitly maps
that compound-pole improvement. It has not started. No S4 merge/release/CI
was performed. The older S3/main-checkout snapshots below are historical.

Latest owner decision (2026-11-11): he tested the
`deck-instruments-20261110` draft on the Steam Deck and said **“Está ótimo no
Deck.”** Task 37 is accepted on the Deck too; do not ask again. He then asked to
start **S4** ([task 34](tasks/34-highres-s4.md)) with a supervised **Claude
Fable 5.2** worker (`--agent claude --model claude-fable-5-2`). Because Fable
consumes a lot, the coordinator watches the Claude 5-hour session usage
(`orca account list --json` → `rateLimits.claude.session.usedPercent`) and,
as it nears 80%, asks the worker to commit/push its progress and write a
handoff note so another agent can continue. S4 progress and the handoff state
are recorded in `docs/tasks/34-highres-s4.md` by the worker.

At 75% of the Claude 5h window the Fable worker checkpointed at `ffc4358`
(LOD evidence done, no presentation code yet) and was stopped. At the owner's
request S4 continues on **Codex GPT-6.1 Sol, effort high** in the same
`tg2-highres-s4` worktree (run `run_47bdb5658e2b`, dispatch `ctx_551d89a0b47b`).
Before the switch, the trees were saved as `refs/keep/tg2-s4-fable-{worktree,engine,ui}-20261111`.
Sprite filtering: the owner asked whether nearest would look more faithful.
The coordinator proposed nearest magnification under Linear Off (area
averaging kept for minification). The owner chose to **keep the current plan
(box filter) and judge it at the S4 visual review**. Raise this option again
at that review; don't change the worker's brief now.

**S4 approved and merged (2026-11-11).** Sol finished S4 at `727764f`
(89,085 promoted actors, all-frame anchor/palette/priority errors 0, stock
hashes unchanged, +0.26/+0.38 ms CPU at 2×/4× on this Mac). The owner played
it at 4× and approved it, then said objects still pop in. The internal
continuous switch didn't help him either. Merged into `main` as `a8041a2`.
Smooth growth is mapped as [task 39](tasks/39-highres-continuous-actor-size.md),
not started. The poles follow-up is task 38. The S4 worker has finished.

**v0.2.0 published (2026-11-11)** at the owner's explicit request ("está bom
o suficiente"), from `main` at `a74e308`, with the experimental internal
resolution row (default 1×, road/background only) included by his decision.
Tag `v0.2.0`, [CI 43019230068](https://github.com/vittau/top-gear-2-genesis-pc/actions/runs/43019230068)
green on all five jobs, release marked Latest. Notes: `release/v0.2.0.md`.
Linux tarball SHA-256 `6e6b6b8c9bf7bb93bff7572eaccd6d90c5eee5fb25aa7520d769993cbbbb1fec`,
`BUILD-INFO` version `0.2.0-ga74e308`. Windows and Intel Mac remain unplayed.

Previous owner decision (2026-11-10): [task 37](tasks/37-intermittent-race-menu-instruments.md)
is done. A supervised OpenCode worker confirmed the coordinator's static
diagnosis (BOTH persisted at boot diverted Z80 `$025E..$0261`, four entries of
the music driver's octave table, to the second Z80), fixed `z80_route()`, and
the owner approved the fix by ear (“Está certo”). It is merged into `main`
(branch `vittau/tg2-race-menu-instruments`). Deck draft
[deck-instruments-20261110](https://github.com/vittau/top-gear-2-genesis-pc/releases/tag/untagged-8c70f39421b827e442b5)
(target `8f2bd53`, tar.gz only, CI 42911855879) awaits the owner's Deck test.
At the owner's request the `tg2-race-menu-instruments` worktree was then removed
through Orca (its OpenCode session was idle and interrupted). Branch
`vittau/tg2-race-menu-instruments` is retained at `8cba6d4`; verified bundles of
the branch and both dirty submodule trees, the worker report and probe scripts
are in `~/.cache/tg2-worktree-backups/20261110-race-menu-instruments/`
(`manifest.json`). Only the main checkout remains registered.

Earlier owner decision: he tested the local macOS filter/menu build and said
**“Está tudo certo.”** Tasks 35/36 are approved; do not request that approval
again. He separately reported occasional missing instruments in race-menu
music, then explicitly deferred it to another session after saving the
filter/menu work. See [task 37](tasks/37-intermittent-race-menu-instruments.md).
At his subsequent request, the filter/menu agent and its
`tg2-linear-filter-s3` worktree were closed/removed through Orca. Branch
`vittau/tg2-linear-filter-s3` is retained at `8a6936e` (already merged/pushed).
Before removal, source snapshots including dirty nested submodules and
untracked source were exported to verified Git bundles, and the local
reports/summaries/probe scripts/captures were archived under
`~/.cache/tg2-worktree-backups/20261110-linear-filter-s3/`.
`manifest.json` maps source commits/bundles; `evidence/linear-s3/worker-report.md`
and `evidence/linear-s3-followup/report.md` replace the now-removed worker
build paths cited below. Its saved settings and any build saves/states were
also preserved there. The historical S3 checkout was subsequently removed too,
at the owner's explicit request. Its source snapshots and final qualification
evidence are in `~/.cache/tg2-worktree-backups/20261110-highres-s1-s2-close/`:
`manifest.json` maps the verified Git bundles and `evidence/s3-reverify/`
contains the report, summaries, captures and cost CSVs. Wide-menu/2P evidence
is alongside it under `evidence/`. Branch `vittau/tg2-highres-s3` remains at
`d78e513`. Only the main checkout remains registered for this project.
No audio investigation or S4 implementation is active. The manual game has closed.
For a visible manual launch, unset both LNG_SCRIPT and LNG_TEST_HIDDEN:
setting them to the string 0 still hides the window because the code checks
for their presence. The corrected visible launch was verified with one
“Top Gear 2” window and brought to the foreground. The new Linux draft
still provides a Deck candidate; local Mac acceptance is not Deck performance evidence.

Current feedback: the owner tested the Deck tar.gz and said it worked well,
but **Linear Filter no longer has an effect during gameplay while still
working in the main menu**. [Task 35](tasks/35-linear-filter-highres.md) is now
implemented and locally approved; the latest Deck performance is unmeasured. His exact original
scale/toggle sequence was not supplied; controlled local reproduction is documented.
The owner also requested [task 36](tasks/36-unify-runtime-menu-groups.md):
unify Esc Display/Graphics/Video into **Video**, and Sound/Audio into **Audio**.
Category order must be **VIDEO → AUDIO → SYSTEM → MODS → SAVE STATES**.
Worker follow-up on `vittau/tg2-linear-filter-s3` is locally qualified and
merged into main as `87e926b`: menu unification `d8f822c`,
probe-path follow-up `fbeaedf`, and sampler diagnosis `9534ac8`, followed by a
separate native-art filter fix. Pinned SDL2/Metal proves a 4× 1280×800 source
can equal the output and legitimately make a final sampler invisible. The
coordinator approved filtering native RGB inside S3 with the existing On
choice; Off retains the accepted image and the analytic road stays independent.
See LINEAR_FILTER.md and RUNTIME_MENU.md for focused evidence and limitations. The follow-up
also fixes the Windows Python applicator's UI routing/idempotence and validates
the 43-patch stack by actual application. A no-audit/no-pacing 4× cost pair adds
4.511 ms of CPU locally (1.882→6.392 ms); account for this before the next Deck
candidate, without extrapolating it to device performance.
The coordinator reviewed the source/evidence and fixed a review gap in the
portable Windows applicator through the worker follow-up (`185660b`), then
qualified the no-pacing cost harness (`8a6936e`). Windows itself was not built.
Both tasks are in the new Linux-only draft
[deck-filter-menu-20261110](https://github.com/vittau/top-gear-2-genesis-pc/releases/tag/untagged-250db4e89d9b27e23c8f),
target `87e926b12db46a6f4aec7326d14ab470b1a4875f`, packaged version
`0.1.0-g87e926b`. [CI 42898689826](https://github.com/vittau/top-gear-2-genesis-pc/actions/runs/42898689826)
passed Linux build and independent content/glibc/smoke verification: glibc
2.34, 600-frame tarball and AppImage boots, exit 0. Attached assets are
tar.gz, AppImage and SHA256SUMS, but the release itself remains a draft.
Tarball SHA-256: `5fe2a14e2f952fd1d50990f353734c1a2a0dcf92f595be65b117a5172954ee56`;
AppImage: `91bc3f3f4dde4bfd73bb2453494b79ece822df57a22e22390af36373b0339bae`.
The owner should update the existing tar.gz folder, keeping ROM/settings/saves
and Steam shortcut, and compare Linear On/Off in a race at his chosen scale.
Next coordinator: respect the local approval above and the explicit audio
deferral; use the owner's next-session direction to investigate task 37 or
continue S4. The original `deck-s3-20261110` draft/asset identity
below remains unchanged. No worker assignment is active after the follow-up.
The checkpoint below retains the source/build history of that tested draft.

Session checkpoint: 2026-11-10. The owner is ending the session. Do not launch
new implementation work merely because this checkpoint exists.

## Start here

1. Read `AGENTS.md`, this file, `STATUS.md`, and `HIGHRES.md` §§3, 8, 9, 13.
2. Read the owner's new feedback before choosing the next task. Fix a reported
   S3/Deck defect first; otherwise S4 is the next high-resolution step, with
   a prepared brief in [task 34](tasks/34-highres-s4.md).
3. Use Orca's `orca-cli` and `orchestration` skills for supervised workers.
   **Only Opus, Fable or Sol may implement S3/S4.** The last worker used
   Codex `gpt-6.1-sol`, medium. Do not fall back to Flash/Haiku for this work.

## Git and completion state

- S3 is implemented, locally qualified, visually accepted, and merged into
  `main` as `a2057597b29de1542a0dbc8d21a7aed9a80c918e`.
- The owner viewed the five curated same-frame native/2× comparisons (straight,
  curve, hill, rain, tunnel) in Preview and said **“Está ótimo.”** Approval was
  recorded in `d78e513`, before the merge. Do not ask for that approval again.
- S3's branch is `vittau/tg2-highres-s3`, at `d78e513` when merged. The old
  checkout was removed from
  `/Users/vitor/orca/workspaces/top-gear-2-genesis-pc/tg2-highres-s1-s2`.
  Its name reflects its history, not unfinished S1/S2 work. Begin new changes
  from current `main`; the S3 branch lacks the later documentation commits
  and retained some older audio code that `main` correctly removed.
- The root checkout is `/Users/vitor/git/top-gear-2-genesis-pc` on `main`.
  At the checkpoint its only pre-existing dirt was the engine's applied
  patches and an untracked `.DS_Store`. Neither was added to the merge.
  The engine upstream pin remains `dd520f1`; do not commit a patched pin.
  The root engine working tree was not reset/rebuilt after the merge: its
  applied patch set may be stale. Snapshot both nested source trees before
  refreshing the current project patch stack, then regenerate/build. The
  successful CI used a clean recursive checkout of the exact merge revision.
- Historical pre-S4 snapshot: implementation now exists on the separate S4
  review branch; task 34 has the current handoff. Task 28 remains paused.
  Clean FM and Clean engine samples were rejected and removed; keep the
  finished Music/SFX volume controls. Do not restore the withdrawn options.

## Draft delivered for the owner's Steam Deck test

- Tag name on the draft: `deck-s3-20261110`.
- [Open the draft](https://github.com/vittau/top-gear-2-genesis-pc/releases/tag/untagged-fb40acbd6ff0b4a9d90d).
  It is **draft + prerelease**, not published. Its target is `a205759`, not a
  future `main` revision. GitHub uses an `untagged-*` URL for this draft.
- [Linux-only CI run 42842299392](https://github.com/vittau/top-gear-2-genesis-pc/actions/runs/42842299392)
  passed both Linux jobs. Windows/macOS were deliberately skipped. No `v*`
  tag or full platform matrix was pushed for this Deck-only draft.
- Assets: `TG2Recomp-linux-x86_64.tar.gz`, `TG2Recomp-x86_64.AppImage`,
  `SHA256SUMS`. Built version: `0.1.0-ga205759`; engine `dd520f1f975a`;
  Release profile, static SDL2/C++ runtime, TCP/reverse-debug rings disabled.
- Both tarball and AppImage passed content gates and 600-frame headless
  smoke tests with ROM discovery by content, exit 0. The downloaded packages
  were independently checked in CI: highest required glibc symbol **2.34**,
  within the **≤2.35** release floor. SHA-256:

  ```text
  37ae02c929a223ad6300a1d7243f196864a902f390b1415a9006347ab6434618  TG2Recomp-linux-x86_64.tar.gz
  e5ea30e405cd798869a34f467a5f2cbf9fa7832b91f1e15d653a5ef33945e825  TG2Recomp-x86_64.AppImage
  ```

- **Owner uses the extracted tar.gz on the Deck, not AppImage.** Continue
  supporting that folder layout and the existing Steam shortcut to
  `TG2Recomp`; keep his ROM, settings and saves. A matching executable path
  avoids changing the shortcut. Do not require migration to AppImage.
- Internal resolution defaults to **1×**. To test S3, select 2× in the shared
  Internal resolution row and restart. Check Adaptive 16:10, gamepad/overlay,
  audio and frame pacing. The owner has now reported that the draft worked
  well, with the Linear Filter regression recorded above; this does not
  establish individual performance/GPU measurements. He had played an older tarball and reported aspect/log
  issues; do not describe the Deck as never having been played at all.
- A later fix needs a new build with an explicit source revision; never
  silently relabel these existing binaries as containing new commits.
  Draft creation does not authorize publishing or a future release tag.

## Evidence and known boundaries

Committed references: `HIGHRES.md` §13, `VALIDATION.md` task 33,
`tasks/33-highres-s3.md`, and `docs/images/highres-{straight,curve,hill,rain,tunnel}.png`.

Local ignored evidence from the removed S3 checkout was archived under
`~/.cache/tg2-worktree-backups/20261110-highres-s1-s2-close/evidence/`.
Paths below retain their original build-relative spelling for provenance:

- `build/s3-reverify/worker-report.md` — exact changes, commands and exit codes.
- `build/s3-reverify/final-summary.json`, `qualification-commands.json`,
  `commands.json`, per-track `drive/` summaries and same-frame 1×/N× pairs.
- `build/s3-wide-menu-{before,after}/summary.json` and
  `build/s3-wide-2p/split2p/split-summary.json`.

Final local qualification: 22,575 presented images, 445,794 measured stripe
rows, zero audit violations, maximum stripe-centre error 0.5 output pixel;
all four execution manifests empty. Stock frame hashes remain
`60=2A0B972960C5E325`, `300=1131D937D70234FD`. Stock 1× 60-fps comparison has
360/360 distinct pictures, unchanged sampled RAM and identical WAV hash.
Measured builder cost on this Mac: 0.803/1.067/1.396 ms at 2×/3×/4×; these
are local development CPU measurements, not Deck/GPU performance claims.

S3 fixes worth protecting: serial freshness beyond 65,535 captures; 3× cap
at 4095 columns; native menus/2P not accidentally expanded at 32:9; actual
H32 Off width (3× = 768×600, not 960×600); real option/launcher persistence;
white lane/border/snow classification in the audit.

Remaining scope is deliberate:

- Sprites/HUD/sky/plane-A art retain native detail. S4 handles actors, S5
  HUD/effects/weather and tunnel-opening artwork.
- S3's colour terrain mask can repaint an overlay pixel matching plane B.
  No visible failure was found in approved captures; S4/S5 need explicit
  layer/coverage handling rather than more colour heuristics.
- Full N× + 60-fps temporal qualification belongs to S6; current N× evidence
  includes a short combined smoke only. Stock 1× 60 fps is qualified.
- Scale switching requires restart (live switching is S7); NTSC exclusion
  awaits the future filter. GPU/Deck performance still needs playtest evidence.

## Validation and coordination preferences

The owner questioned the expensive full scale matrix. It had already finished
by the time the reduction reached the worker. **Do not repeat it.** Reuse
valid evidence; use short directed checks in 2×/3×/4×, one long audit at the
largest effective scale, and weather/tunnel in one scale unless an actual
scale-specific failure justifies more. Keep stock gates and manifests.
`HIGHRES.md` §13.4 has the reduced reproduction recipe.

Build/heavy-analysis lock and ≤3 jobs still apply. Run headless; one runtime
at a time. CI remains manual, Linux by default, coordinator only. Do not
publish audio/graphics WIP. Keep ROMs, dumps, generated C and saves out of
git and release assets. Before anything that could discard a checkout,
snapshot untracked files too, following the global instructions.

Orca run: `run_c27967950521`. Successful implementation dispatch:
`ctx_691e1900abf0`; documentation follow-up: `ctx_19e86d733377` (succeeded,
exited and released). There is no active build, runtime, probe or worker
assignment at this checkpoint. Rediscover handles after a restart.
The abandoned historical Fable dispatch `ctx_f40a338dbfcc` has retained
metadata; its exact observation previously confirmed exit. Do not revive
that stale assignment as if S3 were still unfinished.

Other inactive TG2 checkouts were removed from Orca at the owner's request:
`tg2-clean-fm-pcm`, `tg2-deck-aspect-logs`, `tg2-highres-design`,
`tg2-ntsc-scanlines`. Branches were retained. Before removal, full source
trees (including dirty nested submodules and untracked source) were committed
to safety refs and exported to verified Git bundles. Recovery manifest:
`~/.cache/tg2-worktree-backups/20261110/manifest.json`. Original Fable WIP was
also committed/pushed as `bb8f45f`; its safety refs were originally
`refs/keep/tg2-s3-fable-{core,engine,worktree}-20261110` in the respective repos.
After checkout removal, use the verified bundles/manifests above for recovery.

When the owner returns, report where things stand in plain language. If input
is actually needed, follow his global red-callout, ping and Telegram
“Claudão” instructions. The existing Make notification scenario is
`6660765`, connection `11751065` (“Claudão”), organization `9317102`, team
`3207272`; discover and verify its current interface before use, never write
credentials into this repository.

**Task 39 approved (2026-11-11).** Sol delivered continuous growth on
`vittau/tg2-highres-continuous` at `b43af85`, with fractional projection size
and 60 fps size interpolation. The owner played it and said "Está ótimo". Still
pending on that branch: make continuous the default (the default is still stepped), and
investigate the Ayers Rock (Australia, stage 2) rocks that still swap sprites.
That track was never in the evidence; it may be an excluded kind such as `$82`, an
untabulated kind or a fallback. A survey of the other countries is also pending. The follow-up to the
same worker (`ctx_f1e2d6292f22`) failed with `agent-update-prompt`. The owner
must update Codex, then resend it. Merge into `main` after that.

**12:00 update.** The follow-up (dispatch `ctx_57e6e08d6e0a`) committed
`b151a25`, which makes continuous the default. It then stopped when Codex hit its
5-hour usage limit (resets 14:48). The country survey
(`tools/survey_actor_kinds.py`, under the heavy lock) kept running in the
background. Its uncommitted tree is saved at
`refs/keep/tg2-t39-followup-limit-20261111` (`21e1c71`). After 14:48, resend
to `dispatch:ctx_57e6e08d6e0a` to finish the rocks diagnosis, the survey write-up and `worker_done`.

**Task 39 merged (2026-11-11, `9f8345a`).** Continuous growth is the default,
and the Ayers Rock rocks (kind `$96`) are promoted; the owner approved both. Next:
Sol (dispatch `ctx_8ecb75cf3bf5`, branch `vittau/tg2-highres-more-kinds`)
promotes the untabulated ordinary kinds `$81/$93/$97/$A1–$A4`. The pre-existing
Ayers night-road audit failure is mapped as task 41. Task 40 (gamepad triggers,
removal of the in-game CONTROL TYPE menu) is running on OpenCode in the
`tg2-trigger-pedals` worktree (dispatch `ctx_9eebeaa6e88e`).

**Seven more kinds merged (2026-11-11, `06335bd`).** `$81/$93/$97/$A1–$A4`
are promoted with continuous growth. The owner played Egypt at 4×/60 fps and said
"Está ótimo". Still open: poles/specials (task 38), the Ayers night-road audit
(task 41), task 40 (triggers + CONTROL TYPE removal, OpenCode), S5–S7, and
Deck/GPU performance at N×.
