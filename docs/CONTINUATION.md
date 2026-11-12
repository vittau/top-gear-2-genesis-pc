# Current project state

Historical log, preserved verbatim: [continuation-log-2026-11.md](history/continuation-log-2026-11.md). Its old assignments, draft links and “next step” instructions are historical.

## Shipped

The latest public release is **v0.4.0**, tagged at `999d641` and published on
2026-11-12 ([release notes](../release/v0.4.0.md), CI run 43313690404, all
three platforms green). It contains everything in v0.3.0 (`7e19228`:
widescreen, 60-fps races, BOTH audio, save states, volumes, linear filtering,
high-resolution road/background, detailed actors with continuous growth, RT/LT
pedals, the native four-row setup carousel) plus:

- smoother N× road: bounded whole-band fit of silhouettes and inner colour
  boundaries within two native pixels ([road-wobble.md](reviews/road-wobble.md));
- BOTH engine sound kept across quickstate loads from the menus and rewinds
  (engine patch 0015, optional chip-1 trailer; older states still load —
  [engine-sound-load.md](reviews/engine-sound-load.md));
- launcher volume sliders and Race Sound labels, wrapped option help, the
  synced Race Sound page;
- the architecture review (Phases A–D and closing, `docs/reviews/`): safe patch
  application, `tools/regression.py` golden, release diagnostic guards, single
  version source, 16 area patches, native BOTH policy.

S3, S4, continuous actor growth and the road smoothing were owner-approved;
they are not unfinished assignments. Internal resolution defaults to 1×;
2×/3×/4× remains experimental and requires a restart. HUD/sky/poles/special
artwork retain native detail. The owner has played Linux, Apple Silicon macOS
and the Deck tarball; Windows/Intel macOS still lack real-device playtests.
Physical trigger testing and Deck N× performance remain unverified. Preserve
the Deck user's extracted tarball folder, ROM/settings/saves and existing Steam
shortcut; do not require migration to AppImage.

Launcher enhancements continue to be presented as **mods**. Keep the finished
Music/SFX faders; the rejected Clean FM/engine-sample options must not return.
`tools/regression.py` needs Python 3.11+ (on the Mac use
`/opt/homebrew/bin/python3.14`).

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
[phase-d.md](reviews/phase-d.md), [closing.md](reviews/closing.md),
[engine-sound-load.md](reviews/engine-sound-load.md), plus the focused
HIGHRES/AUDIO/VALIDATION ledgers and task headers. Some ledger sections retain
older checkpoint wording; use the release/tag history and current task status
for completion state. Captures, dumps, WAVs, ROMs and generated C stay out of Git.
Historical removed-worktree recovery manifests are listed in the archived log.
