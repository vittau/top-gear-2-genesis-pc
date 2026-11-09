# Task specs

Each file is the brief a worker got for one piece of work. Finished specs stay
as a record of what was asked; the results and evidence are in
`../VALIDATION.md` and the topic docs. Planned work that has no spec yet is in
[`../ROADMAP.md`](../ROADMAP.md).

New specs take the next number and follow the same opening: read `AGENTS.md`,
the machine-resource rules, and never trigger CI.

| # | Task | State |
|---|---|---|
| [01](01-baseline-bringup.md) | Native 4:3 baseline bring-up of Top Gear 2 (USA) | Done (on `main`, in v0.1.0) |
| [02](02-widescreen.md) | Adaptive widescreen for Top Gear 2 | Done (on `main`, in v0.1.0) |
| [03](03-60fps.md) | True 60 fps races for Top Gear 2 | Done (on `main`, in v0.1.0) |
| [04](04-ci-release-builds.md) | GitHub Actions release builds (Linux/Steam Deck, Windows, macOS) | Done (on `main`, in v0.1.0) |
| [05](05-music-and-sfx.md) | Music and sound effects at the same time | Done (on `main`, in v0.1.0) |
| [06](06-options-ui.md) | Player-facing options (controller-friendly) | Done (on `main`, in v0.1.0) |
| [07](07-hud-edge-anchor.md) | Edge-anchored HUD option for widescreen races | Done (on `main`, in v0.1.0) |
| [08](08-full-game-qualification.md) | Full-game qualification (complete races, tracks, modes) | Done (on `main`, in v0.1.0) |
| [09](09-60fps-physics-parity.md) | Make 60 fps races physics-identical to stock | Done (on `main`, in v0.1.0) |
| [10](10-track-coverage.md) | All-track coverage (16 tracks, rain, nitro) | Done (on `main`, in v0.1.0) |
| [11](11-widescreen-hill-margins.md) | Black widescreen margins on hills (owner-reported) | Done (on `main`, in v0.1.0) |
| [12](12-performance-audio-pacing.md) | Performance and audio pacing on low-end CPUs (owner-reported) | Done (on `main`, in v0.1.0) |
| [13](13-renderer-tunnel-flicker-overscan.md) | Widescreen renderer fixes from the second owner playtest | Done (on `main`, in v0.1.0) |
| [14](14-release-packaging-polish.md) | Release packaging polish (macOS .app, Linux AppImage, tagged draft releases) | Done (on `main`, in v0.1.0) |
| [15](15-audio-device-regression.md) | Real-device audio is broken (pops, dropouts, delays): owner bug, top priority | Done (on `main`, in v0.1.0) |
| [16](16-both-audio-real-play.md) | BOTH sound mode doesn't work in real play, and its menu text looks wrong (owner bug) | Done (on `main`, in v0.1.0) |
| [17](17-widescreen-menu-screens.md) | Widescreen for every extendable non-race screen | Deferred to the final phase ([roadmap](../ROADMAP.md#widescreen-on-the-other-screens)) |
| [18](18-music-tempo-reference.md) | Music tempo/pitch vs a reference (owner bug: music slightly slow, occasional speed changes) | Done (on `main`, in v0.1.0) |
| [19](19-vgm-tempo-and-logic-check.md) | Pin music tempo and check the music logic against the owner's VGM rips | Done (on `main`, in v0.1.0) |
| [20](20-both-dual-chip.md) | BOTH sound mode via a second virtual sound chip (owner bug: BOTH sounds like noise) | Done (on `main`, in v0.1.0) |
| [21](21-race-crop-overscan.md) | Crop the race's black bands (owner request) + HUD Edges map split | Done (on `main`, in v0.1.0) |
| [22](22-release-qualification.md) | v0.1.0 release qualification (every race, default options) | Done (on `main`, in v0.1.0) |
| [23](23-app-icon.md) | Project and application icon (owner request) | Done (on `main`, in v0.1.0) |
| [24](24-interior-label-650c.md) | Fix the skipped scene-init call at $00650C (release bug) | Done (on `main`, in v0.1.0) |
| [25](25-state-load-and-coverage.md) | Cross-session save states, then the 19 unreached races | Done (on `main`, in v0.1.0) |
| [26](26-owner-playtest-e586c00.md) | Bugs from the owner's e586c00 playtest (release) | Done; merged 2026-11-09, after v0.1.0 |
| [27](27-setup-screen-quickstate.md) | Save states on the car setup screen | Mapped, not started ([roadmap](../ROADMAP.md#save-states-on-the-car-setup-screen)) |
| [28](28-ntsc-scanlines.md) | Blargg NTSC filter and scanlines | Paused by the owner (2026-11-09), not started |
| [29](29-highres-design.md) | High-resolution rendering — ground truth and design | In progress |
| [30](30-clean-fm-and-pcm.md) | Clean FM, separate volumes, better engine/nitro PCM | In progress |
