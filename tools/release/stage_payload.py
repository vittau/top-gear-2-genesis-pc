#!/usr/bin/env python3
"""Stage one release payload directory: binary, assets, notices, README.

Only allowlisted inputs enter the fresh destination: the compiled executable,
the launcher assets the build staged beside it, the licences of the shipped
code and a generated end-user README. Build directories are never copied, so a
ROM, generated C, save state or debug dump that happens to live in the build
tree cannot leak into a release. tools/release/verify_artifact.py then checks
the result independently.

macOS releases pass --app-bundle NAME to produce a NAME.app with an Info.plist
and Contents/Resources, plus the end-user README beside the bundle.

Usage:
    stage_payload.py --binary PATH --target-dir DIR --dest DIR
                     --version V --platform linux-x86_64
                     [--binary-name NAME] [--assets DIR] [--sdl-source DIR]
                     [--app-bundle TG2Recomp.app --bundle-id ID
                      --minimum-system-version 11.0]
"""
import argparse
import datetime
import os
import re
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
{steps_en}
COMO JOGAR (PORTUGUÊS)
{steps_pt}
{extra}CONTENTS
{contents}

Top Gear 2 is a trademark of its respective owners. This port ships no game
data; the ROM is supplied by the user.
"""

FLAT_STEPS_EN = """  1. Put the ROM file in this folder, next to {exe}.
     Any filename and any extension works: the game identifies the cartridge
     by its content, not by its name.
  2. Run {exe}.
  3. Done. No installation, no setup, no emulator configuration.
  If no matching ROM is found the launcher/picker opens instead.
"""

FLAT_STEPS_PT = """  1. Coloque o arquivo da ROM nesta pasta, ao lado de {exe}.
     Qualquer nome e qualquer extensão funcionam: o jogo identifica o
     cartucho pelo conteúdo, não pelo nome do arquivo.
  2. Execute {exe}.
  3. Pronto. Não precisa instalar, configurar nem usar emulador.
  Se nenhuma ROM compatível for encontrada, o seletor de arquivos abre.
"""

BUNDLE_STEPS_EN = """  1. Move {exe} to Applications.
  2. The build is not signed by Apple. Clear the download quarantine once,
     in Terminal: xattr -dr com.apple.quarantine /Applications/{exe}
  3. Open {exe} and pick the ROM in the launcher. Any filename and any
     extension works: the game identifies the cartridge by its content.
     The app keeps a copy and starts the game directly from then on.
"""

BUNDLE_STEPS_PT = """  1. Mova {exe} para Aplicativos.
  2. O build não é assinado pela Apple. Remova a quarentena do download uma
     vez, no Terminal: xattr -dr com.apple.quarantine /Applications/{exe}
  3. Abra {exe} e escolha a ROM no launcher. Qualquer nome e qualquer
     extensão funcionam: o jogo identifica o cartucho pelo conteúdo.
     O app guarda uma cópia e, daí em diante, abre o jogo direto.
"""

FLAT_CONTENTS = """  {exe:<22} game executable
  assets/                launcher fonts and images
  licenses/              licences of the bundled/open-source code
  README.txt             this file
  BUILD-INFO.txt         build version and source revision
"""

BUNDLE_CONTENTS = """  {app:<22} game application bundle (macOS)
  README.txt             this file
  Inside {app}: Contents/MacOS/{binary}, Contents/Resources/assets,
  Contents/Resources/licenses and BUILD-INFO.txt.
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

