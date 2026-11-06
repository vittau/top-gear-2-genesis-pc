#!/usr/bin/env bash
# Apply game-owned framework fixes without changing the upstream submodule pin.
#
# Idempotent: patches that are already applied are skipped. When a patch file
# has been regenerated (a new version of an already-applied patch), the old
# version blocks the new one; rerun with --reset to restore both engine
# submodules to their pinned commits and apply every patch from scratch.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
engine="$repo/segagenesisrecomp"
core="$engine/external/m68k-recomp-core"

if [ "${1:-}" = "--reset" ]; then
    git -C "$engine" checkout -q -- .
    git -C "$core" checkout -q -- .
    # Files created by our patches (untracked in the pinned engine).
    git -C "$engine" clean -q -f -- runner
    git -C "$core" clean -q -f
fi

for patch in "$repo"/patches/segagenesisrecomp/*.patch; do
    [ -f "$patch" ] || continue
    target="$engine"
    case "$(basename "$patch")" in
        core-*) target="$core" ;;
    esac
    if git -C "$target" apply --reverse --check "$patch" 2>/dev/null; then
        continue
    fi
    if ! git -C "$target" apply --check "$patch" 2>/dev/null; then
        echo "apply-engine-patches: $(basename "$patch") does not apply." >&2
        echo "If a patch was regenerated, rerun: tools/apply-engine-patches.sh --reset" >&2
        exit 1
    fi
    git -C "$target" apply "$patch"
done
