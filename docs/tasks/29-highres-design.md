# Task 29: high-resolution rendering — ground truth and design

Read `AGENTS.md` first. Follow the "Machine resources" rules: at most 3 build
jobs (`JOBS=3 tools/build-linux.sh`, which also works on macOS), and run every
build and heavy analysis under `flock ~/.cache/tg2-heavy.lock`. Never trigger
CI, push tags or change workflow triggers. Use `SDL_VIDEODRIVER=dummy` and
`SDL_AUDIODRIVER=dummy` for every run. One runtime instance at a time. The ROM
is `~/roms/genesis/tg2.bin`. The system Python has no Pillow; make a venv in
your own scratch space if a tool needs it.

This task is **research and design only**: the implementation is a later task
that will be built on your document. Another worker is building the NTSC and
scanline stages (task 28) in the presentation path at the same time, so **do
not edit** `game/tg2_video.c`, `game/tg2_options.c` or engine presentation
code on your branch. Read them as much as you like. A throwaway spike to prove
feasibility is welcome, but keep it in a separate commit marked
`spike:` and say whether it should be kept. Engine patch numbers 0033–0039 are
reserved for the later implementation; you should not need any. Commit often
on your branch and push it. Do not merge into `main`.

The owner's requirements are in `docs/ROADMAP.md`, "High-resolution
rendering" (and "HD menus, fonts and HUD pack" as a later extension). Read
both in full.

## Questions to answer, with ROM/RAM evidence

Disassembly and runtime evidence are ground truth (engine PRINCIPLES #16).
Use `tools/disasm_tg2.py`, `docs/RAM_MAP.md`, `docs/WIDESCREEN.md`,
`docs/FRAMERATE.md`, and TCP probes (`tools/tg2_runner.py`).

1. **Road.** Which per-line state does the game compute for the road (curve,
   hill, scale, stripe phase, colours, horizon), where in RAM, and is it enough
   to re-rasterise the road at N× vertical and horizontal resolution? How does
   the 60 fps interpolation (`FRAMERATE.md`) already reconstruct it, and can
   sub-line interpolation reuse that?
2. **Sprite LOD.** The game picks smaller, lower-detail sprite variants with
   distance (trees, signs, cars). Map the LOD tables: per object, the pattern
   sets and the distance thresholds, with ROM addresses. Can we always pick the
   most detailed variant and scale it to the on-screen size with sub-pixel
   position? What breaks (sprite limits, palette lines, priorities)?
3. **Background and HUD.** How are the background layers, the HUD and the
   overscan crop composed today, and what does N× need from each?
4. **Interactions.** Widescreen margins (`WIDESCREEN.md`), 60 fps synthesized
   frames, split-screen 2P, tunnels, weather (`RAIN_WIDESCREEN.md`), menus
   (stay native), the "Internal resolution" option the engine already has
   (hidden for TG2 by patch 0017), and the NTSC/scanline stages: NTSC will be
   mutually exclusive with a render scale above 1×; scanlines run at output
   resolution and should work on an N× frame.
5. **Cost.** Estimated CPU cost at 2×, 3× and 4× on this Mac and on the Ryzen 5
   3500U / Steam Deck, and whether any part needs the GPU.

## Deliverable

`docs/HIGHRES.md`: the findings with evidence (addresses, captures, probe
commands), then a proposed architecture and an implementation plan split into
steps that can each be verified on their own (e.g. road first, then sprites,
then background/HUD), each with its acceptance check. Byte-identical Off output
(frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`) must stay a rule of
the plan. Flag anything that needs the owner's decision.

Report with `worker_done`: commits, the document, the evidence paths, open
questions, and what is not verified.
