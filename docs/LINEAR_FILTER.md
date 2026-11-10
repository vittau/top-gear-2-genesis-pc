# Linear filtering at the valid picture boundary

The original boundary fix was implemented on `vittau/tg2-rain-widescreen`.
Engine patch `0025-linear-filter-picture-bounds.patch` owns this change;
`game/tg2_video.c` and generated code are unchanged.

## Cause and fix

The runner allocated its CPU presentation texture at framebuffer capacity
(initially the native stride × maximum height), and only supplied an active
source rectangle to `SDL_RenderCopy`. Custom widescreen allocation also grows
and retains its largest width. After overscan cropping a race is only 200
rows high, while the texture still contains its full allocation and leftover
rows. Width reductions and H32/H40 transitions similarly leave unused columns.
Uploading the full allocation for linear mode refreshed those pixels but did
not make them valid picture pixels.

SDL's Metal renderer uses normalized texture coordinates and a sampler that
clamps at the **texture** boundary, not the source rectangle. The Metal SDK's
`MTLSampler.h` documents ClampToEdge as the default S/T address mode; SDL
`SDL_render_metal.m` only changes the nearest/linear min/mag filters. Hence
a bilinear footprint at the active right/bottom edge can include unused
pixels inside the allocation. The software SDL renderer crops/scales the
source rectangle and did not reproduce the artefact.

The linear CPU path now uploads into a cached streaming texture whose width
and height are exactly the active picture. A dimension change recreates it;
rows are uploaded with the real source pitch. This makes the hardware clamp
boundary coincide with the picture boundary, without padding guesses. The
nearest path retains its original texture and upload. The same helper serves
high-refresh CPU interpolation and the cached image serves the state menu's
background. The existing HD-GPU output and peer-view textures are already
exact-sized and bypass this CPU conversion.

## Default preference

`app_config_defaults()` initializes `linear_filter = 0`. The launcher receives
that value in `RecompLauncherCSettings`; its Genesis profile's `linear_filter=1`
entry is a **capability**, not a default. Launcher settings loading only
updates keys that exist. Game defaults/mod migrations only set game options,
not this filter. Runtime UI reads/writes the same `g_app_config` field; its
bool descriptor's `0,1,1` arguments mean min/max/step, not default On. There
is no separate Graphics reset default in that menu. Release verification
rejects `settings.ini` and `rom.cfg` in payloads, so a payload does not ship a
saved On choice.

The texture creation now explicitly applies the saved preference through
`SDL_SetTextureScaleMode`, instead of accepting an ambient
`SDL_RENDER_SCALE_QUALITY` hint as the actual mode. Missing settings stay Off;
an explicit user's On value stays On. No existing preference is migrated or
rewritten to Off.

## Capture method

Guest screenshots do not show the final filter. The patch adds opt-in
`GENESIS_WINDOW_CAPTURE_FRAMES=1400,1490,...` and
`GENESIS_WINDOW_CAPTURE_PREFIX=/absolute/path/window` diagnostics. They read
SDL's rendered output after the final game copy, before Present, and include
window scaling and bars; ordinary screenshots/hashes are unchanged.

The exact controller route from `game/baseline-route.json` is replayed with
16 capture points: menu and race × Off/16:9/Adaptive/21:9 × integer/fractional
window scale. Windows are 640×448 for menu integer (the H32 menu's 512×448
picture plus bars), 2× the active race picture for race integer, and 777×503
for fractional. Each mode/size is selected 30 guest frames before its capture.
Software uses SDL dummy; Metal uses Cocoa with `LNG_SCRIPT=0 LNG_TEST_HIDDEN=1`
(the existing hidden-window test facility), without showing a desktop window.
Private scripts, captures and logs live in `build/qual/linear/` and
`build/qual/linear-metal/`.

## Results (macOS arm64)

- All eight successful matrix processes (before/after × linear/nearest ×
  software/Metal) exited 0 and left dispatch/floor/interior/unsafe manifests
  at **0/0/0/0**. Each produced all 16 requested window captures.
- **Nearest:** all 16 software pairs and all 16 Metal pairs are byte-identical
  as PNG file bytes, for both menu and race, all four view modes, and both
  window scales. Software linear pairs are also identical (that backend
  already crops its source before filtering).
- **Metal linear:** reproduced edge contamination in all eight race cases
  (Off, 16:9, Adaptive, 21:9 at integer and fractional scales) and in the
  later menu cases after the texture had grown. Earlier menu cases with no
  contaminated allocation are unchanged, apart from at most 1–2 levels of
  GPU texture-coordinate rounding. The representative fractional native
  race has 403 pixel differences above two colour levels, **all on the
  right/bottom picture edge**. The menu example has 406 such differences,
  all on its bottom row. There are 82 common recorded guest-frame hashes
  between the Metal linear runs, all identical: only final sampling changes.
