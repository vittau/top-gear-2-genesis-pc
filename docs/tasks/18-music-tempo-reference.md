# Task 18: music tempo/pitch vs a reference (owner bug: music slightly slow, occasional speed changes)

Read `AGENTS.md` (follow its "CI budget" rules: never trigger CI),
`docs/PERFORMANCE.md` (§10 real-device audio), `docs/AUDIO.md`,
`segagenesisrecomp/GENESIS_AUDIO_FIDELITY.md` and the engine docs
`segagenesisrecomp/docs/ENGINE_AUDIO_*.md` and `Z80_STATIC_RECOMP.md`.
Also read the tools `tools/audio_device_capture.py` and
`tools/audio_glitch_detect.py`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`;
- build the release config too (see task 15/16 specs for the cmake line).

Other agents run TG2Recomp in parallel:
- use **TCP port 4570** only;
- kill only your own PIDs.

**Never play sound on the owner's speakers.** SDL ignores `PULSE_SINK`;
task 15 found that. Use `SDL_AUDIODRIVER=dummy` plus WAV capture, or the
null-sink method from PERFORMANCE.md §10, which routes by stream/target
properties. No visible windows. No sudo: user-level installs only
(`~/tools`, AppImage, `flatpak --user`). Commit often and push your
branch.

## Owner report (after the task 15 fix)

> No pops or artefacts anymore, but I still feel slight changes in music
> speed sometimes. I also have the impression the music is always slightly
> slower than normal.

The owner suggested comparing side-by-side against an emulator, or a
Genesis music renderer/VGM player. That's the core of this task.

## Phase A: a reference and an objective comparison

1. **Reference audio.** Produce reference recordings of the same music
   from an accurate source, ideally two:
   - **An accurate emulator** (Genesis Plus GX through a libretro
     frontend such as RetroArch AppImage + `genesis_plus_gx` core,
     BlastEm, or clownmdemu built locally), running the owner's ROM
     `~/roms/genesis/tg2.bin`, NTSC.
     Record: (a) the title-screen music from cold boot with no input, at
     least 60 s; (b) the first race's music on the baseline route if you
     can drive inputs, otherwise a sound-test entry (SOUND → MUSIC
     TEST).
     Use the emulator's own WAV/recording output or a null sink.
   - **A VGM rendering.** Log our runtime's YM2612/PSG register writes
     with exact guest timestamps as a `.vgm` (the engine has
     `GENESIS_AUDIO_WRITEDUMP`). Render it with an independent player
     (libvgm/vgmplay built locally). If you can find a published VGM rip
     of Top Gear 2, compare against it too. Note its provenance and do
     not commit it.
2. **Comparison tool** `tools/audio_tempo_compare.py`:
   - align the port's offline WAV and its real-device recording against
     the reference, using onset envelopes or chroma cross-correlation;
   - output the **global tempo ratio** (port/ref, in % and BPM);
   - output the **local tempo ratio over time** in 1 s windows, its
     variance and its max deviation;
   - output the **pitch offset** in cents;
   - add a `--selftest` with synthetic stretched signals.
3. **Measure.** Run the comparison for each configuration:
   - port offline capture (deterministic);
   - port real-device capture at 60 fps off and on, 16:9;
   - the reference.
   Separate the two hypotheses:
   - **H1: guest-side slowness.** The Z80 gets fewer cycles per frame
     than hardware. That shows up in the *offline* capture too.
     Candidates: BUSREQ held longer than hardware while the 68k writes
     the command block at scanline 224; Z80 cycle budget per line;
     YM2612 timer A/B rate; Z80 bank or wait-state accounting.
   - **H2: host-side wobble.** DRC ratio swings of up to ±0.5% audibly
     change speed. That shows up only in the real-device capture.

## Phase B: fix

- **H1.** Fix the emulation timing at its root, with cycle-accurate
  BUSREQ/Z80 accounting, so the offline tempo matches the reference
  within ±0.1%. This changes the offline WAV, which is expected and
  intended. Re-baseline the WAV SHA in the docs, and document the
  before/after tempo. Framebuffer hashes for video must stay identical
  (frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`).
- **H2.** Make the real-time delivery tempo-stable. Use a slow, smooth
  DRC controller with a steady-state ratio estimate, so the correction
  is near-constant at the device's real clock offset (≈0.1%) and never
  swings audibly. Keep task 15's zero pops and dropouts.
- Target: local tempo deviation ≤ 0.1% in every 1 s window over a
  3-minute race on the device capture, and global tempo within ±0.1% of
  the reference.

## For the owner

Put side-by-side listening files in `~/Music/tg2-ab/`, outside the repo
(they contain game music, so never commit them):
- `ref-title.wav`, `port-before-title.wav`, `port-after-title.wav`;
- the same three for the race music;
- a short `README.txt` saying what each file is.

## Evidence required

- `docs/AUDIO.md`: a new "Tempo fidelity" section with:
  - the reference method and provenance;
  - the comparison numbers before and after (global %, local
    variance/max, cents) for the offline and device captures;
  - the root cause or causes;
  - the fix.
- Engine patch changes recorded in `patches/segagenesisrecomp/README.md`.
- Nothing left running. Any null sink unloaded. Emulator and tools
  installed only under `~/tools`, with what was installed listed in the
  report.
