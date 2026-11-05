#!/usr/bin/env python3
"""Stage one release payload directory: binary, assets, notices, README.

Only allowlisted inputs enter the fresh destination: the compiled executable,
the launcher assets the build staged beside it, the licences of the shipped
code and a generated end-user README. Build directories are never copied, so a
ROM, generated C, save state or debug dump that happens to live in the build
tree cannot leak into a release. tools/release/verify_artifact.py then checks
the result independently.

Usage:
    stage_payload.py --binary PATH --target-dir DIR --dest DIR
                     --version V --platform linux-x86_64
                     [--binary-name NAME] [--assets DIR] [--sdl-source DIR]
"""
import argparse
import datetime
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

README = """Top Gear 2 Recomp {version} — {platform}

A native PC port of Top Gear 2 (USA, Sega Genesis / Mega Drive), built by
static recompilation. It is not an emulator and it does not include the game.

WHAT YOU NEED
  Top Gear 2 (USA) for the Sega Genesis / Mega Drive.
  CRC32 BD3074D2, SHA-256 b41909d53090e28c1d1e50941dad01676dd3d19caf26c75f66aac6a3ad689ba6,
  1,048,576 bytes. Other regions and revisions are not supported.

HOW TO RUN (ENGLISH)
  1. Put the ROM file in this folder, next to {exe}.
     Any filename and any extension works: the game identifies the cartridge
     by its content, not by its name.
  2. Run {exe}.
  3. Done. No installation, no setup, no emulator configuration.
  If no matching ROM is found the launcher/picker opens instead.

COMO JOGAR (PORTUGUÊS)
  1. Coloque o arquivo da ROM nesta pasta, ao lado de {exe}.
     Qualquer nome e qualquer extensão funcionam: o jogo identifica o
     cartucho pelo conteúdo, não pelo nome do arquivo.
  2. Execute {exe}.
  3. Pronto. Não precisa instalar, configurar nem usar emulador.
  Se nenhuma ROM compatível for encontrada, o seletor de arquivos abre.

{extra}CONTENTS
  {exe}                  game executable
  assets/                launcher fonts and images
  licenses/              licences of the bundled/open-source code
  README.txt             this file
  BUILD-INFO.txt         build version and source revision

Top Gear 2 is a trademark of its respective owners. This port ships no game
data; the ROM is supplied by the user.
"""

LINUX_EXTRA = """STEAM DECK / STEAMOS (controller only)
  1. Copy this folder and your ROM to the Deck (for example under
     ~/Games/TopGear2). Keep the ROM in the same folder as {exe}.
  2. Desktop Mode: right-click {exe} > Properties > Permissions > "Is
     executable" (or run: chmod +x {exe}).
  3. Steam > Games > "Add a Non-Steam Game" > Browse > select {exe} >
     Add. Optionally switch to Game Mode: the game shows up in your library
     and starts with the controller.
  The binary is built against glibc 2.35 and links SDL2 statically. It still
  uses the system graphics stack every SteamOS/desktop image ships (OpenGL,
  X11/Wayland, FreeType, HarfBuzz), so no extra packages or terminal
  commands are needed.

"""

MACOS_EXTRA = """macOS: FIRST LAUNCH (unsigned build)
  This build is not signed or notarized. macOS quarantines downloaded files,
  so the first launch may be blocked. Either:
    - right-click {exe} > Open > Open, or
    - run once: xattr -dr com.apple.quarantine <this folder>
  Put the ROM next to {exe} (this folder), not inside a .app bundle.

"""

WINDOWS_EXTRA = """WINDOWS
  Keep the ROM in this folder, next to {exe}. The build links SDL2 and the
  Visual C++ runtime statically; nothing else has to be installed.

"""

EXTRA = {
    "linux-x86_64": LINUX_EXTRA,
    "macos": MACOS_EXTRA,
    "windows-x64": WINDOWS_EXTRA,
}

