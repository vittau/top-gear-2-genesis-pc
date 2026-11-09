# Task 30: clean FM, separate volumes, better engine/nitro PCM

Read `AGENTS.md` first. Follow the "Machine resources" rules: at most 3 build
jobs (`JOBS=3 tools/build-linux.sh`, which also works on macOS), and run every
build and heavy analysis under `flock ~/.cache/tg2-heavy.lock`. Never load
whole WAVs into memory; stream them and delete large WAVs once their numbers
are extracted. Never trigger CI, push tags or change workflow triggers. Use
`SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy` (or the null-sink
recording path in `docs/PERFORMANCE.md`) for every run. One runtime instance at
a time. The ROM is `~/roms/genesis/tg2.bin`.

Engine changes go in new patches numbered **0040–0044** (reserved for this
task), each with a one-line reason in `patches/segagenesisrecomp/README.md`.
Commit often on your branch and push it. Do not merge into `main`.

The owner's requirements are in `docs/ROADMAP.md`, "Clean FM and separate
volumes" and "Better engine and nitro PCM". Read both in full, and
`docs/AUDIO.md` (the drivers, BOTH, the second Z80 core, chip A/B routing).

## Parts, in this order

1. **Separate volumes.** Music and SFX volume sliders next to the master
   Volume in the Esc menu and the launcher, in every RACE SOUND mode (MUSIC,
   SOUND EFFECTS, BOTH). Classify by source: the Z80 music driver is music; the
   68k FM/PSG engine and the race Z80 SFX image are SFX. In MUSIC and SOUND
   EFFECTS modes one chip carries both, so say how you split it (per-writer
   origin, as patch 0014 does for chip B) and verify it. 100% must stay
   byte-identical.
2. **Clean FM.** An option for an ymfm YM3438-style FM without the YM2612
   ladder distortion; the default stays the stock YM2612 sound and stays
   byte-identical.
3. **Engine and nitro PCM.** The engine and nitro are a 6.6 kHz DAC player in
   the race Z80 SFX image (ROM `$0701F6`). Add band-limited resampling of the
   DAC stream instead of the DAC's sample-and-hold, as an option (or as part of
   clean FM: propose which). Never use samples from other games or versions.

## Acceptance

- With the new options at their defaults, the stock MUSIC/SFX/BOTH WAVs are
  byte-identical to `main`, and the Off-mode frame hashes are unchanged
  (frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`).
- For each part, before/after recordings of the same scripted race and menu,
  with the measurements that prove the change (level per source for the
  sliders, the ladder-distortion signature for clean FM, the spectrum above
  the DAC rate for the resampling), and 0 pops/dropouts/underruns.
- Short A/B files for the owner's listening test in `~/Music/tg2-ab/` (outside
  git).
- `docs/AUDIO.md` updated; the ROADMAP items updated.

Report with `worker_done`: commits, commands and exit codes, measurements,
A/B file paths, and what is not verified.
