# Task 34: S4 — detailed sprites at N× with sub-pixel positions

**Status: in progress (worker on `vittau/tg2-highres-s4`); see "Progress / handoff" at the end.**
Read `AGENTS.md` and [CONTINUATION.md](../CONTINUATION.md) first. Handle any
new S3/Steam Deck playtest defect before starting this step. This brief does
not start a worker or authorize a release.

**Model restriction:** implementation may only use Opus, Fable or Sol because
of the high complexity. Use supervised Orca orchestration. Follow the shared
heavy lock, ≤3 build jobs, headless probes, one runtime and no worker CI rules.

## Starting point and scope

Start from current `main`, which contains the owner-approved S3 in merge
`a205759`. Read `HIGHRES.md` §§3, 5, 7, 8 (S4), 9 and 13 before changing
`game/tg2_video.c`, `game/tg2_highres.c` or their interfaces. Keep game-specific
work in `game/`; genuine engine changes must have project-owned patches.
Read the engine's CLAUDE.md, PRINCIPLES.md and DEBUG.md before working there.

Implement the accepted S4 design: present actors from their most detailed
valid original asset variants, scaled to the captured on-screen size at N×,
with sub-pixel positions and RGB filtering after palette lookup. Preserve
priority, animation and flips, including the tunnel opening. Use only this
game's ROM assets. Guest simulation, culling, SAT and memory stay unchanged.
Off/1× and 2P must keep existing behaviour; N× remains off in 2P.

## Resolve the missing evidence first

`HIGHRES.md` §3 maps the mapper at `$B584`, the remap table at ROM `$10D42`
(**corrected by the evidence: `$57C8`, see `HIGHRES.md` §14**),
the existing pre-cull hook `$B5FA`, and relevant object records and registers.
Recheck addresses against raw ROM/disassembly before adding hooks/seeds.
The per-object-type LOD ladders and scene biases are **partially mapped**;
do not assume every object has nine variants or that index zero is always
the correct detailed asset. Single-model objects must remain valid.

The existing `Scene/Piece` capture in `game/tg2_video.c` stores resolved
integer x/y, attr and size. It does not yet retain all original object/model
metadata or sub-pixel projection needed by S4. At `$B5FA`, current A1 is used
as the emitted piece-list pointer; the object record described at `$B584`
must not be confused with that later pointer. Extend read-only snapshots at
validated hooks, keep them aligned with the SAT actually displayed, and do
not look up mutable live guest state at presentation time. Preserve the
existing scene history and 60-fps endpoint policy.

Finish the LOD evidence with bounded retrospective capture over representative
tracks, grouping object identity/type, selected band/model, projection,
mapping/pattern sets and attributes. Capture streams remain under ignored
build directories. Derive the selection policy from this evidence.

## Composition and boundaries

An explicit coverage/layer representation should distinguish sprites and
plane A from the road. S3 currently uses a colour-equality terrain mask with
a documented same-colour ambiguity. Do not add more colour guesses as a
substitute for correct actor ownership/occlusion. Keep S3's fitted road and
geometry fixes intact.

HUD detail, weather resampling and tunnel-opening artwork reconstruction are
S5. Full N× + 60-fps qualification is S6; live scale changes are S7. Preserve
their current behaviour and state limitations honestly; do not expand this
task into those stages without a concrete dependency or owner direction.
The experimental scale row remains default 1× and applies after restart.

## Acceptance and evidence

