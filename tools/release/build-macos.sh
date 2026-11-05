#!/usr/bin/env bash
# Build and stage the macOS release payload (universal2: arm64 + x86_64).
#
# Usage: tools/release/build-macos.sh --rom PATH --sdl PATH
#            [--build DIR] [--out DIR] [--version V] [--jobs N]
#            [--architectures "arm64;x86_64"]
#
# Release profile: Release, native IPO on, TCP debug server and reverse-debug
# rings disabled, SDL2 linked statically from the pinned source tree. The
# payload is a plain folder (not a .app bundle) so engine patch 0002's
# "cartridge next to the executable" search finds a ROM dropped beside it;
# SDL_GetBasePath() inside a bundle would report Contents/MacOS instead.
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
    -DGENESIS_NATIVE_IPO=ON
cmake --build "$build" --target TG2Recomp -j"$jobs"

name="TG2Recomp-macos"
stage="$out/$name"
rm -rf "$stage"
mkdir -p "$out"
python3 "$repo/tools/release/stage_payload.py" \
    --binary "$build/TG2Recomp" \
    --target-dir "$build" \
    --dest "$stage" \
    --version "$version" \
    --platform macos \
    --binary-name TG2Recomp \
    --sdl-source "$sdl"
python3 "$repo/tools/release/verify_artifact.py" --dir "$stage" \
    --require TG2Recomp --require assets --require licenses --require README.txt

lipo -info "$stage/TG2Recomp"
rm -f "$out/$name.tar.gz"
tar -C "$out" -czf "$out/$name.tar.gz" "$name"
(cd "$out" && shasum -a 256 "$name.tar.gz" > "$name.tar.gz.sha256")
echo "Built $out/$name.tar.gz"
cat "$out/$name.tar.gz.sha256"
