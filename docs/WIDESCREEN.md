# Top Gear 2 USA widescreen

The game owns `game/tg2_video.c`; the shared engine's VDP mode, guest scroll
lists, projection registers, collisions and object activation remain unchanged.
`GameSpec.video_default = "fit"` selects Adaptive for a fresh installation.
The shared Widescreen package supplies its enable switch, Adaptive and fixed
16:9 / 21:9 / 32:9 choices, and settings persistence. `tg2_options.c` supplies
the TG2 description; the consumer enables the launcher's Mods page.
Explicit `--widescreen off` always selects the untouched native renderer.

## Technique and boundaries

Races use H32 (256 by 224). A 224-line 16:9 view requests 398 pixels,
71 extra on either side; 21:9 requests 523 pixels, with 133/134 extra pixels.
Adaptive uses the actual drawable aspect, with a 320-pixel minimum imposed
by the shared runner's frame preparation and a 4096-pixel resource bound.
The original 256-pixel image is copied into the center of every race row.
No stretching, H40 mode switch, guest camera shift, CPU divisor change or
write to canonical state is involved.

The renderer qualifies the copied race raster handler's first opcode
(`$2C9D`, `$601E` or `$6042` at `$FFF9FE`), H32 without interlace, and a zero
2P flag at `$FF189E`. ROM `$0048B6` and `$006896` test that flag to select
single/split raster work. H40 title/menu/shop screens and split-screen keep
a centered original image with black side bars. The native HUD remains
centered; there is no edge-anchored HUD option in this implementation.

The raster ISR copied from `$004682..004703` writes live VSRAM and CRAM
and advances A5 through `$FF231E`'s list. Consequently a frame-start plane
snapshot cannot reproduce the road: each output row samples **that row's**
VDP state, patterns, palette, horizontal scroll and vertical scroll.

Plane B's race name table is `$E000`, 64 by 64 tiles (512 by 512 pixels).
Its atlas contains four perspective road sections in rows 0..431, a separator,
and the skyline in rows 440..511. The road sections straddle X=0: their
left/right halves meet across the VDP's 512-pixel seam, with exterior ground
at the opposite X=256. ROM `$0079D6` / `$007A10` select the road producer;
`$007B00`, `$007CDC`, `$007E70` dispatch to scanline variants that write the
raster state. Their scroll and template-row selections provide the original
curve, hills, road width, lane markings and rumble-strip phase.

For the margins the renderer unwraps the road seam around the native view,
samples that one road, and extends its exterior ground beyond the template's
512-pixel domain. It never wraps into a second road. The skyline keeps its
scrolling authored panorama wrap. This distinction matters at 21:9 and wider.
The first exploratory raw-plane capture showed exactly why unrestricted
wrapping is unsuitable: plane A's HUD reappeared in both road margins.

Plane A at `$C000` holds the screen-space HUD and the player-car art, with
raster positioning also used for special roadside effects. It is retained
through the exact native center, not repeated into added columns. This leaves
special plane-rendered roadside structures as a remaining limitation.

## Mapping capture

Ordinary actors use the game's mapper at `$00B584`. Before its horizontal
cull at `$00B5FA` (`cmpi.w #$100,d3`, raw bytes `0C430100`), the host records
unwrapped mapping pieces from A1 with the mapping header at A0, native D1/D2
projection, D5 attributes and D6 width. `$00B6F0..00B7BE` establishes the
8-byte piece format, flip handling, vertical occlusion, attributes and SAT
coordinates. Host capture retains the same vertical rules and changes no
registers or RAM. The native cull still executes for the guest's SAT.

Two further read-only hooks delimit each scene: `$0067EE` resets the capture
at the native SAT allocator reset (`377C007F9ED0`); `$006982` publishes it
after `$00B85E` has linked the SAT (`177C0001A01C`). A four-scene history
matches the complete published SAT bytes against live VRAM `$BE00` before
using a captured scene. Captured pieces are drawn only in added columns,
with live patterns/palette, native allocation order and plane-B priority.
The native viewport, including its sprite limits and raster effects, remains
pixel identical. `tg2_video` reports published/displayed serials, matching
native pieces, margin pieces, overflow, and the last scanline scroll states.

This expands the **presentation capture**, not simulation activation. Objects
rejected before reaching the mapper and special plane-rasterized objects are
not recovered. A full claim of expanded scenery/car visibility requires
additional coverage of those producers; it must not be inferred from the
ordinary-mapper hook alone.

## Reproduction and qualification

Build and replay without opening desktop windows:

```sh
JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build
build/analysis-venv/bin/python tools/verify_widescreen.py --port 4400
```

The verification tool needs Pillow. It translates only the controller events
in `game/baseline-route.json` to the engine's input timeline, so captures occur
at exact wall frames rather than a TCP polling approximation. PNGs, RAM/VRAM
dumps, exact scripts, logs, diagnostic JSON and all four copied evidence
manifests stay under `build/ws/{off,16-9,21-9}/`. Required race captures are
`frame-2800.png`, `frame-3300.png`, and `frame-4501.png`; title and main menu
are also captured at 600 and 1350. The tool asserts the stock Off hashes
(frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`), zero dispatch /
floor / interior / unsafe entries, and identical canonical RAM, VRAM and
native-center pixels at every comparison frame.

Final measured results and remaining visual qualifications are recorded below
after executing that route. Other tracks, rain/night, split-screen gameplay,
controller-driven launcher operation, Windows/macOS/Deck and full race
completion are not covered by the first-track headless route.
