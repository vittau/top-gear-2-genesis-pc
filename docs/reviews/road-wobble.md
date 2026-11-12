# Road boundary smoothing follow-up

Implemented on `road-wobble`, from current main `209bdcd`. Local qualification:
macOS arm64, Homebrew SDL2, Release optimisation with trace/reverse debug enabled.
No CI, merge, tag, release, engine patch or submodule pin change. The owner's
original `~/.cache/tg2-evidence/native_save_2.bin` is untouched; a copy loads
successfully in the current build and reproduces the Ayers Rock shoulder wobble.

## ROM investigation and choice

Raw USA ROM SHA-256 is the AGENTS.md input. Disassembly was regenerated with
`tools/disasm_tg2.py` and Capstone, not inferred from generated C. Private output:
`build/road-wobble/road-{emitter,project,project2}.asm`.

| ROM | Observed operation and data |
|---|---|
| `$7FA8..$7FBE` | Reads camera/track position `$FF1D9E`, track-record pointer `$FF1DFE`; builds the depth table at `$FF1254`, then stores count `$FF1D94` and screen limit `$FF1DBE`. |
| `$7FC0..$8046`, repeated through `$83A6` | Reads signed curve/slope bytes from 16-byte track records. Integrates curve with `add.w d4,d0; asr.w #1,d0; add.w d0,d2`; integrates slope into D3 and projects Y with `muls.w $200(a4),d6; lsl.l #2; swap d6`. Writes eight-byte centre/Y/clip/curve records to `$FF1254`. The `ASR` and `SWAP` already discard precision. `$FF221A` supplies the depth projection table pointer. |
| `$8402..$84E4` | Expands depth samples into six-byte scanline records at `$FF0C54`: curve/lateral input, depth scale, depth/phase. `$848A..$84A4` obtains reciprocal/interpolation increments through `$FF0650`; `$84AE..$84BA` stores the integer scale word and advances its fixed-point accumulator with `swap; add.l; swap`. |
| `$8726..$87E4` | Reads those six-byte records per visible row. `$877E` shifts scale D1 right four bits; `$8782` looks up an **integer atlas row** through `$FF222A`. `$8786..$878E` adds camera lateral offset, negates, multiplies scale by lateral input, shifts left three, then swaps to obtain integer H-scroll. `$87D2/$87D4` writes the paired scroll words; `$87D6..$87D8` writes atlas V-scroll. |
| `$7A10..$7C66` and alternate emitters | Uses the six-byte records, track descriptor `$FF241C`, stripe phase `$FF1D9E`, and per-row kind table `$FF2F4A` to emit discrete palette/atlas selections. Descriptor byte 3 bits 3/4 select the alternate families. |

The coordinator's proposed middle path was evaluated explicitly: retaining the
low word before `$878E` supplies fractional **centre translation only**. Width
was independently reduced at `$877E/$8782`, and the atlas adds its own 2/4 or
4/6-pixel staircase. Shoulder and lane offsets are independently quantised
atlas texels. Thus that fraction alone cannot remove either edge's width
wobble or the inner grey boundary. Earlier curve integration and Y/scanline
expansion are also quantised. Recovering all geometry from inputs would require
an additional per-row/staging-buffer capture and picture-history contract,
including 60-fps endpoint selection and family-specific atlas reconstruction.
It is feasible future work, but not a single cheap fractional hook. No such
hook was added, and no unmeasured improvement from it is claimed.

Chosen approach: the authorised whole-band smoothing fallback, using the
captured authored boundaries themselves. It addresses all colour boundaries
and remains independent of guest execution and current/live RAM. There is no
native guest routine replacement, re-projection, temporal lag or engine change.

## Implementation

