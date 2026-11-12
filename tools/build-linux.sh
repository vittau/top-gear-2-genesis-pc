#!/usr/bin/env bash
# Usage: tools/build-linux.sh [ROM] [BUILD_DIR]
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
"$repo/tools/apply-engine-patches.sh"
rom=${1:-"$HOME/roms/genesis/tg2.bin"}
build=${2:-"$repo/build"}
cmake -S "$repo" -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DGENESIS_NATIVE_IPO=OFF -DTG2_ROM="$(realpath "$rom")" -DGEN_ENABLE_TRACE=ON -DSONIC_REVERSE_DEBUG=ON
mkdir -p "$HOME/.cache"
flock "$HOME/.cache/tg2-heavy.lock" cmake --build "$build" --target TG2Recomp -j"${JOBS:-3}"
