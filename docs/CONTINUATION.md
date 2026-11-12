# Current project state

Historical log, preserved verbatim: [continuation-log-2026-11.md](history/continuation-log-2026-11.md). Its old assignments, draft links and “next step” instructions are historical.

## Shipped

The latest public release recorded in this repository is **v0.3.0**, tagged at
`7e19228` ([release notes](../release/v0.3.0.md)). It includes widescreen,
60-fps races, BOTH audio, save states, volumes, linear filtering, high-resolution
road/background and detailed actors with continuous growth, RT/LT pedals and
the native four-row setup carousel. S3, S4 and continuous actor growth were
owner-approved and merged; they are not unfinished implementation assignments.
The seven additional ordinary actor kinds also shipped (`06335bd` precedes
the release tag).

Internal resolution defaults to 1×; 2×/3×/4× remains experimental and requires a
restart. HUD/sky/poles/special artwork retain native detail. The owner has played
Linux, Apple Silicon macOS and the Deck tarball; Windows/Intel macOS still lack
real-device playtests. Physical trigger testing and Deck N× performance remain
unverified. Preserve the Deck user's extracted tarball folder, ROM/settings/
saves and existing Steam shortcut; do not require migration to AppImage.

## Main since that release

The review work through `597f287` is merged but **not in v0.3.0**:

- Phase A: safe in-place engine patch application with snapshots and tree stamps,
  removal of retired state, and measured baseline preservation.
- Phase B: game modules/headers/options cleanup, release diagnostic guards,
  a single version source and the official picture/audio regression tool.
- Overlay footer: help text wraps inside the panel at default and Deck sizes.
- Phase C: 47 historical patches consolidated into 16 area patches, local
  commit/export maintenance modes, dead-code removal and game-owned data paths.
- Phase D: native BOTH sound policy and menu row drawing replace temporary
  sound-word steering and frame-post repainting, preserving the golden output.

The closing review additionally synchronizes live RACE SOUND page choices and
repairs the HUD checker; evidence is in [closing.md](reviews/closing.md).
No new release or cross-platform CI qualification accompanies these reviews.
Launcher enhancements continue to be presented as **mods**. Keep the finished
Music/SFX faders; the rejected Clean FM/engine-sample options must not return.

## Open work

- [Detailed compound poles, task 38](tasks/38-highres-poles.md): mapped, not
  implemented; preserve compound identity, height, clipping and priority.
- [Ayers Rock road audit, task 41](tasks/41-ayers-road-audit.md): low-priority
  checker-versus-renderer diagnosis, not fixed. Stage 2 is **daytime**, not
  night. The owner found the road visually correct; the audit also fails with
  actors disabled. Compare failing 1×/N× rows before changing a renderer or
  threshold.
- High-resolution S5 (HUD/effects/weather/tunnel art), S6 (full combined N×/
  60-fps temporal qualification) and S7 (live scale changes) remain separate.
  See [HIGHRES.md](HIGHRES.md) and [ROADMAP.md](ROADMAP.md).
- [NTSC/scanlines, task 28](tasks/28-ntsc-scanlines.md): owner-paused; the licence
  decision remains a gate before adding Blargg-derived code. Its old patch
  number reservations predate Phase C; use the current patch README if resumed.
- Platform/device qualification above and the remaining audio/save-state/
  presentation backlog are tracked in [ROADMAP.md](ROADMAP.md). Do not infer
  device performance from this Mac's CPU measurements.

## Resume work

Read `AGENTS.md`, the owner's new request and the relevant task/evidence first.
Start from current `origin/main`; do not revive historical dispatch IDs or
assume old worktrees/build paths still exist. Reading this file does not launch
an implementation task. Model restrictions for high-resolution work and all
resource/CI rules remain in `AGENTS.md`.

Apply the current engine/core/UI stack with `tools/apply-engine-patches.sh`
(the single Python applicator snapshots dirty/untracked source before resets).
Keep the recorded submodule pins and project-owned patches; do not commit
patched submodule gitlinks. Maintenance/import/export and historical numbering
are documented in [the patch README](../patches/segagenesisrecomp/README.md).

```sh
flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh
flock ~/.cache/tg2-heavy.lock python3 tools/regression.py --uncapped
```

The regression tool requires Python 3.11+ and the local USA ROM; it compares
SFX/MUSIC/BOTH, options off/default on, live changes and SOUND-page hashes with
`tools/regression-golden.json`, streams/deletes WAVs, and checks the four
execution manifests. Do not re-record it to accept unexplained differences.
For focused HUD qualification, use `tools/verify_hud.py --uncapped` with Pillow
and its documented centered-reference recording step. Release-config evidence
and this Mac's probe workarounds are in the review reports.

For new high-resolution work, reuse valid evidence: short directed per-scale
checks, one long audit at the largest effective scale, weather/tunnel in one
scale unless a specific failure warrants more ([HIGHRES §13.4](HIGHRES.md#134-reproduction-and-reduced-validation-plan)).
Do not repeat the old full matrix automatically. For a requested visible launch,
unset `LNG_SCRIPT` and `LNG_TEST_HIDDEN`; setting either to `0` still hides it.

Evidence: [phase-a.md](reviews/phase-a.md), [phase-b.md](reviews/phase-b.md),
[overlay-footer.md](reviews/overlay-footer.md), [phase-c.md](reviews/phase-c.md),
[phase-d.md](reviews/phase-d.md), [closing.md](reviews/closing.md), plus the focused
HIGHRES/AUDIO/VALIDATION ledgers and task headers. Some ledger sections retain
older checkpoint wording; use the release/tag history and current task status
for completion state. Captures, dumps, WAVs, ROMs and generated C stay out of Git.
Historical removed-worktree recovery manifests are listed in the archived log.
