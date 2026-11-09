# macOS bundle icon: native resolution and continuous corners

Branch `vittau/tg2-mac-icon` starts directly at `origin/main` (`278d306`),
not at the rain/linear-filter branch. Engine patch **0026** owns the runtime
change. No recomp-ui file or submodule pin is changed.

## Why the runtime icon became blurry

The existing package script already produced an ICNS with 16 through 1024
physical pixels. Its master is the approved 1024px photo. The separate
`icon/embed_icon.py` intentionally extracts the ICO's **32px** DIB for the
cross-platform SDL window icon.

`runner/main.c` called `SDL_SetWindowIcon` with that embedded bitmap. SDL
2.28.5's Cocoa implementation (`SDL_cocoawindow.m`, `Cocoa_SetWindowIcon`)
creates an NSImage and calls `[NSApp setApplicationIconImage:nsimage]`:
the small *window* icon therefore replaces the application's bundle icon in
the Dock/Cmd+Tab.

Patch `0026-preserve-macos-bundle-icon.patch` excludes that game-window call
under `__APPLE__`; Windows/Linux retain the original code. The host also
explicitly leaves `RecompLauncherCGameInfo.window_icon_path = NULL` on Apple.
The launcher already receives a zero-initialized GameInfo here, so it did
not have another small-image override to fix: `launcher_ng_capi.c` passes
the path to `launcher_platform_set_icon`, and both SDL2/SDL3 implementations
return immediately on NULL/empty paths. This follows the existing host
contract and needs no new recomp-ui patch process.

## macOS shape, without another bitmap master

`tools/release/icon/macos_icon.swift` uses Apple's public SwiftUI
`RoundedRectangle(cornerRadius: 185, style: .continuous)` path. The body is
824×824 at `(100,100)` on a transparent 1024×1024 canvas. CoreGraphics clips
the existing artwork into that path and adds a subtle black shadow (24%
alpha, 8px downward offset, 16px blur). ImageIO writes the build-local PNG;
`sips` derives every ICNS representation from it, then `iconutil` packs it.
The Xcode/macOS frameworks are build-time tools only; no Swift code or new
pip dependency enters the application. The design uses public system
geometry rather than copying a binary template from
[Apple Design Resources](https://developer.apple.com/design/resources/).

No binary master or comparison image is added to git. The approved master,
Windows ICO, embedded detail PNG and Linux icon are byte-identical to main:

- Master/Linux PNG SHA256: `8b0094d4e8c5e2f7d7a32cf0e3f463faeab409f373a476921ce276dd1a938236`.
- Windows ICO SHA256: `2787e151df57531ee9958ab6ea2e5b14c6eaf2413e9bf9d2b00b708300f189f5`.
- Embedded 32px source SHA256: `5c0e8d1a0724b66b25a370f5acfab3b96909e5070296d52c4b5445c86fdc06af`.

## Evidence (macOS arm64)

Release command, **exit 0**, with the shared lock and three build jobs:

```
flock ~/.cache/tg2-heavy.lock tools/release/build-macos.sh \
  --rom "$HOME/roms/genesis/tg2.bin" \
  --sdl "$HOME/tg2-deps/sdl/SDL2-2.28.5" \
  --build "$PWD/build-release/mac-icon" \
  --out "$PWD/build-release/mac-icon-dist" \
  --architectures arm64 --jobs 3 --version 0.1.0
```

This is the actual Release/IPO-on, TCP/reverse-debug-off package. `lipo`
reports arm64; artifact verification passes with system-framework-only
linkage. Build log: `build/qual/mac-icon/release-build.log`.

`iconutil -c iconset` on the generated ICNS yields the ten standard files:
16, 32, 32, 64, 128, 256, 256, 512, 512 and **1024** physical pixels.
See `build/qual/mac-icon/icns-sizes.json`; Info.plist points to `TG2Recomp`.
The fully opaque master body measures exactly `(100,100)..(924,924)`.

Side-by-side PNGs (**TG2 left, Finder right; each icon at the named size**):

- `build/qual/mac-icon/comparison-1024.png` — 2048×1024.
- `build/qual/mac-icon/comparison-128.png` — 256×128.
- `build/qual/mac-icon/comparison-32.png` — 64×32.

Finder is exported through `NSWorkspace.icon(forFile:)` from
`/System/Library/CoreServices/Finder.app`, using its native IconServices
representations (which include 1024 and 2048), rather than enlarging the
256px maximum inside its legacy Finder.icns. The comparisons use the
running app's system-rendered icon; `comparison-packaged-*.png` also shows
the raw packaged derivative. IconServices adds its normal system appearance,
so its output is not expected to be byte-identical to raw ICNS pixels.

The packaged `.app` was launched twice with Cocoa and hidden windows using
the existing `LNG_SCRIPT` / `LNG_TEST_HIDDEN=1` facility: once directly into
the game and once into the real launcher. Both exited **0**. An external
Swift/AppKit check exported `NSRunningApplication(pid).icon` at 1024/128/32;
its representations include 1024/2048, the sharp original artwork and the
correct 824px body. Game and launcher exports are pixel-identical at all
three sizes. Logs, PNGs and helper script:
`build/qual/mac-icon/{check_running.py,export_system_icon.swift,
running-check.log,game-*,launcher-*}`. No desktop window was shown or raised.
This complements the compiled Apple code path, where the custom SDL icon
call is absent and the launcher path is NULL.

The Release binary also ran 360 frames with SDL dummy/software and both
widescreen and 60 fps off (exit **0**):

```
SDL_VIDEODRIVER=dummy SDL_RENDER_DRIVER=software SDL_AUDIODRIVER=dummy \
TG2_RACE_60FPS=0 <app>/Contents/MacOS/TG2Recomp ~/roms/genesis/tg2.bin \
  --no-launcher --turbo --max-frames 360 --widescreen off \
  --hash-frames 60 --fresh-evidence
```

Frame 60: **2A0B972960C5E325**; frame 300: **1131D937D70234FD**.
Dispatch/floor/interior/unsafe manifests: **0/0/0/0**, both after the game
launch and after the stock probe. Evidence: `build/qual/mac-icon/off.log`,
`off-manifests.json` and `game-evidence/`.

The ZIP was built before runtime tests wrote user data beside the staged
.app, then independently extracted and verified again: exit **0**, 24 files,
no ROM/generated code/debug output (`archive-verify.log`). Deliverable:
`build-release/mac-icon-dist/TG2Recomp-macos.zip`, SHA256
`998a72a98f5f53c943dbc6beff1442a9b9a5c039f46614697fe947a3926e5461`.

Not separately verified: a visual Dock/Cmd+Tab screenshot, universal2/Intel,
other macOS versions, or Windows/Linux execution. Those platforms' runtime
branch and assets are unchanged. Owner visual confirmation remains useful;
the launched-app icon API check is complete. Nothing was installed in
`/Applications`, and no CI/workflow/tag was triggered or changed.
