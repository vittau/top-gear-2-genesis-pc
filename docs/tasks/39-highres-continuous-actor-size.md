# Task 39: continuous actor growth without pop-in at N×

**Status: implemented and locally qualified (Sol, 2026-11-11); owner motion review pending.** Read `AGENTS.md`,
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

Implementation and local technical gates are complete on
`vittau/tg2-highres-continuous`, based on `origin/main` at `c56d2fa`. The
owner clarified during this work that exact matching to hand-drawn original
heights is unnecessary; prioritize smooth growth. Owner played the continuous build and approved it (“Está ótimo”); continuous
is now the default, with `TG2_ACTOR_SIZE=stepped` retained internally.

### Implemented and verified

- Raw ROM and 26,066 runtime projection entries confirm the diagnosis:
  `$FF17E0` is the integer row's scale; D4 has a separate interpolated value,
  rounded to an integer before ×4. A validated read-only `$B314` hook keeps
  the full unsigned depth fraction for both projection paths.
- Size now uses model-0 extent × projection / fixed model-0 reference,
  never the guest band/extent. ROM references: scenery 2270.0837, cars
  2499.1775. 60-fps pictures interpolate scale and anchor together.
- Scenery matches by stable world depth plus record/lateral. Runtime proved
  the active camera is `$FF17F4`, set by `$B04C..$B058`. This prevents the
  old anchor matcher from confusing equal objects at different depths.
- Three tracks, 1,200 controller frames each, 4×/60 fps On: 44,505 matched
  visible frame pairs, 1,721 band crossings, 0 residuals over the stated
  0.1% size/projection threshold; max residual 0.000034%. Stepped maximum
  frame change 100%, new 25.46% (physical near-range growth); old continuous
  leaves up to 46.49% unexplained residual. Per-kind tables: HIGHRES §15.
- Three 4× audits plus 2× Linear On: 48,120 promoted actors / 600,084
  native-row replays, floor/SAT/anchor/palette/priority/replay errors 0;
  native poles overlap in both directions. Four manifests empty in every
  run. Stock G1, native 32:9 2P and cap/Off boundaries pass. Stock hashes:
  frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`.
- Changed-region masks include both native and new silhouettes. Continuous
  near/middle/far photometric tolerances are explicitly 80/80/96, stepped
  retains 64/80/96; outside-region limits stay unchanged. Initial Canada
  exit 1 (near car group 69.8417 >64) is retained; qualified repeat exits 0
  under the declared new bound. No attempt was made to force original sizes.

### Review and ready build

`build/task39/video/stepped-vs-continuous-4x-60.mp4`: 20 seconds, 60 fps,
2848×840, trees/signs/cars, identical guest input and ending RAM SHA-256.
Bulk PNGs were deleted; individual MP4s and a few QA pictures remain.

Run `build/task39/play-continuous.sh` for the owner. It launches the branch's
ready build visibly with the internal continuous switch; `build/settings.ini`
has internal scale 4 and 60-fps races On. The script itself has not been run
visibly by the worker. Default stepping is retained outside that launcher.

`build/task39/worker-report.md` and `qualified-summary.json` consolidate exact
commands/exits, manifests, trace maxima, stock hashes, CPU and limitations.
CPU uses [3000,3900), 900 frames, 1280×800, 60 fps On, full audio/rendering,
no audits/dumps/pacer work. Original S4 → new means: 2× 2.5311 →2.7323 ms;
4× 3.1509 →3.4553 ms (new mean of two runs, 3.0133–3.8973 ms). Thus observed
increments are +0.2012/+0.3044 ms, with material 4× run variation; not a
resolved Deck/GPU cost. Same-branch stepped/continuous pairs are also retained.

### Remaining and constraints retained

Coordinator: review the MP4 and launch the build for the owner's motion
judgment; record whether continuous should become the default. Native
spawn/culling, poles/special pieces, player/HUD/menus and 2P remain as S4.
All-country coverage, S6, live scale changes and real-platform performance
remain outside this task. No CI, tags, releases, generated C edits, engine
changes or submodule pin changes. Existing applied submodule dirt is retained.
No runtime or heavy process is left running at completion.

### Approved default and country follow-up (2026-11-11)

Owner approved the motion (“Está ótimo”). Continuous is now the N× default;
only `TG2_ACTOR_SIZE=stepped` selects the old ladder. Targeted default-change
build, stock G1 and 300-frame Auckland 4×/60-fps actor drive all exit 0;
stock hashes are unchanged, four manifests empty, actor invariants pass.
Commands: `build/task39-followup/default-commands.json`.

Ayers Rock is Australasia country 0 / race slot 2 / ROM index 1, not password
`stage=2` (stage means difficulty). Its 900-frame 1× capture verifies index 1
and descriptor `$01BA96`, with empty manifests. The rock asset is ordinary
kind `$96`, record `$FF8E08`, model 0 32×16 through model 10 2×1; the
original allowlist does not include it. Native sheet confirms the rock image;
next: promote this ordinary ladder with the existing guards, then a bounded
first-race survey of the other 13 countries. No other country kinds will be
fixed in this follow-up.
