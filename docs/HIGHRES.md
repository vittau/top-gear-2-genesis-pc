# High-resolution rendering: ground truth, architecture and plan

**Task 29 — research and design.** The design below is unchanged; steps S1 and
S2 were implemented and verified by task 31 (2026-11-09), see §12. S3 and later
are not started.

Everything below was measured or read on the stock USA ROM
(CRC32 `BD3074D2`). Evidence paths are private under `build/highres/`, as the
repo rules require. Unless stated otherwise the presentation shows a
single-player race, widescreen Off, 60 fps Off, Hide overscan Off, so the frame
is the full 224-line picture.

Status of this document:

| | |
|---|---|
| Verified by ROM disassembly | road/raster emitters, LOD block and table, mapper entry, per-line state producer |
| Verified by runtime capture | per-line scroll/atlas state over 12 race frames; 18k mapper entries with model indices and pattern sets; atlas geometry and palette banks decoded from a live VRAM dump |
| Estimated | CPU cost at 2×/3×/4× (benchmarks on this Mac; Ryzen 3500U / Deck extrapolated, not measured) |
| Not derived | the per-object-type LOD ladder (which model is most detailed, and the exact screen thresholds), `$FF1894` bias semantics on other tracks |

---

## 0. Scope, rules and what "N×" means

The owner's requirement (`docs/ROADMAP.md`, "High-resolution rendering"):

- redraw the road from the game's own per-line parameters at N× resolution,
  not by upscaling the 224-line raster;
- always draw the most detailed sprite variant, scaled to the on-screen size
  with good filtering and sub-pixel positions;
- scale the background layers cleanly and keep the HUD sharp;
- use the game's own assets, made better.

"Render scale" here means the **presented picture** is `N × 356 × 200`
(16:9, Hide overscan on) for N = 2, 3, 4, instead of `356 × 200`. The guest
VDP, the raster program, the simulation and the font/tile data stay native.
The only thing that changes is what our renderer writes into the presented
frame and how tall that frame is.

Rules inherited from `AGENTS.md` and `ROADMAP.md`:

1. With the option Off (and with every other option Off) the presented output
   must stay byte-identical: frame 60 `2A0B972960C5E325`, frame 300
   `1131D937D70234FD`. At this task's starting commit these hashes reproduce
   on the current build (including with the spike hooks; see §10).
2. It is an option; `settings.ini` + launcher Mods page + in-game overlay, like
   `[mods.race60]`, `[mods.widescreen]`, `[mods.hud]`, `[mods.overscan]`.
3. Presentation only: no guest RAM/VRAM/CRAM/CPU writes, no new simulation
   parameters, no change to object activation, collision or SAT construction.
4. NTSC (task 28) runs at native source resolution and is mutually exclusive
   with a render scale above 1×. Scanlines run at **output** resolution and
   must work on an N× frame. Task 28 is paused, so this design only defines
   the slots; see §5.1.

---

## 1. What a race picture is made of

### 1.1 The raster program

`$004654..$00466A` copies a self-modifying H-interrupt program from ROM
`$004682..$004703` to `$FFF9FE`. Its records are streamed through A5:

| List pointer | Meaning | Source |
|---|---|---|
| `$FF231E` | primary raster list | A3-`$60EA` at `$004898` / `$0049D6` |
| `$FF01E6`, `$FF2324`, `$FF232C` | alternate list / offset / base | `$0048D8`, `$0048D4` |

Each record writes VDP data/control longs. The two forms that matter to a race
row are (see §10 for the disassembly):

- `$46C6..$46D0`: `move.w (a5)+,(a6)` / `move.l #$40000010,4(a6)` /
  `move.w (a5)+,(a6)` — a **VSRAM write with two words** (VSRAM[0] = plane A
  vertical scroll, VSRAM[1] = plane B vertical scroll), and
- the `$2C9D` / `$601E` / `$6042` entry forms, which are the first opcodes the
  widescreen qualifier accepts at `$FFF9FE`.

H-scroll is written the same way, through the VRAM H-scroll table at `$B800`
(`reg[13]=$2E`), one word pair per line.

Therefore the game's per-line state *is* the raster list, and by the time a row
is rendered the state is already visible in `GVDP`: `reg[]`, `vsram[0..1]`,
`vram` (H-scroll table, tiles, name tables) and `cram`.

### 1.2 The road emitters

`$007A10` is the road state builder. It reads the race descriptor at
`$FF241C` (`-$5FEC(a3)`), tests **bit 3** and **bit 4** of descriptor byte 3
(`$7A86`, `$7A90`) and picks one of three emitters, each with its own per-row
jump table:

| Descriptor flags | Path | Per-row jump table |
|---|---|---|
| bit 3 set | `$7C68` … | `$7CE4` |
| bit 4 set | `$7DFC` … | `$7E78` |
| neither | `$7A9A` … | `$7B08` |

The row emitters (`$7B88`, `$7BA4`, `$7BC4`, `$7BEC`, `$7C14`, `$7C3E` and the
`$7CDC`/`$7E70` variants) write the raster list records and the VSRAM pairs.
Their inputs, all read from RAM:

| RAM | A3 offset | Role (evidence) |
|---|---|---|
| `$FF17BC` | `-$6C4C` | horizon / screen limit; measured **200** during a race |
| `$FF1DBE` | `-$664A` | road row/height offset added to the first raster line |
| `$FF1D9E` | `-$666A` | race clock/scroll value copied into D5 (stripe/scroll phase) |
| `$FF0C5E` | `-$77AA` | per-line road table base (**not** the atlas) |
| `$FF231A` | `-$60EE` | picture staging pointer, `+$370` = VSRAM table |
| `$FF2F4A` | `-$54BE` | per-row "row kind" byte table |
| `$FF8EBC` | absolute | phase → sub-emitter index table (jump table selector) |
| `$FF1D30`, `$FF1D3C` | `-$66D8`, `-$66CC` | row-count/segment inputs |
| `$FF1996` | `-$666A` | sampled segment-table base (RAM_MAP) |

The player snapshot the picture build copies immediately before this
(`$00681E..$006846`) carries the camera: `+$7C` view position, `+$80` state,
`+$84` slope, `+$86` curvature. The physics copy is `+$14`/`+$16`.

### 1.3 Measured per-line state

`tools/highres_probe.py` (new, committed) captures `tg2_video {"rows":1}` plus
the player record, a full 64 KiB VRAM dump and CRAM at chosen race frames.
Evidence: `build/highres/road-c00/samples.json` (12 samples, Auckland).

Per presented picture over native lines 8..207 (200 rows):

| Measurement | Range over 6 samples |
|---|---|
| Distinct 4-word row states (`ha,hb,va,vb`) | 141–200 |
| H-scroll runs (plane A+B) | 54–68 |
| VSRAM runs | 127–200 |
| Distinct plane-B atlas rows reached | 88–145 |

So the raster list is essentially **one VSRAM write per line** and **~60
H-scroll writes**, and the picture uses only ~110 of the 512 atlas rows.

Example, Auckland frame 8347, lines 150–207 (the visible road), with the width
measured from the atlas row itself (§1.4):