- Fresh-run tests removed `settings.ini`, opened Graphics, and toggled the
  selected filter twice to return to its original value while exercising
  the real settings writer: the new file contains `linear_filter = 0`.
  Repeating with the ambient SDL linear hint still writes 0 and produces
  identical output. Starting with an explicit saved 1 retains 1. Each run
  exited 0 with 0/0/0/0 manifests; captures/settings/check JSON are in
  `build/qual/linear/{fresh,fresh-hint,explicit-on}/`.
- `TG2_RACE_60FPS=0 python3 tools/probe_run.py --exe build/TG2Recomp
  --out build/qual/linear/off --frames 360 --port 4620 --widescreen off
  --shots 300` exited **0**: frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD`; manifests 0/0/0/0.
- Capture instrumentation build, fixed build, and a clean patch-set
  application/rebuild all exited 0, under the heavy lock with `-j3`.
  Logs: `/tmp/linear-{capture-build,fix-build,patch-build}.log`.

Full presented race (before / after):

![Before](images/linear-race-before.png)
![After](images/linear-race-after.png)

Ten-times nearest zooms, **before left / after right**, from the actual
presented captures (no generated pixels or repainting):

![Race corner](images/linear-race-corner-before-after.png)
![Menu corner](images/linear-menu-corner-before-after.png)

Evidence: `build/qual/linear/{probe.log,probe-rest.log,metal-probe.log,
metal-nearest.log,fresh.log,off.log}`, the paired PNG directories, and
`build/qual/linear-metal/linear-comparison.json`. Probe scripts are copied
into `build/qual/linear/{probe,metal-probe,fresh-probe}.py`.

Not separately exercised: Windows/Linux GPU drivers, the generic engine's
HD-GPU and high-refresh interpolation paths, netplay peer view, and a live
owner play session. TG2 hides internal resolution because its game renderer
does not use that generic HD path. Launcher defaults and payload/reset
behaviour were traced in source; the actual fresh-config write was exercised
through recomp-ui in the running game, rather than an interactive launcher
session. No CI or workflow was triggered or modified.

Final clean replay of the committed patch: `tools/apply-engine-patches.sh
--reset` and `flock ~/.cache/tg2-heavy.lock cmake --build build --target
TG2Recomp -j3` exited 0 (`/tmp/linear-final-build.log`); repeating the stock
probe under `build/qual/linear/final-off/` exited 0 with both required hashes
and 0/0/0/0 manifests. Temporary engine/core keep refs preserve the applied
working trees from before the clean validation; no submodule pin changed.

## S3: a correct final sampler can have no visible effect

The owner reported that the `deck-s3-20261110` extracted tarball filters the
main menu but no longer visibly filters races. His internal scale and toggle
sequence were not supplied. The draft's source remains `a205759`; this
investigation does not relabel that draft or establish its exact Deck GPU state.

A fresh current-main build was tested using the draft's pinned **SDL2 2.28.5**,
hidden Cocoa/Metal windows, and the exact controller route in
`game/baseline-route.json`. These are final SDL output captures at guest frames
1350 (native menu) and 3300 (1P race), not guest screenshots.

| Output / internal scale | Menu pixels changed by On | Race pixels changed by On |
|---|---:|---:|
| 1280×800 / 1× | 125,411 | 175,807 |
| 1280×800 / 2× | 125,411 | 93,205 |
| 1280×800 / 4× | 125,411 | **0** |
| 777×503 / 4× | 50,485 | 17,947 |

Each On/Off pair has 55 common guest framebuffer samples with identical
geometry/hashes. At 4× / 1280×800 the active race source is 1280×800 and the
Linear On texture is exactly 1280×800. Renderer scale is 1, saved/active filter
are both 1, and `SDL_GetTextureScaleMode` reports Linear. Off reports Nearest
and uses the same active source in its retained capacity texture. Every final
output pixel matches at 1:1. Fractional output restores a visible difference;
the 777×503 case samples the same source at approximately 0.607× with bars.

The first differing menu pixel in the Deck-sized pair is (328,27), the 1× race
pair (302,22), and the 2× race pair (303,23). There is no first divergence in
the 4× race pair. A real controller Off→On change before the route saves
`linear_filter=1` and produces exactly the saved-On menu and race captures,
with all 55 guest hashes matching. Texture growth/recreation, active picture
bounds, pitch, saved value and live sampler were checked. The active-boundary
fix in patch 0025 remains intact.

The first relevant difference from native rendering is upstream of SDL:
`render_scanline()` in `game/tg2_video.c` nearest-expands the native art into N
columns, and `tg2_highres_build()` duplicates rows before repainting smooth
road runs. This is the accepted S3 contract in HIGHRES.md §§8/9/13. A final
bilinear sampler at 1:1 samples texel centres and cannot undo that expansion.
At 2× it only softens boundaries over the final high-resolution texel footprint.

No broken sampler or lost preference was found in the pinned SDL tests.
Changing Linear On to smooth native art inside S3 needs a visual-policy
decision first: it would override the existing nearest art/HUD behavior while
On. The scoped proposal is to use the existing toggle for RGB interpolation
of native art during game-owned S3 composition, retain coverage/priority
against the independently rendered road, and leave Linear Off byte-identical.
It adds no setting and does not downscale the high-resolution road. The
coordinator approved that opt-in scope after reviewing this evidence; the
implementation and qualification follow below.

Pre-fix reproduction at commit `9534ac8` (all commands under `flock ~/.cache/tg2-heavy.lock`; builds `-j3`):

```sh
cmake -S . -B build -DTG2_SDL_SOURCE=/path/to/SDL2-2.28.5
cmake --build build --target TG2Recomp -j3
build/venv/bin/python tools/check_linear_filter.py --backend metal --scales 4 --live --out build/linear-s3/pinned-metal4
build/venv/bin/python tools/check_linear_filter.py --backend metal --scales 1,2 --uncapped --out build/linear-s3/pinned-metal12
build/venv/bin/python tools/check_linear_filter.py --backend metal --scales 4 --size 777x503 --uncapped --out build/linear-s3/pinned-metal-fractional
```

The tool restores the scratch build's settings file. Use `--backend software`
for a dummy-video check. Patch `0052` adds JSON sidecars to the opt-in final
captures: renderer, output/logical/viewport geometry, scale, texture/source
sizes, pitch and saved/active/sampler values. Capture pairs and sidecars live
under the named directories; `summary.json` records differences and manifests.
The real menu paths are now **VIDEO → Linear filter** and **VIDEO → Internal
resolution (restart)**; the earlier Graphics references above describe the
historical boundary-fix validation.

A preliminary development build used Homebrew **sdl2-compat 2.32.74** and showed
incorrect viewport sizing after S3 growth. Those small-picture captures were
rejected as draft qualification. Rebuilding with pinned SDL2 produced the
correct viewport. No compatibility-layer workaround was added. Metal evidence
is from this Mac; Steam Deck/Linux GPU behavior and the owner's exact settings
still require confirmation.


## S3 native-art filtering with the existing toggle

Linear On now bilinearly samples native RGB during game-owned N× composition.
The native artwork keeps its original detail, positions and integer-N× size;
there is no LOD promotion, independent filter preference, or S4 implementation.
Linear Off retains the accepted nearest expansion and road renderer. Default
Off and the saved `linear_filter` key are unchanged; the filter is live, while
Internal resolution still applies on restart.

The game reuses `GameVideo`'s immutable presented-raster seam. The native
foreground mask follows the actual Genesis winner (high sprite, high A, high
B, low sprite, low A, low B), rather than comparing RGB colours. Game-owned
weather, window/tunnel margins, extra sprites and HUD relocation update the
same mask when they write a pixel. This preserves an opaque overlay even if
its RGB happens to equal the road. The temporal path captures the selected
presented snapshot's layers, rather than mixing a current-tick mask with old
artwork. Sprite/status evaluation on the live machine is still performed once.

The analytic road is rendered as an underlay. Native RGB is interpolated with
premultiplied binary coverage and composited over it. A footprint with no native
foreground leaves the road pixel untouched. Non-road rows use ordinary native
RGB interpolation. Sampling clamps to the active native picture, including the
overscan-cropped top/bottom boundary, so excluded bands do not bleed into it.
All of this code lives in `game/`; no new framework rendering patch was needed.

Pinned SDL2 2.28.5, hidden Metal, same frame 3300 at 4× / 1280×800:

- On now changes **124,690** final pixels (121,293 by more than two levels),
  mean maximum-channel difference 3.70066/255; first change at **(302,22)**.
- Off's 55 recorded geometry/hash samples match the pre-fix Off launch, and
  both final menu/race captures retain its appearance.
- A real controller toggle during the race completes at frame 2883, saves On,
  and yields exactly the saved-On frame-3300 final presentation. Native menus
  retain their existing final-SDL filtering behavior.
- The coverage PGM identifies **256,928** output pixels with no native-art
  footprint; **zero** of those road pixels differ between On and Off.
- Both saved-On and live-On report zero incomplete coverage frames. All three
  runtime processes exit 0 with all four execution manifests empty.

Evidence: `build/linear-s3/fixed-metal4/summary.json`, paired final window PNGs
and sampler JSON; `build/linear-s3/final-mask/summary.json` and
`s4-on/native-coverage-3300.pgm`. Use the current probe with
`--native-art-filter`; On's game-owned sampling now intentionally changes N×
guest framebuffer RGB, whereas final SDL sampling alone still does not.
`--live --live-frame 2800` exercises the toggle in the race before the route
accelerates. `--uncapped` retains rendering/audio work while disabling pacing.

Geometry checks distinguish the analytic road from the filtered artwork. N×
road audit records measure the underlay before overlay composition when Linear
On is enabled; the independent coverage comparison checks the finished output.
The downscale check compares Linear On against a native RGB reference sampled
with the same bilinear policy, keeping the original numeric tolerances. Off
continues to use the unfiltered native reference. A first driven On check used
the old unfiltered reference and returned 1 for its intentional RGB blur; its
road/margin audits and manifests already passed. Reanalysis of the nine retained
same-frame pairs with the correct Linear On reference passes (mean 0.558–1.367,
maximum fraction above 64 is 0.017%). No track matrix was repeated to replace
that valid capture evidence.

Local builder cost in that driven 4× On case is approximately **8.29 ms/frame**,
including native-art filtering and audit-enabled wall timing on this Mac.
This is not directly comparable with the earlier isolated no-audit CPU cost. Extra native
RGB/coverage storage is about 4.4 MiB and is host presentation data. This is
not a Steam Deck performance measurement. The owner must verify the resulting
look and performance in a new candidate built from the new source revision;
the old draft remains unchanged.

Final focused guards (all runtime manifests 0/0/0/0):

| Guard | Result |
|---|---|
| 2× / 1280×800, saved Off/On | Probe exit 0; 178,272 race pixels differ; Off retains 55/55 pre-fix hashes |
| 4× / 777×503, saved Off/On | Probe exit 0; 55,751 race pixels differ |
| HUD Edges, 4× / 1280×800 | Probe exit 0; correct shifted clusters; zero uncovered-road differences and incomplete masks |
| Guest RAM at frame 3300 (2×, fractional 4× and HUD Edges) | Off/On SHA-256 identical: `da75a309e6360f5984b8d2314ddec39f1155bb63eecd30c2eb312f477d7e279d` |
| Auckland 4× On, 1,800 driven frames | Runtime exit 0; 2,240 audited pictures; road/margins pass; nine retained Linear On reference pairs pass reanalysis |
| Bavaria rain 4× On, 600 driven frames | Probe exit 0; 1,045 audited pictures; road/margins/downscale pass; zero incomplete coverage frames |
| Auckland 4× On + 60 fps, 300 driven frames | Probe exit 0; 742 audited pictures; road/margins/downscale pass; zero incomplete coverage frames |
| 32:9 native 2P, requested scale 1× vs 4×, Linear On | 4,500/4,500 hashes equal, always 796×224; 445 observed active-race samples |
| Final stock 1× / widescreen Off / 60-fps Off, 360 frames | Probe exit 0; `60=2A0B972960C5E325`, `300=1131D937D70234FD` |

The 2P baseline engine completed normally, but its local poller hit server
shutdown before saving its summary. Its complete 4,500 hashes and empty
manifests were retained; the corrected scale-4 runner exited 0 and completed
the paired comparison. This poller error is not hidden as a successful script
exit. Auckland's unfiltered-reference failure and subsequent reanalysis are
likewise retained separately.

The Auckland pictures include the tunnel wall/opening approach
(`fixed-drive/drive/auckland-scale4/frame-9335.png`) and its same-frame native
reference; native priority/coverage comes from the displayed raster. This
focused pass is not a full tunnel traversal/track matrix. Rain and temporal
cases cover their respective overlay/capture paths. The underlay audits total
4,027 pictures and 1,016,488 measured sub-rows, with zero geometry/gap/stripe/
margin violations; maximum stripe-centre error is 0.4961 output pixel.

Exact commands, exit handling and consolidated JSON are in
`build/linear-s3/worker-report.md` and `final-evidence.json`; the reusable final
presentation probe is `tools/check_linear_filter.py`. No CI, new draft/tag,
release, ROM-derived git artifact, or submodule pin update was made. Windows,
Linux/Deck GPU drivers, owner visual acceptance and device performance remain
unverified for this fix.
