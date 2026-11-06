# Top Gear 2 USA widescreen

Top Gear 2 races now render in an adaptive widescreen viewport: the road, its
rumble strips, the roadside scenery, the skyline and ordinary sprite actors
continue into the added margins, while the native 256-pixel image stays
byte-identical in the centre of every row with HUD: Centered. `Off` keeps the stock 4:3 renderer
untouched.

`game/tg2_video.c` implements this as a game-owned `GameVideo` provider. The
engine's VDP mode, guest raster lists, projection registers, collision state
and object activation are never changed. A fresh installation selects
`video_default = "fit"` (Adaptive); the shared launcher Mods page supplies the
Off / Adaptive / fixed 16:9, 21:9, 32:9 choices and persists them in
`settings.ini` next to the executable as `[mods.widescreen] enabled` and
`aspect`. The same pages offer **HUD** placement and **Hide overscan**
(default On); both persist as `[mods.hud] placement` and `[mods.overscan]
hidden`. The in-game recomp-ui overlay edits the same values. `--widescreen
off` always selects the stock renderer.

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
table. Its atlas holds four perspective road sections in rows 0..431,
ground/separator rows 432..447, and the authored skyline panorama in rows
448..511.

- The road sections straddle the plane seam at X=0: the road's two halves
  meet across X=0/512, with the exterior ground around X=256. `road_x()`
  unwraps the road around the native view's centre so both halves of *one*
  road are sampled, and clamps to the atlas half-domain `[-256, 255]`.
  Margins therefore never show a second, wrapped road.
- Rows 448..511 are the skyline: they keep the plane's authored panorama wrap,
  so the skyline continues scrolling through the margins.