| line | atlas Y | template | width | H-scroll centre | left/right edge |
|---:|---:|---:|---:|---:|---:|
| 152 | 6 | 1 | 16 | 134 | 126 / 141 |
| 160 | 169 | 2 | 62 | 148 | 117 / 178 |
| 170 | 193 | 2 | 120 | 167 | 107 / 226 |
| 180 | 74 | 1 | 182 | 187 | 96 / 277 |
| 190 | 100 | 1 | 244 | 206 | 84 / 327 |
| 200 | 268 | 2 | 302 | 225 | 74 / 375 |
| 207 | 284 | 2 | 342 | 238 | 67 / 408 |

The width grows monotonically: the road is a continuous perspective strip whose
atlas address is chosen per line. The template column alternates between 1 and
2 for *appearance* reasons only (§1.4).

### 1.4 Atlas geometry, measured from live VRAM

Decoding plane B (`$E000`, 64×64 name table, patterns at `$0000..`) for every
atlas row gives the exact road silhouette (`build/highres/atlas-widths-002.json`):

| Atlas rows | Content | Measured behaviour |
|---|---|---|
| 0–143 | template 1 | road width `4 + 2k` px, k = row; edge steps **+2/+4 px per row** (tile staircase) |
| 144–287 | template 2 | **identical art and widths** to template 1 |
| 288–359 | template 3 | road width `4 + ~5k` px, edge steps +4/+6 px per row |
| 360–431 | template 4 | **identical art and widths** to template 3 |
| 432–447 | ground/separator | solid ground rows, then a half-width grass strip with a transparent half |
| 448–511 | panorama/skyline | authored repeating panorama; the game pins its top row above the skyline (measured: 86 identical atlas rows), which renders as a flat sky band |

The two members of each pair are *pixel-identical art* but carry a different
**tile palette bank** (attribute bit 13):

| | asphalt (nibble 14) | lane mark (nibble 13) |
|---|---|---|
| template 1 row 100 | attr `$01DC`, palette 14, CRAM `$444` | palette 13, CRAM `$444` |
| template 2 row 244 | attr `$21DC`, palette 30, CRAM `$444` | palette 29, CRAM `$AAA` (white) |

So the game animates the lane markings by **choosing the palette bank per
line** while the geometry stays identical. This is the "stripe phase" that
`docs/FRAMERATE.md` protects: it is a discrete, per-line appearance choice, and
it must never be blended. (A half-line therefore has a well-defined geometry
but a *nearest* bank.)

Consequence for N×: the authored vertical granularity of the road is one atlas
row, and one atlas row is a 2–6 px width step. **A higher-resolution road
cannot contain more authored detail than that.** What N× *can* do is:

1. place each output row's road silhouette at the continuous width and centre
   the game's own per-line numbers imply (instead of a 2–6 px stair step),
   i.e. anti-alias the edges;
2. sample the atlas per output column with a proper reconstruction filter
   instead of nearest-upscaling the resolved 224-line pixels;
3. give sprite positions and the road centre sub-pixel precision;
4. render the background/skyline/ground at N× from their own per-line scroll
   instead of upscaling the composed row.

Points 1–2 change the *look* relative to stock (smoother, less stair-stepped).
That is the owner's intent ("made better"), but it is a decision to confirm;
see §9.

---

## 2. Question 1 — the road

### 2.1 Is the per-line state enough to re-rasterise at N×?

**Yes, for geometry and colour; the atlas is the limit on detail.** A row is
fully described by:

- `atlas_row` (plane B VSRAM[1] + line, 0..511) → template, k, width, art;
- bank (template parity / tile attribute) → lane-mark colour;
- `centre` (plane B H-scroll) → horizontal placement;
- the row's captured CRAM → actual RGB for every nibble;
- plane A/plane B priority and the sprite scene for occlusion.

All five are captured per row today (the 60 fps `Picture` in `tg2_video.c`
copies a whole `GVDP` per row; the new implementation should capture a *compact*
row state instead, §7.2).

Rules for interpolation, derived from the measurements:

| Quantity | Continuous? | Rule at N× |
|---|---|---|
| road width (k) | yes, monotone per line, identical art across the pairs | interpolate between adjacent rows **within the same pair family** (0–287 / 288–431); snap at the family boundary |
| centre (H-scroll) | yes, integer per line | interpolate (and add the 60 fps temporal fraction when synthesising) |
| bank / lane-mark colour | **no** | nearest row; never blend |
| atlas art | discrete | sample the *authored* atlas (nearest for interior texels, filtered only where the geometry demands it) |
| ground / panorama | continuous scroll, discrete art | interpolate scroll, keep art discrete |

### 2.2 How the 60 fps path already reconstructs it, and what sub-line can reuse

`docs/FRAMERATE.md` describes the working 60 fps reconstruction:

- per-row endpoint snapshots (full `GVDP`), bracketed three V-ints back;
- per output row: all discrete state from the **nearest** endpoint (atlas row,
  VRAM, CRAM, plane-A HUD state, sprite attributes);
- only plane-B horizontal translation and matched sprite coordinates are
  interpolated;
- VSRAM is **never** interpolated across time — the failing frame 3600 example
  shows two endpoint atlas rows with the same intended width averaging into a
  different template row.

Sub-line interpolation reuses exactly that policy with a different axis:

- the two neighbours are **adjacent rows of one picture**, not two pictures;
- their atlas rows are in the same template (or belong to the same pair family
  after normalisation), so averaging k is geometric, not a template jump;
- bank, art and palette still come from the nearest row;
- H-scroll is interpolated, as today.

The measured width sequence (§1.3) is the evidence that this is sound: the
per-row width is monotone and the pair choice does not change it, so
sub-line width = interpolation of k is well defined and monotone too.

For a synthesised 60 fps frame the two axes compose: choose the discrete source
picture per row (existing policy), then resolve that row's sub-line position
inside the picture's own raster. No new temporal state is required.

### 2.3 Re-rasterising: keep the VDP replay or paint the road ourselves?

The current renderer gets each row from the VDP itself (or, in the 60 fps path,
replays a captured row through `gvdp_render_scanline()`), which produces a
native-resolution index row. At N× that is the wrong tool for the road: the VDP
has no notion of a fractional line, and replaying it N times per source row
would only duplicate rows.

Proposed split (see §7):

- **Road** — our own strip rasteriser over the captured per-row state, at N×
  vertical and horizontal resolution: per output row, compute `k_real`,
  `centre_real`, bank; per output column, compute the source atlas column,
  test against the road silhouette, and sample art/colour. Edges get analytic
  coverage so the silhouette is smooth at N×.
- **Everything else** (sky, skyline, ground, plane-A effects, sprites, HUD) —
  still derived from the captured VDP state, drawn at N× by the same provider,
  using per-row scroll and the sprite capture it already has.

That keeps the "guest raster state is authoritative on every row" principle:
the game decides width, phase, colours and sprite selection; we only resolve
them at a higher sampling rate.

---

## 3. Question 2 — sprite LOD

### 3.1 Where the variant is chosen

The scenery/object mapper entry is `$00B584`. Its calling convention (verified
by disassembly and by the existing pre-cull hook at `$B5FA`):

| Register | Meaning |
|---|---|
| `A1` | object mapping record (WRAM around `$FF8E94..$FF9FFF`), fields: `+0` art block, `+4` mapping-table pointer, `+8` attribute word |
| `D7` | **model index** into that mapping table (`(a0,d7.w*4)`) |
| `D1`,`D2` | projected position values used by the mapper |
| `D5` | attributes (palette/priority/flip) |

