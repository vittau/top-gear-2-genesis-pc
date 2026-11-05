#!/usr/bin/env bash
# Apply game-owned framework fixes without changing the upstream submodule pin.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
for patch in "$repo"/patches/segagenesisrecomp/*.patch; do
    [ -f "$patch" ] || continue
    if git -C "$repo/segagenesisrecomp" apply --reverse --check "$patch" 2>/dev/null; then
        continue
    fi
    git -C "$repo/segagenesisrecomp" apply --check "$patch"
    git -C "$repo/segagenesisrecomp" apply "$patch"
done
