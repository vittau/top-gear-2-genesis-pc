# Task 23: project and application icon (owner request)

Read `AGENTS.md` first. Follow its "Machine resources" rules (at most 3
build jobs, `flock ~/.cache/tg2-heavy.lock` around any build) and its "CI
budget" (never trigger CI). This is a light task: avoid full rebuilds unless
you need one to check the in-game window icon.

## Goal

Design one icon that represents the project everywhere:
- the GitHub repository (social preview and README);
- the app icon on each platform:
  - Linux AppImage `.DirIcon` and desktop entry;
  - macOS `.icns` in `TG2Recomp.app`;
  - Windows `.exe` icon resource;
- the game window's own icon (title bar and taskbar).

Today `tools/release/make_icon.py` renders a plain speedometer mark into
`tools/release/tg2recomp.png`. The macOS and AppImage builds use that PNG.
The running window shows a generic icon: the Wayland title bar showed a
placeholder "W".

## Direction from the owner

The owner wants it **inspired by the Sega Genesis cover of Top Gear 2**:
its mood, palette and composition. Think of a sports car on a road in
perspective, speed, and 90s Genesis box-art energy. He may provide the
cover image; if a file appears, the coordinator will send you its path.

Hard constraints:
- **Original artwork only.** Don't copy, trace or include the cover art, the
  "Top Gear" logo or wordmark, Kemco/Gremlin/Sega marks, or any ROM-derived
  graphics. "Inspired by" means the same spirit, drawn from scratch.
- It must read at **16×16 and 32×32**, where a car silhouette becomes mush.
  Design a bold simple mark first. A detailed large version may add detail,
  as long as the silhouette stays the same.
- Generate it from source in the repo, reproducibly: SVG, or code like the
  current `make_icon.py`, rendered to a 1024 px master. Keep only the source
  and the masters in git, not every intermediate size.

## Deliverables

1. Present **2–3 concepts** first, as PNG previews at 1024, 64, 32 and 16 px,
   outside git under `build/icon/`. Send them to the coordinator with `ask`
   and stop until one is chosen. The owner picks.
2. For the chosen concept:
   - Replace `tools/release/tg2recomp.png` (keep the path, which packaging
     uses) and update `make_icon.py`, or add an SVG with a render script.
   - **Windows:** produce a multi-size `.ico` (16/24/32/48/64/256) and embed
     it in `TG2Recomp.exe` with a `.rc` resource in CMake, Windows only. Check
     the CMake logic as far as you can on Linux.
   - **Window icon:** set it at runtime from an embedded copy of the icon
     (`SDL_SetWindowIcon`), for X11, Windows and macOS. On Wayland the
     compositor takes the icon from the app id and desktop file. Make the
     SDL app id / `SDL_VIDEO_WAYLAND_WMCLASS` match the AppImage desktop entry,
     and report what can and cannot work on Wayland and on the Steam Deck in
     Game Mode. If this needs an engine change, add it as a new patch in
     `patches/segagenesisrecomp/` (check the highest number on `origin/main`
     first) with a README line.
   - A 1280×640 GitHub social preview image (`docs/images/social-preview.png`);
     the coordinator uploads it.
3. Evidence: the previews, the `.ico` contents (sizes), a screenshot of the
   window's title bar on X11 or XWayland if feasible (no sound, kill your
   process afterwards), and the Off-mode frame hashes unchanged (frame 60
   `2A0B972960C5E325`, frame 300 `1131D937D70234FD`).

Commit often and push your branch.