- Rows 432..447 are ground/separators, not panorama. Rows 432..439
  contain solid ground; rows 440..441 have grass in atlas X=256..511 and
  transparent tiles in X=0..255. Hills can repeat these rows across many
  output lines between the water and the road. Each margin continues its
  native edge sample on these rows, so it cannot wrap from grass into the
  transparent half and expose the black backdrop. Colours still come from
  that exact output line's CRAM, preserving the raster grass shades. On a
  synthesized 60 fps picture these rows take their scroll from the same
  discrete source picture as their atlas Y, for the reason described under
  [Motion-only synthesized black lines](#motion-only-synthesized-black-lines).
- Each row uses its own H-scroll (plane B register / VSRAM) and V-scroll, so
  the margin continues that exact scanline's perspective.

**Plane A — HUD, player car, special effects.** Plane A is `$C000` and holds
the HUD, the player car art and raster-positioned special effects, including
the Auckland tunnel wall. With HUD: Centered it is carried through the exact
native centre. HUD: Edges relocates only the HUD cells and map markers; car
art and effects keep their native positions. When an opaque high-priority
plane-A texel is the displayed native edge pixel, its colour continues through
that margin row to the screen edge, so a tunnel wall never exposes the
plane-B scenery it hides (see below).

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
inset. The player chooses it on the launcher's Mods page ("HUD at edges") or
the in-game overlay's Mods section ("HUD"); both persist the same value in
`settings.ini` as:

```ini
[mods.hud]
placement = centered   ; or edges
```

The renderer applies it through `tg2_video_set_hud_mode(0|1)` /
`tg2_video_get_hud_mode()` in `game/tg2_video.h` without resetting the scene;
probes can force it with `TG2_HUD_MODE=centered|edges`. It has no effect with
widescreen Off, in menus or in split-screen. Resets and state loads retain the
presentation preference.

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
V-scroll phase: the initial window band hides plane A, whose nonnegative
V-scroll can point at HUD cells behind that window; those hidden cells must
not be relocated. The window band remains unchanged. Each opaque HUD pixel
moves by the corresponding margin width (71/71 at 16:9, 133/134 at 21:9). The asymmetric right margin is handled
explicitly, so odd-width canvases preserve the right inset exactly.

Vacated opaque pixels are recomposed from the current plane B, non-HUD plane
A and ordinary SAT sprites, with native layer priority. Transparent HUD pixels
do not overwrite the scene. The two map marker sprites move with the right
cluster, sampling the displayed SAT and current patterns on every scanline.
There are no guest RAM/VRAM writes, new function seeds or engine changes.
`tg2_video` reports `hud_edges`, `hud_plane_pixels` and `hud_marker_pixels`.

## Hide overscan

The stock top eight rows are the VDP window plane: solid black except for the
red/orange pattern-0 marks at native x=16..31 (see
[Native red/orange top band](#native-redorange-top-band)). A CRT hid that band
in overscan; on a modern display it is visible above the HUD.

**Hide overscan** (default **On**) blanks the active top window band rows in
every mode, including widescreen Off. It is a presentation option only: guest
RAM, VRAM, CRAM and simulation are untouched, and an inactive window (menus)
keeps its rows. With it Off the image is byte-identical to before the option
existed.

The option is a normal `[mods.*]` boolean, offered by the launcher's Mods page
and the in-game recomp-ui overlay and persisted next to the executable
(`build/task13/options/`: launcher detail, overlay row, and the overlay after
toggling it Off, which writes `hidden = 0`):

```ini
[mods.overscan]
hidden = 1
```

`TG2_HIDE_OVERSCAN=0|1` is a probe-only override and is never persisted.
`tg2_video` reports `hide_overscan` in its status JSON.

Measured at race frame 3300: with Hide overscan Off the 4:3 image shows the
stock red marks at x=16..31, rows 0..7; with it On those 56 pixels are black.
The 16:9 image is identical at x=87..102 (the 71-pixel origin) and shows the
same result. **No other pixel changes**; the difference bounding box is exactly
the mark area. Crops: `build/task13/overscan/crop-{4-3,16-9}.png`, full frames
alongside them. With all options off (widescreen Off, 60 fps Off, Hide overscan
Off) the stock hashes still pass: frame 60 `2A0B972960C5E325`, frame 300
`1131D937D70234FD` (`build/task13/hashes.txt`).

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
our sampler found HUD pattern IDs in plane A behind the active window.
Requiring the HUD's signed-negative V-scroll phase fixes that classification without a fixed
screen rectangle; the corrected captures preserve those top rows exactly.

The options-page row is intentionally left for integration with task 06:
that plumbing was not yet in `origin/main` when this branch was completed.
The setter/getter and environment selection are ready for it; this branch
adds no overlapping settings implementation. Coverage remains the baseline
single-player first track; the additional tracks and conditions listed below
have not been qualified by this HUD probe.

### Native red/orange top band

The red/orange marks in rows 0..7 are **window-plane pixels**, separate from
the HUD and from the sprite/object pool. They are already present in stock.
Race VDP setup `$002520` selects window base `$0000` (`$00254E`, register 3),
left boundary 0 (`$00260A`, register 17 = 0) and top window height 8
(`$002618`, register 18 = 1). Thus the window replaces plane A across the
first eight rows, while the actual HUD starts below it.

`$002628..$00263E` initializes the first 32 VRAM words to `$8003`, selecting
the high-priority solid-black pattern 3. The displayed dumps have window
cells 2 and 3 (VRAM `$0004/$0006`) equal to zero, selecting pattern 0. That
pattern aliases the same low VRAM words: `$80038003` decodes as nibbles
`8,0,0,3,8,0,0,3`, while its row 1 is zero. Palette-0 entry 8 is `$000C`
(red RGB 206/0/0), and entry 3 is `$024C` (orange 206/87/49). This accounts
for all 56 colored pixels in columns 16..31, rows 0 and 2..7. No displayed
SAT sprite intersects rows 0..7. The exact source of the later zeroed two
name-table cells was not traced; the displayed layer, patterns and colors
are established directly by the dumps and per-line palette snapshots.

At baseline frame 4501 (also checked at 2800 and 3300):

| Mode | Native origin | Red/orange columns, inclusive |
|---|---:|---:|
| Off, 256 pixels | 0 | 16..31 |
| 16:9 Centered or Edges, 398 pixels | 71 | 87..102 |
| 21:9 Centered or Edges, 523 pixels | 133 | 149..164 |

The apparent x≈88 element is already shifted by the 71-pixel margin;
x≈88 is **not** its native coordinate. Its position is correct in both HUD
modes. The entire eight-row native band matches stock after subtracting each
margin, and the investigation's read-only diagnostics leave all captured
full images unchanged. Off hashes remain frame 60 `2A0B972960C5E325`, frame
300 `1131D937D70234FD`; all four manifests remain empty in every new run.
No presentation-position change was needed.

`tg2_video` with `{"top":1}` now returns the live registers, first two VSRAM
words and CRAM for each of the first eight scanlines. The read-only snapshots
also cover rows that do not qualify for margin extension, avoiding stale
scroll-only observations. `tools/analyze_top_band.py` checks the source
texels, offsets, complete native bands and unchanged before/after images.
Its artifacts are under `build/hud/top-band/`: `stock-top.png`,
`before-after-{centered,edges}-{16-9,21-9}.png`, and `top-band-summary.json`.
The before/after crops are identical because this follow-up adds diagnostics
and evidence, without changing rendering. The route capture command and its
logs are retained alongside those artifacts in `capture.py`/`capture.log`.

### Solid window and backdrop margin bands

The top window spans native rows 0..7, but the earlier margin compositor
sampled plane B on row 0 and exposed grey/green scenery beside the black
native window. Solid, opaque high-priority window edges now continue their
native colour through the margins. The native centre, including its existing
red/orange window pixels, is preserved. Low-priority margin sprites respect
the window priority; high-priority sprites retain the native compositor order.

Classification uses each row's live window registers and unscrolled H32
window name table. All eight native edge pixels must have one colour, and
all eight window texels must be opaque, high priority, and match that displayed
colour. Transparent windows and nonuniform panorama detail retain ordinary
scenery continuation. There is no hard-coded row-0 colour or fixed black fill.

The margin CSV also exports `edge_solid`, `window_band` and `backdrop_band`.
The checker counts `band_colour_violations` whenever an adjacent margin differs
from the native edge of a qualified solid window/backdrop band, including the
reverse of a black gap: coloured pixels leaking beside a black native band.
Qualified window edges are excluded from the ground/black-gap rules, whose
plane-B samples are hidden behind the window.
Backdrop qualification requires a uniform eight-column edge matching the
backdrop colour with transparent underlying planes (or disabled display).
Scenery pixels are still checked before sprite/HUD occlusion, so legitimate
actors and panorama details are not treated as band errors.

The extended check fails the pre-window-fix 16:9 / Edges / 60 fps On route
with **5838 band-colour violations**, while the existing black-gap and ground
counters stay 0 (`build/hills/window-before-check.json`, expected exit 1).
After correction, all **eight** 16:9/21:9 × Centered/Edges × 60 fps Off/On
combinations pass with **0 band-colour, 0 black-gap and 0 ground-colour
violations**. Each covers 2933 complete frames and 1,313,984 edge samples;
the total is **10,511,872**, including **989,012 qualified solid-band
samples** (123,600 per Off combination, 123,653 per On combination).
`build/hills/window-matrix.json` and `window-results.json` retain the counts;
all **40** manifests in the nine passing runs plus the pre-fix countercheck
have zero entries. The stock Off hashes and all five Centered/Off native
centre/RAM/VRAM comparisons still pass.

At frame 5135, every combination changes only margin pixels on native line 0;
the 16:9 pair changes **142 pixels**, and the native centre remains identical.
All eight top margin rows are black. See `build/hills/window-before-5135-2x.png`,
`window-after-5135-2x.png`, `window-reproduction.json`,
`window-source-lines-5135.json` and `window-pixel-checks.json`. These are separate
from the earlier hill-fix PNG pair, which is retained as historical evidence.

### Plane-A tunnel walls

Auckland's tunnel is **plane A**, not plane B: an opaque high-priority
raster-positioned overlay whose opening moves and grows over roughly
30 presented pictures (`~8112..8156` at 60 fps). Before this fix the native
centre showed the black wall and its bright opening while the margins kept
drawing plane B's sky, skyline, water and grass, so one screen looked like two
pictures (`build/user-reports/tunnel-margins.png`).

`plane_a_margins()` now tests the *displayed* native edge pixel: it samples
the same plane-A texel the native compositor uses (`pixel()` at
`edge - ha, line + va`), requires it to be opaque, high priority and equal to
the native edge colour, and then continues that colour through the margin row
to the screen edge. Plane B scenery, a low-priority texel, or a sprite over the
edge never qualifies, so ordinary margins are untouched. The native 256-pixel
centre is still copied verbatim afterwards.

The edge colour, rather than a plane-A texel farther out, is deliberate: the
overlay silhouette can end exactly at the native edge (the tunnel mouth) and
continuing a neighbouring texel would leave a visible seam. Entry and exit
transitions therefore follow each line's own edge automatically; the mouth
grows and shrinks per line without a scene flag or a fixed screen rectangle.

Before/after stills at entry, inside and exit, in 16:9 and 21:9:
`build/task13/tunnel/{before,after}-{16-9,21-9}-{entry,inside,exit}.png`, plus
full ten-picture strips ending in `-sheet.png`. Only margin pixels change at
the tunnel; the native centre and HUD are unchanged.

## Hill margin regression check

`TG2_MARGIN_AUDIT=<private.csv>` records both adjacent margin pixels on every
eligible race line, before sprites and relocated HUD can hide a gap. Each row
includes the actual native edge colour, native plane-A/B texels and attributes,
the margin's plane-B texel, the native B colour from the same per-line CRAM,
atlas Y and player slope. The same hook receives the synthesized native row
when 60 fps is enabled; it therefore audits real and intermediate pictures.

`tools/check_margin_artifacts.py` counts black backdrop gaps where the native
edge has visible scenery. Opaque black panorama art is distinguished from a
transparent texel exposing the backdrop; plane-A car/effect pixels over an
already empty native B edge are not classified as scenery. It also checks
exact ground colour continuity across separator lines and between ground
texels on ordinary road lines, including palette-bank and grass-stripe phase.
`tools/verify_widescreen.py --margin-audit` runs it and returns nonzero for any
violation or an empty capture. Custom controller routes can be supplied with
`--route` and `--end-frame`; all output remains under the selected build path.

```sh
TG2_RACE_60FPS=1 TG2_HUD_MODE=edges python3 tools/verify_widescreen.py \
  --port 4500 --out build/hills/after-edges-60 --modes 16:9,21:9 \
  --margin-audit --turbo --shots 2685,5135,5140
# Repeat with TG2_RACE_60FPS=0 and TG2_HUD_MODE=centered as needed.
```

### Qualified Auckland hill evidence

The baseline controller route covers flat ground and both slope signs
(`$FF18E0` ranges **−190..128**), with moving horizon/ground separator rows.
At wall frame **5135** (audit frame 5134), native line **125** samples plane-B
atlas Y=441, tile attribute `$0273`, index **15** on both edges. Plane A is
transparent there. The previous margin sampler reaches index **0** and exposes
the black backdrop; the corrected sampler keeps index 15 and that line's
CRAM colour **RGB (87,119,49)**.

Before/after 2× PNGs: `build/hills/before-5135-2x.png` and
`build/hills/after-5135-2x.png`. Only margin pixels on native lines **123..133**
change; **1556** black margin pixels recover scenery, and the entire native
256×224 centre is byte-identical. `build/hills/reproduction.json` and
`before-source-lines-5135.json` retain the pixel/source evidence.

All eight combinations below cover **2933 complete race frames**, every line
**0..223**, both edges: **1,313,984** samples per combination, with no missing
frames or incomplete rows. Reports and commands are under `build/hills/`;
`matrix.json` links the four paired aspect runs. Every final runtime manifest
has zero entries.

| HUD | 60 fps | 16:9 black / ground-colour violations | 21:9 black / ground-colour violations |
|---|---|---:|---:|
| Centered | Off | 0 / 0 | 0 / 0 |
| Edges | Off | 0 / 0 | 0 / 0 |
| Centered | On | 0 / 0 | 0 / 0 |
| Edges | On | 0 / 0 | 0 / 0 |

The old renderer, rebuilt with the identical complete audit, fails with
**11,100 black-backdrop gaps and 11,100 ground-colour violations in each
aspect** (`before-complete/summary.json`, expected exit 1). It has the same
2933 frames and complete row coverage; the fixed renderer returns exit 0.

The existing 60 fps road artefact check also passes unchanged:
**2503** audit frames, **1511** synthesized frames and **83,732** tested road
lines, with every edge/stripe/discrete-row/translation/snapshot violation
counter **0** (`road-after/road-artifacts.json`, exit 0). The two 12-frame
visual strips remain under `road-after/road-strip-{3600,4500}-2x.png`.

With both options Off, frame 60 remains **`2A0B972960C5E325`** and frame 300
**`1131D937D70234FD`**. With 60 fps Off and Centered HUD, the canonical RAM,
VRAM and native-centre comparisons pass at all five baseline capture frames
in both widths (`after-centered-0/summary.json`).

### Motion-only synthesized black lines

The second playtest still showed brief one-pixel black lines in the margins on
hills, but only in motion. The audit streams every presented picture, including
synthesized ones, so the residual was in the interpolation policy rather than
an unaudited frame.

Ground/separator rows (atlas Y **432..447**) have one opaque and one transparent
half. When both endpoints are non-road on such a row, the road-envelope clamp
does not constrain H-scroll, and the row used interpolated translation. That
could move the transparent half onto the native edge, leaving a one-line black
backdrop gap. Example: frames 12329..12336, native line 107, right side —
`atlas_y=441`, `margin_bp=0`, both endpoints' rows opaque. The line appeared for
one or two synthesized pictures and vanished on the neighbouring ones, matching
the reported flicker.

Synthesized ground/separator rows now keep **their discrete source scroll**,
exactly like their atlas Y, VRAM, patterns and palette; panorama rows 448..511
remain horizontally interpolated. The road artefact check still passes because
a snapped row is exactly its nearest source row.

`tools/check_margin_artifacts.py` also counts **brief backdrop lines**: a
backdrop row that appears for at most three consecutive presented pictures and
then disappears. Runs touching the first or last captured picture are excluded
as capture boundaries, because the pre-race/countdown transition would
otherwise be counted once per line.

| Run (16:9, Auckland full route) | Frames | Samples | Brief backdrop lines | Other violations |
|---|---:|---:|---:|---:|
| Before, 60 fps On | 10139 | 4,542,272 | **1019** | 0 / 0 / 0 |
| After, 60 fps On | 10139 | 4,542,272 | **0** | 0 / 0 / 0 |
| Before, 60 fps Off | 10574 | 4,737,152 | **0** | 0 / 0 / 0 |
| After, 60 fps Off | 10574 | 4,737,152 | **0** | 0 / 0 / 0 |

Machine-readable results are `build/task13/margins/{before,after}-{60,off}.json`
(the 60 fps On before run exits 1 on the 1019 flicker lines; the other three
exit 0). The real-picture scan is the 60 fps Off rows: **0** single-frame black
lines in 10,574 presented pictures, so the defect was specific to synthesized
frames.

The same-input physics replay still matches: Off and 16:9 + Edges + 60 fps
produce identical complete-player-record and 64 KiB WRAM hashes on
**5000/5000** frames (`build/evidence/replay-comparison.json`), and the road
artefact check passes with **2503** frames, **1511** synthesized frames,
**83,732** tested rows and **0** violations
(`build/fps/task13-road/road-artifacts.json`). The changes are host-only; no
guest write or new hook was added.

## Known artefacts and limitations

- **Plane-A effects extend by their native edge, not by reprojection.** A
  plane-A texel that is the visible native edge is continued through the
  margin as its edge colour (the tunnel wall). Plane-A detail wholly inside the
  native centre, or a textured edge that changes across the margin, is not
  re-projected; ordinary actors and roadside objects still come from the
  sprite capture.
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
