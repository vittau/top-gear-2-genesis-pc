# Releasing Top Gear 2 Recomp

`.github/workflows/build.yml` builds the three distribution targets and
publishes downloadable artifacts. It runs only on a manual dispatch or a `v*`
release tag (see [CI cost control](#ci-cost-control)):

| Artifact | Runner | Payload |
|---|---|---|
| `TG2Recomp-linux-x86_64` | `ubuntu-22.04` (glibc 2.35) | folder + `TG2Recomp-linux-x86_64.tar.gz` + `TG2Recomp-x86_64.AppImage` + `.sha256` for both |
| `TG2Recomp-windows-x64` | `windows-latest` (MSVC, default VS generator, static CRT) | `TG2Recomp.exe`, `assets/`, `licenses/`, `README.txt` |
| `TG2Recomp-macos` | `macos-latest` (universal2: arm64 + x86_64) | staged folder + `TG2Recomp-macos.zip` (contains `TG2Recomp.app` and `README.txt`) + `.sha256` |

Linux ships both a tarball and a single-file AppImage; the tarball remains the
simple folder layout, the AppImage is the one-file download for Steam Deck and
desktop integration. Windows has no executable bit, so the artifact is the
folder itself (the release job zips it). macOS ships a proper `.app` bundle
inside a zip: GitHub artifact ZIPs do not preserve the executable bit, so
publish the `.zip`, which keeps `TG2Recomp.app` runnable.

## Runtime requirements

- **Linux:** glibc ≤ 2.35 and the standard desktop graphics stack every
  SteamOS 3.x or desktop image ships — OpenGL (GLVND), X11 or Wayland,
  FreeType and HarfBuzz. SDL2 and libstdc++ are linked statically; `ldd`
  shows only those system libraries and the binary carries a `$ORIGIN`
  RUNPATH for any future bundled library. The AppImage contains the same
  binary and adds no bundled host libraries, so its floor is identical.
- **Windows:** one executable, static MSVC runtime and static SDL2. No DLLs
  and no Visual C++ redistributable.
- **macOS:** a standard universal2 `.app` with only system frameworks. The
  payload deliberately skips Homebrew FreeType/HarfBuzz (arm64-only dylibs
  would break the x86_64 slice and add host-specific dependencies), so the
  launcher uses outline emoji instead of colour emoji. The bundle declares
  high-DPI (`NSHighResolutionCapable`) and a minimum of macOS 11.0.


## What the build does

1. Checks out this repository with all submodules.
2. Checks out `vittau/top-gear-2-private-inputs` with the
   `TG2_ROM_DEPLOY_KEY` deploy key (`persist-credentials: false`) and verifies
   the ROM SHA-256. The ROM is used only as the recompiler's input; it is never
   copied into a payload, cache or log.
3. Applies `patches/segagenesisrecomp/*.patch` through
   `tools/apply-engine-patches.sh` on Linux/macOS and its portable Python twin
   `tools/apply-engine-patches.py` on Windows.
4. Builds SDL2 2.28.5 from the pinned, SHA-256-verified upstream tarball
   (`tools/release/fetch-sdl.py`) and links it **statically**.
5. Configures a Release build with native IPO and the debug instrumentation
   off (`GEN_ENABLE_TRACE=OFF`, `SONIC_REVERSE_DEBUG=OFF`), so release payloads
   have **no TCP debug server and no reverse-debug rings**.
6. Stages only allowlisted files (`tools/release/stage_payload.py`), runs
   `tools/release/verify_artifact.py`, and does a 600-frame headless smoke run
   with dummy video/audio drivers and the ROM dropped next to the executable
   under an unrelated filename (`tools/release/smoke_run.py`).
7. On Linux, builds `TG2Recomp-x86_64.AppImage` from the staged payload with
   the pinned `appimagetool` (`tools/release/build-appimage.sh`), extracts the
   finished file again and gates its contents and glibc floor. Its smoke run
   drops the ROM beside the `.AppImage` and uses `--appimage-extract-and-run`
   when the runner has no usable FUSE.
8. On macOS, builds `TG2Recomp.app` (`Contents/MacOS/TG2Recomp`,
   `Contents/Info.plist`, `Contents/Resources/assets`, `licenses`, icon),
   checks the bundle metadata and universal2 slices, and runs the smoke test
   with the ROM beside the `.app`.
9. Uploads the artifact. A separate `linux-verify` job downloads the uploaded
   Linux artifact, checks the tarball and AppImage hashes, extracts both, proves
   the highest required glibc symbol version is ≤ 2.35 (`objdump -T`,
   `tools/release/verify_glibc.py`, plus a clean `ldd` after installing the
   desktop runtime libraries), and repeats both smoke runs on the downloaded
   payload.

Pull requests from forks are skipped: GitHub does not expose repository
secrets to fork PRs, so the private ROM (and therefore C generation) is not
available. Branch PRs in this repository build normally.

## CI cost control

The owner does not pay for GitHub Actions, so CI never runs on ordinary pushes
or pull requests (AGENTS.md, "CI budget"):

| Event | Jobs |
|---|---|
| `workflow_dispatch`, `platforms=linux` (default) | Linux + `linux-verify` only |
| `workflow_dispatch`, `platforms=all` | full matrix (Linux, Windows, macOS) |
| `workflow_dispatch`, `platforms=all`, `dry_run=true` | full matrix + release assembly, no GitHub release |
| Push of a `v*` tag | full matrix + draft release job |

Validate locally first. Use `platforms=all` only for a release candidate or a
change to platform-specific code. Concurrency keeps `cancel-in-progress`, so a
superseded run stops instead of billing twice.

## Packaging verification status

Before the first tagged draft release, these points need a green CI run:

- macOS job log showing the `.app` smoke run found a ROM placed beside
  `TG2Recomp.app` under a decoy filename (engine patch 0007).
- Linux job log showing the AppImage found a ROM beside the `.AppImage` and,
  when FUSE is unavailable, ran with `--appimage-extract-and-run`.
- A `workflow_dispatch` run with `dry_run=true` printing the real assembled
  payload (four deliverables plus `SHA256SUMS`).
- The full green run containing all three platform artifacts.

Verified locally on the development host instead: the Linux tarball and
AppImage build and boot with the ROM detected by content, the Off-mode frame
hashes are unchanged, the macOS bundle layout and path rules are unit-tested,
and `assemble_release.py` gates a synthetic artifact set. The macOS binary
itself and the GitHub release API call cannot be exercised on Linux.

## Cutting a release

1. Confirm `git status` is clean, submodules are at their committed pins, and
   a manual `build` run with `platforms=all` is green.
2. Write optional hand-written notes in `release/<tag>.md` (for example
   `release/v0.1.0.md`). If the file is absent the release body is generated
   from the commits.
3. Push the tag (`git tag v0.1.0 && git push origin v0.1.0`). The `build`
   workflow builds all three platforms and the `release` job then:
   - downloads the three artifacts,
   - assembles the payload with `tools/release/assemble_release.py`, which
     re-verifies the tarball, the extracted AppImage, the macOS zip and the
     Windows folder with the same artifact gate,
   - creates **only a draft** GitHub release with
     `TG2Recomp-linux-x86_64.tar.gz`, `TG2Recomp-x86_64.AppImage`,
     `TG2Recomp-windows-x64.zip`, `TG2Recomp-macos.zip` and `SHA256SUMS`.

   The job never publishes the release; the owner reviews the drafts and
   publishes manually. Nothing in CI pushes a tag.
4. Validate the packaging without tagging: run `build` with
   `workflow_dispatch`, `platforms=all` and `dry_run=true`. That
   assembles and prints the exact payload listing (and the build artifacts
   remain downloadable) but skips the GitHub release call.

Release payloads contain `BUILD-INFO.txt` with the game and engine revisions
and `README.txt` with end-user instructions. The `build` run URL identifies the
exact commit each payload came from.

The artifacts are release candidates until the owner validates on real
hardware (Steam Deck/SteamOS with a controller, Windows, and both macOS
architectures). CI proves the Linux glibc floor and a headless boot on all
three platforms; it does not prove audio, input or rendering on a device.

## End-user instructions (English)

You need a Top Gear 2 (USA) ROM. The game identifies it by content (CRC32
`BD3074D2`, 1,048,576 bytes), so any filename and extension work.

**Windows and Linux tarball**

1. Unpack the release: the Windows folder as-is, or
   `TG2Recomp-linux-x86_64.tar.gz` on Linux.
2. Put your ROM in the same folder as `TG2Recomp` / `TG2Recomp.exe`.
3. Run `TG2Recomp` or `TG2Recomp.exe`.
4. Done: no installation, setup, or emulator. If no matching ROM is found the
   launcher/picker opens instead.

**macOS**

1. Unpack `TG2Recomp-macos.zip` and move `TG2Recomp.app` to *Applications*.
2. The app is not signed by Apple. Clear the download quarantine once, in
   Terminal: `xattr -dr com.apple.quarantine /Applications/TG2Recomp.app`
3. Open `TG2Recomp.app` and pick your ROM in the launcher. The app keeps a copy
   and starts the game directly from then on.

To keep it portable instead, leave `TG2Recomp.app` outside *Applications* and
put the ROM next to it (in the folder containing the bundle, not inside it).

**Linux AppImage (single file)**

1. Put `TG2Recomp-x86_64.AppImage` and your ROM in the same folder.
2. Make the file executable once, then run it (double-click, or
   `./TG2Recomp-x86_64.AppImage`). If your file manager offers an "integrate"
   option it also adds a menu entry.
3. If the system has no FUSE, run it once as
   `./TG2Recomp-x86_64.AppImage --appimage-extract-and-run`; SteamOS normally
   has FUSE and the plain launch works.

`settings.ini`, logs and saves are written next to the executable (Linux,
Windows). On macOS an app in *Applications* keeps them, with the ROM copy, in
`~/Library/Application Support/TG2Recomp/`; a portable copy writes them next
to `TG2Recomp.app`, or to that folder when its own folder is read-only.

## Instruções para o usuário (Português)

Você precisa da ROM de Top Gear 2 (USA). O jogo identifica o cartucho pelo
conteúdo (CRC32 `BD3074D2`, 1.048.576 bytes), então qualquer nome e extensão
funcionam.

**Windows e tarball do Linux**

1. Descompacte a versão: a pasta do Windows, ou o
   `TG2Recomp-linux-x86_64.tar.gz` no Linux.
2. Coloque a ROM na mesma pasta de `TG2Recomp` / `TG2Recomp.exe`.
3. Execute `TG2Recomp` ou `TG2Recomp.exe`.
4. Pronto: não precisa instalar, configurar nem usar emulador. Se nenhuma ROM
   compatível for encontrada, o seletor de arquivos abre.

**macOS**

1. Descompacte o `TG2Recomp-macos.zip` e mova o `TG2Recomp.app` para
   *Aplicativos*.
2. O app não é assinado pela Apple. Remova a quarentena do download uma vez,
   no Terminal: `xattr -dr com.apple.quarantine /Applications/TG2Recomp.app`
3. Abra o `TG2Recomp.app` e escolha a ROM no launcher. O app guarda uma cópia
   e, daí em diante, abre o jogo direto.

Para usar no modo portátil, deixe o `TG2Recomp.app` fora de *Aplicativos* e
coloque a ROM ao lado dele (na pasta que contém o pacote, não dentro dele).

**AppImage do Linux (arquivo único)**

1. Coloque `TG2Recomp-x86_64.AppImage` e a ROM na mesma pasta.
2. Torne o arquivo executável uma vez e execute (duplo clique ou
   `./TG2Recomp-x86_64.AppImage`). Se o gerenciador de arquivos oferecer
   "integrar", ele também cria um atalho no menu.
3. Se o sistema não tiver FUSE, execute uma vez como
   `./TG2Recomp-x86_64.AppImage --appimage-extract-and-run`; o SteamOS
   normalmente tem FUSE e a execução normal funciona.

`settings.ini`, logs e saves são gravados ao lado do executável (Linux,
Windows). No macOS, um app em *Aplicativos* os guarda, junto com a cópia da
ROM, em `~/Library/Application Support/TG2Recomp/`; uma cópia portátil grava
ao lado do `TG2Recomp.app`, ou nessa pasta quando a sua própria pasta é
somente leitura.

## Options (English)

Every port option can be changed with only a controller, either before
starting or from the in-game menu, and is saved immediately in `settings.ini`
next to the executable (`TG2Recomp` / `TG2Recomp.exe`). On macOS it goes
where the end-user instructions above describe.

| Option | Values | Default | Persisted as |
|---|---|---|---|
| Widescreen | Off / Adaptive (fit) / 16:9 / 21:9 (32:9 also available) | Adaptive | `[mods.widescreen] enabled`, `aspect` |
| 60 fps races | Off / On | On | `[mods.race60] enabled` |
| HUD | Centered / Edges | Centered | `[mods.hud] placement` |

- **Launcher:** run `TG2Recomp --launcher` to open it even when the ROM is
  already beside the executable (a plain double-click still boots straight
  into the game). Open **Mods**, then **Features**. D-pad moves, A/click
  selects or toggles, B goes back.
- **In-game menu:** press F1 or Esc on a keyboard. On a controller, hold
  **Back + RB** to open or close it. D-pad moves, A accepts or toggles, B goes
  back, X closes.
- **60 fps races** applies from the next race start. Changing it during a race
  never changes that race's physics.
- **HUD: Edges** only affects widescreen races; **Centered** is the stock
  centered HUD and has no effect when widescreen is Off.
- `settings.ini` is hand-editable. Delete it to return every option to its
  default. `TG2_RACE_60FPS=0|1` and `TG2_HUD_MODE=centered|edges` are
  probe-only overrides and are never saved.

## Opções (Português)

Todas as opções do port podem ser alteradas só com o controle, antes de
começar ou pelo menu dentro do jogo, e são salvas na hora em `settings.ini`,
ao lado do executável (`TG2Recomp` / `TG2Recomp.exe`). No macOS, ele fica
onde as instruções para o usuário acima indicam.

| Opção | Valores | Padrão | Salva como |
|---|---|---|---|
| Widescreen | Desligado / Adaptativo (fit) / 16:9 / 21:9 (32:9 também disponível) | Adaptativo | `[mods.widescreen] enabled`, `aspect` |
| 60 fps nas corridas | Desligado / Ligado | Ligado | `[mods.race60] enabled` |
| HUD | Centralizado / Nas bordas | Centralizado | `[mods.hud] placement` |

- **Launcher:** execute `TG2Recomp --launcher` para abri-lo mesmo com a ROM já
  ao lado do executável (um duplo clique normal continua indo direto ao jogo).
  Abra **Mods** e depois **Features**. O direcional move, A/clique seleciona
  ou alterna, B volta.
- **Menu dentro do jogo:** F1 ou Esc no teclado. No controle, segure
  **Back + RB** para abrir ou fechar. O direcional move, A aceita ou alterna,
  B volta, X fecha.
- **60 fps nas corridas** vale a partir da próxima corrida. Mudar durante uma
  corrida não altera a física daquela corrida.
- **HUD: Nas bordas** só vale em corridas widescreen; **Centralizado** é o HUD
  original, centralizado, e não tem efeito com widescreen desligado.
- `settings.ini` pode ser editado à mão. Apague o arquivo para voltar todas as
  opções ao padrão. `TG2_RACE_60FPS=0|1` e `TG2_HUD_MODE=centered|edges` são
  apenas para testes automatizados e nunca são salvos.

## Steam Deck / SteamOS

**AppImage (recommended, one file)**

1. Copy `TG2Recomp-x86_64.AppImage` and your ROM to the Deck, in the same
   folder (for example `~/Games/TopGear2`). The ROM must sit next to the
   `.AppImage` file.
2. Desktop Mode: right-click the AppImage > Properties > Permissions > "Is
   executable" (or `chmod +x TG2Recomp-x86_64.AppImage` once). SteamOS ships
   FUSE, so a normal double-click works; `--appimage-extract-and-run` is only
   a fallback for systems without FUSE.
3. Steam > Games > "Add a Non-Steam Game" > Browse > select the `.AppImage` >
   "Add Selected Programs". Optionally rename it. Switch to Game Mode: the
   game appears in the library and starts with the controller.
4. Settings, logs and saves appear next to the AppImage in `~/Games/TopGear2`;
   keep that folder writable.

**Tarball (folder layout)**

1. Extract `TG2Recomp-linux-x86_64.tar.gz` and your ROM to the Deck (for
   example `~/Games/TopGear2`). The ROM must sit in the same folder as
   `TG2Recomp`.
2. Desktop Mode: right-click `TG2Recomp` > Properties > Permissions > check
   "Is executable", or run `chmod +x TG2Recomp` once.
3. Desktop Mode: Steam > Games > "Add a Non-Steam Game" > Browse > select
   `TG2Recomp` > "Add Selected Programs". Switch to Game Mode; the game appears
   in the library and starts with the controller. No terminal commands are
   needed after the one-time executable bit (a release tarball preserves it, so
   extracting from the tarball is enough).
4. The Linux binary requires glibc ≤ 2.35 and links SDL2 statically, matching
   SteamOS 3.x. It negotiates X11/Wayland through SDL2, so Gamescope and
   controller-only operation work without extra packages.

## macOS notes

The macOS artifact is `TG2Recomp.app` (universal2) plus `README.txt`, zipped as
`TG2Recomp-macos.zip`:

```
TG2Recomp.app/Contents/Info.plist          bundle id io.github.vittau.tg2recomp,
                                           version, LSMinimumSystemVersion 11.0,
                                           NSHighResolutionCapable
TG2Recomp.app/Contents/MacOS/TG2Recomp      universal2 executable, static SDL2
TG2Recomp.app/Contents/Resources/assets/    launcher fonts and images
TG2Recomp.app/Contents/Resources/licenses/  bundled/open-source licences
TG2Recomp.app/Contents/Resources/TG2Recomp.icns
```

The `.app` is unsigned and not notarized, so macOS quarantines downloaded
copies. Right-click > Open no longer bypasses Gatekeeper on current macOS, and
*Privacy & Security → Open Anyway* can lose its confirmation dialog: the
`syspolicyd` evaluation then waits forever ("waiting on another evaluation")
and the icon bounces until a restart (seen on macOS 27.2, 2026-11-07). The
reliable step is to run once:

```sh
xattr -dr com.apple.quarantine TG2Recomp.app
```

Gatekeeper does not affect a build produced locally by CI's checkout, only
downloaded archives.

**Where files go.** An app in an Applications folder (`/Applications`,
`~/Applications` or a subfolder) is an installed app (engine patch 0019):
settings, logs, saves and the cartridge live in
`~/Library/Application Support/TG2Recomp/`. The cartridge search covers that
folder, and a ROM picked in the launcher is copied there after its CRC check,
so later launches boot straight in. Anywhere else the app is portable (patch
0007): the player drops the ROM beside `TG2Recomp.app`, the search covers the
folder containing the bundle, and data is written beside the `.app` when that
folder is writable, otherwise to Application Support. Read-only assets stay
inside the bundle, where SDL reports `Contents/Resources`.

## Windows notes

`TG2Recomp.exe` uses the static MSVC runtime and a static SDL2, so the folder
has no DLL dependencies to install. Windows SmartScreen may warn about an
unsigned executable; "More info" > "Run anyway" is expected until a signing
certificate is available.

## Pins and cache policy

- SDL2 `2.28.5`, tarball SHA-256
  `332cb37d0be20cb9541739c61f79bae5a477427d79ae85e352089afdaf6666e4`
  (`tools/release/fetch-sdl.py`; the only cached download).
- `appimagetool` `1.9.1`, SHA-256
  `ed4ce84f0d9caff66f50bcca6ff6f35aae54ce8135408b3fa33abfc3cb384eb0`
  (`tools/release/build-appimage.sh`). Its embedded runtime is reused instead
  of downloading the floating `continuous` runtime.
- The release icon is `tools/release/tg2recomp.png`, generated reproducibly by
  `tools/release/make_icon.py` with the Python standard library only.
- Workflow actions are pinned to full commit SHAs with the matching release
  tag in a comment.
- Caches hold only the SDL2 tarball. Generated C, build trees, the ROM, save
  states and debug dumps are never cached or uploaded, and
  `tools/release/verify_artifact.py` fails the job if a payload contains a file
  matching the ROM hash, a ROM-like file over 512 KiB, a `generated/`
  directory, a `GenesisRecomp` binary, a save state or runtime diagnostics.