LICENSES = [
    ("segagenesisrecomp/LICENSE.md", "segagenesisrecomp-LICENSE.md"),
    ("segagenesisrecomp/LICENSE-recompiler", "segagenesisrecomp-LICENSE-recompiler"),
    ("segagenesisrecomp/THIRD-PARTY-LICENSES.md", "segagenesisrecomp-THIRD-PARTY-LICENSES.md"),
    ("recomp-ui/LICENSE", "recomp-ui-LICENSE"),
]


def git_revision(directory):
    try:
        return subprocess.check_output(
            ["git", "-C", directory, "rev-parse", "--short=12", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:  # noqa: BLE001 - metadata is best-effort
        return "unknown"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True)
    parser.add_argument("--target-dir", help="build directory holding assets/")
    parser.add_argument("--assets")
    parser.add_argument("--dest", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", required=True, choices=sorted(EXTRA))
    parser.add_argument("--binary-name")
    parser.add_argument("--sdl-source")
    args = parser.parse_args()

    binary_name = args.binary_name or ("TG2Recomp.exe" if args.platform == "windows-x64" else "TG2Recomp")
    assets = args.assets or (os.path.join(args.target_dir, "assets") if args.target_dir else None)
    if not os.path.isfile(args.binary):
        raise SystemExit(f"stage: missing executable {args.binary}")
    if not assets or not os.path.isdir(assets):
        raise SystemExit(f"stage: missing launcher assets directory {assets}")
    if os.path.exists(args.dest):
        if os.listdir(args.dest):
            raise SystemExit(f"stage: refusing to stage into non-empty {args.dest}")
    else:
        os.makedirs(args.dest)

    target = os.path.join(args.dest, binary_name)
    shutil.copy2(args.binary, target)
    if os.name != "nt":
        os.chmod(target, 0o755)

    shutil.copytree(assets, os.path.join(args.dest, "assets"))

    licenses = os.path.join(args.dest, "licenses")
    os.makedirs(licenses)
    for source, name in LICENSES:
        path = os.path.join(REPO, source)
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(licenses, name))
        else:
            print(f"stage: warning: licence file missing: {source}", file=sys.stderr)
    if args.sdl_source:
        sdl_license = os.path.join(args.sdl_source, "LICENSE.txt")
        if not os.path.isfile(sdl_license):
            raise SystemExit(f"stage: missing SDL2 licence {sdl_license}")
        shutil.copy2(sdl_license, os.path.join(licenses, "SDL2-LICENSE.txt"))
    else:
        raise SystemExit("stage: --sdl-source is required to ship the SDL2 licence")

    extra = EXTRA[args.platform].format(exe=binary_name)
    with open(os.path.join(args.dest, "README.txt"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            README.format(
                version=args.version,
                platform=args.platform,
                exe=binary_name,
                extra=extra,
            )
        )

    engine = git_revision(os.path.join(REPO, "segagenesisrecomp"))
    game = os.environ.get("GITHUB_SHA") or git_revision(REPO)
    quarantine = ""
    if args.platform == "macos":
        quarantine = (
            "Gatekeeper: the build is unsigned and not notarized; after download run\n"
            "  xattr -dr com.apple.quarantine <this folder>\n"
            "or right-click the executable > Open the first time.\n"
        )
    with open(os.path.join(args.dest, "BUILD-INFO.txt"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(
            f"game=Top Gear 2 (USA)\n"
            f"platform={args.platform}\n"
            f"version={args.version}\n"
            f"game_revision={game}\n"
            f"engine_revision={engine}\n"
            f"packaged_utc={datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
            f"debug_tcp_server=disabled\n"
            f"reverse_debug_rings=disabled\n"
            f"build_type=Release\n"
            f"{quarantine}"
        )

    total = sum(
        os.path.getsize(os.path.join(root, name))
        for root, _, names in os.walk(args.dest)
        for name in names
    )
    print(f"stage: {args.dest} ({total} bytes)")


if __name__ == "__main__":
    main()
