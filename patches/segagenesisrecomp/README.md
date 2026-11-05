# Engine patches

- `0001-preserve-irq-register-effects.patch`: preserve general-register changes made by guest ISRs, including raster pointers advanced between H-interrupts.

- `0002-detect-local-rom-by-content.patch`: find a cartridge matching the game CRC beside the executable or in the working directory before opening a launcher.

- `0003-game-settings-and-menu-rows.patch`: let a game persist its own options in the shared settings.ini, append game-owned rows to the in-game settings menu, capture the open menu in debug screenshots, and let `--launcher` open on an auto-detected cartridge.

- `core-0003-rts-stack-dispatch.patch`: emit computed tail dispatch for guest-pushed RTS targets, preventing the road renderer from leaking its guest stack (applies to `external/m68k-recomp-core/`).

`tools/build-linux.sh` applies these idempotently through
`tools/apply-engine-patches.sh`. The submodule stays pinned to the upstream
commit; local fixes remain visible as its applied working-tree diff.