- Stock Off/1× G1–G3 still pass (frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD`), and all four execution manifests are empty after runs.
- Object identities/counts, screen positions ×N (error <1 output pixel),
  palette banks and priority agree with the captured 1× reference. A detailed
  variant may have a different number of pieces; compare actor semantics,
  not an artificial equality of piece counts.
- Same-frame downscale comparisons include actor silhouettes, with tolerance
  and expected detail/antialiasing differences documented, not hidden.
- Review six representative pictures covering opponent cars, trees and signs
  at three distances, plus tunnel/road occlusion. No priority inversion.
- 2P stays native and unchanged; native menus and extreme-width/cap guards
  remain intact. Add targeted regression checks for any changed boundary.
- Extend `tools/check_highres.py` with a sprite-position/variant table and
  useful independent coverage checks. Reuse valid S3 evidence. Short directed
  per-scale coverage plus one long audit at the largest effective scale is
  sufficient unless a real scale-dependent failure appears; no blanket
  repetition of the full track × scale matrix.
- Measure incremental CPU cost without audit/dump/pacer work. Do not claim
  Deck/GPU performance from a development-host measurement.
- Commit/push small coherent changes; report commands, exits, hashes,
  manifest counts, capture paths and limitations with `worker_done`.
  Update HIGHRES/VALIDATION/status. Owner visual acceptance is still required
  for S4; the existing S3 approval does not approve future sprite changes.

## Progress / handoff

Updated 2026-11-11 (CHECKPOINT at ~75% of the Claude 5 h window) by the S4
worker (Claude Fable 5.2), branch `vittau/tg2-highres-s4`. A new agent can
continue from this section plus `HIGHRES.md` §14.

### Decisions already taken (do not reopen)

- **Size: stepped by default** (authored 1× size of the guest's band). One
  internal switch `TG2_ACTOR_SIZE=continuous` (env only, no menu row) for ONE
  extra stepped-vs-continuous same-frame review pair (approaching car or
  tree). Spend nothing more on continuous.
- **Position criterion:** drawn N× anchor vs N × captured sub-pixel anchor
  (< 1 output pixel), and `floor(anchor)` must equal the 1× SAT position for
  every promoted actor; report the maximum error.
- **Poles (`$BD/$83/$84`) and tunnel/special pieces (`$8A/$F8/$F9/$FC/$FD`)
  stay native** in S4, recorded as a follow-up. Verify native poles and
  promoted actors occlude correctly where they overlap and put one such case
  in the review pictures if it occurs on the three tracks.
- **Untabulated kinds fall back to the guest's own model; count fallbacks per
  track** in the sprite table.

### Done (commits)

- `e4b4205` — evidence phase: hooks `$B42E`, `$B4D6`, `$B584` in
  `game/game.toml` (checked against raw ROM), `game/tg2_actors.c` (projection
  latch + `TG2_ACTOR_LOG` evidence stream only), `check_highres.py lod`,
  `tools/analyze_actors.py`, `tools/actor_sheet.py`, `HIGHRES.md` §14.
- Stock G1 on the build **with** the new hooks: exit 0, frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD` in all five
  configurations, four manifests empty (`build/s4/g1-hooks.log`).
- 1× 16:9 probe: the displayed scene is selected every picture
  (`displayed == published`, e.g. 350/350 at frame 3500): `build/s4/probe_scene.py`.

**No presentation code exists yet.** Nothing is half-edited; the tree builds.

### Exact next step: implement presentation (design already worked out)

1. **Snapshots (`game/tg2_actors.c`, storage in `Scene` of `tg2_video.c`).**
   A draft header with the intended API is in `build/s4/tg2_actors.h.draft`
   (ignored dir; recreate from this text if missing): `Tg2Actor` (sub-pixel
   anchor, guest anchor, clip row, `first_piece` depth key, guest/detailed
   model piece ranges, keys, kind, models, fallback, high), `Tg2ActorSet`
   inside `Scene`, `tg2_actors_object()` at `$B584` returning the actor index
   that the `$B5FA` hook stores in each `Piece` (`Piece.actor`, −1 = native).
   - Not promoted (stay native): no latched projection for the same record and
     X, `$FF1878` = `$FFFE`/`$FD66`, kinds `$82 $83 $84 $BD $8A $F8 $F9 $FC $FD`,
     invalid pointers, 2P (`$FF189E`).
   - Screen coordinates: `gx = D1.w + 128`, `gy = D2.w + $FF2452 − 128`
     (base line: the object occupies rows `< gy`), clip row
     `$FF1836 + $FF2452 − 128` (rows ≥ clip hidden). `x = gx + (D1 >> 16)/65536`
     from the latch. `y`: latched `D2.w` (+ `D2 >> 16`/65536 on the `$B42E`
     path), clamped to `$FF17BC − 2` like `$B434/$B4DC`, minus
     `h·scale/65536/2^$FF242A` (`h = $FF17DC`, `scale = $FF17E0`), then clamp
     into `[gy, gy + 255/256]`.
   - Model pieces relative to the anchor, per 10-byte header
     (`set, halfw, height, attr, $8888`): `x0 = attr&$800 ? +halfw : −halfw`;
     piece `dx = x0 + (attr&$800 ? −xoff − pw : xoff)`, `dy = −height + yoff`,
     `attr = (((hattr|8(A1)) ^ (pa&$1800)) + (pa&$7FF)) | $FF234E`
     (+`$8000` when `$FF22E8`); later pieces are in front.
   - Detailed model: scenery 0; cars per `HIGHRES.md` §14.3 rule 2.
2. **Per-picture prepare** (first race row, with the displayed `GVDP`):
   rasterise each distinct guest/detailed model to palette indices from
   `v->vram`, measure opaque extents, `size = guest/detail` on the detailed
   model's longer axis; `size > 1` → fallback to the guest's model. If the
   guest model cannot be rasterised the actor stays native.
3. **Actor-free native row (`tg2_video.c`).** Enable the raster-row seam
   whenever the scale is above 1 (`filter_raster_enabled`,
   `scanline_presented`, and the 60 fps `gvdp_capture_presented_scanline`
   branch). Per race row: walk the SAT like the engine
   (`genesis_vdp.c sprite_render_line`: 64 sprites, 16 per line,
   `x == 0 && on_line > 1` masks the rest, 256-pixel budget), skip SAT entries
   whose matched scene piece belongs to a promoted actor, and recompose only
   the pixels an actor covered with the engine's rule
   (`genesis_vdp_compose.h`: plane byte = index | $40 opaque | $80 priority).
   Record per 1× canvas pixel: `foreground` (not plane B), `occluder`
   (high-priority plane pixel; in margins the existing rule: plane-B high,
   weather pixel, window side) and `front` (0 none, `$FFFF` HUD/player car,
   else scene piece index + 1 of a native mapper sprite). SAT→piece matching
   must be done on the endpoint's own unmodified SAT (store `sat_piece[64]` in
   `Scene` in `select_scene`), because `mix_sprites` moves SAT entries on
   synthesized 60 fps pictures. In the margin sprite loop skip promoted
   pieces. `hud_row` (HUD edges mode) re-exposes "ordinary SAT sprites" under
   vacated HUD pixels: skip promoted SAT entries there too.
   Self-check to add: with no entry flagged, the recomposed row must equal the
   engine's native row (count mismatches under an env audit).