`tg2_road_fit.c` minimises
`sum(observed * (x - authored)^2) + 64 * sum((second_difference(x))^2)`
on each band, subject to `abs(x - authored) <= 2` at every observation.
A pentadiagonal Cholesky solve and active bounds give the constrained optimum;
this avoids the kinks introduced by clipping an unconstrained curve. Silhouettes
use the entire band. Inner boundaries match the complete texel-kind sequence
across repeated stripe structures; intervening structures have zero observation
weight. Colours/palettes/stripe phase remain those of the source row.

The existing band discontinuities remain: absent road, atlas family change or
width-index jump above eight. No fit or sub-row interpolation crosses these.
A common reduction of a row's displacements prevents thin runs from crossing
and preserves at least 25% of every authored run's width. Sub-row interpolation
and analytic pixel coverage then use the fitted boundaries. The two-pixel bound
also holds relative to the interpolated authored silhouette at presented rows.
Near hard bounds, topology changes and band ends, some curvature remains; this
is a measured reduction, not a claim of mathematically perfect edges.

The road audit's fit allowance changes from 1.5 to 2 native pixels by design.
Its colour-search radius now follows the largest **actual colour-boundary**
displacement, rather than only silhouette movement; independent inner fitting
otherwise generated false outlier reports. Pixel geometry, holes, stripe counts,
stripe centres and continuity checks are unchanged. Trace-only optional
`TG2_ROAD_BOUNDARY_AUDIT=1` adds `.edges` scalar source-boundary evidence next to
`.nxroad` pixel evidence. Normal play performs no audit I/O.

## Measured wobble and placement

`tools/measure_road_wobble.py` streams matched files and rejects changed authored
geometry/topology. It measures RMS second spatial derivative of boundary X,
in native pixels/native-row². For recurring inner structures with gaps, divided
differences account for actual row spacing; gaps above four rows are excluded.
Silhouettes remain linked across stripe topology changes. This measures spatial
roughness, not a subjective judgement or a temporal-jitter score.

| Matched pictures | Outer boundary RMS before → after | Inner boundary RMS before → after |
|---|---:|---:|
| Owner slot 2, 52 presented pictures, 2× and 4× | 0.51043 → 0.25112 (**50.8% lower**) | 0.90102 → 0.19956 (**77.9% lower**) |
| Auckland baseline route, 2,732 pictures, 2× and 4× | 0.53751 → 0.31862 (**40.7% lower**) | 0.92617 → 0.23503 (**74.6% lower**) |

Source-boundary results agree between scales because the geometry is independent
of N. Raw authored RMS is unchanged (owner outer 2.15271, inner 1.69664;
route outer 2.02223, inner 1.41022). Hill outer improves 0.16142 →
0.05249 and inner 0.73102 → 0.02946; tunnel outer 0.59027 → 0.32359
and inner 0.96480 → 0.30084, each over 30 matched pictures at both scales. Maximum source-boundary deviation is **2.0
native pixels**, including every fitted inner boundary. Maximum presented-edge
deviation from the corresponding interpolated authored edge is 2.0 on the
route, 1.96875 at owner 4× and 1.93359 at owner 2×. Quantised audit coordinates
have 1/256-native-pixel resolution.

The separate presented-row silhouette metric includes linear-interpolation
knots: owner 2× 0.56378 → 0.39808; owner 4× 0.86769 → 0.71316; route 4×
1.51585 → 1.29060. Source and presented metrics have different sample spacing
and should not be conflated. Scalar reports are
`build/road-wobble/metric-{owner,route,hill,tunnel}-{2,4}x.json`.

## Review images and motion

All private images are under `build/road-wobble/`; none is committed. Each
comparison is a full-colour road crop with **before left / after right**,
retaining its original output resolution. Full original screenshots are also
retained in `before/` and `after/`.

