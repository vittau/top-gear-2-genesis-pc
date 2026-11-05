# Releasing Top Gear 2 Recomp

`.github/workflows/build.yml` builds the three distribution targets on every
push, pull request and manual dispatch, and publishes downloadable artifacts:

| Artifact | Runner | Payload |
|---|---|---|
| `TG2Recomp-linux-x86_64` | `ubuntu-22.04` (glibc 2.35) | folder + `TG2Recomp-linux-x86_64.tar.gz` + `.sha256` |
| `TG2Recomp-windows-x64` | `windows-latest` (MSVC, default VS generator, static CRT) | `TG2Recomp.exe`, `assets/`, `licenses/`, `README.txt` |
| `TG2Recomp-macos` | `macos-latest` (universal2: arm64 + x86_64) | folder + `TG2Recomp-macos.tar.gz` + `.sha256` |

Linux and macOS artifacts contain both the staged folder (convenient for
inspection) and a tarball, because GitHub artifact ZIPs do not preserve the
executable bit. Publish or distribute the `.tar.gz`: extracting it keeps
`TG2Recomp` executable. Windows has no such bit, so the artifact is the folder
itself.

## Runtime requirements

- **Linux:** glibc ≤ 2.35 and the standard desktop graphics stack every
  SteamOS 3.x or desktop image ships — OpenGL (GLVND), X11 or Wayland,
  FreeType and HarfBuzz. SDL2 and libstdc++ are linked statically; `ldd`
  shows only those system libraries and the binary carries a `$ORIGIN`
  RUNPATH for any future bundled library.
- **Windows:** one executable, static MSVC runtime and static SDL2. No DLLs
  and no Visual C++ redistributable.
- **macOS:** only system frameworks. The universal2 payload deliberately
  skips Homebrew FreeType/HarfBuzz (arm64-only dylibs would break the x86_64
  slice and add host-specific dependencies), so the launcher uses outline
  emoji instead of colour emoji.


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
7. Uploads the artifact. A separate `linux-verify` job downloads the uploaded
   Linux artifact, checks the tarball hash, extracts it, proves the highest
   required glibc symbol version is ≤ 2.35 (`objdump -T`,
   `tools/release/verify_glibc.py`, plus a clean `ldd` after installing the
   desktop runtime libraries), and repeats the smoke run on the downloaded
   payload.

Pull requests from forks are skipped: GitHub does not expose repository
secrets to fork PRs, so the private ROM (and therefore C generation) is not
available. Branch PRs in this repository build normally.

## Cutting a release

1. Confirm `git status` is clean, submodules are at their committed pins, and
   the branch is green in `build`.
2. Download all three artifacts from the latest green run, or cut a tag first
   and download from that run. Release payloads contain `BUILD-INFO.txt` with
   the game and engine revisions and `README.txt` with end-user instructions.
3. Verify the Linux and macOS tarballs against their `.sha256` files, and
   publish those files (or the extracted folders) to the GitHub release
   together with the Windows folder zipped by GitHub.
4. Record the source revision: the `build` run URL and `BUILD-INFO.txt`
   identify the exact commit each payload came from.

The artifacts are release candidates until the owner validates on real
hardware (Steam Deck/SteamOS with a controller, Windows, and both macOS
architectures). CI proves the Linux glibc floor and a headless boot on all
three platforms; it does not prove audio, input or rendering on a device.

## End-user instructions (English)

1. Put your Top Gear 2 (USA) ROM next to the executable. Any filename and any
   extension work: the game identifies the cartridge by its content (CRC32
   `BD3074D2`, 1,048,576 bytes), not by its name.
2. Run the executable (`TG2Recomp` / `TG2Recomp.exe`). No installation, no
   setup, no emulator.
3. If no matching ROM is present, the launcher/picker opens instead.

## Instruções para o usuário (Português)

1. Coloque a ROM de Top Gear 2 (USA) ao lado do executável. Qualquer nome e
   qualquer extensão funcionam: o jogo identifica o cartucho pelo conteúdo
   (CRC32 `BD3074D2`, 1.048.576 bytes), não pelo nome do arquivo.
2. Execute o programa (`TG2Recomp` / `TG2Recomp.exe`). Não precisa instalar,
   configurar nem usar emulador.
3. Se nenhuma ROM compatível for encontrada, o seletor de arquivos abre.

## Options (English)

Every port option can be changed with only a controller, either before
starting or from the in-game menu, and is saved immediately in `settings.ini`
next to the executable (`TG2Recomp` / `TG2Recomp.exe`).

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
ao lado do executável (`TG2Recomp` / `TG2Recomp.exe`).

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

1. Copy the extracted `TG2Recomp-linux-x86_64` folder and your ROM to the Deck
   (for example `~/Games/TopGear2`). The ROM must sit in the same folder as
   `TG2Recomp`.
2. In Desktop Mode, make the binary executable: right-click `TG2Recomp` >
   Properties > Permissions > check "Is executable", or run
   `chmod +x TG2Recomp` once.
3. Desktop Mode: Steam > Games > "Add a Non-Steam Game" > Browse > select
   `TG2Recomp` > "Add Selected Programs". Switch to Game Mode; the game appears
   in the library and starts with the controller. No terminal commands are
   needed after the one-time executable bit (a release tarball preserves it, so
   extracting from the tarball is enough).
4. The Linux binary requires glibc ≤ 2.35 and links SDL2 statically, matching
   SteamOS 3.x. It negotiates X11/Wayland through SDL2, so Gamescope and
   controller-only operation work without extra packages.

## macOS notes

The macOS payload is a folder, not a `.app` bundle: engine patch 0002 searches
for a cartridge (content CRC32 + size) next to the executable, and inside a
bundle that directory would be `Foo.app/Contents/MacOS`, not the folder the
user sees. A plain folder keeps "drop the ROM next to the binary" literally
true.

The build is unsigned and not notarized, so macOS quarantines downloaded
copies. Either right-click the executable > Open > Open the first time, or run

```sh
xattr -dr com.apple.quarantine TG2Recomp-macos
```

Gatekeeper does not affect a build produced locally by CI's checkout, only
downloaded archives.

## Windows notes

`TG2Recomp.exe` uses the static MSVC runtime and a static SDL2, so the folder
has no DLL dependencies to install. Windows SmartScreen may warn about an
unsigned executable; "More info" > "Run anyway" is expected until a signing
certificate is available.

## Pins and cache policy

- SDL2 `2.28.5`, tarball SHA-256
  `332cb37d0be20cb9541739c61f79bae5a477427d79ae85e352089afdaf6666e4`
  (`tools/release/fetch-sdl.py`; the only cached download).
- Workflow actions are pinned to full commit SHAs with the matching release
  tag in a comment.
- Caches hold only the SDL2 tarball. Generated C, build trees, the ROM, save
  states and debug dumps are never cached or uploaded, and
  `tools/release/verify_artifact.py` fails the job if a payload contains a file
  matching the ROM hash, a ROM-like file over 512 KiB, a `generated/`
  directory, a `GenesisRecomp` binary, a save state or runtime diagnostics.
