# Task 04: GitHub Actions release builds (Linux/Steam Deck, Windows, macOS)

Read `AGENTS.md` (especially "Distribution targets"), `docs/BRINGUP.md`,
`CMakeLists.txt`, `tools/build-linux.sh`, `tools/apply-engine-patches.sh`
and `.github/workflows/rom-access.yml`. Look at how the reference project
packages releases: `~/git/tg2-deps/RocketKnightAdventuresRecomp/tools/`
(`build-linux.sh`, `build-windows.ps1`, `release/`, `verify_release.py`)
and its `RELEASING.md`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- for any local runtime test use **TCP port 4420**, and kill only processes
  you started (by PID).

Other agents work on widescreen and 60 fps in parallel. Only touch
`.github/`, build/packaging scripts under `tools/`, CMake packaging bits
and `docs/RELEASING.md`. Commit often and push your branch.

## Goal

`.github/workflows/build.yml` runs on push to any branch, on pull requests
and on manual dispatch. It produces downloadable build artifacts:

| Artifact | Runner | Requirement |
|---|---|---|
| `TG2Recomp-linux-x86_64` | `ubuntu-22.04` (or a Steam Runtime "sniper" container) | Must run on Steam Deck (SteamOS 3.x). glibc no newer than 2.35. Self-contained: AppImage or a folder with a bundled/static SDL2 (`$ORIGIN` rpath). Must work under Gamescope with a controller only. |
| `TG2Recomp-windows-x64` | `windows-latest` (MSVC) | A folder with the exe and the required DLLs (SDL2), nothing else to install. |
| `TG2Recomp-macos` | `macos-latest` (arm64), plus Intel x86_64 via a universal2 binary or a second job on an Intel runner | `.app` bundle or a folder. SDL2 bundled. Document the Gatekeeper/quarantine step (unsigned). |

## Hard constraints

- **The ROM.** Each job fetches the private ROM exactly as
  `rom-access.yml` does: `actions/checkout` of
  `vittau/top-gear-2-private-inputs` with secret `TG2_ROM_DEPLOY_KEY`,
  `persist-credentials: false`. It verifies the SHA-256 and uses the ROM
  **only** for C generation.
- **What must never be in an artifact, cache or log:** the ROM, generated
  C (`generated/`), `GenesisRecomp`, save states, or debug dumps. Add a
  verification step that fails the job if any file in the artifact matches
  the ROM hash, any `.bin`/`.md`/`.gen`/`.smd` larger than 512 KB is
  present, or a `generated/` directory or GenesisRecomp binary is present.
  Adapt RKA's `verify_release.py` idea.
- **Engine patches.** Apply them via `tools/apply-engine-patches.sh`, or
  the equivalent on Windows; write a PowerShell or Python twin if bash
  isn't usable there.
- **Debug features.** Release builds disable the TCP debug server and
  reverse-debug rings if CMake supports that (check the engine/RKA
  options). Note what was disabled.
- **Using the build.** A user runs it with the ROM dropped next to the
  binary, with zero setup (the content-based auto-detection from engine
  patch 0002). On macOS, "next to the binary" means next to the `.app`;
  check that patch 0002's search covers that, and report if it doesn't.
- **Pins.** Pin action versions. Cache only the toolchain/SDL builds,
  never generated C.

## Evidence required

- A green run of `build.yml` on your branch, with all three platform
  artifacts. Report the run URL.
- For the Linux artifact: download it in a separate job (or locally) and
  show `objdump -T`/`ldd` output proving the maximum required glibc symbol
  version is ≤ 2.35, plus a headless smoke run (SDL dummy video/audio,
  `--no-launcher`, ROM auto-detected from the executable directory). It
  should run about 600 frames, exit 0, and log that the ROM was found.
- For Windows and macOS: a headless smoke step in the job itself (same
  ~600-frame run, dummy drivers) if the runner supports it; otherwise
  explain why not.
- `docs/RELEASING.md`: how to cut a release, what each artifact contains,
  and the end-user instructions in Portuguese and English (drop the ROM
  next to the executable and run). Include Steam Deck instructions: adding
  it as a non-Steam game in Desktop Mode, and where the ROM goes.

If one platform can't be made green, deliver the others green and give a
precise diagnosis for the failing one. Report that as partial.
