# Task 41: Ayers Rock night-road audit failure (S3 road)

**Status: mapped (2026-11-11). Not started.** Read `AGENTS.md`, `HIGHRES.md`
§13 and task 39's handoff. Only Opus, Fable or Sol may change the high-resolution road.

During task 39 the full Ayers Rock drive (Australia, slot 2; a night race)
failed the S3 road audit on stripe count and stripe-centre checks.
Geometry, gap, hole and outlier checks pass. The same fixed input with
actors disabled fails too (6,057 stripe and 3,990 centre violations, with identical
guest RAM), so the failure predates S4/39. Ayers Rock was never part of the S3
qualification (Auckland, Canada, Bavaria rain).

Decide first whether this is a checker limitation (night palette, lane colours the
classifier doesn't know) or a real rendering defect, using same-frame 1×/N× crops
of the failing rows. Fix the real defect, or calibrate the checker with evidence. Never
waive thresholds silently. Evidence is under
`tg2-highres-s4/build/task39-followup/{rocks/ayers,road-baseline}` (ignored build dirs).
