# Task 20: BOTH sound mode via a second virtual sound chip (owner bug: BOTH sounds like noise)

Read `AGENTS.md` (follow its "CI budget" rules: never trigger CI),
`docs/AUDIO.md` (all of it: the drivers, §5-7 BOTH, §10 limitations, §12
the 68k↔Z80 interaction map), `game/tg2_audio_both.c`,
`game/tg2_options.c` and the engine audio code (`segagenesisrecomp/runner/audio/`,
YM2612 via ymfm, SN76489).

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- run `tools/apply-engine-patches.sh`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents may run TG2Recomp:
- use **TCP port 4590** only;
- kill only your own PIDs.

**Never play sound on the owner's speakers**: dummy audio or offline
WAV capture only. No visible windows. Task 19 runs in parallel and may
touch audio timing (YM timer B, sample clock). Keep your engine change
isolated to chip instantiation and routing, and merge `origin/main`
before reporting. Commit often and push your branch.

The owner accepts small accuracy concessions for a better experience.
This is one: real hardware has one chip.

## Owner report

> I selected BOTH. In the race the audio was completely broken, with
> artefacts and sounds repeating. You couldn't even make out the sound
> effects, just noise.
>
> When I go back to the menu with BOTH selected it seems to switch to
> MUSIC, although I think BOTH was applied.

**Root cause of the noise.** BOTH is a *shared-chip mix*. The Z80 music
driver and the 68k SFX engine program the same six FM channels and the
same PSG, so they overwrite each other's notes, instruments and
frequencies. Task 16's evidence only counted writes and never judged
the result.

## Design: two virtual chips, routed by writer

Only when BOTH is active:
- **Chip A** (YM2612 + SN76489) receives every write issued by the Z80:
  the music driver.
- **Chip B**, a second YM2612 + SN76489, receives every YM/PSG write
  issued by the 68k: the SFX engine and engine noise. The engine already
  knows the writer for each write (the write dump records the writer
  PC), and 68k accesses arrive through the Z80 bus window or the PSG
  port.
- **Status reads.** Z80 reads of the YM status and timers come from
  chip A. Its timer B is the music clock, so the tempo is unchanged.
  68k reads of the YM status (busy flag) come from chip B.
- **DAC.** If either driver uses the DAC (reg `$2A`/`$2B`), keep it on
  the chip of its writer.
- **Mixing.** Mix A and B at the output. Balance the levels so BOTH
  sounds like MUSIC and SFX together at their stock loudness, and don't
  clip: apply headroom or a soft limiter only if needed. Document the
  mix gain.
- Find out whether the game, in BOTH, still needs the hooks from task
  16 that force music-side and SFX-side policy reads (`$FF240E`). With
  separate chips, both drivers should run exactly as in their stock
  modes: the music driver as in MUSIC, the SFX engine as in SFX.

Keep the routing **off** in MUSIC and SFX modes. Stock modes keep a
single chip and are byte-identical.

## Menu display bug

After leaving the RACE SOUND page with BOTH selected, returning to it
shows MUSIC. Make the page always display the current host choice,
whichever way it was entered (B, H, glyphs as task 16 made them).

## Objective acceptance (required, beyond "it compiles")

On the same deterministic input route through a race, with the offline
capture:

1. Render **MUSIC mode**, **SFX mode** and **BOTH mode** WAVs.
2. In BOTH, chip A's separate output must match MUSIC mode's output.
   Chip B's must match SFX mode's output. Use a sample-exact or
   near-exact comparison: correlation ≥ 0.99 and residual RMS reported.
   Export chips A and B individually behind a debug env var for this
   check.
3. The BOTH mix must equal the gained A+B (residual ≈ 0).
4. Check perceptual sanity: no clipping (peak below full scale), and no
   repeated-buffer artefacts (tools/audio_glitch_detect.py on the BOTH
   WAV: 0 pops, 0 dropouts).
5. Do a real-device check via the null-sink method (PERFORMANCE.md §10;
   SDL ignores PULSE_SINK, so use the documented routing): a 3-minute
   race in BOTH with 0 pops and 0 dropouts.

## Constraints

- With every option off, the stock frame hashes are unchanged (frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD`), and MUSIC/SFX
  offline WAVs are byte-identical to the current main.
- Manifests stay empty.
- CPU: a second YM2612 costs CPU. Measure the frame-time p95 in BOTH on
  the release config and keep it within the PERFORMANCE.md budget.

## Evidence required

- `docs/AUDIO.md`: §5-7 and §10 rewritten for the dual-chip design,
  with the acceptance numbers above.
- Short listening files for the owner in `~/Music/tg2-ab/`, outside the
  repo: `both-before.wav`, `both-after.wav`, `music-only.wav` and
  `sfx-only.wav` from the same race, plus a README update.
- A PNG of the RACE SOUND page re-entered after selecting BOTH, showing
  BOTH.
- Any engine change as a patch in `patches/segagenesisrecomp/` with a
  README line.