Two ways reach it:

1. **Direct** calls from the scenery/object builder (`$B986`, `$B990`, `$B99A`
   → `$B9DE`/`$B9E8`) pass D7 = object type.
2. **The LOD block** `$B520..$B584` remaps the type through a distance bucket
   before calling `$B584`:

```
$B52A  d6 = d7                      ; object type
$B52C  d7 = 8*d7 + type             ; 9 * type
$B530  d6 = 0x90 - d1
$B538  d6 >>= 2                     ; arithmetic
$B53A  d4 = word($FF17D6)            ; default per-scene adjustment
$B53E  ...  word($FF1878) == ...      ; the special-mode word
$B544  ...  word($FF189E)            ; 2P flag gates the second variant
$B54A  d4 = word($FF17D8)            ; one of the two variants
$B554  d4 = word($FF187A)            ; shared adjustment value
$B558  d6 += d4                      ; ($FF187A used only on a match)
$B55A  d6 -= word($FF17DE) >> 2
$B562  d6 >>= 3
$B564  clamp d6 to 0..8             ; nine distance bands
$B572  d7 += d6 + word($FF1894)     ; $FF1894 = per-scene bias (0 on Auckland)
$B578  a0 = $10D42                  ; LEA PC-relative (+2 for the extension word)
$B57C  d7 = byte[a0 + d7]           ; per-type, per-band model index
$B584  mapper entry with D7 = model index
```

So: **nine distance bands per object type**, remapped through the byte table at
ROM `$10D42`, with a bias in `$FF1894` and adjustment words in `$FF17D6`,
`$FF17D8`, `$FF17DE`, `$FF187A` selected by the special-mode word `$FF1878`
(the same word the widescreen sprite capture already tests) and the 2P flag
`$FF189E`. Everything is read-only data; nothing is computed from simulation
state that we would have to change.

### 3.2 Runtime evidence

Spike hook at `$B584` and `$B5F0` (`game/tg2_lod_probe.c`, see §10) logged
18,190 mapper entries in a 30 s Auckland drive:

- 69 distinct **piece lists** (pattern sets) were used, each with its own
  pattern IDs and piece sizes;
- 18,190 `$B584` entries were logged in the 30 s run (36,360 spike records
  including the paired `$B5F0` readings);
- per object record the model index changes as it approaches, e.g. record
  `$FF8DAE` at frames 7412→7450: model `8` (d1 33..49), then `7` (d1 48),
  then `6` (d1 62), while D2 stayed at the horizon clamp 144/145 — the bucket
  shrinks as `0x90 - d1` grows, i.e. closer objects take smaller buckets and
  therefore more detailed models;
- one-piece models 11–24 are the far end of some ladders (patterns 147, 156,
  174, 186, 194, 200, 206, 209, 211, 213, 215, 216, 217 with decreasing
  widths 24→4 px), and multi-header models reach 10+ patterns per object.

### 3.3 Can we always pick the most detailed variant?

**Yes, in principle, read-only.** The mapping table is data: for a captured
object we know `A1` (its record) and can resolve model index 0..8 ourselves by
reading `(4(A1) + model*4)` → mapping header → piece list. We draw the most
detailed variant in our renderer, scaled to the object's own on-screen size
(which the captured projection gives us), at N× with sub-pixel position.

What breaks / what must be handled:

1. **No feedback into the guest.** The guest's SAT, cull and sprite-per-line
   limits are built from the variant *it* chose. We must not change the guest's
   choice: our variant is drawn in the presented picture only. The native
   centre is then *not* a copy of the guest framebuffer at N× (see §5.4 for the
   Off/1× guarantee).
2. **Sprite emission limits disappear for us, but the guest's still apply.**
   The VDP still enforces 80 sprites (§5) and its per-line limits on the guest
   SAT, and `$00B85E` still links the SAT the guest asked for. Our margin/actor
   renderer already draws pre-cull pieces without those caps; at N× we own the
   whole row, so the caps stop being a rendering limit — but overdraw cost
   grows with the detailed variant (more pieces).
3. **The detailed variant is not a scaled copy of the far one.** Different
   pattern sets (different art, sometimes different piece counts). Scaling it
   to the far object's rectangle changes the composition slightly (a tree's
   silhouette at 20 px will be a filtered 64 px tree, not the authored 20 px
   art). This is the owner's "same assets, made better" call; it is also the
   single biggest visual change in the task.
4. **Palette lines are unaffected** (bank bits are per piece, copied with the
   variant), but a bilinear filter must run after palette lookup (RGB), never on
   palette indices, or colour bleeds between unrelated palette entries.
5. **Priority order** stays the native one: high-priority sprite beats high-
   priority plane B, low-priority sprite loses. The existing margin compositor
   already implements it; the same rule applies at N×.
6. **Animation/flip** must come from the chosen variant's attributes, not the
   guest's; the mapper's flip bits and `$FF1878` mirroring are per piece.
7. **Not all objects have a 9-step ladder.** Some are single-piece sprites at
   one model (models 11–24 above); "most detailed" then just means model 0..N
   of that object's own set, and the safest rule is: resolve model 0 only when
   the table says a *lower* model exists, otherwise keep the guest's.

**Partially mapped:** the per-type ladder (which model index is the most
detailed for each object type, and the exact screen-space thresholds) is not
tabulated yet. The deterministic way to finish it, cheaply, in the
implementation task:

- log `(A1, type = d7 before `$B52C`, band = d6, model = d7 after `$B57C`,
  D1, D2)` at `$B584` for one full lap on two tracks; group by `A1`;
- join with the same run's SAT/pattern dump to name each model's art;
- the 9-band ladder per type then falls out of the log; no guessing.

---

## 4. Question 3 — background and HUD, and what N× needs from each

### 4.1 Composition today

| Layer | Source | Per-line inputs | Notes |
|---|---|---|---|
| Sky | plane B atlas row 448 (a flat colour band) or the backdrop `reg[7]&63` | VSRAM[1] pinned so the row repeats (measured: 86 identical rows at frame 8347) | the gradient-skies task will replace this band with a ramp |
| Skyline / panorama | plane B rows 448–511 | H-scroll and VSRAM per line, authored wrap | widescreen keeps the wrap |
| Ground / hills | plane B rows 432–447 | per-line H/V scroll; half-transparent grass halves | margin rules must not wrap into the transparent half |
| Road | plane B rows 0–431 | VSRAM[1] (atlas row), H-scroll (centre), palette bank | §1–2 |
| HUD | plane A (`$C000`) high-priority cells `$004..$084`, plus map-marker sprites `$106/$10E` and, on some frames, the whole cluster as sprites | plane-A H/V scroll per line | `WIDESCREEN.md` §"HUD" has the ownership proof |
| Player car | plane A raster-positioned | per-line scroll | stays native in widescreen |
| Weather | plane A rows 128–383 | per-line H/V scroll, 256-line wrap | `RAIN_WIDESCREEN.md` |
| Tunnel | plane A opaque high-priority overlay | per line | edge colour continues into margins |
| Sprite actors | SAT + pre-cull scene capture | captured pieces | §3 |
| Window band | window plane, rows 0–7 | stock marks | blanked/cropped by Hide overscan |

