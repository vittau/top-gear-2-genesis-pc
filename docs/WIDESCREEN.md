# Top Gear 2 USA widescreen

Top Gear 2 races now render in an adaptive widescreen viewport: the road, its
rumble strips, the roadside scenery, the skyline and ordinary sprite actors
continue into the added margins, while the native 256-pixel image stays
byte-identical in the centre of every row with HUD: Centered. `Off` keeps the stock 4:3 renderer
untouched.

`game/tg2_video.c` implements this as a game-owned `GameVideo` provider. The
engine's VDP mode, guest raster lists, projection registers, collision state
and object activation are never changed. A fresh installation selects
`video_default = "fit"`; `game/tg2_options.c` describes the feature in the
shared launcher Mods page, which supplies the Off / Adaptive / fixed 16:9,
21:9, 32:9 choices and their persistence. `--widescreen off` always selects
the stock renderer.

## Why a game-owned renderer

TG2 draws the road with a **per-scanline raster program**, not with a camera
transform: `$004654..$00466A` copies self-modifying H-int code to `$FFF9FE`;
that code walks raster records through A5 (`$FF231E`, alternate
`$FF01E6`/`$FF2324`) and rewrites plane B's horizontal and vertical scroll,
VSRAM and CRAM on every line. The road renderers at `$007B00` / `$007CDC` /
`$007E70` only emit that per-line state (curve, hills, road width, marking and
rumble phase). There is no single "road X" variable a `[[widescreen_site]]`
injection could widen, and widening the guest camera would change collision
and the projection the game itself uses.

The sampled VDP state already contains the correct projection for *any* screen
column, so the renderer reproduces each output row from that row's live VDP
state, and extends the two depth planes sideways. Every row is independent:
hills and banked curves keep their per-line perspective in the margins.

`game/game.toml` therefore contains only three read-only `game_hook` sites
(`$0067EE`, `$00B5FA`, `$006982`), not scroll/projection injections.

## What each layer does

**Plane B — road and skyline.** Plane B is `$E000`, a 64×64 (512×512) name
table. Its atlas holds four perspective road sections in rows 0..431, a
separator, and the authored skyline panorama in rows 432..511.

- The road sections straddle the plane seam at X=0: the road's two halves
  meet across X=0/512, with the exterior ground around X=256. `road_x()`
  unwraps the road around the native view's centre so both halves of *one*
  road are sampled, and clamps to the atlas half-domain `[-256, 255]`.
  Margins therefore never show a second, wrapped road.
- Rows 432..511 are the skyline: they keep the plane's authored panorama wrap,
  so the skyline continues scrolling through the margins.
- Each row uses its own H-scroll (plane B register / VSRAM) and V-scroll, so
  the margin continues that exact scanline's perspective.

**Plane A — HUD, player car, special effects.** Plane A is `$C000` and holds
the HUD, the player car art and raster-positioned special effects. With HUD: Centered it is
carried through the exact native centre. HUD: Edges relocates only the HUD
cells and map markers; car art and effects keep their native positions.

**Sprites — opponent cars and roadside objects.** The game's mapper at
`$00B584` projects each object and then performs the native horizontal cull at
`$00B5FA` (`cmpi.w #$100,d3`, bytes `0C430100`). A read-only hook at that
address records the object's mapping pieces *before* the cull: unwrapped D1/D2
projection, D5 attributes, D6 width, the mapping header at A0 and the 8-byte
piece list at A1, applying the same vertical occlusion rules as
`$00B6F0..$00B7BE`. The native cull still runs unchanged for the guest's SAT.

The pieces are drawn only in the added columns, with live VRAM patterns and
CRAM palette, in the native reverse allocation order, and with plane-B
priority resolved exactly as the native compositor does (sprite high priority
always wins; low priority loses to a high-priority plane-B pixel). The player
car remains native. The whole native viewport remains native with HUD: Centered;
HUD: Edges changes only the classified HUD pixels.

Two further read-only hooks delimit a scene: `$0067EE` clears the capture at
the SAT allocator reset (`move.w #$7f,-$6130(a3)`), and `$006982` publishes it
after `$00B85E` has linked the SAT. A four-scene history is kept; the renderer
only uses the newest capture whose SAT bytes match the SAT actually present in
live VRAM at `$BE00`, so a captured actor is never painted over the next
frame's picture. The `tg2_video` debug command reports
`published`/`displayed` serials, matched pieces, margin pieces, sprite margin
pixels, overflow and the per-line scroll states.

Because the projection is screen-space linear and the viewport is grown
symmetrically, no projection change is needed: an actor at native X=274 or
X=-40 is the correct continuation of the same projection the native view uses.
Object activation, collision and the object pool are untouched — this widens
*presentation* (plus the pre-cull capture), not simulation.

## Modes and widths

- `off` — the engine's native renderer; no `tg2_video` row is touched.
- `16:9`, `21:9`, `32:9`, `W:H` — shared package fixed ratios.
- `fit` (Adaptive) — the drawable aspect from the window, clamped to the
  runner's 320-pixel minimum logical width and the 4096-pixel resource bound.

