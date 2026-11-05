# Task 05: music and sound effects at the same time

Read `AGENTS.md`, `docs/BRINGUP.md` and `docs/RAM_MAP.md`. Also read the
engine audio docs: `segagenesisrecomp/GENESIS_AUDIO_FIDELITY.md`, and in
`segagenesisrecomp/docs/` the `ENGINE_AUDIO_*.md` files and
`Z80_STATIC_RECOMP.md`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents run TG2Recomp instances in parallel on this machine:
- use **TCP port 4430** and only that one;
- kill only processes you started (by PID). Never `pkill TG2Recomp`.

Other agents are working on widescreen (video renderer) and 60 fps (race
timing). Stay out of those areas. Commit often and push your branch to
origin.

## Background

On the original cartridge the player has to choose, in the SOUND menu,
between music and sound effects during races. The owner thinks this is a
hardware limit: the sound driver has too few FM/PSG channels for both. The
port should be able to play **music and SFX together**.

The owner's preference, in order:
1. **Preferred:** a new **"BOTH"** choice in the in-game SOUND menu, next
   to the stock choices. Stock choices behave exactly as before.
2. **Acceptable if much simpler:** remove the choice and always play both.
   In that case add a host option in the recomp-ui mods/settings page
   (default on) so stock behaviour can still be selected.

## Phase A: investigate (write `docs/AUDIO.md` as you go)

- **The SOUND menu.** Find the setting's RAM variable, its possible values
  and where each race reads it. Find how the menu renders its option text
  (tile strings in ROM) and how it cycles values.
- **The driver.** Find the sound driver: 68k-side calls, the Z80 program
  and its upload, the command/mailbox protocol (music start, SFX trigger,
  engine-pitch updates). Map how channels are allocated to music vs SFX.
  Is the exclusivity a real channel shortage, or just a policy branch in
  the game?
- **What happens today.** With music selected, are SFX/engine-noise
  commands not sent, or sent and dropped? With SFX selected, is the music
  never started?

Record every address in `docs/RAM_MAP.md` and `docs/AUDIO.md`.

## Phase B: implement

Pick on the evidence and justify the choice in `docs/AUDIO.md`.
Candidate techniques, simplest first:

1. **Policy only.** If the game simply skips one kind of command based on
   the setting, make the skipped path run too. Do this with
   instruction-hook/game-hook logic in `game/` keyed on the new setting,
   never by editing generated C. Verify the channels don't collide.
2. **Channel stealing.** If music and SFX share channels, SFX may already
   preempt a music channel, as many Genesis drivers do. Check whether the
   result sounds acceptable.
3. **Second virtual sound chip (host-side).** We're not limited by
   hardware. Run a second YM2612+PSG instance that receives only the SFX
   command stream, or the SFX-mode driver state, and mix both outputs on
   the host. Look at how the engine instantiates its YM2612/SN76489 and the
   Z80. A full second Z80 + driver instance fed the SFX commands might be
   the cleanest approach if the driver is mode-exclusive. Note that it
   touches the engine: if you do this, keep it game-opt-in and record any
   engine change as a patch in `patches/segagenesisrecomp/`.

For option 1 (the BOTH menu entry):
- add the value so the menu cycles through it and shows "BOTH" with the
  menu's own font/tiles;
- write the new text through a hook or a RAM/VRAM-side string;
- never patch the ROM file;
- make sure an unexpected setting value can't crash any reader of it.

## Constraints

- With BOTH (or the host option) off, the output must stay byte-identical
  to stock: frame 60 `2A0B972960C5E325` and frame 300 `1131D937D70234FD`
  framebuffer hashes, plus the stock audio for the same input route.
  Compare WAV captures of the music-only and SFX-only modes before and
  after your change; they must be sample-identical.
- No new `dispatch_misses.toml` or floor entries.

## Evidence required

- `docs/AUDIO.md` covering the driver map, the root cause of the
  exclusivity, the chosen technique and its justification.
- A PNG of the SOUND menu showing the BOTH choice, if option 1.
- WAV captures under `build/audio/` (git-ignored) of the same race route
  in MUSIC, SFX and BOTH modes. Report peak/RMS for each and prove that
  BOTH contains both:
  - correlation against the music-only and SFX-only captures, or
  - spectral/energy evidence that the engine/SFX events appear over the
    music.
- Proof that the stock modes are sample-identical to before your change.
- The miss/floor manifests, empty.

If BOTH can't be made clean, deliver Phase A in full plus the simplest
working variant (always-both behind a host option). Report it as partial,
and say exactly what's missing.