### 4.2 What each needs at N×

- **Sky**: N× is trivial if it is a flat colour (fill at output resolution).
  If gradient skies land first, draw the ramp at output resolution — no
  upscaling at all. Decision for the gradient-skies task, but N× removes its
  banding ceiling.
- **Skyline/panorama/ground**: per-line scroll gives an exact horizontal
  mapping at any column; resample the authored art at output resolution. The
  panorama is 1:1 art, so N× is a filtered upscale for those rows and cannot
  gain detail; the *edges* (skyline silhouette) can be anti-aliased the same way
  as the road if we want.
- **HUD**: "keep the HUD sharp" means do **not** filter it. Two options
  (§9): draw HUD tiles at native 1× pixel size inside the N× frame (sharp but
  physically small), or at exact integer N× (crisp and proportional). Both are
  feasible because the HUD is name-table cells with known pattern IDs; the
  current renderer already classifies them.
- **HD menus, fonts and HUD pack (later extension).** That pack replaces the
  original tile art with faithful HD redraws keyed by the original tile
  content, and validates each entry by box-filter downsampling it back to the
  original size and comparing pixel-for-pixel (`ROADMAP.md`). N× is where the
  pack becomes useful: at 1× the pack could only be drawn downsampled, at N× a
  2×/4× entry lands on an exact output grid. The seam is the same as the HUD
  decision above: our HUD/tile sampler takes an optional texture source keyed
  by `(pattern id, palette bank)`, falls back to VRAM art when the pack has no
  entry, and is Off by default. No game logic or font data changes. The same
  box-filter-downsample rule doubles as the whole-frame acceptance check for
  N× itself (§8, S3).
- **Plane-A effects** (car, tunnel, weather): weather needs the N× coordinate
  mapping (it already samples per-line scroll); tunnel needs the same
  edge-continuation rule at N×; the car stays native-size (or N× if we accept
  the change of look) — decision.
- **Crop/overscan**: unaffected; the crop is a shift of rows `[8,208)` of the
  *presented* buffer. At N× the crop becomes `[8N, 208N)` and the canvas width
  follows the cropped N× height (§7.4).

---

## 5. Question 4 — interactions

### 5.1 NTSC / scanlines (task 28, paused)

Slots, per the owner's shared rules:

- **NTSC** consumes the native 356×200 picture and is mutually exclusive with
  render scale > 1. The option surface must refuse the pair (grey out NTSC, or
  turn render scale back to 1 when NTSC is picked, with a visible note).
- **Scanlines** run after the final scale to the window, on the output
  resolution, so they operate on an N× frame exactly as on a 1× frame. Nothing
  in this design changes the stage's input contract: RGB pixels of the
  presented picture at its logical size.
- The presentation chain this design targets is today's: provider rows →
  `present_window` (patch 0012) → linear filter (patch 0025) → upload →
  `SDL_RenderCopy`. The N× frame is just a taller/wider presented picture for
  those stages.

### 5.2 Widescreen margins

The margin compositor already rasters every output column from that row's live
state (`road_x`, `pixel`, sprite capture, plane-A edge rules), so its work is
per-output-pixel and scales with the canvas. At N×:

- width becomes `N × current_width` (or the aspect-derived width at the N×
  height), so the rotation from 16:9@200 lines (356) to 16:9@400 lines (712)
  is automatic if `width()` uses the cropped presented height — which it
  already does (`cropped_height(nh)`);
- the road atlas's half-domain clamp `[-256,255]` and the panorama wrap stay
  valid: they are in *source* atlas pixels, and the N× renderer divides output
  x by N before sampling;
- adaptive width at N× should be clamped like today (320 minimum logical width,
  4096 resource bound). At 4× 32:9 the canvas would exceed 4096, so the
  existing bound must be applied at the N× size, and the fallback (native
  presentation) must be visible rather than a crash.

### 5.3 60 fps synthesized frames

Two composition axes, as described in §2.2. The existing temporal policy is
unchanged: nearest source picture for discrete state, interpolated H-scroll for
plane B, matched sprite coordinates, no VSRAM interpolation across time. The
extra sub-line resolution is orthogonal and reuses the same row state, so
`docs/FRAMERATE.md`'s artefact rules still hold; the road artefact checker must
be extended to N× (§8, S3).

### 5.4 Split-screen 2P, menus, and the Off guarantee

- **2P split-screen** stays native 4:3 and is excluded from N× exactly as it is
  excluded from the widescreen qualifier (`$FF189E != 0`, `race()` returns
  0). Later extension: N× per viewport, but the 2P picture uses the whole
  224 lines with its own raster, so it needs its own qualifier and tests.
  Proposal: not in the first implementation.
- **Menus/shop/results/intro** stay native, centred, as today (`WIDESCREEN.md`
  §Modes). The N× option must not change their canvas.
- **Off / 1×**: `present_window` keeps returning the stock crop; the render
  scale hooks are not entered; `width()` returns today's value; every frame
  hash stays identical. This is a per-step acceptance check (§8).

### 5.5 The engine's "Internal resolution" option

