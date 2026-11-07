# Application artwork and desktop identity

The owner selected **Crest of Fire**, original generated airbrush-style artwork
with a silver sports car and a warm sunset. The authoritative 1024×1024 master
is `tools/release/tg2recomp.png`. It is shared by the README, AppImage icon,
macOS bundle icon and GitHub social preview. No cover artwork, logos or
ROM-derived graphics are included. Exact prompts and generation settings live
in `tools/release/icon/PROMPTS.md`.

## Regeneration and build inputs

`python3 tools/release/make_icon.py --all` uses Pillow to derive:

- `tools/release/icon/tg2recomp-{16,24,32}.png`: tighter same-car crops with
  modest contrast/sharpening for small physical pixel sizes;
- `tools/release/tg2recomp.ico`: 16/24/32/48/64/256 px, using those same crops
  for 16/24/32, uncompressed 32-bit DIBs below 256 and a PNG at 256;
- `docs/images/social-preview.png`: 1280×640 with plain project text.

Pillow and a DejaVu Sans font are artwork tools only. A normal build needs
neither: it extracts the 32px ICO image into a build-local RGBA header with
`tools/release/icon/embed_icon.py` (Python standard library). `GameSpec`
passes immutable pixels to the runner, which calls `SDL_SetWindowIcon` after
creating the gameplay window. No image decoder or loose icon file is needed
at runtime. The generated header stays outside git.

On Windows, CMake enables RC and compiles the configured `tg2recomp.rc` only
under `WIN32`, embedding the multi-size ICO directly in the executable. On
macOS, `build-macos.sh` uses `sips` and `iconutil`, taking the small crops at
16/32 physical pixels and the master at larger sizes. AppImage packaging
copies the master to both `tg2recomp.png` and `.DirIcon`.

Patch `0015-game-application-icon.patch` adds generic, optional `GameSpec`
fields; the artwork and `tg2recomp` identity remain in the game repository.
The highest patch on `origin/main` was 0013 when checked; 0014 was reserved
for the concurrent BOTH worker by the coordinator.

## Wayland and Steam Deck

The desktop basename, `Icon`, `StartupWMClass`, game app id and the default
`SDL_VIDEO_WAYLAND_WMCLASS` / `SDL_VIDEO_X11_WMCLASS` all use **tg2recomp**.
Identity is set before any SDL video initialization, including the launcher.
Explicit environment overrides remain available to the host.

SDL2 cannot submit a window icon to a native Wayland compositor through
`SDL_SetWindowIcon`. The compositor must resolve `tg2recomp` to installed
desktop metadata and an icon in its icon search path. The AppImage contains
matching metadata, but merely mounting/running an AppImage does not install
its desktop entry into the user's desktop database. A desktop integration
manager or installation supplies that connection. A compositor/theme may
also omit icons from title bars even when it has the right icon.

Steam Deck Desktop Mode follows those desktop rules. Game Mode uses Steam's
library/shortcut artwork and Gamescope shell policy: matching the SDL app id
and setting the window icon does not automatically populate Steam grid,
hero, capsule or shortcut artwork. No Game Mode artwork integration or Deck
visual test is claimed here.

## Validation

All paths below are relative to this worktree. No CI was triggered.

- `flock ~/.cache/tg2-heavy.lock ... JOBS=3 tools/build-linux.sh`: exit 0
  after reapplying the saved engine patch stack with `--reset`; log
  `build/icon/build.log`. Generated headers and ROM translations remain in
  the ignored build directory.
- `python3 build/icon/verify_assets.py`: exit 0; validates 1024×1024 master,
  1280×640 social preview, all six ICO sizes, pixel equality of the ICO's
  small entries with the PNG crops, embedded RGBA equality, and identical
  asset SHA-256s after regeneration. Evidence: `build/icon/assets-verification.json`.
- Windows cross-CMake configure: exit 0, including the Windows-only RC
  source and compiler rule. Requesting the single-resource Ninja target
  also pulled in code-generation prerequisites, which failed because this
  host lacks Windows C runtime headers (`stdio.h` / `errno.h`); that command
  exited 1. The exact RC command emitted by CMake was then compiled directly
  with LLVM windres under the heavy lock (exit 0), with six `ICON` resources
  and one `GROUP_ICON` confirmed by `llvm-readobj` in
  `build/icon/windows-resources.txt`. A complete Windows executable/run is
  not qualified by these checks.
- `python3 tools/probe_run.py --exe build/TG2Recomp --out build/icon/headless
  --frames 360 --port 4620 --widescreen off --shots 300`: exit 0. Dummy video
  and audio; TCP screenshot/probe results in `build/icon/headless/`.
- `python3 build/icon/x11-evidence.py`: final run exit 0 after 600 frames,
  `SDL_VIDEODRIVER=x11`, `SDL_AUDIODRIVER=dummy`, TCP port 4620. The actual
  `WM_CLASS` was `(TG2Recomp, tg2recomp)`; its class matches the desktop entry.
  `_NET_WM_ICON` was exactly 32×32, pixel-identical to the approved crop.
  Evidence: `build/icon/x11/result.json`, `build/icon/x11/client-window.png`.
- Both completed runs preserved Off-mode frame 60 **2A0B972960C5E325** and
  frame 300 **1131D937D70234FD**, with **zero dispatch misses** and **zero
  floor entries**. Logs/manifests are in each run directory; combined
  assertions are in `build/icon/runtime-verification.json`. Both processes
  exited and no runtime from this worktree remains.
- `bash -n tools/release/build-macos.sh tools/release/build-appimage.sh`,
  Python compilation checks and `git diff --check`: exit 0.

The X11 capture contains the 640×448 client area. The compositor reports a
34px top decoration, but that title bar is absent from the X11 drawable;
Orca's Linux computer-use provider reports screenshot capture unsupported.
A decorated-title-bar screenshot was therefore not obtainable here. The
window icon itself was verified directly through `_NET_WM_ICON`, without
claiming that this theme displays it in the title bar.

macOS `.icns` generation/visual behavior, native Wayland icon resolution,
Windows Explorer/taskbar appearance, packaged AppImage desktop integration
and Steam Deck Game Mode were not exercised on their target systems. The
existing packaging paths consume the new artwork; a release qualification
on those systems remains necessary.
