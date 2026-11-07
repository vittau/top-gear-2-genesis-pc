# Engine patches

- `0001-preserve-irq-register-effects.patch`: preserve general-register changes made by guest ISRs, including raster pointers advanced between H-interrupts.

- `0002-detect-local-rom-by-content.patch`: find a cartridge matching the game CRC beside the executable or in the working directory before opening a launcher.

- `0003-game-settings-and-menu-rows.patch`: let a game persist its own options in the shared settings.ini, append game-owned rows to the in-game settings menu, capture the open menu in debug screenshots, and let `--launcher` open on an auto-detected cartridge.

- `core-0003-rts-stack-dispatch.patch`: emit computed tail dispatch for guest-pushed RTS targets, preventing the road renderer from leaking its guest stack (applies to `external/m68k-recomp-core/`).

- `0004-executable-base-path-and-replay-logs.patch`: resolve the base directory from the running image, honoring `$APPIMAGE` only when the executable really lives inside that AppImage (an inherited variable from a parent AppImage sent logs, settings, evidence and save states to `~/.local/bin`).

- `0005-exact-guest-clock-and-frame-telemetry.patch`: keep the guest clock exact (a late frame repays its tick instead of resetting the cadence; presentation-only work is skipped and the picture dropped), and record an always-on per-frame wall/CPU/DRC statistics ring.

- `0006-audio-drc-prime-snap-and-ratio-bound.patch`: discard the boot pre-roll at prime instead of resampling it away for ~26 s, hit the steady-state ring with 100 ms of cushion, allow the servo the full +/-0.5 % a real device crystal needs, splice accumulated latency out behind a 4 ms gain dip instead of letting the ring overflow, and resume live play one pull block after a stall instead of holding the cursor until the ring is full again (that hold turned every stall into permanent delay).

- `0007-macos-app-bundle-paths.patch`: resolve the running image with `_NSGetExecutablePath` on macOS, search the folder containing `X.app` for the cartridge, and put settings, logs and saves beside `X.app` when writable or in `~/Library/Application Support/TG2Recomp/` otherwise; assets stay in `Contents/Resources` where SDL reports them.

- `0008-exact-audio-sample-clock.patch`: drain the mixer with the machine's own frame length (`262 x 3420 = 896040` master cycles, not `895780`) and keep the PSG's sub-sample divider remainder across frame boundaries instead of discarding it. The offline tap was emitting 3732 samples per frame instead of 3733.5, i.e. the whole audio stream played 402 ppm flat against hardware; it is now exact (0 ppm) and the framebuffer hashes are unchanged. (`GENESIS_MIXER_RESET_LEFTOVER=1` restores the old per-frame reset for A/B measurement only.)

- `0010-ym-timer-b-free-running-phase.patch`: make the CPU-visible YM2612 timer B a free-running grid instead of re-arming it on every `$27` load write. The load bit starts a stopped timer and does not re-phase a running one (the same rule as ymfm's `fm_engine_base::update_timer`, which renders the FM), so a driver that reloads the timer once per music tick — this game's Z80 driver writes `$27=$2E` ~50 times a second — has its polling lateness repaid by the following shorter tick. Re-arming on every write turned every late tick into permanent tempo loss: the title theme ran 7.2 % slow in the menus (mean tick 21.25 ms against a 19.82 ms timer) and the long-run average is now the timer period (19.82 ms, matching the hardware formula and the owner's VGM rips within 0.1 %).

- `0009-tempo-stable-drc-controller.patch`: make the real-time playback ratio tempo-stable. Steady state is an integral estimate of the device's constant clock offset (2 s error low-pass, 50 ppm/s slew) instead of a proportional servo on ring fill, so frame-cadence sawtooth and host jitter cannot modulate the music speed; a fill excursion beyond 25 ms is a hitch, not a clock, and switches to the fast proportional path (300 ms low-pass, 0.5 %/s) so the ring still refills quickly. The control update now uses the real pull-block duration instead of a nominal 12 ms, and the deadband no longer forces the correction back to zero (which was a slow +/-200 ppm triangle wobble).


`tools/build-linux.sh` applies these idempotently through
`tools/apply-engine-patches.sh`, which stamps the tree with a hash of every
patch file plus the engine commit (so a second run is a no-op even when a later
patch touches lines an earlier one changed). After adding or regenerating a
patch, run it once with `--reset`. The submodule stays pinned to the upstream
commit; local fixes remain visible as its applied working-tree diff.

- `0011-writer-routed-second-sound-chip.patch`: tag every queued FM/PSG write with its writer and, when the game asks for it, feed a second virtual YM2612+SN76489 from the 68K-origin writes while the first chip keeps the Z80 music driver (`audio_set_chip_routing`). Stock modes keep the single chip and are untouched; the per-chip timer/status model keeps chip A's timer B as the music clock (patch 0010's free-running phase included) and gives the 68K side its own. `audio_mixer_chip_output()` exposes each chip's stream for the BOTH acceptance export (`GENESIS_AUDIO_CHIPDUMP`). The 68K no longer stalls the Z80 for its chip writes while routing is on, because those go to the second chip.

- `0012-game-video-presented-window.patch`: let a game video provider crop empty scanline bands from the presented picture (a `present_window` hook called once per completed frame, so captures, hashes and the margin audit keep all native rows) — Top Gear 2's race overscan crop needs it.

- `0013-runtime-menu-quit-row.patch`: enable the recomp-ui standard "Quit game" row (two presses) in the in-game menu and leave through the normal window-close path, so a controller-only player (Steam Deck) can exit without the system menu.

- `0015-game-application-icon.patch`: expose game-owned desktop app id and embedded RGBA window icon, set SDL2 Wayland/X11 identity before video initialization, and call `SDL_SetWindowIcon` for the gameplay window.
- `0016-photo-freeze-hotkey.patch`: P freezes emulation on the current frame without the game's own PAUSE screen (P or Esc resumes), so a player can line up a clean screenshot of the window. Nothing changes until P is pressed.