A 224-line 16:9 frame requests 398 pixels (71 extra per side) and 21:9
requests 523 (133/134 per side). Adaptive at a 1600×900 window gives 398, at
1234×567 gives 488, at 1000×1000 gives 320 (the runner minimum), at 3840×720
gives 1195.

Title, menus and shop screens are H40 (320×224) and are left at their native
size, centred with pillarbox bars. Split-screen is detected with the 2P flag
at `$FF189E` (`$0048B6`/`$006896` select single/split raster work) and stays
centred 4:3. The race qualifier also requires H32 without interlace, plane A
`$E000`, plane B `$C000`, a 0x11 plane-size register, and one of the race H-int
first opcodes (`$2C9D`, `$601E`, `$6042` at `$FFF9FE`).

## HUD

**Centered** is the default and preserves the existing widescreen pixels.
**Edges** places the speed/MPH, gear/AUTO, nitro and car icon at the left edge,
and the track map, LAP and position at the right edge, retaining each native
inset. The preference is exposed by `tg2_video_set_hud_mode(0|1)` and
`tg2_video_get_hud_mode()` in `game/tg2_video.h`; probes can select it with
`TG2_HUD_MODE=centered|edges`. It has no effect with widescreen Off, in menus
or in split-screen. The options UI can call the setter without resetting the
renderer; resets and state loads retain the presentation preference.

Read-only TCP name-table/SAT dumps and per-line raster snapshots establish:

| Content | Displayed source | Ownership |
|---|---|---|
| Left instruments | Plane A `$C000`, cells in columns 2..8, rows 0..9 | High-priority pattern IDs `$0004..$003C` |
| Map, LAP, position | Plane A, columns 22..29, rows 0..9 | High-priority pattern IDs `$003D..$0084` |
| Map's player/leader markers | Displayed SAT `$BE00` | 2×2 sprites, first patterns `$0106` and `$010E` |
| Window | Inactive over the race HUD | No HUD content |

All 129 instrument cells occur exactly once in the name table at baseline
frames 2800, 3300 and 4501. Their identities remain fixed while the guest
updates their pattern data: `$00F5F8` converts speed, `$00F71E` selects the lap,
and `$00F79A` prepares changed pattern DMA sources. `$00FE8A` positions the
map marker templates at `$FF8B76/$FF8B7E`; `$00F468` copies them to the SAT.
The markers bypass the scenery mapper and therefore need their own displayed
SAT read in addition to the existing pre-cull scenery capture.

The renderer classifies the live name-table cells by these pattern IDs,
rather than cutting fixed rectangles from the framebuffer. Each row uses its
actual plane-A H-scroll and V-scroll; the HUD appears at screen row 14 even
though it starts at name-table row 0, and the raster switches to other cells
above and below it. Classification also requires the signed-negative plane-A
V-scroll phase: the initial black band briefly samples some HUD cells with
nonnegative V-scroll and a different palette, and remains unchanged. Each opaque HUD pixel moves by the corresponding margin
width (71/71 at 16:9, 133/134 at 21:9). The asymmetric right margin is handled
explicitly, so odd-width canvases preserve the right inset exactly.

Vacated opaque pixels are recomposed from the current plane B, non-HUD plane
A and ordinary SAT sprites, with native layer priority. Transparent HUD pixels
do not overwrite the scene. The two map marker sprites move with the right
cluster, sampling the displayed SAT and current patterns on every scanline.
There are no guest RAM/VRAM writes, new function seeds or engine changes.
`tg2_video` reports `hud_edges`, `hud_plane_pixels` and `hud_marker_pixels`.

## Off-mode guarantees

