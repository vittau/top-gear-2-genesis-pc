# Engine patches

- `0001-preserve-irq-register-effects.patch`: preserve general-register changes made by guest ISRs, including raster pointers advanced between H-interrupts.

- `0002-detect-local-rom-by-content.patch`: find a cartridge matching the game CRC beside the executable or in the working directory before opening a launcher.

- `0003-game-settings-and-menu-rows.patch`: let a game persist its own options in the shared settings.ini, append game-owned rows to the in-game settings menu, capture the open menu in debug screenshots, and let `--launcher` open on an auto-detected cartridge.

- `core-0003-rts-stack-dispatch.patch`: emit computed tail dispatch for guest-pushed RTS targets, preventing the road renderer from leaking its guest stack (applies to `external/m68k-recomp-core/`).

- `core-0004-exact-stack-delta.patch`: account every instruction that moves the guest stack in the split-function counter (`_sp_popped` / `g_split_sp_popped`), not just the MOVE/MOVEA/MOVEM/PEA and `ADDQ/SUBQ #n,SP` forms. One rule now drives both the `has_sp_adjust` pre-scan and the emission, so an arithmetic/logical form with a `(SP)+` or `-(SP)` effective address can no longer drift the counter. A drift used to turn a plain RTS into a "guest pushed a jump target" dispatch: Top Gear 2's `$7336` RTS at `$754A` dispatched the `$650C` return slot after sixteen `move.w d0,-(sp)` / `add.w (sp)+,d0` iterations, which skipped the whole scene-init continuation (task 24). `tools/check_stack_delta.py` cross-checks the generated C against the ROM (applies to `external/m68k-recomp-core/`).

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