Today the row is hidden for TG2 by patch 0017 because `tg2_video` owns rows and
the engine's HD path is bypassed (`main.c`: `s_hd_requested && !ui_open &&
!s_video_frame.owner`). The engine's HD renderer is a *supersampled VDP
re-render* plus a GPU upscale — it cannot produce N× road geometry, so
un-hiding it as-is would repeat the old no-op.

Proposal: keep the row (patch 0017 stays), and let the game provider own the
scale through its own Mod row:

```ini
[mods.highres]
scale = 2          ; 1 (off) | 2 | 3 | 4
```

If the owner prefers one control, the later implementation can instead consume
`g_app_config.internal_scale` (patch 0033 exposes it to `GameVideo`) and drop
the `hide_internal_resolution` flag — decision in §9. Either way the value is a
*render scale*, not a window scale.

### 5.6 Weather, tunnels, hills, night

- Weather: per-line plane-A sampling continues; N× divides output coordinates
  by N before sampling. The existing rule (sparse particles, no edge smear)
  is unchanged.
- Tunnels: the "continue the native edge colour" rule is a 1× rule for
  margins; at N× there are no margins, and the tunnel must be sampled per line
  at N×. Its plane-A texel is a solid wall, so nearest at N× is correct; the
  opening silhouette is where the sub-pixel rule applies.
- Hills: width/centre are both per line; the road strip rasteriser handles them
  exactly as in §1. The crest case (two road bands with a ground band between)
  is visible in the measured data (e.g. lines 158–207 alternate bands) and must
  be rendered band by band, not as one polygon.

---

## 6. Question 5 — cost

### 6.1 Measured per-pixel cost of the row work

A micro-benchmark replicating the renderer's per-output-pixel work (plane-B
atlas sample with `road_x`, plane-A sample, palette lookup — the dominant cost
in `game/tg2_video.c`'s margin loop) on this Mac (Apple Silicon, arm64, clang
`-O2`), 300 frames, atlas + scroll data taken from the live Auckland capture:

| Scale | Canvas (4:3) | ms/frame | Canvas (16:9) | ms/frame | ns/pixel |
|---:|---|---:|---|---:|---:|
| 1× | 256×224 | 0.28 | 398×224 | 0.43 | 4.7–4.9 |
| 2× | 512×448 | 1.09 | 796×448 | 1.67 | 4.7 |
| 3× | 768×672 | 2.46 | 1194×672 | 3.84 | 4.8 |
| 4× | 1024×896 | 4.28 | 1592×896 | 6.74 | 4.7 |

Linearity is clean (4.66–4.88 ns/pixel over a 16× pixel-count range), so the
model is trustworthy. Note this is the *nearest* sampling cost; a filtered
vertical road resample plus edge coverage roughly doubles the **road rows
only** (the road is ~28 % of a race picture's rows), so budget +25–50 % over
these numbers for the real renderer.

Presented 16:9, Hide-overscan-cropped pictures (the shipping shape):

| Scale | Canvas | Pixel count | Estimated row cost (this Mac) |
|---:|---|---:|---:|
| 1× | 356×200 | 71 k | 0.35 ms |
| 2× | 712×400 | 285 k | 1.4–1.7 ms |
| 3× | 1068×600 | 641 k | 3.1–4.5 ms |
| 4× | 1424×800 | 1.14 M | 5.5–8 ms |

Add sprites (the capture already draws a few thousand margin pixels; at N×
every actor is drawn by us, so budget another 0.3–1 ms at 2×) and the HUD
(a few thousand pixels, negligible).

### 6.2 Whole-frame context

The runner's own telemetry during the measured turbo runs gives
3.0–4.2 ms/frame for the emulation + current renderer (600-frame windows,
`frame_performance` columns; `build/highres/cost-*`). The guest emulation
dominates, and the widescreen renderer's marginal cost (0.1–0.4 ms) is inside
the run-to-run noise of that telemetry — which is why §6.1 benchmarks the row
work directly.

Frame budget at 60000/1001 Hz is **16.7 ms**.

### 6.3 Estimates for the target machines

Scaling this Mac's 4.7 ns/pixel by the single-core memory-throughput ratio to a
Ryzen 5 3500U / Steam Deck (≈2.5–3.5× slower on this access pattern; **not
measured here**, flagged as an estimate):

| Scale (16:9, cropped) | This Mac | 3500U / Deck (≈3×) | Verdict at 60 fps |
|---:|---|---|---|
| 1× | 0.4 ms | ~1.2 ms | fine |
| 2× | 1.4–2.5 ms | 4–7 ms | fine on both |
| 3× | 3.1–5.5 ms | 9–16 ms | marginal on Deck |
| 4× | 5.5–9 ms | 17–27 ms | GPU or 30 fps only on Deck |

Plus the guest (3–5 ms on the Deck class). Proposed defaults: **2× on all
platforms**, up to 3×/4× on desktop with a warning, and a GPU path for 3×+ if
the owner wants 4× everywhere (see §9).

### 6.4 Does any part need the GPU?

- 2× CPU-only is comfortable on all targets.
- 3×+ benefits from GPU, and the engine already has an SDL-Renderer GPU path
  (`genesis_hd_gpu_render`) used by the "Internal resolution" feature; but that
  path consumes the *VDP raster*, not our N× rows. A GPU N× path would need a
  game-owned shader/texture upload (a new texture of the presented size, one
  upload per frame, plus a composite pass). That is a bigger engine seam and
  should be a separate step *after* the CPU renderer is correct and qualified.
- Recommendation: implement CPU first (1×–2× shipping, 3× desktop-only),
  measure on the Deck, then decide on GPU.

---

## 7. Proposed architecture

### 7.1 Where it lives

```
game/tg2_video.c        presentation policy (scale option, canvas, crop, present_window)
game/tg2_highres.c/.h   NEW: N× frame builder (road strip rasteriser, background,
                        sprites, HUD placement) — no engine knowledge
game/tg2_options.c      the [mods.highres] row (task 28 owns this file right now)
```

`tg2_highres.c` is fed a **row state** and a **scene**, produces the N× picture
into the presented framebuffer, and never touches the guest.

### 7.2 Compact per-row capture

Instead of the 60 fps path's 64 KiB `GVDP` copy per row (113 MiB history), the
N× builder needs ~200 bytes per row:

```c
typedef struct {
    unsigned char reg[24];      /* VDP registers at this line              */
    unsigned short vsram[2];    /* plane A / plane B vertical scroll       */
    unsigned short cram[64];    /* palette at this line (raster changes)   */
    unsigned short hscroll[2];  /* plane A / plane B H-scroll for this row */
    unsigned char bank[2];      /* palette bank seen at the left/right edge*/
    short width_k;              /* normalised atlas row used by the road   */
    unsigned char flags;        /* road / ground / panorama / sky / window */
} RowState;
```

Captured per presented picture only when scale > 1 (zero cost otherwise). The
per-frame VRAM (64 KiB), the scene capture (`$B5FA`, `$6982`, `$67EE`) and the
SAT are already available.

### 7.3 Road strip rasteriser

For each output row `r` (0..H*N):

1. `src = r / N`, `frac = (r % N) / N`;
2. resolve rows `src`, `src+1` of the picture; if their atlas rows belong to the
   same pair family, `k_real = lerp(k(src), k(src+1), frac)`; otherwise use
   `k(src)`;
3. bank = bank(src) (nearest, never blended);
4. `width = width_from_k(k_real)` — the measured ramps in §1.4 (`4 + 2k` with a
   2/4 px saw-tooth for rows 0–287, `≈4 + 5k` with 4/6 px steps for 288–431),
   expressed as a per-template slope table rather than a hard-coded constant,
   so a different track descriptor cannot silently break it;
5. `centre_real = lerp(centre(src), centre(src+1), frac)`, plus the 60 fps
   temporal fraction when synthesising;
6. per output column `c`: `src_x = (c - origin)/N`; the strip spans
   `[centre- width/2, centre + width/2]`; inside, sample the authored atlas at
   `src_x - centre` (nearest for interior texels; the silhouette column uses
   analytic coverage so the edge is smooth at N×);
7. colour = captured CRAM[bank|nibble]; the row's ground/panorama rows use the
   same per-column mapping with their own scroll.

Hills, crests and multiple road bands per frame fall out of the per-row/band
classification the capture already provides (the atlas row ranges encode the
band). Nothing here needs the game's curve/hill formula: the per-line state is
finer-grained evidence than the formula would be, and it is what the game
actually drew.

### 7.4 Presented height (the engine seam)

Today `present_window` may only *crop* within `native_h` (patch 0012
contract), and `MAX_SCREEN_HEIGHT` is 480 with the framebuffer/texture sized by
that constant; `display_logical_height()` also halves any picture taller than
240 lines as if it were interlaced. An N× picture therefore needs a real seam:

**Patch 0033** (proposed): a `GameVideo.presented_size` style extension, e.g.

```c
/* Called once per completed frame, before the crop. A provider that returns a
 * positive height > native_h has already written that many complete rows into
 * the framebuffer; the runner reports that height to screenshots, hashes, the
 * overlay, the logical canvas and the texture. */
