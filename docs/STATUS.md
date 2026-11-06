# Project status (session paused 2026-11-06 ~01:30)

Overall estimate: about **75%** of the goal, which is a native Top Gear 2
on Windows, Linux/Steam Deck and macOS, with widescreen and true 60 fps,
plus music and SFX together. Everything below has been verified
headlessly. The owner has played one short session (Linux, Ryzen 5 3500U).

## On `main`

| Area | State | Docs |
|---|---|---|
| Native 4:3 baseline | Boot → menus → full 4-lap race → results/shop/next race; 2P split-screen; 33.7-min soak. 0 dispatch misses. | `BRINGUP.md`, `VALIDATION.md` |
| Widescreen | Adaptive / 16:9 / 21:9 race renderer: road, background, sprites in the margins. HUD Centered or Edges. Off is byte-identical to stock. | `WIDESCREEN.md` |
| 60 fps | Stock simulation plus host-only interpolation. Identical WRAM over 16000 frames; 60 pictures/s; no road artefacts; adds 50 ms display latency. | `FRAMERATE.md` |
| Hill margins (owner bug) | Black margin bands on downhills and the top-window line fixed; per-line margin audit at 0 violations in 8 combinations. Merged 2026-11-06. | `WIDESCREEN.md` |
| Options | Widescreen / 60 fps / HUD in the launcher and the in-game overlay (gamepad: Back+RB), persisted in `settings.ini [mods.*]`. | `RELEASING.md` |
| CI | `build.yml`: Linux (glibc ≤ 2.35, Deck), Windows x64, macOS universal2. The ROM comes from the private repo via deploy key; artifacts are gated against ROM or generated C. | `RELEASING.md` |
| ROM | Auto-detected by CRC next to the executable, whatever the file name. | `BRINGUP.md` |

Engine changes live as patches in `patches/segagenesisrecomp/`. The
submodule pin is upstream `dd520f1`.

## In progress at pause (worktrees under `~/orca/workspaces/top-gear-2-genesis-pc/`)

Every tree has a snapshot at `refs/keep/<worktree>-pause`, pushed to origin.

| Task | Worktree / branch | State |
|---|---|---|
| 12 Performance + audio pacing (owner bug) | `tg2-performance` | Music tempo wobbles under CPU load; release build is better than dev. Also asked: decouple music from frame pacing, and fix the feedback replay being written to `~/.local/bin/logs`. Nothing pushed yet. |
| 10 All-track coverage | `tg2-track-coverage` | Reversing the password system to reach all 16 tracks, rain and nitro. Uncommitted password tools only. |
| 05 Music + SFX "BOTH" | `tg2-audio-both` | Stalled 2026-11-05 18:48: the session died after a provider overload. Restarted 2026-11-06 with a fresh OpenCode worker, continuing from commit 144132c and the uncommitted draft. |

## Owner feedback (first playtest)

- Controls: OK.
- Black margins on downhills: fixed and merged.
- Music slightly slow / wobbling: task 12.
- Not yet answered: whether the 50 ms 60 fps latency is acceptable.

## Owner feedback (second playtest, release-config build of f618606) — not yet dispatched

1. **Tunnel looks wrong in widescreen.** Inside a tunnel, the native centre
   draws black walls/ceiling with the exit window, while the margins keep
   showing the outside sky/skyline from plane B. Screenshot:
   `build/user-reports/tunnel-margins.png`. The margins must follow
   whatever covers plane B in the native edge columns (tunnel walls).
2. **Music still slow during races.** Forwarded to task 12.
3. **Brief black margin lines still flicker on road tilts** (smaller than
   before). **Not visible while paused**, so it only appears in motion;
   paused shows only repeated real pictures. Strong suspect: the 60 fps
   synthesized frames. Repro: run the margin audit on every presented
   frame, including the synthesized ones, and compare with 60 fps off. It's a residual of the hill fix, probably on lines or frames
   the audit doesn't cover (interpolated 60 fps frames?).
4. **Red marks in the black top band.** This is stock window-plane
   pattern 0 at native x=16–31, normally hidden by CRT overscan. Proposal:
   a presentation option "Hide overscan" (default on) that blanks the top
   window band.

## Open items after these

- Real-device checks: Steam Deck (Gamescope, controller only), Windows,
  macOS (unsigned; the payload is a folder, not a `.app`).
- 14 of 16 tracks, rain and nitro not yet seen (task 10).
- First public release: the owner decides when to make the repo public.
  `vittau/top-gear-2-private-inputs` must stay private forever.

## For playtests

The release artifact is unpacked at `~/Games/TG2-release-69a96ef/`, with
the ROM next to the binary. The dev build is
`build-main/TG2Recomp ~/roms/genesis/tg2.bin`.
