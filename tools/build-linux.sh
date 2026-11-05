#!/usr/bin/env bash
# Usage: tools/build-linux.sh [ROM] [BUILD_DIR]
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
rom=${1:-"$HOME/roms/genesis/tg2.bin"}
build=${2:-"$repo/build"}
cmake -S "$repo" -B "$build" -G Ninja -DCMAKE_BUILD_TYPE=Release \
    -DTG2_ROM="$(realpath "$rom")" -DGEN_ENABLE_TRACE=ON -DSONIC_REVERSE_DEBUG=ON
cmake --build "$build" --target TG2Recomp -j"${JOBS:-8}"
