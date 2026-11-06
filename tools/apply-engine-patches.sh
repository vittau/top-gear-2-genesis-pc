#!/usr/bin/env bash
# Apply game-owned framework fixes without changing the upstream submodule pin.
#
# Idempotent. Two mechanisms:
#   * a stamp (hash of every patch file + the engine commit) makes a second run
#     a no-op, which matters because a later patch may touch lines an earlier
#     one already changed -- such a patch cannot be recognised by itself with
#     `git apply --reverse --check`;
#   * per-patch reverse-check for a partially applied tree.
# When a patch file is regenerated, or a new patch is added on top of one that
# already modified the same lines, rerun with --reset (it restores both engine
# submodules to their pinned commits, applies everything again and rewrites the
# stamp).
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
engine="$repo/segagenesisrecomp"
core="$engine/external/m68k-recomp-core"
# The stamp lives in this repository's git dir: a submodule's .git is a
# file, and a worktree's .git is a pointer file too.
stamp="$(git -C "$repo" rev-parse --git-dir)/tg2-engine-patches.stamp"

patch_hash() {
    cat "$repo"/patches/segagenesisrecomp/*.patch | sha256sum | cut -d' ' -f1
}

if [ "${1:-}" = "--reset" ]; then
    git -C "$engine" checkout -q -- .
    git -C "$core" checkout -q -- .
    # Files created by our patches (untracked in the pinned engine).
    git -C "$engine" clean -q -f -- runner
    git -C "$core" clean -q -f
    rm -f "$stamp"
fi

want="$(patch_hash) $(git -C "$engine" rev-parse HEAD)"
if [ "$(cat "$stamp" 2>/dev/null || true)" = "$want" ]; then
    exit 0
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
printf '%s\n' "$want" > "$stamp"
