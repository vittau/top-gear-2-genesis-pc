# Engine patches

- `0001-preserve-irq-register-effects.patch`: preserve general-register changes made by guest ISRs, including raster pointers advanced between H-interrupts.

- `0002-detect-local-rom-by-content.patch`: find a cartridge matching the game CRC beside the executable or in the working directory before opening a launcher.

- `0003-game-settings-and-menu-rows.patch`: let a game persist its own options in the shared settings.ini, append game-owned rows to the in-game settings menu, capture the open menu in debug screenshots, and let `--launcher` open on an auto-detected cartridge.

- `core-0003-rts-stack-dispatch.patch`: emit computed tail dispatch for guest-pushed RTS targets, preventing the road renderer from leaking its guest stack (applies to `external/m68k-recomp-core/`).

- `0004-executable-base-path-and-replay-logs.patch`: resolve the base directory from the running image, honoring `$APPIMAGE` only when the executable really lives inside that AppImage (an inherited variable from a parent AppImage sent logs, settings, evidence and save states to `~/.local/bin`).

- `0005-exact-guest-clock-and-frame-telemetry.patch`: keep the guest clock exact (a late frame repays its tick instead of resetting the cadence; presentation-only work is skipped and the picture dropped), and record an always-on per-frame wall/CPU/DRC statistics ring.

- `0006-audio-drc-prime-snap-and-ratio-bound.patch`: discard the boot pre-roll at prime instead of resampling it away for ~26 s, and bound the DRC ratio to +/-0.2 % so a deficit cannot be masked as audible tempo/pitch drift.

`tools/build-linux.sh` applies these idempotently through
`tools/apply-engine-patches.sh`. The submodule stays pinned to the upstream
commit; local fixes remain visible as its applied working-tree diff.
