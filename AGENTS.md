# Top Gear 2 (Genesis) — native PC static recompilation

Goal: native Linux (and later Windows) executable of **Top Gear 2 (USA), Sega
Genesis**, built by static recompilation with the `segagenesisrecomp`
framework. The finished port runs **widescreen (adaptive, 16:9+)** at a
**true 60 fps**. No emulator core.

`docs/ORIGINAL_PLAN.md` is the owner's initial roadmap. Treat it as a
suggestion, not a spec. Some of the tools it names don't exist as described.

## Layout

| Path | What |
|---|---|
| `segagenesisrecomp/` | Engine submodule (recompiler + shared runner). Read its `CLAUDE.md`, `PRINCIPLES.md` and `DEBUG.md` before working on it. |
| `recomp-ui/` | Launcher/overlay UI submodule (same one RocketKnightAdventuresRecomp uses). |
| `game/` | Everything specific to Top Gear 2: `game.toml`, `tg2_spec.c`, renderer, options, discovery evidence. |
| `tools/` | Project scripts: build, probes, smoke tests. |
| `docs/` | Findings, RAM/ROM maps, validation ledger. |
| `patches/segagenesisrecomp/` | Engine fixes we need but can't push upstream. Keep as `git format-patch` files, applied by `tools/apply-engine-patches.sh`. |

Reference implementation: `~/git/tg2-deps/RocketKnightAdventuresRecomp`. It
is a non-Sonic game with no community disassembly that reached adaptive
widescreen, so it's the closest template. Copy its structure (CMake, spec,
`game.toml` discovery loop, `tools/build-linux.sh`, its custom `GameVideo`
renderer) and adapt it. Don't copy its game-specific addresses.

## ROM

- Top Gear 2 (USA). CRC32 `BD3074D2`, SHA-256
  `b41909d53090e28c1d1e50941dad01676dd3d19caf26c75f66aac6a3ad689ba6`, 1 MB.
  Header serial `GM T-23066 -00`, region U.
- Vectors: SSP `$00FFFFFE`, entry `$000200`, V-int `$00FF01EA` (RAM),
  H-int `$00FFF9FE` (RAM).
- Read-only copy at `~/roms/genesis/tg2.bin`. Point builds/tools at it by
  path. **Never copy a ROM, dump, save state or generated C into git.**

## Rules

- Never edit generated C. Fix `game.toml`, discovery evidence, or the
  recompiler/runner, then regenerate.
- Disassembly and runtime evidence are ground truth (engine PRINCIPLES #16).
  Check every new function seed against the raw ROM before adding it.
- After every run, check `dispatch_misses.toml` / `floor_coverage.toml`
  next to the executable. Fix the misses in discovery, not with stubs.
- Keep game-specific code in `game/`. Change the engine only for genuine
  framework bugs. Record each engine change as a patch in
  `patches/segagenesisrecomp/` with a one-line reason in
  `patches/segagenesisrecomp/README.md`.
- Widescreen and 60 fps must be options. With both off, the output must stay
  byte-identical to the stock 4:3 behaviour (framebuffer hashes).
- One runtime instance at a time. Kill the previous one before relaunching.
- Run headless/TCP probes. Don't steal the desktop with windows unless the
  task asks for it.
- Tools live in `~/tools` (cmake 4.1.2, ninja), linked into `~/.local/bin`.
  There is no passwordless sudo. Ask before anything that needs it.
- Commit often in small, described commits and push your branch to origin. Never commit ROM-derived artifacts.
- Commit identity: `Vitor Machado <2932830+vittau@users.noreply.github.com>`. It's set in this repo's git config, so don't override it. Never put a personal e-mail in commits, patches (`git format-patch` `From:` headers) or docs.

## Machine resources (5.7 GiB RAM, 8 threads)

This laptop has only **5.7 GiB of RAM**. On 2026-11-06 systemd-oomd killed
the whole Orca session (77 processes), including every worker, during
parallel builds and a 1.3 GB in-memory WAV analysis.

- Builds use **at most 3 jobs** (`JOBS=3 tools/build-linux.sh`, `ninja -j3`).
- Wrap every build and every heavy analysis in the shared machine-wide lock:
  `flock ~/.cache/tg2-heavy.lock <command>`. Only one heavy step runs at a
  time, across all agents.
- Never load whole WAVs or dumps into memory. Stream them (memmap, chunked
  reads, or downsample first), and keep any single process under ~600 MB RSS.
- At most one TG2Recomp instance per agent. Kill it as soon as its capture is
  done.
- Delete large temporary files (WAVs over 100 MB, dumps) once their numbers
  are extracted.
- The coordinator runs at most two workers at once, and never two that both
  build heavily at the same time.

## CI budget (GitHub Free, private repo)

The owner does not pay for GitHub. The private repo gets **2000 Actions
minutes/month**, and macOS minutes count **10x** and Windows **2x**. A full
3-platform run costs roughly 15x a Linux-only run. Running every push burned
the monthly quota on 2026-11-06.

- CI **never** runs on ordinary pushes or pull requests. `build.yml` runs
  only on manual `workflow_dispatch` (default `platforms=linux`) and on
  release tags `v*`. `rom-access.yml` is manual only.
- Validate locally first: `tools/build-linux.sh`, probes, hashes, audits.
  CI is for cross-platform proof and releases, not for iteration.
- Workers must **never** trigger CI (dispatch, tag, re-run) or change these
  triggers. Only the coordinator dispatches CI, at most a few runs a week.
  Use `platforms=all` only to qualify a release candidate or a change that
  touches platform-specific code (Windows/macOS paths, packaging).
- Never push `v*` tags without the owner's go-ahead.
- If the quota is exhausted, wait for the monthly reset. Don't work around
  it, e.g. with new repos or accounts.

## Reporting

Finish with evidence: commands run, exit codes, frame hashes or screenshot
paths, dispatch-miss counts. Say plainly what is verified and what isn't.

## Distribution targets

- Release targets: Windows x64, Linux x86_64 (including Steam Deck / SteamOS / Gamescope with controller-only operation), and macOS on Apple Silicon and Intel.
- Build Linux releases against an older glibc than this host's 2.44; bundle or statically link SDL2 and avoid dependencies on host installation paths. This workstation build is development evidence, not a qualified release artifact.
- Zero setup: users place their ROM next to the executable and launch it. Search the executable directory and working directory by content for CRC32 `BD3074D2`, regardless of filename or extension; show a clear message or launcher picker only when no match exists. Deck users must not need terminal commands.
- Releases contain prebuilt native code; users never build or run a generator. Generated C, ROMs, dumps and save states stay out of git and release payloads.