MACOS_EXTRA = """macOS DETAILS
  Gatekeeper: this build is not signed or notarized, so macOS blocks the
  first launch until the quarantine is cleared (step 2 above). System
  Settings > Privacy & Security > Open Anyway also works; if the icon then
  keeps bouncing and the game never opens, restart the Mac and run step 2.
  Files: an app in Applications keeps the ROM copy, settings, logs and saves
  in ~/Library/Application Support/TG2Recomp/. Replacing {app}
  with a newer version keeps them.
  Portable: outside Applications, put the ROM next to {app}
  (in the same folder as the bundle, not inside it). Data is then written
  next to {app} when that folder is writable.

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
    parser.add_argument("--app-bundle", help="macOS: create NAME.app instead of a bare folder")
    parser.add_argument("--icon", help="macOS: .icns icon copied into the bundle")
    parser.add_argument("--bundle-id", default="io.github.vittau.tg2recomp")
    parser.add_argument("--bundle-display-name", default="Top Gear 2 Recomp")
    parser.add_argument("--minimum-system-version", default="11.0")
    args = parser.parse_args()

    if args.app_bundle and args.platform != "macos":
        raise SystemExit("stage: --app-bundle is only valid with --platform macos")
    binary_name = args.binary_name or ("TG2Recomp.exe" if args.platform == "windows-x64" else "TG2Recomp")
    assets = args.assets or (os.path.join(args.target_dir, "assets") if args.target_dir else None)
    if not os.path.isfile(args.binary):
        raise SystemExit(f"stage: missing executable {args.binary}")
    if not assets or not os.path.isdir(assets):
        raise SystemExit(f"stage: missing launcher assets directory {assets}")
    if not args.sdl_source:
        raise SystemExit("stage: --sdl-source is required to ship the SDL2 licence")
    sdl_license = os.path.join(args.sdl_source, "LICENSE.txt")
    if not os.path.isfile(sdl_license):
        raise SystemExit(f"stage: missing SDL2 licence {sdl_license}")
    if os.path.exists(args.dest):
        if os.listdir(args.dest):
            raise SystemExit(f"stage: refusing to stage into non-empty {args.dest}")
    else:
        os.makedirs(args.dest)

    if args.app_bundle:
        stage_macos_bundle(args, binary_name, assets, sdl_license)
    else:
        stage_flat(args, binary_name, assets, sdl_license)

    total = sum(
        os.path.getsize(os.path.join(root, name))
        for root, _, names in os.walk(args.dest)
        for name in names
    )
    print(f"stage: {args.dest} ({total} bytes)")


def copy_licenses(licenses_dir, sdl_license):
    os.makedirs(licenses_dir)
    for source, name in LICENSES:
        path = os.path.join(REPO, source)
        if os.path.isfile(path):
            shutil.copy2(path, os.path.join(licenses_dir, name))
        else:
            print(f"stage: warning: licence file missing: {source}", file=sys.stderr)
    shutil.copy2(sdl_license, os.path.join(licenses_dir, "SDL2-LICENSE.txt"))


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def readme_text(args, binary_name, contents, app=None, app_short=None):
    extra = EXTRA[args.platform].format(
        exe=binary_name, app=app or "", app_short=app_short or app or "")
    # In a bundle the thing the player runs (and drops the ROM beside) is the
    # .app, not the Mach-O executable inside Contents/MacOS.
    run_name = app or binary_name
    steps_en, steps_pt = ((BUNDLE_STEPS_EN, BUNDLE_STEPS_PT) if app
                          else (FLAT_STEPS_EN, FLAT_STEPS_PT))
    return README.format(
        version=args.version,
        platform=args.platform,
        steps_en=steps_en.format(exe=run_name),
        steps_pt=steps_pt.format(exe=run_name),
        exe=run_name,
        app=app or "",
        extra=extra,
        contents=contents.format(exe=run_name, app=app or "", binary=binary_name),
    )


def build_info_text(args):
    engine = git_revision(os.path.join(REPO, "segagenesisrecomp"))
    game = os.environ.get("GITHUB_SHA") or git_revision(REPO)
    quarantine = ""
    if args.platform == "macos":
        quarantine = (
            "Gatekeeper: the build is unsigned and not notarized; after download run\n"
            "  xattr -dr com.apple.quarantine TG2Recomp.app\n"
        )
    return (
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


def stage_flat(args, binary_name, assets, sdl_license):
    target = os.path.join(args.dest, binary_name)
    shutil.copy2(args.binary, target)
    if os.name != "nt":
        os.chmod(target, 0o755)
    shutil.copytree(assets, os.path.join(args.dest, "assets"))
    copy_licenses(os.path.join(args.dest, "licenses"), sdl_license)
    write_text(os.path.join(args.dest, "README.txt"),
               readme_text(args, binary_name, FLAT_CONTENTS))
    write_text(os.path.join(args.dest, "BUILD-INFO.txt"), build_info_text(args))


def numeric_version(version):
    match = re.match(r"(\d+(?:\.\d+){0,2})", version)
    return match.group(1) if match else "0.2.0"


INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleIdentifier</key>
    <string>{bundle_id}</string>
    <key>CFBundleName</key>
    <string>{display_name}</string>
    <key>CFBundleDisplayName</key>
    <string>{display_name}</string>
    <key>CFBundleExecutable</key>
    <string>{executable}</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleSignature</key>
    <string>????</string>
    <key>CFBundleShortVersionString</key>
    <string>{short_version}</string>
    <key>CFBundleVersion</key>
    <string>{short_version}</string>
    <key>TG2BuildVersion</key>
    <string>{build_version}</string>
    <key>LSMinimumSystemVersion</key>
    <string>{minimum_system_version}</string>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.racing-games</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>SDL_FILESYSTEM_BASE_DIR_TYPE</key>
    <string>resource</string>
{icon_entry}    <key>CFBundleSupportedPlatforms</key>
    <array>
        <string>MacOSX</string>
    </array>
</dict>
</plist>
"""


def stage_macos_bundle(args, binary_name, assets, sdl_license):
    app = args.app_bundle
    app_dir = os.path.join(args.dest, app)
    macos_dir = os.path.join(app_dir, "Contents", "MacOS")
    resources = os.path.join(app_dir, "Contents", "Resources")
    os.makedirs(macos_dir)
    os.makedirs(resources)

    target = os.path.join(macos_dir, binary_name)
    shutil.copy2(args.binary, target)
    os.chmod(target, 0o755)
    shutil.copytree(assets, os.path.join(resources, "assets"))
    copy_licenses(os.path.join(resources, "licenses"), sdl_license)

    write_text(os.path.join(app_dir, "Contents", "Info.plist"), INFO_PLIST.format(
        bundle_id=args.bundle_id,
        display_name=args.bundle_display_name,
        executable=binary_name,
        short_version=numeric_version(args.version),
        build_version=args.version,
        minimum_system_version=args.minimum_system_version,
        icon_entry=(f"    <key>CFBundleIconFile</key>\n    <string>{os.path.splitext(os.path.basename(args.icon))[0]}</string>\n"
                    if args.icon else ""),
    ))
    if args.icon:
        if not os.path.isfile(args.icon):
            raise SystemExit(f"stage: missing icon {args.icon}")
        shutil.copy2(args.icon, os.path.join(resources, os.path.basename(args.icon)))
    readme = readme_text(args, binary_name, BUNDLE_CONTENTS, app=app, app_short=os.path.splitext(app)[0])
    write_text(os.path.join(args.dest, "README.txt"), readme)
    write_text(os.path.join(resources, "README.txt"), readme)
    write_text(os.path.join(resources, "BUILD-INFO.txt"), build_info_text(args))



if __name__ == "__main__":
    main()
