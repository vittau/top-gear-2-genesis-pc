#!/usr/bin/env bash
# Build and stage the macOS release payload (universal2: arm64 + x86_64).
#
# Usage: tools/release/build-macos.sh --rom PATH --sdl PATH
#            [--build DIR] [--out DIR] [--version V] [--jobs N]
#            [--architectures "arm64;x86_64"]
#
# Release profile: Release, native IPO on, TCP debug server and reverse-debug
# rings disabled, SDL2 linked statically from the pinned source tree. The
# payload is TG2Recomp.app (Contents/MacOS binary, Contents/Resources assets)
# plus README.txt; engine patch 0007 searches the folder containing the .app
# for a dropped cartridge and keeps user data there when writable.
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
build="$repo/build-release/macos"
out="$repo/build-release/dist/macos"
version="0.1.0"
jobs="${JOBS:-$(sysctl -n hw.ncpu 2>/dev/null || echo 8)}"
architectures="arm64;x86_64"
rom=""
sdl=""

while [ $# -gt 0 ]; do
    case "$1" in
        --rom) rom="$2"; shift 2;;
        --sdl) sdl="$2"; shift 2;;
        --build) build="$2"; shift 2;;
        --out) out="$2"; shift 2;;
        --version) version="$2"; shift 2;;
        --jobs) jobs="$2"; shift 2;;
        --architectures) architectures="$2"; shift 2;;
        -h|--help) sed -n '2,14p' "$0"; exit 0;;
        *) echo "Unknown argument: $1" >&2; exit 2;;
    esac
done
[ -n "$rom" ] || { echo "--rom is required" >&2; exit 2; }
[ -n "$sdl" ] || { echo "--sdl is required (see tools/release/fetch-sdl.py)" >&2; exit 2; }
[ -f "$rom" ] || { echo "ROM not found: $rom" >&2; exit 2; }
[ -f "$sdl/CMakeLists.txt" ] || { echo "SDL2 source not found: $sdl" >&2; exit 2; }
[ "$(uname -s)" = Darwin ] || { echo "build-macos.sh must run on macOS" >&2; exit 2; }

"$repo/tools/apply-engine-patches.sh"

# Homebrew's FreeType/HarfBuzz are single-architecture dylibs, which break a
# universal2 link; skip them so the payload only uses system frameworks.
cmake -S "$repo" -B "$build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_OSX_ARCHITECTURES="$architectures" \
    -DCMAKE_OSX_DEPLOYMENT_TARGET=11.0 \
    -DGENESIS_RECOMP_ROOT="$repo/segagenesisrecomp" \
    -DTG2_ROM="$(cd "$(dirname "$rom")" && pwd)/$(basename "$rom")" \
    -DTG2_SDL_SOURCE="$(cd "$sdl" && pwd)" \
    -DTG2_BUILD_VERSION="$version" \
    -DGEN_ENABLE_TRACE=OFF \
    -DSONIC_REVERSE_DEBUG=OFF \
    -DGENESIS_NATIVE_IPO=ON \
    -DCMAKE_DISABLE_FIND_PACKAGE_Freetype=ON \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build "$build" --target TG2Recomp -j"$jobs"

name="TG2Recomp-macos"
stage="$out/$name"
app="TG2Recomp.app"
rm -rf "$stage"
mkdir -p "$out"

# Build the .icns from the checked-in 1024px release icon with the tools macOS
# ships (sips + iconutil), so no image package is needed on the runner.
iconset="$build/icon.iconset"
rm -rf "$iconset"
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" "$repo/tools/release/tg2recomp.png" \
        --out "$iconset/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    sips -z "$double" "$double" "$repo/tools/release/tg2recomp.png" \
        --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
done
iconutil -c icns "$iconset" -o "$build/TG2Recomp.icns"

python3 "$repo/tools/release/stage_payload.py" \
    --binary "$build/TG2Recomp" \
    --target-dir "$build" \
    --dest "$stage" \
    --version "$version" \
    --platform macos \
    --binary-name TG2Recomp \
    --sdl-source "$sdl" \
    --app-bundle "$app" \
    --icon "$build/TG2Recomp.icns" \
    --bundle-id io.github.vittau.tg2recomp \
    --bundle-display-name "Top Gear 2 Recomp" \
    --minimum-system-version 11.0
python3 "$repo/tools/release/verify_artifact.py" --dir "$stage" \
    --require README.txt \
    --require "$app/Contents/Info.plist" \
    --require "$app/Contents/MacOS/TG2Recomp" \
    --require "$app/Contents/Resources/assets" \
    --require "$app/Contents/Resources/licenses"

lipo -info "$stage/$app/Contents/MacOS/TG2Recomp"
# Only system frameworks: the universal2 payload links SDL2 statically, so no
# host Homebrew dylib may leak into either slice.
if otool -L "$stage/$app/Contents/MacOS/TG2Recomp" \
    | tail -n +2 | grep -Ev '/System/Library/|/usr/lib/|:$'; then
    echo "macOS payload depends on a non-system library" >&2
    exit 1
fi

# macOS artifact: the .app plus the end-user README in one zip. Zip keeps the
# executable bit and the bundle directory structure; the staged folder stays
# available for inspection in the CI artifact.
rm -f "$out/TG2Recomp-macos.zip"
(cd "$out" && zip -qry "$name.zip" "$app" README.txt)
(cd "$out" && shasum -a 256 "$name.zip" > "$name.zip.sha256")
echo "Built $out/$name.zip"
cat "$out/$name.zip.sha256"