int (*presented_height)(int native_w, int native_h);
```

with the supporting changes:

- `MAX_SCREEN_HEIGHT` (or a per-frame bound) sized for the maximum supported
  scale (4 × 224 = 896) so the buffers and texture fit;
- `display_logical_height()` must not squash a tall non-interlaced picture: gate
  the >240 heuristic on the VDP's interlace mode instead of the height;
- the linear filter's picture-bounds clamp (patch 0025) must use the N× height;
- `framebuf_active_hash()` must hash the N× active region (the acceptance
  hashes in §8 are then taken at scale 1, where it is unchanged);
- the margin/road audit hooks keep seeing native rows (they are per-row debug
  outputs).

Alternative seam if the owner prefers a minimal engine surface: keep the
presented height native, add a second `uint32_t *presented` buffer supplied by
the runner at N× size, and swap pointers in the present path. It is more code
in the runner for the same effect; patch 0033 as above is smaller.

### 7.5 Presentation chain at N×

```
guest rows (native)            -- existing sink
  -> compact RowState capture  (only when scale > 1)
  -> tg2_highres_build()       (post-frame, writes H*N rows into the framebuffer)
  -> present_window            (crop rows 8N..208N, unchanged semantics)
  -> linear filter / nearest   (patch 0025 clamp at N× height)
  -> NTSC stage slot           (refused when scale > 1; native only)
  -> scanline stage slot       (runs at output resolution, works at N×)
  -> SDL upload + render
```

---

## 8. Implementation plan (each step independently verifiable)

Every step ends with the same mandatory gates, recorded as evidence:

- **G1:** Off (all options Off) frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD` unchanged.
- **G2:** `dispatch_misses.toml`, `floor_coverage.toml`,
  `interior_label_misses.toml`, `floor_unsafe.toml` all 0 entries after every
  run.
- **G3:** stock 1× + widescreen + 60 fps canonical comparisons still pass
  (RAM/VRAM/native-centre at frames 600/1350/2800/3300/4501).

### S1 — Row-state capture and the option skeleton (no visual change)

**Done (task 31):** compact capture + scale skeleton, §12.

- Add `[mods.highres] scale` (1..4, default 1), env override
  `TG2_HIGHRES_SCALE`, and a `tg2_video` status field.
- Capture `RowState` per race row when scale > 1.
- Acceptance: with scale = 1 the build is bit-identical (G1–G3); with scale > 1
  and the builder stubbed to copy native rows, the picture is still identical
  at 1× and the capture's cost is measured and reported.
- **Check:** `probe_run.py --frames 360` + the standard widescreen verification
  (`tools/verify_widescreen.py`), plus a dump of the captured row state versus
  the live `rows[]` for 3 frames.

### S2 — Engine seam for a taller presented picture (patch 0033)

**Done (task 31):** `GameVideo.present_frame`, §12.

- Implement `presented_height` + buffer/texture sizing + the interlace and
  linear-filter corrections; no game behaviour yet.
- Acceptance: a temporary test provider that returns `2×native_h` with a
  synthetic pattern presents correctly in a windowed run and in screenshots;
  interlaced/2P frames are unaffected; with the provider returning 0 the build
  is bit-identical (G1).
- **Check:** `--widescreen off/16:9` screenshots at 2× height; G1–G3.

### S3 — Road + background at N× (the core)

- Implement `tg2_highres_build()`: road strip rasteriser, sky, skyline, ground
  at N×; keep sprites/HUD native-sized in the frame for now (drawn by the
  existing row renderer at 1× in the N× frame is *not* acceptable — instead the
  builder draws the native picture's non-road rows scaled by nearest until S4
  replaces them; this keeps the step visually coherent and testable).
- Acceptance:
  - 2×/3×/4× screenshots on straight, curve and hill frames of Auckland
    (`build/highres/`, frames around 8347/8535) show a continuous road with no
    gaps, no fan-shaped duplicates, no striped tearing;
  - the existing road artefact checker, adapted to N× (`check_road_artifacts.py`
    with an N× stride), reports 0 violations on ≥ 3000 presented frames;
  - the margin audit rules (no black gap, no ground-colour break, no brief
    backdrop line) are re-run at N× with 0 violations;
  - **downscale check** (the HD-pack rule, applied to the whole frame): box-
    downsample the N× picture by N and compare with the 1× reference; the
    silhouette and colours must match within a documented tolerance (road edges
    are allowed to differ by antialiasing; stripe counts and centres must not).
- **Check:** a new `tools/check_highres.py` that automates the above plus PNGs.

### S4 — Sprites at N× with sub-pixel positions and detailed variants

- Draw the pre-cull scene (`$B5FA` capture) at N×: resolve each object's model 0
  (most detailed) read-only from `A1`, scale to the captured on-screen size,
  place at sub-pixel coordinates, filter in RGB after palette lookup, honour
  priority and flip.
- Acceptance:
  - sprite count, screen positions ×N and palette attribution match the 1×
    reference for a fixed frame set (tolerance: < 1 output pixel);
  - downscale check as in S3, now including actor silhouettes;
  - no priority inversion on the tunnel/road frames;
  - all 2P frames unaffected (N× still off in 2P).
- **Check:** `check_highres.py` extended with a sprite-position table; manual
  PNG review of 6 frames (opponent cars, trees, signs at three distances).

### S5 — HUD, plane-A effects, weather (and the HUD scale decision)

- HUD drawn at the chosen rule (native 1× sharp, or exact integer N×); map
  markers and the sprite-phase HUD cluster included; tunnel continuation,
  car and weather at N×.
- Acceptance: HUD/marker pixel offsets match the 1× rule at every capture frame
  (the existing `verify_hud_map.py` logic, scaled); the rain replay
  (`check_weather_captures.py` equivalent) shows particles at N× coordinates
  with the same density; tunnel before/after/mouth frames show no seam.
- **Check:** extend `verify_hud_map.py`, `check_weather_captures.py` for N×.

### S6 — 60 fps at N×

- Compose temporal interpolation over sub-line rows using the existing nearest-
  endpoint policy.
- Acceptance: 30 synthesized frames on the baseline route with 0 road-audit
  violations at N×; the same-input replay comparison (WRAM/player-record
  hashes, lap splits) unchanged; Off/On audio identical.
- **Check:** `tg2_replay_route.py` + `compare_race_replay.py` pair (as in
  `FRAMERATE.md`), adapted to N× capture.

### S7 — Option surface, UI text, presentation interactions

- Launcher Mods row and overlay row ("Render scale 1×/2×/3×/4×"), settings
  persistence, `settings.ini` docs; NTSC mutual exclusion note; scanline stage
  note; adaptive width clamps at N×; live switching behaviour (apply on next
  race start, like the 60 fps latch).
- Acceptance: option round-trips through settings.ini and both UIs; at 1× the
  row is a no-op; screenshots at every scale; the launcher text lists the cost
  caveat; NTSC cannot be enabled with scale > 1.

### S8 — Perf gates and platform defaults

- Measure the real renderer at 1×/2×/3×/4× on this Mac and (when hardware is
  available) on the Deck; record the numbers next to §6.
- Acceptance: 2× holds 60 fps on the Deck-class target (measured, not
  estimated); 3× documented as desktop-only; 4× behind a warning until the GPU
  path exists.

### Notes on ordering

S1 and S2 can run in parallel. S3 is the bulk. S4/S5 need S3's builder. S6 must
come after S3 (temporal policy depends on row state), S7 after S5, S8 last.
The road work first is deliberate: it is the largest visible gain, the most
evidence-backed, and it validates the capture + seam with the least new code.

---

## 9. Decisions needed from the owner

