# Task 34: S4 — detailed sprites at N× with sub-pixel positions

**Status: implemented and locally qualified on `vittau/tg2-highres-s4`; owner visual acceptance pending.**
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

Updated 2026-11-11 by the continuing Sol worker. Implementation and local
technical qualification are complete; **owner visual acceptance is pending**.
This branch has not been merged or released. No CI, tags, submodule pin
changes, new engine patches or ROM-derived git artifacts were introduced.

### Implemented

- Immutable actor/model snapshots at the already validated hooks, detailed
  original assets, authored stepped sizes, double-precision subpixel anchors,
  per-row palette RGB/coverage filtering and native clip/depth/priority masks.
- Explicit foreground ownership replaces S3's RGB-equality-only ambiguity in
  N× terrain composition. HUD/player car, poles and tunnel/special artwork
  remain native; 2P and native menus stay excluded.
- Guest culling and final SAT ownership guards keep an actor native when no
  guest piece survives or the final/mixed pieces are inconsistent. 60-fps
  anchors agree with the actual rounded synthesized SAT cell.
- Native row replay audit, all-frame actor totals, sampled variant/position
  tables and connected silhouette-group downscale checks in
  `check_highres.py`. Diagnostic reads share the controller poll.
- A stock 1× widescreen / 60-fps Off / overscan case now selects its scene
  before the blanked first row; G3 passes. Framerate comparisons stream data.

### Decisions retained

Stepped by default; only `TG2_ACTOR_SIZE=continuous` for one review pair, no
menu row. Every promoted actor's floor agrees with the displayed native SAT;
drawn anchor agrees with N× captured subpixel anchor. Untabulated kinds use
the guest model, counted. Poles `$BD/$83/$84` and special/tunnel pieces
`$8A/$F8/$F9/$FC/$FD` remain native.

The operator highlighted the visible pole-detail mismatch in picture 05;
**[task 38](38-highres-poles.md)** now maps detailed compound head/shaft
reconstruction and is linked from HIGHRES and the roadmap. It has not started.

### Results and exact evidence

`build/s4/worker-report.md` is the full report; `qualified-summary.json` is the
scalar consolidation. Exact commands/exits are in `final-commands.json`,
`boundaries-commands.json`, `cost-commands.json` and `pair-commands.json`.
`HIGHRES.md` §§14.5–14.7 and `VALIDATION.md` record the implemented policy,
tolerances, resolved findings and results.

- Build and stock G1/G3 pass; Off hashes remain frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD`; all four manifests empty.
- 1× Off/16:9/21:9 G3 runs: 5,600 frames each, native centre/state identical.
  1× 60-fps stock repeat: 360/360 distinct pictures, unchanged sampled RAM,
  byte-identical WAV SHA-256.
- Final 4× long audit: 3,301 pictures / 812,488 road rows / 161,582 stripe
  centres, max centre error 0.5 output px, zero road/margin violations.
- 89,085 promoted actors across Auckland/Canada/rain: all-frame position,
  palette, priority and native-row replay mismatches 0; floor/analytic-anchor
  errors 0, serialized coordinate error ≤2.1e-8 output px. Unknown/model
  fallbacks 0 per track. Native SAT guards 14/6/15; fully guest-culled objects
  13,516/5,264/1,257, retained native.
- Directed 2×/3×/4×, native 32:9 2P, cap/Off/menu boundaries, Linear On,
  combined 60-fps smoke and actual tunnel/pole overlap cases pass.
- Local incremental whole-frame CPU: +0.2565 ms at 2×, +0.3831 ms at 4×
  over 900 fixed input frames, without audits/dumps/pacer work. Not Deck/GPU.

The original long command returned 1 solely because the first local-box
checker assigned a near car's detail to a far sign's overlapping box. Its
runtime, road, margins and all-frame invariants passed. The corrected
connected-group `sprite-pairs` check reuses those exact 25 pairs and exits 0;
all original metrics (including individual patch 114.25) are retained. A
Canada snow-detail global S3-threshold false positive and matching Linear On
reference are also documented, rather than hidden or solved by raising the
unchanged-region tolerance. Final S4 gates pass.

### Review pictures (ignored local artifacts)

Six native/N× same-frame pictures under `build/s4/review/`:
`01-far.png`, `02-middle.png`, `03-near-car.png`, `04-near-tree.png`,
`05-pole-rain.png`, `06-tunnel.png`. Extra requested artifacts:
`stepped-continuous.png` (frame 221, identical guest RAM) and
`pole-occlusion.png`. `pictures.json` maps their exact sources and model data.

### Remaining / resume

Coordinator: review the pictures with the owner and record his S4 acceptance
or concrete defects; the implementation is ready for that review. Keep pole
improvement task 38 visible. S5 HUD/weather/tunnel-opening artwork, full N× +
60-fps qualification (S6), live switching (S7), other-country/platform and
Deck/GPU qualification remain unverified here. No runtime or heavy step is
left running. Only the initial applied patch dirt in both submodules remains;
never commit those pins.
