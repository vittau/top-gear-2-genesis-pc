# Task 34: S4 — detailed sprites at N× with sub-pixel positions

**Status: prepared for the next session; implementation not started.**
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

`HIGHRES.md` §3 maps the mapper at `$B584`, the remap table at ROM `$10D42`,
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