**Decided by the owner on 2026-11-09** (coordinator's recommendations,
approved as a set). Where they differ from this section's original
recommendations, the decision wins:

| # | Question | Decision |
|---|---|---|
| 1 | Road/silhouette look | **Smooth** analytic edges at N×. |
| 2 | HUD size at N× | **Integer N×** (nearest, crisp, same relative size) — *not* native 1×, which would make the HUD N times smaller on screen. Applies to the player car and map markers too. |
| 3 | Detailed sprite variants | **Always promote** to the most detailed variant, guarded by the downscale check. |
| 4 | Which control drives the scale | **The engine's "Internal resolution" row** (un-hidden for TG2 and driving the provider), as the owner asked on 2026-11-07 — not a separate `[mods.highres]` option. |
| 5 | Default | **1×** until the cost is measured on the Steam Deck. |
| 6 | First implementation scope | **S1–S3 (road + background) as an experimental option**, then S4/S5. |
| 7 | 2P split-screen at N× | **Later.** |

The original analysis follows.


1. **Look of the road/silhouettes.** Smooth (analytic edges at N×, sub-pixel
   steps) vs exact staircase reproduction (nearest, only more pixels). My
   recommendation: smooth, because it is the only way N× is visibly better than
   a plain upscale, and it uses the game's own width/centre numbers.
2. **HUD size at N×.** Native 1× (sharp, smaller relative to the frame) vs
   integer N× (crisp, proportional). My recommendation: native 1× per the
   owner's "keep the HUD sharp", with a "HUD scale" row later if he wants it
   bigger. Note this also affects the player car and the map markers.
3. **Detailed sprite variants.**
   Redraw every actor from its most detailed model (the owner's request) —
   confirm that a filtered 64 px tree standing in for the authored 20 px art is
   acceptable. Alternative: only promote when the upscale factor is ≥ some
   threshold (e.g. > 2×), keeping far actors authored.
4. **Reuse of the engine's "Internal resolution" row.** Keep it hidden and use
   `[mods.highres] scale` (my recommendation), or un-hide it and make the
   engine's scale drive the provider (one control, more engine coupling)?
5. **Defaults.** 2× everywhere with 3×/4× opt-in (my recommendation), or 1×
   default so nothing changes until the player opts in?
6. **Scope of the first implementation.** Road + background only (S1–S3), then
   sprites, then HUD — or all of S1–S5 in one release? My recommendation: ship
   S1–S3 as an experimental option, then S4/S5.
7. **2P split-screen at N×** — later or never? My recommendation: later.

## 10. Evidence index and reproduction

Tooling added by this task:

- `tools/highres_probe.py` — drives a race through the game's own password
  screen and samples `tg2_video {"rows":1}`, the player record, full VRAM,
  CRAM, H-scroll table and SAT; optionally logs the spike's LOD ring. Pure
  read-only TCP queries. Usage:

  ```sh
  flock ~/.cache/tg2-heavy.lock python3 tools/highres_probe.py \
      --port 4640 --out build/highres/road-c00 --country 0 --seconds 24 \
      --every 90
  ```

- `game/tg2_lod_probe.c` (spike commit, see below) — two read-only hooks
  (`$B584`, `$B5F0`) and a `tg2_lod` TCP command; dumps binary records and, via
  `TG2_LOD_DUMP=<path>`, a 48-byte-per-entry ring.

Captured evidence (private):

| Path | What |
|---|---|
| `build/highres/road-c00/samples.json` | 12 race samples: rows, player record, full VRAM, CRAM, SAT |
| `build/highres/atlas-widths-002.json` | per-atlas-row road silhouette from that VRAM |
| `build/highres/lod-c00/lod.bin` | 31,607 spike records (mapper entry + resolved piece list) |
| `build/highres/lod-c00/samples.json` | the same run's VRAM/WRAM dumps for pattern sets |
| `build/highres/spike-off/stderr.log` | Off hashes with the spike build (frame 60/300) |
| `/tmp/bench-data.bin`, `/tmp/bench.c` | the cost micro-benchmark data/source (rebuildable) |

Spike commit: it is a separate commit marked `spike:` and should **not** be
merged. It exists to supply the LOD evidence; the probe hooks add ~0.1 % to a
frame and change no output (Off hashes verified). Recommendation: drop the
`game/tg2_lod_probe.*`, the two `game.toml` hook sites and the CMake/spec
wiring before the implementation branch starts; keep `tools/highres_probe.py`
(the script does not depend on the probe binary).

ROM checks used while writing this: `~/roms/genesis/tg2.bin` CRC32 `BD3074D2`.

## 11. What is not verified

- The per-object-type LOD ladder and the exact screen-distance thresholds
  (§3.3): mechanism and table are verified, the ladder needs the one-lap log
  described there.
- `$FF1894` bias semantics on other tracks, and the `$FF1878 == $FFFE` special
  mode's effect on LOD (the code path is verified; its trigger conditions on
  other stages are not).
- Any cost figure for Ryzen 5 3500U / Steam Deck: extrapolated from this Mac,
  not measured.
- The engine seam as specified (patch 0033) is a design, not a build; the
  interlace/linear-filter/hash interactions are reasoned from the current code,
  not tested.
- Tracks other than Auckland (16-track crop evidence exists for the current
  renderer, but not for N×), weather at N×, hill crests at N× beyond the
  measured frame, and 2P.
- The look decisions in §9 are the owner's; screenshots of a prototype are not
  part of this task.

---

## 12. S1 and S2 implemented (task 31)

**Status: S1 and S2 are built and verified on this Mac (macOS arm64, Apple
Silicon, `build/TG2Recomp` from `tools/build-linux.sh`).** S3 — the actual N×
road/background builder — is not started, so no race picture is drawn at N×
yet. Nothing here depends on the §9 decisions: the scale is read through one
function, there is no user-facing control, and the only thing that presents a
taller picture is a temporary test provider that a test must switch on.

### 12.1 What was built

| Piece | Where | What |
|---|---|---|
| Render scale | `game/tg2_highres.c`, `tg2_highres_scale()` | the single place the port reads the scale from. Default 1; `TG2_HIGHRES_SCALE=1..4` overrides it for captures. S7 replaces the `requested` source with the engine's "Internal resolution" value (decision 4). No `settings.ini` key, no launcher/overlay row. |
| Compact row capture | `tg2_highres_capture_row()`, `Tg2RowState` | 165 bytes per row: `reg[24]`, `vsram[2]`, `cram[64]`, `hscroll[2]`, `bank[2]`, `width_k`, `flags`. 203 rows per race picture (37 KB). Captured only when the scale is above 1 — the stock path pays nothing. |
| Row classification | `flags` / `width_k` | `road`, `ground` (atlas Y 432..447), `panorama` (448..511), `window`, `bank1`; `width_k` is the atlas row normalised into its authored pair family (§1.4), `-1` for non-road rows. `bank[0]`/`bank[1]` come from a bounded left/right edge probe of the live name table, so they are the palette bank actually drawn, not a lookup table. |
| Presented-height seam | engine patch 0033, `GameVideo.present_frame` | called once per completed frame, after every native row and before the presented-window crop; the provider rewrites the runner framebuffer in place and returns the number of complete rows it wrote. The crop, `[FBHASH]`, screenshots, the runtime overlay, the logical canvas and the texture upload all use that height. |
| Buffer and texture sizing | patch 0033 | `MAX_SCREEN_HEIGHT` 480 → **896** (4 × 224); interlace mode 2 (448) still fits. |
| Interlace correction | patch 0033 | `display_logical_height()` and the netplay half-view clamp now test `gvdp_interlace_double()` instead of "height > 240", so a tall non-interlaced picture is not squashed to half height. |
| Canvas | `game/tg2_video.c`, `width()`, `canvas_scale()` | an N× picture presents exactly N× the 1× canvas (356 × 2 = 712 at 16:9, 200 rows → 400). Like the crop, the canvas follows the previous completed picture, so Menus keep the stock canvas even with the scale raised. On the first race frame the provider declines the paint (the wider canvas does not exist yet) and the picture starts at 1×: one transition frame, not a squashed picture. |
| Crop | `present_window()` | the same overscan bands at N×: `8N` rows at the top and `16N` at the bottom (`native_h` divisible by 224). |
| Temporary test provider | `TG2_HIGHRES_TEST_PROVIDER=1` | a synthetic 2× native picture (gradient + checkerboard + 32-row rulers + magenta edge columns). **Off unless a test sets it**; it is not a player path and is removed when S3's real builder lands. |
| Checks | `tools/check_highres.py` | subcommands `g1`, `capture`, `s2`, `route`. Standard library only (its PNG reader needs no Pillow). |

