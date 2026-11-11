# Task 39: continuous actor growth without pop-in at N×

**Status: in progress (Sol, 2026-11-11).** Read `AGENTS.md`,
`HIGHRES.md` §14 and [task 34](34-highres-s4.md) (its "Progress / handoff"
section) first. Only Opus, Fable or Sol may implement this S4 extension. Use supervised Orca
orchestration, the shared heavy lock, at most 3 jobs, headless probes, one runtime and no worker CI.

## Owner request

After he played S4 at 4× ("Funcionou bem, mas não é bem o que eu esperava"),
the owner reported that objects still **pop in, changing size abruptly** as they
approach. He wants their size to **grow smoothly and continuously** with distance,
not in steps. He tried the internal `TG2_ACTOR_SIZE=continuous` switch too and
said they **still grow in steps; not much changed**.

## Why the current "continuous" switch still steps (coordinator reading, to verify)

Source: `game/tg2_actors.c`, `actor_size_policy()`, `band_ratio()`, `tg2_actors_object()`.

1. **The base is still the guest's band.** Size = (guest model extent / model 0
   extent) × `scale / band-centre scale`. When the guest changes level, the guest
   extent jumps to the next authored size, and the band centre changes with it.
   The product is continuous only if the authored ladder followed the projection
   exactly. HIGHRES §14 measured 0.99–1.23× (signs about 15% larger), and below
   ~6 px the art is quantised (0.6–1.5×), so every band boundary leaves a jump.
2. **The scale input may be quantised.** `a.scale` is `ram16($FF17E0)`. On the
   **interpolated path** (depth < `$40`, `$B37C..$B42C`) the guest interpolates
   scale with the depth fraction (`D4` = scale × 4). On the **depth-table path**
   (far objects) the scale comes from an integer depth row. Check which value
   `$17E0` holds at the hook, and whether the finer `D4` (or depth + fraction) is
   available for both paths.
3. **No temporal interpolation of size.** In 60 fps races `mix_pieces` interpolates
   actor anchors only. Size comes from the nearer endpoint, so even a
   continuous per-tick size changes only at the guest tick rate.

## Goal

Draw every promoted actor from its model 0 at a size that is a smooth function
of its projection, with no visible steps at band boundaries:

- Size = model 0 extent × (projection scale / the reference scale at which model 0 is
  authored), calibrated **per kind** from the ROM or the existing captures, never from the
  guest's current band. Use the most precise projection the guest computes
  (interpolated scale or depth + fraction). For far objects, interpolate the
  depth table with the fraction if one exists.
- In 60 fps races, interpolate size between endpoints just like the anchor.
- The bottom-centre anchor stays at the sub-pixel projection, so objects stay
  planted on the road while they grow.
- Make continuous the **default** at N×, if the owner approves the result. Stepped stays
  available through the internal switch for comparison. At 1×/Off nothing changes
  (stock hashes `60=2A0B972960C5E325`, `300=1131D937D70234FD`).

## Evidence

- A per-actor size-versus-time trace over approaching objects (cars, trees, signs,
  barrels) on 2–3 tracks, stepped vs new. Report the max frame-to-frame relative size change
  and whether any jump is above a stated threshold at band boundaries.
- Keep the S4 gates: floor(anchor) == 1× SAT, palette/priority, occlusion, 2P/menus native,
  manifests empty. Downscale silhouette bounds will change because the size intentionally
  differs from 1×. Document the new tolerance; don't hide it.
- A short MP4 or GIF (in an ignored build dir) of an approaching tree/sign/car for the
  owner, stepped vs continuous. The owner judges motion, so still pictures are not enough.
- The CPU cost increment, measured as in task 34.

Poles (task 38) are out of scope unless they share the size code naturally.

## Progress / handoff

Branch `vittau/tg2-highres-continuous`, based on `origin/main` at `c56d2fa`.
Existing build and patched submodules retained; no CI or engine edits.

First milestone: raw-ROM inspection verifies `$B314` (`3744 93D4`) as
the common projection entry with unsigned D2 fraction intact on both paths.
`$B410` stores the integer row scale into `$FF17E0`; `$B416..$B428`
interpolates D4 separately, truncating to an integer before ×4. The distant
path discards D2 at `$B480`. A new read-only entry hook preserves that
fraction and reconstructs the unrounded table interpolation, for evidence
only at this milestone. No generated C was edited.

`tools/check_actor_growth.py` records deterministic 4×/60-fps input-script
runs and streams per-frame sizes. The instrumented old policy is retained
locally as `build/task39/TG2Recomp-instrumented-s4`. Initial Auckland old
continuous run: exit 0, four manifests empty; measured boundary jumps up to
66.50% (tree), with up to 46.49% unexplained by the precise projection.
Artifacts and raw-ROM disassembly are under ignored `build/task39/`.

Next: replace band-relative sizing with model-0 projection calibration,
interpolate its size between guest pictures, qualify traces on three tracks,
and produce the motion comparison, cost measurements and stock gates.
Default stays stepped until owner approval, as requested by the spec.