| Scene | 2× comparison | 4× comparison |
|---|---|---|
| Owner slot 2, sharp S curve / shoulder | `comparisons/owner-2x.png` | `comparisons/owner-4x.png` |
| Straight, Auckland frame 3600 | `comparisons/straight-2x.png` | `comparisons/straight-4x.png` |
| Gentle curve, Auckland frame 4501 | `comparisons/gentle-curve-2x.png` | `comparisons/gentle-curve-4x.png` |
| Stronger curve, Auckland frame 3400 | `comparisons/sharp-curve-2x.png` | `comparisons/sharp-curve-4x.png` |
| Hill/crest, saved from driven Auckland frame 11913 | `comparisons/hill-2x.png` | `comparisons/hill-4x.png` |
| Tunnel opening, driven Auckland frame 11113 | `comparisons/tunnel-2x.png` | `comparisons/tunnel-4x.png` |

Motion: `comparisons/curve-{2,4}x.apng` is a lossless 13-picture side-by-side
sequence, frames 3590–3602, with 60-fps timing. Conventional compact previews
are `curve-{2,4}x.gif` (GIF uses 20-ms frame timing and palette quantisation).
Full-colour numbered frames `curve-{2,4}x-00.png` through `-12.png` and
`curve-{2,4}x-sheet.png` avoid GIF limitations. The owner state has zero speed;
its 12-frame sequence is retained but the moving evidence uses the driven route.
The owner, hill, tunnel, straight and curve images were visually inspected;
road silhouettes and grey/shoulder boundaries are smoother, while hard stripe
phase changes, native tunnel walls, HUD and car art remain visible as authored.
Final subjective acceptance belongs to the owner.

Final owner captures at **2×/3×/4×**, Linear Off and On, all exit 0 with all four
execution manifests zero. Their `.edges` geometry is byte-identical between
filter choices on all 52 captured pictures per scale (`linear-geometry.json`). The final images differ between filters at every scale,
confirming that On actually ran (`linear-image-differences.json`).
A separate 4× Linear On tunnel capture also exits 0. Native-art filtering is
unchanged; no separate physical-display sampler or S5 qualification is claimed.

## Gates and known checker limitation

The canonical golden is untouched. `tools/regression.py --uncapped` passes all
**784 frame hashes, 10 complete WAV hashes and 16 SOUND-page screenshot hashes**:
SFX/MUSIC/BOTH, options off/default on, live race changes and SOUND page. Every
existing golden is scale 1, so there is no designed N× golden to re-record.
All four execution manifests have zero entries throughout successful captures.

The Auckland 2×/4× route audit passes before and after: respectively 328,034
and 656,068 presented road rows, no envelope, geometry, hole, stripe, continuity,
colour-outlier, margin or stripe-centre violations. Final maximum measured
pixel-edge error is 0.796875 output pixel at 4×; lane-centre error is at most
0.5 output pixel. Matched hill and tunnel audits pass at 2× and 4×, too.

**The owner's Ayers Rock state does not pass the existing stripe classifier.**
This reproduces the known open Ayers audit (task 41) on the unchanged renderer,
not an empty-manifest or silhouette failure. At 4× its 17,472 presented rows
report stripe-count/centre rows 3,768/2,477 before and 4,028/2,789 after; at 2×
8,736 rows report 1,600/1,086 before and 1,910/1,241 after. Both have zero
silhouette/envelope/geometry/hole/continuity/colour-outlier violations. The
counts shift as independently smoothed stripe pixels cross classifier thresholds;
this task does not diagnose or waive that existing classifier discrepancy.
Owner images are provided for direct review. Reports retain the failing exit 1
and examples, not a passing stamp or a relaxed stripe threshold.

`tools/test_road_fit.py` compiles the real C solver and independently checks
box constraints, translation/reflection invariance, exact straight lines and
KKT optimality, including missing observations and severely noisy curves:
**162 fits plus reflections pass**, worst residual `7.3e-11`. This also guards
against the defensive authored-data fallback hiding a numerical failure.

## Cost at 4×

