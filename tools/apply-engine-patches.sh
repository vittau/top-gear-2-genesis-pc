#!/usr/bin/env bash
# Portable entry point; snapshot/reset/stamp logic lives only in Python.
set -euo pipefail
repo=$(cd "$(dirname "$0")/.." && pwd)
exec python3 "$repo/tools/apply-engine-patches.py" "$@"
