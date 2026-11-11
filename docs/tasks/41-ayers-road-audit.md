# Task 41: Ayers Rock road audit failure (S3 road)

**Status: mapped (2026-11-11). Low priority, not started.** The owner played Ayers Rock (stage 2) at 4× and found the road correct ("Me parece bom"), so the failure is most likely in the checker. The task is to find why the stripe classifier misidentifies this track's lanes, then fix the checker with evidence, without waiving thresholds. Read `AGENTS.md`, `HIGHRES.md`
§13 and task 39's handoff. Only Opus, Fable or Sol may change the high-resolution road.

During task 39 the full Ayers Rock drive (Australia, slot 2) failed the S3 road audit on stripe count and stripe-centre checks.
Geometry, gap, hole and outlier checks pass. The same fixed input with
actors disabled fails too (6,057 stripe and 3,990 centre violations, with identical
guest RAM), so the failure predates S4/39. Ayers Rock was never part of the S3
qualification (Auckland, Canada, Bavaria rain).

**Correction (owner, 2026-11-11):** stage 2 (Ayers Rock) is a **daytime** race;
stage 3 is the night one. The workers' "night-road" label was wrong, so a
night palette doesn't explain the failure. The maximum stripe-centre error is
315 px while geometry stays within 0.7 px, which suggests lane misidentification by
the checker, but that isn't verified.

Decide first whether this is a checker limitation (lane colours or stripe patterns the
classifier doesn't know) or a real rendering defect, using same-frame 1×/N× crops
of the failing rows. Fix the real defect, or calibrate the checker with evidence. Never
waive thresholds silently. Evidence is under
`tg2-highres-s4/build/task39-followup/{rocks/ayers,road-baseline}` (ignored build dirs).