Same committed route interval `[3000,3360)`, 16:9, race 60 fps, drawable
1280×800, SDL dummy/software, uncapped full-runtime mode. No audit, screenshots,
native dump or WAV work in either cost interval. CPU work includes audio and
presentation, excludes pacer waiting. Builder timing is wall-clock time and
its TCP sample bounds differ by a few frames; whole CPU uses the exact same
360 frames.

| Measurement | Before | After | Change |
|---|---:|---:|---:|
| Builder, µs/presented picture | 519.36 | 524.97 | +5.61 µs / +1.1% |
| Whole frame CPU mean, µs | 2995.1 | 3030.3 | +35.2 µs / +1.2% |
| Whole frame CPU p95, µs | 3843 | 3750 | -93 µs (run variability) |
| Layout CPU mean, µs | 592.8 | 600.5 | +7.7 µs |

Evidence: `cost-{before,after}/drive/auckland-scale4-60-cost/drive-summary.json`
and `frame-stats.csv`. These Mac measurements are not a Deck performance claim.

## Commands and exits

All builds/captures/heavy analyses were wrapped with the single machine-wide
`flock ~/.cache/tg2-heavy.lock`; builds use at most `-j3`, no nested locks.
One headless runtime at a time, stopped before the next launch. Large native
`.road` dumps were removed once their purpose was served; metrics and selected
scalar audits/captures remain private. Full-route metrics were extracted before
pruning bulk scalar audits to the selected screenshot frames;
`route-audit-file-hashes.json` indexes all 21,856 original `.edges`/`.nxroad`
files and their hashes. Re-running the metric on the retained route subset
therefore measures that subset; the complete owner/hill/tunnel evidence remains. The reproduction harnesses below are
retained under the ignored evidence directory.

| Command (after the `flock` prefix) | Exit / evidence |
|---|---|
| `env JOBS=3 tools/build-linux.sh` | Initial exit 1: uninitialised submodules; `git submodule update --init --recursive` exits 0, then build exits 0 (`base-build.log`). |
| `cmake --build build --target TG2Recomp -j3` | 0 for baseline audit, implementation and final builds; `*-build.log`. |
| `build/road-wobble/venv/bin/python tools/test_road_fit.py` | 0; `numeric-fit.log`. |
| `build/road-wobble/venv/bin/python tools/regression.py --uncapped --out build/road-wobble/regression` | 0; `regression.log`, canonical golden unchanged. WAVs streamed and deleted by the tool. |
| `.../python build/road-wobble/capture.py {before,after} {2,4} {owner,route,hill,tunnel}` | All 0; logs and `counts.json` in each capture directory. Also final 3× owner, Linear On owner 2×/3×/4× and tunnel 4×, all 0. |
| `.../python tools/check_road_artifacts.py <capture> --nx --min-frames 1 --out <capture>/audit-summary.json` | Route/hill/tunnel before and after 0; owner before and after 1 as above. `analysis.log`, `directed-analysis.log`. |
| `.../python tools/measure_road_wobble.py <before> <after> --out <metric.json>` | 0 for all eight matched capture pairs; `metric-*.json`. |
| `.../python tools/check_highres.py drive --exe <base-or-final> --out <cost-dir> --port 4491 --scale 4 --frames 360 --no-audit --uncapped --cost-route --output-size 1280x800 --race60` | Both 0; `cost.log`, summary/manifests. |
| `.../python build/road-wobble/explore.py` | Harness 0; intentionally stopped the finite runtime after collecting checkpoints (runtime reports 2 / incomplete measurement, not a performance sample). All four manifests 0; `explore.log`, `explore/summary.json`. |
| Python compilation, `git diff --check` | 0 on final sources. |

Unverified: owner acceptance of these new pictures/motion, physical Deck/N×
performance, Linux, Windows, Intel macOS, real controller/display presentation,
and CI. No new release qualification is implied. The known Ayers stripe-audit
failure remains open; broader S5/S6 work is outside this task.
