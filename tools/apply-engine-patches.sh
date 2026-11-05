#!/usr/bin/env bash
# Apply game-owned framework fixes without changing the upstream submodule pin.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
for patch in "$repo"/patches/segagenesisrecomp/*.patch; do
    [ -f "$patch" ] || continue
    target="$repo/segagenesisrecomp"
    case "$(basename "$patch")" in
        core-*) target="$target/external/m68k-recomp-core" ;;
    esac
    if git -C "$target" apply --reverse --check "$patch" 2>/dev/null; then
        continue
    fi
    git -C "$target" apply --check "$patch"
    git -C "$target" apply "$patch"
done