4. **Builder (`tg2_highres.c`).** Terrain mask = colour equality AND NOT
   `foreground` (removes the S3 same-colour ambiguity without changing other
   pixels). After the rows (and the Linear On filter), paint actors far → near
   (capture order): per output pixel map to texel space, box filter of width
   `max(1, 1/(size·N))` texels in premultiplied RGB after the row's own palette
   (`Tg2RowState.cram`), skip rows ≥ clip·N, skip where
   `(occluder && !high) || front == $FFFF || front − 1 >= first_piece`.
   Rows that did not go through the actor-free path keep native sprites, so
   paint only rows flagged as actor-free.
5. **1× reference dump.** `tg2_highres {"dump":…}` reads the 1× canvas back
   from the framebuffer, which will now lack promoted actors. Keep a true 1×
   reference row (native centre + promoted margin pieces) for the dump.
6. **60 fps.** Interpolate actor anchors in `mix_pieces` (match by record,
   nearest anchor), everything else from the nearer endpoint.
7. **Checks (`tools/check_highres.py`).** New TCP JSON of the prepared actors
   (kind, record, guest/detailed model, fallback reason, guest anchor,
   sub-pixel anchor, size, palette lines, priority, drawn N× box, visible
   pixels, pieces/inside/matched in SAT). Table: counts by kind per track,
   fallbacks per track, max `floor(anchor) − guest`, max drawn-anchor error,
   palette/priority agreement; actor-free row self-check; downscale with
   actor silhouettes. Then gates G1–G3, 2P split, cap, cost with
   `TG2_ACTORS=0` vs on (no audit), six review pictures + the stepped vs
   continuous pair, docs (HIGHRES §14/§13, VALIDATION, STATUS).

