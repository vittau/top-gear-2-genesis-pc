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
requests 523 (133/134 per side). With the overscan crop the same ratios at the
presented 200 lines ask for 356 and 467 (50/50 and 105/106). Adaptive at a
1600×900 window gives 356, at 1234×567 gives 435, at 1000×1000 gives 320 (the
runner minimum), at 3840×720 gives 1067; with the crop off the same windows
give 398 / 488 / 320 / 1195.

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

## Hide overscan (crop)

Every TG2 race picture uses only native lines **8..207**. Rows 0..7 are the VDP
window plane: solid black except for the stock red/orange pattern-0 marks at
native x=16..31 (see [Native red/orange top band](#native-redorange-top-band)).
Rows 208..223 are the bare backdrop. A CRT hid both bands in overscan; on a
modern display they showed as bars above and below the picture.

**Hide overscan** (default **On**) therefore *crops* them: the presented race
picture is 200 lines tall instead of 224, and the canvas height follows.

| Mode | Hide overscan Off (stock) | Hide overscan On |
|---|---|---|
| widescreen Off | 256 × 224 | **256 × 200** |
| 16:9 | 398 × 224 | **356 × 200** |
| 21:9 | 523 × 224 | **467 × 200** |
| Adaptive | window aspect × 224 | window aspect × 200 (1600×900 → 356, 1234×567 → 435, 1000×1000 → 320, 3840×720 → 1067) |

The canvas width is computed from the *cropped* height, so a 16:9 window shows
a true 16:9 356 × 200 picture with no letterbox bars. The OS window never
resizes when a race starts or ends; only the logical canvas changes, and menus
keep today's 398 × 224 canvas (a race frame is 356 × 200, so a boundary frame
may differ for one frame — no picture content is ever clipped).

**Nothing is assumed about the bands.** A frame is cropped only when that exact
frame earns it:

- the picture is a single-player race (the widescreen qualifier: H32, no
  interlace, race plane bases, a race H-int program, 2P flag clear);
- all eight top rows were blanked by the stock window band;
- all sixteen bottom rows, as actually rendered (margins included), are empty,
  i.e. nothing but the backdrop.

A picture that draws into either band keeps its full 224 lines, so no visible
content can be removed. Menus, the shop, results, split-screen and every other
non-race screen are unchanged: pillarboxed and letterboxed exactly as before,
and split-screen keeps 256 × 224 by the qualifier. `tg2_video` reports `crop`,
`crop_frames` and `crop_withheld` (race pictures that kept their height).

The engine seam is patch **0011**: `GameVideo.present_window()` is called once
per completed frame, after every row was produced, so the provider decides from
that frame's actual pixels. The runner then shifts rows `[first,last)` to the
top of the framebuffer *before* any screenshot, hash, overlay composite or
upload. Guest output, the 60 fps picture history, per-row captures and the
margin CSV still see all 224 native lines; only presentation geometry changes.

The option is a normal `[mods.*]` boolean, offered by the launcher's Mods page
and the in-game recomp-ui overlay and persisted next to the executable:

```ini
[mods.overscan]
hidden = 1
```

`TG2_HIDE_OVERSCAN=0|1` is a probe-only override and is never persisted.
`tg2_video` reports `hide_overscan` in its status JSON. Its option text (both
UIs) describes the crop, not only the blanking.

### Why the crop is safe: the active-line evidence

`tools/check_active_lines.py` classifies every presented row as *picture*
(any colour that is not black or one of the three stock window-mark colours:
red `$E0`-ladder 206/0/0, orange 206/87/49 and grey 87/87/87, all confined to
native columns 16..31), *window* (black plus those exact marks) or *empty*
(all black). A capture whose top band holds nothing but those marks is a race
picture — exactly the picture the crop removes. Every capture below is a stock
picture: widescreen Off, 60 fps Off and Hide overscan Off, so all 224 lines are
visible.

`tools/tg2_active_lines.py` reaches a track through the game's own password
screen, then captures the countdown, the first seconds, cruising, a nitro
burst and both pause screens. Results per country are in
`build/crop/active/` and summarised below (evidence table under
[Measured crop evidence](#measured-crop-evidence)).

### HUD placement with the crop

The crop changes only which rows are presented; every renderer coordinate stays
native. Margins, sprite capture and the HUD relocation therefore keep working
row by row: the HUD rows (native 14..94) are simply the top of the presented
picture.
Centered and Edges both keep their documented anchoring (Edges moves the two
clusters by the margin, which is now computed from the 200-line height:
50/50 at 16:9, 105/106 at 21:9).

## Off-mode guarantees

With `--widescreen off` and Hide overscan Off, the provider's width and row
callbacks are never entered: `game_video_prepare_frame` leaves the frame
unowned and the runner presents the native 256 × 224 image. With Hide overscan
On the provider owns the rows to blank the active top window band and to crop
the two bands; the width stays native and the presented picture is 256 × 200.
The measured stock hashes are unchanged (frame 60 `2A0B972960C5E325`, frame 300
`1131D937D70234FD`) both with Hide overscan Off and On, because those
boot/menu frames have no active top window and are never cropped.

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
| Race screenshots | `frame-2800.png`, `frame-3300.png`, `frame-4501.png` in each mode (16:9 = 398×224, 21:9 = 523×224, Off = 256×224; with the overscan crop on, 356×200 / 467×200 / 256×200) |
| Menus | `frame-600.png`, `frame-1350.png`: 320-pixel native image centred with bars |
| Adaptive widths | 398 / 488 / 320 / 1195 at 224 lines, 356 / 435 / 320 / 1067 at the cropped 200 lines, 256 after a live switch to Off (`adaptive-*.png`) |
| Sprite capture | up to 29 captured pieces per scene, up to 6 pieces reaching a margin, up to 1982 margin sprite pixels in a frame, 0 overflow; every captured scene matched live SAT bytes |
| Canonical state | RAM and VRAM dumps identical to Off at 600, 1350, 2800, 3300, 4501 |
| Native centre | pixel-identical to Off at the same frames |
| Discovery | `dispatch_misses.toml`, `floor_coverage.toml`, `interior_label_misses.toml`, `floor_unsafe.toml` all report 0 entries after each route |

`margin-*.png` frames show actors and roadside objects crossing the old
256-pixel edge: `16-9/margin-3220.png` has an opponent car straddling the
right boundary and a tree in the left margin, and `21-9/margin-3221.png` shows
the same car wholly inside the right margin with the tree further out in the
left margin.

### Measured crop evidence

All captures below are private artifacts under `build/crop/` (not in git). The
pre-change runs are in `before/`, the shipping behaviour in `after/`.

| Check | Result |
|---|---|
| 16:9 race pictures | `after/16-9-on/16-9/frame-{2800,3300,4501}.png` are **356 × 200**; their native 256-pixel centre is byte-identical to rows 8..207 of the 398 × 224 pre-change captures (0 pixel differences) |
| 21:9 race pictures | `after/21-9-on/21-9/frame-{2800,3300,4501}.png` are **467 × 200** |
| Off race pictures | `after/off-on/off/frame-{2800,3300,4501}.png` are **256 × 200** |
| Menus | 398 × 224 (16:9), 523 × 224 (21:9), 320 × 224 (Off) at frames 600 and 1350, byte-identical to the pre-change captures |
| Stock picture with the option Off | `after/*-off/` are still 224 lines and byte-identical to `before/*-off/` at every comparison frame |
| Off hashes | frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD` in `after/off-on/off/stderr.log` |
| Active lines | 16 tracks, 279 captures, 181 race pictures: every one uses rows 8..207 with an empty bottom band |
| Margin audit | `margins/{16-9,21-9,16-9-60}/summary.json`: 2933 frames, 1,313,984 samples, rows 0..223 complete, 0 black-gap, 0 ground-colour, 0 band-colour and 0 brief-backdrop violations in each |
| 60 fps synthesized pictures | `after/16-9-60/16-9/frame-4510.png` .. `frame-4515.png`: every one **356 × 200** with content on rows 0..199 (no band, no flash); road audit 2503 frames / 1511 synthesized pictures / 83,732 road lines / 0 violations |
| Split-screen | `split/on/summary.json`: all 32 pictures 224 lines (never cropped) during 3115 two-player frames; 6 of them draw into rows 208..223 (the second viewport's HUD), which is why 2P is excluded from the crop |
| Road artifacts | `road/road-artifacts.json`: `passed`, 0 violations |
| Manifests | 0 entries after every run |

Active-line evidence, produced by `tools/tg2_active_lines.py` (password route
into each of the 16 tracks, `--extras nitro,pause` on the baseline track) and
classified by `tools/check_active_lines.py`; the table is regenerated by
`tools/summarize_active_lines.py 'build/crop/active/*/summary.json'`:

| Track | pictures | race pictures | situations captured | race picture rows | band failures |
|---|---:|---:|---|---|---:|
| 0 Australasia/Auckland — sun | 24 | 18 | cruise, nitro, pause, pre-race panels/countdown, race start, resume | 8..207 | 0 |
| 1 Britain/Loch Ness — overcast | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 2 Canada/Banff — sun+cloud | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 3 Egypt/Abu Simbel — sun | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 4 France/Bordeaux — sun | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 5 Germany/Bavaria — rain | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 6 Greece/Athens — night | 17 | 10 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 7 India/Amber Port — sun | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 8 Ireland/Dublin — overcast | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 9 Italy/Florence — sun | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 10 Japan/Hiroshima — sun | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 11 Scandinavia/Copenhagen — dusk | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 12 South America/Chile — dusk | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 13 Spain/Andalucia — overcast | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 14 Switzerland/Geneva — snow | 17 | 11 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |
| 15 USA/Las Vegas — night | 17 | 10 | cruise, pre-race panels/countdown, race start | 8..207 | 0 |

The capture list per track: `start/countdown` covers the pre-race panels and
the countdown itself (the race picture is already on screen with the clock at
zero), `cruise` is sampled every 240 frames. Auckland additionally ran the
nitro burst (C held for two seconds) and both pause screens (`START`, the pause
text, `START` again). Every race picture on every track — rain, overcast,
night, dusk, snow — has the same active range **8..207** and an empty bottom
band; the top band held only the stock window marks at native columns 16..31. The mark *colours* differ per track's palette (red/orange on Auckland,
grey/pink on Loch Ness, dark red at night), which is why the classifier keys on
the fixed mark columns rather than a colour list.

The finish, podium/results and next-race screens are covered by
`build/crop/flow/full/` (`tools/tg2_race_driver.py --races 1
--periodic-shots`, full 224-line captures): every race picture there keeps the
8..207 active range, and the results/shop screens are non-race pictures that
are never cropped.

Everything above is re-read from disk by
`tools/verify_crop_evidence.py --root build/crop --out build/crop/evidence.json`,
which fails if a cropped picture is not 200 lines, if a removed band carries
content, if an Off capture changed, if a menu changed, or if a margin/road
audit or a manifest is not clean.

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

### Map and markers stay together (sprite-phase HUD)

The baseline route showed the track map separated from its `1ST`/`1P` markers
for about three seconds (frames **3409..3585**): the map stayed at its native
position while the markers moved out to the right margin.

`tools/tg2_hud_diag.py` records the per-scanline raster state that the Edges
relocation depends on. At those frames `hud_plane_pixels` dropped to **0**
while `hud_marker_pixels` stayed at 234, and plane A's V-scroll for the HUD
rows was a **road ramp** (`Va = 112 - line`) instead of `-14`. A read-only
VRAM/SAT dump at frame 3480 explains both: on those frames the game takes the
whole instrument cluster **off plane A and draws it as sprites** — eight
32-pixel sprites with pattern IDs `$04..$7D` (the same IDs the plane-A cells
use) plus the two marker sprites. The Edges relocation only knew about plane-A
cells and the two markers, so the instruments stayed native.

Two changes fix it:

- the sprite walk classifies any high-priority instrument-pattern sprite with
  the same left/right cluster rule as plane-A cells, relocating it with the
  cluster and recomposing the vacated native pixels exactly as the markers
  already did. Ordinary scenery sprites (`$095`, `$0CE`, cars with other IDs)
  keep their native position; `tg2_video` reports `hud_sprite_pixels`.
- plane-A relocation is gated on the **window** (what actually hides plane A)
  instead of the V-scroll sign, so the other HUD raster phase is relocated too.

`tools/verify_hud_map.py` is the automated proof: it replays the same route
frames twice — stock `Off` for the native reference, and the widescreen mode
with HUD Edges — and measures the yellow map outline and the orange `1P` label
in both. Both boxes must be exactly `native + (origin + right)`, and the
markers must keep their displacement from the map. With this fix the sweep
(46 frames, every 60 from 2600 to 5300) passes with **0 failures in 16:9 and
21:9** (`build/crop/hudmap/{16-9,21-9}/summary.json`); the pre-fix renderer
fails frame 3480 ("no map at offset 142") and nothing else
(`build/crop/diag/hudmap-before/summary.json`), and the fixed build passes that
exact frame (`build/crop/diag/hudmap-3480-fixed/summary.json`). The per-scanline
evidence is in `build/crop/diag/hud-dump/diag.json` (V-scroll ramp, SAR dump at
frame 3480).

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
full ten-picture strips ending in `-sheet.png`. With Hide overscan held Off for
the comparison, all three frames in both widths change only margin pixels
(13,806 / 22,326 / 19,436 in 16:9; 25,844 / 42,031 / 36,547 in 21:9) and the
native 256-pixel centre keeps **0** changed pixels. With the shipping default
Hide overscan On the top-band marks are additionally blanked, as expected.

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
**16000/16000** frames, with identical lap splits and finish clock
(`build/evidence/replay16-comparison.json`). The road artefact check passes
with **2503** frames, **1511** synthesized frames, **83,732** tested rows and
**0** violations (`build/fps/task13-road/road-artifacts.json`). The changes are
host-only; no guest write or new hook was added.

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
- **The race's black bands are cropped, not filled.** With Hide overscan On the
  eight top and sixteen bottom lines are removed from the presented picture
  (200 lines). Off keeps the stock 224-line picture including the top band.
  Nothing is synthesised into them.
- HUD: Edges samples each row's live raster state; the existing non-HUD
  plane-A limitations remain.

## Still untested

The widescreen margin work covers the first track, dry daylight, single player,
one car and partial throttle. Not covered here: the plane-B atlas layouts of
the other 15 tracks in the margins, attract mode, LM/head-to-head,
controller-only launcher operation, Windows/macOS/Steam Deck builds, and
physical display/audio. Network session configuration was not part of this
work.

The **crop** is qualified on all 16 tracks (password route: rain, night, fog,
snow, dusk), race start countdown, cruise, nitro, both pause screens, the
finish/results flow and 2P split-screen; see
[Measured crop evidence](#measured-crop-evidence). A situation not in that
list is still safe by construction: a picture that draws into either band is
never cropped (`crop_withheld`).

Split-screen remains intentionally 4:3 and uncropped: the two views use the
whole 224-line frame.

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