- `0014-second-z80-core-race-sfx-pcm.patch`: run a second Z80 core alongside the resident music driver, only while a game enables it (Top Gear 2's BOTH mode). It has its own 8 KB RAM, bank register and bus-request/reset state, so the 68K's upload of a second sound image cannot overwrite or reset the music driver (the first prototype's fatal side effects). A game-owned predicate tells the bus which 68K Z80-space accesses reach the second core; its chip writes carry `AUDIO_ORIGIN_Z80_SFX` and the mixer feeds them to virtual chip B together with the 68K engine, applied in the stock merged-stamp order so chip B reproduces SOUND EFFECTS mode. The core and its RAM are in every save state and rollback snapshot; stock modes never instantiate or step it.

- `0013-runtime-menu-quit-row.patch`: enable the recomp-ui standard "Quit game" row (two presses) in the in-game menu and leave through the normal window-close path, so a controller-only player (Steam Deck) can exit without the system menu.

- `0015-game-application-icon.patch`: expose game-owned desktop app id and embedded RGBA window icon, set SDL2 Wayland/X11 identity before video initialization, and call `SDL_SetWindowIcon` for the gameplay window.

- `0016-photo-freeze-hotkey.patch`: P freezes emulation on the current frame without the game's own PAUSE screen (P or Esc resumes), so a player can line up a clean screenshot of the window. Nothing changes until P is pressed.

- `0017-game-hides-internal-resolution.patch`: a `GameSpec.hide_internal_resolution` flag drops the runtime menu's "Internal resolution" row for games whose own video provider ignores the supersampling scale (Top Gear 2 today: the row did nothing visible).

- `0018-quickstate-frame-boundary-and-resume.patch`: a game hook may offer a per-frame instruction as a host-snapshot boundary (`glue_state_boundary`), which parks a queued save at a repeatable point instead of interrupting whatever instruction the save command landed on, and the adapter may name the PC the game fiber restarts at after a load (`state_resume_pc`). Top Gear 2's screens spin on their own hardware flags, so without this a quickstate loaded in a fresh process resumed inside the new process's boot chain and the picture froze while the guest ran on.

- `0019-macos-installed-app-rom-library.patch`: an app in an Applications folder keeps settings, logs, saves and the cartridge in `~/Library/Application Support/TG2Recomp/` instead of loose files in `/Applications`; the cartridge search covers that folder, and a ROM picked in the launcher is copied there (after its CRC check) so later launches boot straight in.

- `0020-game-default-players.patch`: a `GameSpec.default_players` count enables player 2's default bindings (right-hand keyboard set + second gamepad) before `settings.ini` is read, so a fresh install can start a 2-player race; a saved `[input.pN]` device still wins. The runner logs the effective player map at startup.

- `0021-quickstate-resume-continues-guest-callers.patch`: a load resumed at a game boundary (`state_resume_pc`) keeps the restored A7, and when the resumed loop returns the game fiber continues the return addresses on the guest stack (only longs that follow a JSR/BSR) before the dispatcher fallback. Without it, a Top Gear 2 race loaded from a quickstate ended and fell back to the title loop, skipping the results and the next race.

- `0022-menu-dismissed-button-release.patch`: buttons and pad buttons that are physically held when gameplay input is unblocked (the Enter or pad accept that closed the runtime menu) are latched and suppressed until released, so dismissing the menu cannot also press START/accept in the game. Nothing held means no change. Dev builds also get an input seam for probes, because `SDL_GetKeyboardState` cannot be set from outside the process.

- `0023-state-notices-in-presented-picture.patch`: a save or load result is drawn into the presented picture for 2.5 s at the top-left (`STATE SAVED TO SLOT N`, `STATE LOADED FROM SLOT N`, `SAVE UNAVAILABLE HERE`, `LOAD REJECTED`, ...) using the in-game runtime menu's own 5x7 cell and a light theme colour over a dim panel, instead of relying only on the window title. Presentation only: no guest, framebuffer-hash, replay or normal screenshot change, and `screenshot` with `"presented":1` captures the composited window. Adds the dev-only probes (`key`, `ui_open`, `ui_rows`, `pad`, `virtual_pad`) that drive the real menu over TCP.

- `0024-quickstate-save-waits-for-a-boundary.patch`: a quickstate asked for on a screen with no resumable boundary (the inter-race results, championship table, setup, next-track intro and shop screens) stays queued for up to 15 s instead of being dropped after 2 s, shows `SAVING AT NEXT BOUNDARY...`, and is written at the next boundary the game reaches — pressing START to begin the next race saves the start of that race. A later request replaces the queued one, and a save whose temporary file cannot be opened now reports `SAVE FAILED: CANNOT WRITE STATE` instead of failing silently.

- `0025-linear-filter-picture-bounds.patch`: linear presentation uses an exactly-sized picture texture, preserving nearest output and the saved/default Off preference; opt-in SDL-output captures verify scaled edges.

- `0026-preserve-macos-bundle-icon.patch`: on macOS keep the bundle ICNS for Dock/Cmd+Tab instead of assigning the embedded 32px SDL window icon; the host passes no launcher icon override.

- `0027-menu-esc-only-f1-loads-slot1.patch`: open the runtime menu on Esc only (gamepad Back+RB unchanged) so plain F1 reaches the engine's slot 1 load and Shift+F1 saves slot 1, with the state notices and menu-dismiss latch unchanged.

- `0033-presented-picture-height.patch`: a `GameVideo.present_frame` hook lets a game provider compose and report a presented picture taller than the VDP's own geometry (after every native row, before the presented-window crop), with the buffers/texture sized for 4 x 224 rows; the interlace halving and netplay half-view clamp now key on the VDP's interlace mode instead of a height threshold, so a tall non-interlaced picture is shown at full height. Required by Top Gear 2's high-resolution rendering (task 31, S2).

- `0040-separate-music-sfx-volumes.patch`: tag every frame's applied writes as music or sound effects by *writer* (the resident Z80 music driver is music; the 68K FM/PSG engine and the race SFX PCM image are sound effects, including the first core once the 68K has uploaded that image over the driver) and apply player Music/SFX faders to the generated mix (`audio_mixer_set_source_volumes`). A frame that carries one source is the one chip's stock stream scaled exactly; only a frame that really carries both is rendered on two chips, like BOTH mode. 100%/100% runs nothing extra, so every stock WAV stays byte-identical.

- `0041-fm3438-and-dac-reconstruction.patch`: two host options on the ymfm chip model - `ym2612_set_variant(i, 1)` renders with ymfm's YM3438 core (same notes, no YM2612 ladder discontinuity) and `ym2612_set_dac_resample(i, 1)` replays the DAC ($2A) stream through a 95-tap Kaiser-windowed-sinc reconstruction at 3.3 kHz instead of the chip's sample-and-hold, feeding the filtered level back into the register once per output sample. Both default off (stock YM2612, stock DAC) and both are covered by the save-state/rollback format.