**Deviation from §7.4.** The proposed `presented_height(native_w, native_h)`
signature has no way to hand the provider the buffer it is supposed to have
written. The implemented hook passes the framebuffer, its stride and the
current presented width, and returns the height — one seam instead of a buffer
handoff plus a separate height report. Everything else follows §7.4.

### 12.2 Measured

Capture cost, in-process timer (`TG2_HIGHRES_TIMING=1`, the clock-pair
overhead measured once and subtracted), Auckland in-race pictures, three
samples 40 frames apart:

| Measurement | Value |
|---|---|
| Cost per captured picture | **34–42 µs** across two sessions (individual pictures 29–49 µs) |
| Cost per captured row | **168–209 ns** |
| Rows captured per picture | 203 (lines 8..210; see below) |
| Share of the 16.7 ms frame budget | ≈ 0.25 % |

The 165-byte struct copy is only ≈2 µs; the two palette-bank edge probes on the
51–74 road rows dominate. S3 needs the same silhouette information (and more),
so this work is not thrown away. At scale 1 the capture is not called and
allocates nothing.

Lines 0..7 (blanked overscan band) and 211..223 (the bare-backdrop band the
game renders with a different raster opcode) are not captured because the row
renderer does not take its race-row branch there; the crop removes both bands
from the presented picture, so the captured rows cover every presented race
row exactly. The `capture` checker compares only rows whose capture serial is
the latest picture, which is exactly the set the live `rows[]` was written for.

### 12.3 Verified gates

| Gate | Result |
|---|---|
| **G1** scale 1, all options off (`--widescreen off --frames 360`) | frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD` — unchanged |
| **G1 with scale 2 and the S1 builder stub** | frames 60..360 identical to scale 1, in `off` and in `16:9` |
| **S1/S2 byte identity across a race**, scale 1 vs scale 2 stub | baseline route replayed by frame-exact input script to frame 5600 (races at 3096+): **every** sampled framebuffer hash identical, `off` and `16:9` |
| **G1 with the S2 test provider enabled on menus** | identical to stock (the provider declines every non-race picture) |
| **G2** manifests | `dispatch_misses`, `floor_coverage`, `interior_label_misses`, `floor_unsafe` all 0 entries after every run above |
| **G3** stock 1× + widescreen | `tools/verify_widescreen.py` (off / 16:9 / 21:9) passes at scale 1 |
| **G3** 60 fps canonical | a `TG2_RACE_60FPS=1` run keeps both canonical hashes at scale 1 and at scale 2 with the stub |
| **S1** capture vs live rows, 3 frames | 0 mismatches on 203 fresh rows per frame (51–74 road rows classified) |
| **S2** test picture, `--widescreen off` | 256 × 400 (1×: 256 × 200), edges/rulers/gradient correct, every sampled row distinct |
| **S2** test picture, `16:9` | 712 × 400 (1×: 356 × 200), same pattern checks |
| **S2** menus with the provider on | stock canvas and height, and byte-identical to stock (title digest equal): off 320 × 224, 16:9 398 × 224, password screen 256 × 224 |
| **S2** one windowed run | cocoa window presents the 2× picture; captured and closed |
| **S2** 2P split-screen (frame-exact two-pad script, scale 2, provider on vs off) | `$FF189E != 0` sampled on 3,185 frames; presented geometry stays 224 lines × 398 wide (the 16:9 canvas, 4:3 picture); **all 7,901 framebuffer hashes identical** with the provider off and on |

### 12.4 Evidence

Private, as the repo rules require (regenerate with the commands in §12.5):

| Path | What |
|---|---|
| `build/highres-check/g1-summary.json` | all seven G1 runs, their hash series and manifest counts |
| `build/highres-check/capture/samples.json` | the three captured pictures: every row, the live row words, serials, cost |
| `build/highres-check/capture/summary.json` | mismatch count, cost per picture/row, manifests |
| `build/highres-check/s2/s2-summary.json` | the six headless S2 runs: PNG sizes, pixel digests, pattern facts |
| `build/highres-check/s2/*-race.png`, `*-title.png` | the pictures themselves |
| `build/highres-check/route/route-summary.json` | the baseline-route identity runs: hash series per scale and mode |
| `build/highres-check/split2p/split-summary.json` | the 2P runs: sampled `$FF189E`, geometry, hash comparison |
| `build/ws/` | `tools/verify_widescreen.py` evidence at scale 1 |

### 12.5 Reproduction

```sh
JOBS=3 tools/build-linux.sh                       # applies patches 0001..0033

python3 tools/check_highres.py g1                 # G1/G2 + 60 fps hashes
python3 tools/check_highres.py capture            # S1 capture vs live rows + cost
python3 tools/check_highres.py s2                 # S2 headless screenshots
python3 tools/check_highres.py route              # byte identity across a race
python3 tools/check_highres.py split              # 2P frames stay native
python3 tools/check_highres.py s2 --windowed --only 169-scale2-test   # windowed
python3 tools/verify_widescreen.py                # G3 stock 1x comparisons
```

All runs are headless (`SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`) except
the single `--windowed` check; one runtime instance at a time.

### 12.6 Not verified

- **No real N× picture yet.** The seam is proven with the synthetic provider
  only. S3's road/background builder, its cost and its look are untouched.
- **2P split-screen** is verified to stay native (§12.3), but only as an
  exclusion: N× per viewport is not implemented and was not attempted.
- **Interlaced** pictures are declined by the `native_h == 224` guard plus the
  interlace-aware halves. This game presents no interlaced picture here, so
  that guard is exercised only by the 448-line path being unreachable (the 2P
  race itself is H32 non-interlaced and is excluded by `$FF189E`).
- **Cost of the capture on Ryzen 3500U / Steam Deck** is not measured. The
  figure above is this Mac; §6.3's ≈3× scaling would put it near 0.13 ms.
- **The 4096 px canvas clamp at N×** is reasoned (§5.2) but not exercised: the
  test provider only presents 2×.