With `--widescreen off` (or the mod turned off) the provider's width and row
callbacks are never entered: `game_video_prepare_frame` leaves the frame
unowned and the runner presents the native image. The measured stock hashes
are unchanged (frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`).

For the widened modes with HUD: Centered the native centre is copied from
the original row after the margins are filled, so the canonical RAM, VRAM and native-centre pixels are
byte-identical to the Off run at every comparison frame (2800, 3300, 4501 and
the menu frames 600/1350).

## Measured evidence

Produced by `tools/verify_widescreen.py --port 4400 --modes off,16:9,21:9`
(native release build, headless SDL dummy video/audio). Artifacts are under
`build/ws/{off,16-9,21-9}/`:

| Check | Result |
|---|---|
| Off frame hashes | frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD` |
| Race screenshots | `frame-2800.png`, `frame-3300.png`, `frame-4501.png` in each mode (16:9 = 398×224, 21:9 = 523×224, Off = 256×224) |
| Menus | `frame-600.png`, `frame-1350.png`: 320-pixel native image centred with bars |
| Adaptive widths | 398 / 488 / 320 / 1195 from 1600×900 / 1234×567 / 1000×1000 / 3840×720, 256 after a live switch to Off (`adaptive-*.png`) |
| Sprite capture | up to 29 captured pieces per scene, up to 6 pieces reaching a margin, up to 1982 margin sprite pixels in a frame, 0 overflow; every captured scene matched live SAT bytes |
| Canonical state | RAM and VRAM dumps identical to Off at 600, 1350, 2800, 3300, 4501 |
| Native centre | pixel-identical to Off at the same frames |
| Discovery | `dispatch_misses.toml`, `floor_coverage.toml`, `interior_label_misses.toml`, `floor_unsafe.toml` all report 0 entries after each route |

`margin-*.png` frames show actors and roadside objects crossing the old
256-pixel edge: `16-9/margin-3220.png` has an opponent car straddling the
right boundary and a tree in the left margin, and `21-9/margin-3221.png` shows
the same car wholly inside the right margin with the tree further out in the
left margin.

## HUD validation

`tools/verify_hud.py` replays the same baseline input on **port 4460** using
headless SDL, read-only TCP queries and exact-frame input-script captures.
`--record-baseline` records Centered with the pre-change renderer; after
rebuilding, a normal invocation captures and compares both placements.
`--check-only` validates the saved artifacts without launching another game.
The implementation build (`JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin
build`) and final verification both exited 0.

Artifacts remain under `build/hud/` and are excluded from git:

| Evidence | Result / path |
|---|---|
| Off, both HUD preferences | Frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`; captured pixels, RAM and VRAM identical |
| Centered compatibility | All 75 full-frame hashes at 60-frame intervals match the pre-change renderer in each ratio; all nine PNGs match exactly |
| Required 16:9 PNGs | `{centered,edges}-16-9/frame-{2800,3300,4501}.png`, 398×224 |
| Required 21:9 PNGs | `{centered,edges}-21-9/frame-{2800,3300,4501}.png`, 523×224 |
| Consecutive 60 fps PNGs | `fps60-edges/frame-4510.png` through `frame-4515.png`, with Centered counterparts; six distinct pictures in each run |
| HUD translation | Every opaque HUD/marker pixel matches its Centered source at exactly the left/right margin offset at all nine samples in each pair |
| Vacated HUD positions | Match the independent uncovered sky column; no residual HUD pixels |
| Other raster rows | Rows 0..13 and 94..223 identical, including the initial black-band artefacts and all road/car pixels |
| Guest state | RAM and VRAM byte-identical between Centered and Edges at every capture, including 60 fps |
| Discovery | All four manifests report 0 entries after every completed route |
| Machine-readable results | `summary.json`, per-mode `stderr.log`, `state-*.json`, and copied manifests |

The first comparison exposed a one-row change in the top black band because
its transitional raster state samples HUD pattern IDs. Requiring the HUD's
signed-negative V-scroll phase fixes that classification without a fixed
screen rectangle; the corrected captures preserve those top rows exactly.

The options-page row is intentionally left for integration with task 06:
that plumbing was not yet in `origin/main` when this branch was completed.
The setter/getter and environment selection are ready for it; this branch
adds no overlapping settings implementation. Coverage remains the baseline
single-player first track; the additional tracks and conditions listed below
have not been qualified by this HUD probe.

## Known artefacts and limitations

- **Plane-A special effects are not extended.** Objects the game rasterises
  through plane A (rather than the sprite mapper) are visible only where they
  fall inside the native centre. Ordinary actors and roadside objects are
  covered by the sprite capture; plane-A scenery is not.
- **Actors that never reach the mapper are not recovered.** An object culled
  by game logic before `$00B5FA` has no captured mapping. This was not
  observed for opponents on the baseline route, but it is the capture's
  boundary.
- **Extreme aspect ratios flatten the far exterior.** Beyond the road atlas
  half-domain the exterior ground column is clamped (a flat band) rather than
  invented. Visible at 4K-ultrawide widths (e.g. `adaptive-1195.png`), not at
  16:9 or 21:9.
- **Adaptive in a narrow window keeps 320 logical pixels.** The runner's
  frame preparation always reports a 320-pixel native width, so a window
  narrower than 16:10 leaves small pillarbox bars around the 256-pixel race
  image instead of shrinking to it.
- **The skyline panorama wraps.** It is an authored repeating background; its
  wrap is retained rather than synthesised.
- The game's own black bottom rows remain native pixels. HUD: Edges samples
  each row's live raster state; the existing non-HUD plane-A limitations remain.

## Still untested

The route covers the first track, dry daylight, single player, one car and
partial throttle. Not covered: other tracks (their plane-B atlas layouts may
differ), rain and night, the finish/podium sequence, attract mode, full-race
completion, split-screen 2P (intentionally left 4:3), LM/head-to-head,
controller-only launcher operation, Windows/macOS/Steam Deck builds, and
physical display/audio. Network session configuration was not part of this
work.

## Reproduction

```sh
JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build
build/analysis-venv/bin/python tools/verify_widescreen.py --port 4400
```

Probes launch `build/TG2Recomp` directly, so they must not inherit the host's
`$APPIMAGE`: the runner anchors `debug.ini`, saves and evidence beside
`$APPIMAGE` when it is set, which would move the TCP server away from the
build directory. Both project probe tools strip `APPIMAGE` explicitly. The
tool needs Pillow (present in `build/analysis-venv`), writes only under
`build/`, and uses port 4400; the output stays out of git.
