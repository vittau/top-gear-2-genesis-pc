# Task 39: continuous actor growth without pop-in at N×

**Status: owner-approved; continuous default and Ayers rocks implemented (Sol, 2026-11-11).** Read `AGENTS.md`,
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

Owner played the continuous build and approved it: **“Está ótimo”**. The
branch is `vittau/tg2-highres-continuous`; `b151a25` makes continuous the N×
default, and `dce0c67` adds the ordinary Ayers Rock ladder plus survey tools.
Only `TG2_ACTOR_SIZE=stepped` requests authored stepped sizes. Exact height
matching to hand-drawn small sprites is not a gate, per owner clarification.

### Requested follow-up completed

- Default-change build, stock G1 and 300-frame Auckland 4×/60-fps actor drive
  exit 0; hashes remain frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD`; four manifests empty.
- Ayers Rock is country 0, slot 2 / ROM index 1, descriptor `$01BA96`.
  Password `stage` is difficulty; the tool uses the documented setup-only
  selector to load the real scene, then runs without simulation/RAM changes.
- Rocks are ordinary kind `$96`, record `$FF8E08`, art `$FF9C82`, mapping
  `$011054`, model-0 header `$011090`; a normal 32×16→2×1 ladder. They were
  missing from the allowlist (fallback 1), not `$82` or a compound handler.
  `$96` is now the only additionally promoted kind.
- Ayers 4×/60-fps capture: 4,333 rock presentations, no rock fallbacks,
  4,015 matched size pairs /154 band changes, max residual 0.000032%; all
  actor anchor/SAT/palette/priority/replay checks 0. Short Auckland/Canada/
  rain regressions pass (5,652 /3,832 /4,893 promoted actors).
- Remaining 13 countries: one validated 900-moving-frame 1× first-race
  window each, 11,700 frames /79,487 mapper calls total; selected runs exit
  0, all four manifests empty. All counts are in HIGHRES §14.8 and
  `build/task39-followup/country-summary.json`. No other kind was fixed.
  Unknown fallback-1 kinds: `$81/$93/$97/$A1/$A2/$A3/$A4`; native specials
  include poles, `$82` and tunnels. Model-0 screening found no R2/R3/R4;
  final-SAT fallbacks 5–7 are outside a 1× policy inventory.

### Explicit unresolved diagnostic

**The complete Ayers drive returned 1 on its road lane/centre audit.**
Actor checks, road geometry/gap/outlier checks, margins and manifests pass.
The same fixed input with actors disabled also fails (6,057 stripe /3,990
centre violations), with identical ending guest RAM. Native sprite removal
changes the audit's visibility flags, so the raw audit files are not all
identical. This establishes an existing road diagnostic independent of rock
sizing; it is not fixed, waived or claimed as an all-road pass. Original
failures, baseline runs and comparisons are retained under
`build/task39-followup/{rocks/ayers,road-baseline}`. No road code changed.

### Ready build / evidence

`build/settings.ini` has internal scale **4**, race 60 fps **On**.
`build/task39/play-continuous.sh` now unsets the size override and exercises
that approved default. `build/task39-followup/play-ayers-rock.sh` loads the
local Ayers checkpoint for a quick rock playtest; the worker did not launch
it visibly. The original synchronized 20-second MP4 remains at
`build/task39/video/stepped-vs-continuous-4x-60.mp4`.

Follow-up report: `build/task39-followup/worker-report.md`; original task
39 trace/video/CPU evidence remains under `build/task39/`. The default-change
commands are in `default-commands.json`, actor/regression commands in
`rock-commands.json`, bounded survey commands in `survey-commands.json`.
HIGHRES §14.8 gives per-country native/fallback counts and explicit limits.

No CI, tags, releases, engine changes, generated C edits or submodule pin
changes. Existing applied submodule dirt is retained. All-country **first
race** inventory is complete; later tracks/late-race kinds, S6, poles/special
art and real-platform performance remain unqualified. No runtime is left
running at completion.

## Ordinary-kind extension / progress

**Implemented and locally qualified** on `vittau/tg2-highres-more-kinds`,
based on `origin/main` at `9f8345a`. The owner confirmed Ayers rocks grow
smoothly (“Sim”); main already contains the accepted continuous default and
rock promotion. This extension adds `$81/$93/$97/$A1/$A2/$A3/$A4` only.
No work on the separately mapped Ayers night-road diagnostic.

### Verified and implemented

- Raw ROM `$A43C..$A48C`, `$B04C..$B0A0`, `$B584..$B632` and eight saved
  track/kind records verify ordinary model=level ladders, valid ROM headers,
  matching palette/priority and a larger model 0 at every observed level
  0–10. Model-0 extents: 31×24 /31×24 /48×75 /36×21 /31×21 /21×64 /29×29.
  All seven pass; none needs compound reconstruction or deferral to task 38.
- `$81` reads lateral/height from a per-object slot at `$A41C`. Existing
  height/anchor capture handles it, but lateral equality lost moving-object
  endpoints. Its temporal match now uses the original slot index in
  `$FF1800` plus world depth. Other scenery matching is unchanged.
- Latest Egypt/Italy/Chile/Las Vegas 900-frame 4×/60-fps actor drives exit 0.
  New kinds: 12,767 promoted presentations, 11,176 visible consecutive pairs,
  578 band crossings; maximum residual 0.000030% against the 0.1% gate.
  Model 0 throughout; promoted asset/model fallbacks, floor/SAT/anchor/
  palette/priority/native-row errors all 0. Native R5/R6 guards stay active
  (24 incomplete-SAT /1,710 fully culled cases); no R1–R4 or R7 on these kinds.
- Moving `$81` also passes a 900-frame Ayers actor repeat: 622 promotions,
  578 pairs /32 crossings, max residual 0.000025%, all actor invariants 0.
  G1 and short Auckland/Canada/rain/Ayers regressions pass; four manifests
  empty. Hashes: `60=2A0B972960C5E325`, `300=1131D937D70234FD`.
- New-country/Ayers qualification explicitly uses `--skip-road-audit`, which
  requires `--actors` and preserves actor/native-row/image/margin checks.
  It does not change or qualify the road. Original three regressions keep
  their full road checks. The Ayers night-road diagnostic was not run.

### Ready play build and evidence

`build/more-kinds/play.sh` starts directly in an Egypt race with `$81/$93`.
Arguments `italy`, `chile`, `las-vegas` select scenes for `$97`, `$A1/$A4`,
`$A2/$A3`. Saved settings: internal scale 4 /60-fps races On. Close the
current runtime before selecting another scene. Worker did not launch a
visible game; checkpoints/scripts were checked headlessly.

Full report: `build/more-kinds/worker-report.md`; raw ROM/asset evidence,
command ledgers, traces, scalar gates and play checkpoints remain under
that ignored directory. HIGHRES §14.9 has the per-kind table and exact scope.
Commits: `98dd51b` (verified ladders), `3ec9cfb` (moving identity/growth gate),
plus the final documentation commit recorded in the report.

No CI/tags/releases, engine changes, generated C edits or submodule pin
changes. Existing applied submodule dirt retained. Full all-track/late-race
and real-platform performance qualification remains outside this extension;
poles/special pieces retain their task-38/native scope. No worker-owned
runtime remains at completion.
