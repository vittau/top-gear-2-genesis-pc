# Task 14: release packaging polish (macOS .app, Linux AppImage, tagged draft releases)

Read `AGENTS.md` (especially Distribution targets), `docs/RELEASING.md`,
`.github/workflows/build.yml`, `tools/release/*`, `patches/segagenesisrecomp/`
(0002 ROM auto-detection, 0004 base path) and the RKA reference packaging:
`~/git/tg2-deps/RocketKnightAdventuresRecomp/tools/build-linux.sh` builds an
AppImage, and that repo also has `tools/release/`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`.

For local runtime tests:
- use **TCP port 4530**;
- kill only your own PIDs;
- never open visible windows (the owner is asleep). Headless/dummy only.

Commit often and push your branch.

## Goals

1. **macOS `.app` bundle.** `TG2Recomp.app` (universal2), with:
   - an `Info.plist`: bundle id `io.github.vittau.tg2recomp`, a version
     from the build, `LSMinimumSystemVersion` matching the build's
     deployment target, and high-DPI support;
   - an icon, if the repo has an asset; otherwise skip it and note so;
   - SDL2 statically linked as today.
   The ROM search (engine patch 0002/0004) must find a ROM placed **next
   to the `.app`**. When the executable runs from `X.app/Contents/MacOS/`,
   also search the directory containing `X.app`. Add or adjust an engine
   patch as needed, recorded in `patches/segagenesisrecomp/README.md`.
   Settings, logs and saves must go to a writable location: next to the
   `.app` if writable, otherwise `~/Library/Application Support/TG2Recomp/`.
   Document which. The CI artifact becomes the `.app` plus the README in a
   zip, and the Gatekeeper first-run instructions stay in `RELEASING.md`.
2. **Linux AppImage** (in addition to the existing tarball). A single-file
   `TG2Recomp-x86_64.AppImage` built in the existing ubuntu-22.04 job:
   - the same glibc ≤ 2.35 constraint;
   - the ROM is found next to the AppImage file. Patch 0002 already
     handles `$APPIMAGE`; verify it;
   - the smoke test runs the AppImage with `--appimage-extract-and-run`
     if FUSE isn't available on the runner;
   - Steam Deck guidance: in `RELEASING.md`, explain adding the AppImage
     as a non-Steam game, with the ROM in the same folder.
3. **Tagged draft releases.** On push of a tag `v*`, a workflow job
   collects the three platform artifacts and creates a **draft** GitHub
   release. Draft only, never published, in this private repo. Attach the
   zips/AppImage plus SHA256SUMS and generate notes from
   `release/<tag>.md` if present. **Do not push any tag yourself.**
   Validate the job logic with `act` if available, or by a dry-run step
   that runs on `workflow_dispatch` with an input `dry_run=true` that
   assembles the release payload but skips creation. Run that dry run
   once on your branch.

## Constraints

- The existing artifact gate (no ROM, no generated C, no GenesisRecomp)
  must apply to the new artifacts too.
- No change to game output: Off hashes unchanged (frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD`).

## Evidence required

- A green `build.yml` run on your branch with the `.app` zip, the
  AppImage and the tarball. Report the URL.
- A macOS job log showing the `.app` smoke run found a ROM placed beside
  the `.app` (decoy name).
- A Linux log showing the AppImage found a ROM beside it.
- The dry-run release payload listing.
- `RELEASING.md` updated, in English and Portuguese end-user sections.
