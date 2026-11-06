#!/usr/bin/env python3
"""Headless release smoke test: dummy drivers, ROM auto-detected from disk.

The payload is copied to a scratch directory exactly as a user would unpack
it, the ROM is dropped next to the executable under an unrelated filename
(content-based detection from engine patch 0002, not a filename match), and
the game runs ~600 frames with SDL's dummy video/audio drivers.

Passes when the process exits 0, logs that it found a matching cartridge, and
reports a complete benchmark for the requested frame count.

Usage:
    smoke_run.py --dir PAYLOAD_DIR --exe NAME --rom PATH [--frames 600]
                 [--work DIR] [--keep]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

# The auto-detection must not depend on a filename, so use a decoy name and a
# decoy extension that are not Genesis ROM extensions.
DECOY_ROM_NAME = "fixture-cartridge.dat"
CLEAR_ENV_PREFIXES = ("SDL_", "GENESIS_", "RECOMP_", "RUI_", "LNG_")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="staged payload directory")
    parser.add_argument("--exe", required=True, help="executable name inside the payload")
    parser.add_argument("--rom", required=True)
    parser.add_argument("--frames", type=int, default=600)
    parser.add_argument("--work")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()

    payload = os.path.abspath(args.dir)
    if not os.path.isdir(payload):
        raise SystemExit(f"smoke: not a directory: {payload}")
    if not os.path.isfile(args.rom):
        raise SystemExit(f"smoke: missing ROM input: {args.rom}")

    workspace = args.work or tempfile.mkdtemp(prefix="tg2-smoke-")
    run_dir = os.path.join(workspace, "run")
    if os.path.exists(run_dir):
        shutil.rmtree(run_dir)
    os.makedirs(workspace, exist_ok=True)
    shutil.copytree(payload, run_dir)

    executable = os.path.join(run_dir, args.exe)
    if not os.path.isfile(executable):
        raise SystemExit(f"smoke: payload has no {args.exe}")
    if os.name != "nt":
        os.chmod(executable, 0o755)
    shutil.copyfile(args.rom, os.path.join(run_dir, DECOY_ROM_NAME))

    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith(CLEAR_ENV_PREFIXES)}
    environment.update(
        SDL_VIDEODRIVER="dummy",
        SDL_AUDIODRIVER="dummy",
        SDL_RENDER_DRIVER="software",
        SDL_JOYSTICK_RAWINPUT="0",
        SDL_JOYSTICK_HIDAPI="0",
        SDL_JOYSTICK_WGI="0",
        SDL_DIRECTINPUT_ENABLED="0",
        SDL_XINPUT_ENABLED="0",
        GENESIS_RUN_DONE="1",
    )

    command = [executable, "--no-launcher", "--benchmark", str(args.frames)]
    print(f"smoke: running {' '.join(command)} in {run_dir}")
    try:
        result = subprocess.run(
            command,
            cwd=run_dir,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=args.timeout,
        )
    except subprocess.TimeoutExpired as expired:
        print(expired.stdout or "", flush=True)
        raise SystemExit(f"smoke: timed out after {args.timeout}s")

    output = result.stdout or ""
    print(output, flush=True)

    failures = []
    if result.returncode != 0:
        failures.append(f"exit code {result.returncode}, expected 0")
    if "[ROM] found matching cartridge" not in output:
        failures.append("auto-detection did not log a matching cartridge")
    if "RUN_DONE frames=" not in output:
        failures.append("no RUN_DONE line (run did not finish)")

    benchmark = None
    for line in output.splitlines():
        if line.startswith("GENESISRECOMP_BENCHMARK "):
            try:
                benchmark = json.loads(line[len("GENESISRECOMP_BENCHMARK "):])
            except json.JSONDecodeError:
                failures.append("unparseable benchmark line")
    if benchmark is None:
        failures.append("no GENESISRECOMP_BENCHMARK line")
    else:
        complete = str(benchmark.get("complete")).lower() == "true"
        if benchmark.get("frames") != args.frames or not complete:
            failures.append(
                f"benchmark incomplete: frames={benchmark.get('frames')} "
                f"complete={benchmark.get('complete')}"
            )
        if benchmark.get("game") != "TG2":
            failures.append(f"unexpected game id {benchmark.get('game')}")

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        raise SystemExit(1)

    print(f"smoke: PASS ({args.frames} frames, ROM auto-detected, exit 0)")
    if not args.keep:
        shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    main()
