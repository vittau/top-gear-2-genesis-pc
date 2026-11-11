# Task 38: detailed compound poles at N×

**Status: mapped follow-up; not started.** The owner highlighted the visible
detail mismatch in S4 review picture `05-pole-rain`: the cars/scenery are
promoted while poles still use their authored native bands. Keep this as an
explicit visual improvement, not an implicit consequence of finishing S4.
Read `AGENTS.md`, `HIGHRES.md` §14 and task 34 before implementation.
Only Opus, Fable or Sol may implement this S4 extension; use supervised Orca
orchestration, the shared heavy lock, ≤3 jobs, headless probes and no worker CI.

## Goal and evidence already available

Promote pole kinds `$BD/$83/$84` from their most detailed original ROM assets
at N×, with detail consistent with neighbouring promoted actors. Preserve
the captured authored size/position, variable shaft height and segment order.
No new art and no guest simulation/SAT/culling changes.

S4 intentionally leaves these compound objects native. Raw-ROM sites
`$B986/$B990/$B99A` build the head plus stacked shaft segments, using the
segment-height table at `$10AA4 + 2*level` and height `scale/16 + 3`.
The captured shaft record is `$FF8E76`; each component calls `$B584` directly,
so ordinary projection-latch promotion is insufficient. Re-read the raw ROM
before adding hooks or seeds; do not infer compound identity from a mutable
record at presentation time.

Starting evidence, kept under the ignored S4 build tree:

- `build/highres-check/lod/{canada,bavaria-rain}/`: mapper log and art snapshots.
- `build/s4/review/05-pole-rain.png`, `pole-occlusion.png`: the current visual
  mismatch and an exercised native-pole/promoted-actor overlap.
- `build/s4/final-{canada,rain}/.../drive-summary.json`: palette/priority,
  anchor, final-SAT and native-pole occlusion counters.

## Work

1. Capture one immutable compound identity and subpixel anchor for each pole,
   together with its head and shaft construction. Keep it aligned with the
   displayed endpoint's SAT and the existing 60-fps endpoint policy.
2. Determine valid detailed head/shaft assets from the ROM and track art;
   preserve total height, authored size bands, flips, palette and priority.
   Avoid seams, doubled caps or uneven segment thickness when minifying.
3. Integrate with S4's explicit coverage, native depth, plane priority and clip
   masks. Native/SAT and unknown-asset fallbacks remain counted and safe.
4. Extend the actor table to distinguish compound poles and compare native vs
   N× at near/middle/far distances. Include pole behind/in front of ordinary
   actors, hill clipping and the existing rain case.

## Acceptance

- Off/1× canonical hashes unchanged; 2P native; all four manifests empty.
- Pole identity/count, full height and anchor match the displayed 1× reference;
  floor(anchor) agrees with the native SAT and drawn-anchor error <1 output px.
- Detailed head/shaft improve the visible discrepancy raised by the owner,
  without repeated-segment seams or priority inversion. Include same-frame
  downscale pairs and a magnified overlap case for owner review.
- Short directed per-scale checks plus reused valid S4 road/stock evidence;
  measure incremental CPU cost with no dumps/audits/pacer work.
- Commit/push small changes and update HIGHRES/VALIDATION/status. Owner visual
  acceptance is required; do not claim the pole improvement is already done.

Tunnel/special artwork, HUD/weather work, full N× temporal qualification and
live scale changes remain separate. This brief does not launch a worker or
change the current S4 dispatch's implementation scope.
