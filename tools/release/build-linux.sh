#!/usr/bin/env bash
# Build and stage the Linux x86_64 release payload (Steam Deck / SteamOS 3.x),
# then wrap the same staged files in a single-file AppImage.
#
# Usage: tools/release/build-linux.sh --rom PATH --sdl PATH
#            [--build DIR] [--out DIR] [--version V] [--jobs N]
#
# Set TG2_SKIP_GLIBC_CHECK=1 for a development-host build (the AppImage step
# then skips the 2.35 symbol-floor assertion; CI leaves it enabled).
#
# Release profile: Release, native IPO on, TCP debug server and reverse-debug
# rings disabled, SDL2 linked statically from the pinned source tree, and the
# C++ runtime linked statically so the only runtime requirements are glibc and
# the system graphics/audio libraries every SteamOS image already has.
# Run this on the oldest glibc you intend to support (CI uses ubuntu-22.04,
# glibc 2.35).
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
build="$repo/build-release/linux"
out="$repo/build-release/dist/linux"
version=$(python3 "$repo/tools/release/project_version.py")
jobs="${JOBS:-3}"
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
        -h|--help) sed -n '2,12p' "$0"; exit 0;;
        *) echo "Unknown argument: $1" >&2; exit 2;;
    esac
done
[ -n "$rom" ] || { echo "--rom is required" >&2; exit 2; }
[ -n "$sdl" ] || { echo "--sdl is required (see tools/release/fetch-sdl.py)" >&2; exit 2; }
[ -f "$rom" ] || { echo "ROM not found: $rom" >&2; exit 2; }
[ -f "$sdl/CMakeLists.txt" ] || { echo "SDL2 source not found: $sdl" >&2; exit 2; }

"$repo/tools/apply-engine-patches.sh"

cmake -S "$repo" -B "$build" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DGENESIS_RECOMP_ROOT="$repo/segagenesisrecomp" \
    -DTG2_ROM="$(realpath "$rom")" \
    -DTG2_SDL_SOURCE="$(realpath "$sdl")" \
    -DTG2_BUILD_VERSION="$version" \
    -DGEN_ENABLE_TRACE=OFF \
    -DSONIC_REVERSE_DEBUG=OFF \
    -DGENESIS_NATIVE_IPO=ON \
    -DSDL_PIPEWIRE=OFF \
    -DCMAKE_POLICY_VERSION_MINIMUM=3.5 \
    -DCMAKE_EXE_LINKER_FLAGS="-static-libstdc++ -static-libgcc" \
    '-DCMAKE_INSTALL_RPATH=$ORIGIN' \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON
cmake --build "$build" --target TG2Recomp -j"$jobs"

name="TG2Recomp-linux-x86_64"
stage="$out/$name"
rm -rf "$stage"
mkdir -p "$out"
python3 "$repo/tools/release/stage_payload.py" \
    --binary "$build/TG2Recomp" \
    --target-dir "$build" \
    --dest "$stage" \
    --version "$version" \
    --platform linux-x86_64 \
    --binary-name TG2Recomp \
    --sdl-source "$sdl"
python3 "$repo/tools/release/verify_artifact.py" --dir "$stage" \
    --require TG2Recomp --require assets --require licenses --require README.txt

rm -f "$out/$name.tar.gz"
tar -C "$out" -czf "$out/$name.tar.gz" "$name"
(cd "$out" && sha256sum "$name.tar.gz" > "$name.tar.gz.sha256")
echo "Built $out/$name.tar.gz"
cat "$out/$name.tar.gz.sha256"

# Single-file AppImage next to the tarball; built from the same staged payload
# so both artifacts carry identical binaries and glibc requirements.
"$repo/tools/release/build-appimage.sh" \
    --payload "$stage" \
    --out "$out" \
    --tools "$repo/build-release/appimage-tools" \
    --version "$version" \
    --binary TG2Recomp \
    $([ "${TG2_SKIP_GLIBC_CHECK:-0}" = 1 ] && echo --skip-glibc-check)