### Rebuild / validate

```sh
git submodule update --init --recursive
flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh   # applies patches, regenerates
python3 -m venv build/venv && build/venv/bin/pip install numpy pillow capstone
flock ~/.cache/tg2-heavy.lock build/venv/bin/python tools/check_highres.py g1
flock ~/.cache/tg2-heavy.lock build/venv/bin/python tools/check_highres.py lod --track canada --frames 3600
build/venv/bin/python tools/analyze_actors.py build/highres-check/lod/canada/actors.csv
build/venv/bin/python tools/actor_sheet.py build/highres-check/lod/canada --all
```

Reduced S3 recipe for the final qualification: `HIGHRES.md` §13.4.

### Evidence (ignored build dirs of this worktree)

- `build/highres-check/lod/{auckland,canada,bavaria-rain}/`: `actors.csv`,
  `snap.{vram,cram,ram,png}`, `actor-sheet.{png,json}`, `lod-summary.json`.
- `build/s4/`: `{auckland,canada,bavaria-rain}.txt` (ladders),
  `sheet-*.txt` (art sizes), `g1-hooks.log`, `dis-*.txt`, `xref.py`,
  `probe_scene.py`, `tg2_actors.h.draft`.

**Uncommitted state:** none. The engine and `recomp-ui` submodules show as
modified because the project patch stack is applied; never commit those pins.

### Sol continuation — presentation first pass (2026-11-11)

Immutable actor/model snapshots, per-picture indexed art and the RGB/coverage
painter are now implemented in `game/tg2_actors.*`; `Scene` owns the captured
metadata and endpoint SAT ownership. The row path exposes explicit foreground,
plane occluders and native sprite depth, removes promoted SAT entries in host
composition only, and keeps a native-reference dump; actor anchors interpolate
with the existing 60-fps endpoint policy. `TG2_ACTORS=0` retains a cost baseline.
No new hooks, seeds or engine edits were needed.

Build: `flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh`, exit 0
(`build/s4/build-present.log`). Snapshot-stage stock G1: exit 0, both canonical
hashes in all five configurations, all four manifests empty
(`build/s4/g1-snapshots.log`). Presentation qualification is in progress: this
is an implementation checkpoint, **not accepted S4**. Next: inspect the first
same-frame picture and TCP actor table, fix any composition/position defects,
then add the independent actor checks and execute the reduced acceptance plan.

The directed 2× actor table (`build/s4/short2/.../drive-summary.json`) sampled
280 actors: floor/guest-piece/palette/priority mismatches all 0, drawn-anchor
error ≤1.1e-8 output px (JSON precision), fallback count 0, native-row replay
mismatches 0. Road checks passed; the margin checker exposed duplicate audit
rows while the true-native dump pass was active, which is now suppressed.
The rerun/long 4× qualification is `build/s4/long4` (still running at this
checkpoint). The player's car is explicitly left native using the ROM's own
`$B53A..$B542` player-number comparator (`$FF17D6 == $FF1878`), rather than
assuming every car-table entry is an opponent. Anchor storage is double
precision so a fraction near 1 cannot round up across an integer boundary.

`check_highres.py drive --actors` adds the independent guest-piece position,
ROM variant, palette/priority and native SAT replay tables. Optional local
`--save-state/--load-state` race checkpoints stay ignored and allow short
per-scale follow-ups after 30 frames of republished scene history. Cost mode
refuses actor audits. Remaining work: finish the long run, directed other
scales/weather/poles and filter check, G1/G3/boundaries, CPU A/B, silhouette
review pictures and the single stepped/continuous pair, then final docs.
