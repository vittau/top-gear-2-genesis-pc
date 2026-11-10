# Task 35: Linear Filter has no visible effect in races after S3

**Status: complete.** Implemented/reviewed and merged in `87e926b`; the owner
approved the local macOS playtest (“Está tudo certo”). Linux draft
`deck-filter-menu-20261110` is available; performance on the Deck for this
latest fix remains unmeasured. Implement S3 follow-ups with Opus, Fable or Sol only.

Local evidence and the scoped proposal: [Linear Filter investigation](../LINEAR_FILTER.md#s3-a-correct-final-sampler-can-have-no-visible-effect). The original 1:1 diagnosis is retained, followed by the approved game-owned native-art sampling change.

## Report and source

The owner tested the Linux tar.gz draft `deck-s3-20261110` (source `a205759`,
CI run 42842299392) on his Steam Deck and reported: “Funcionou bem, mas o
Linear Filter deixou de ter efeito in-game. No menu principal ainda funciona.”
He uses the extracted folder, not AppImage. The exact internal scale and
filter-toggle sequence were not supplied; do not claim they are known.

Start from current `main`, not the historical S3 branch (which predates the
main audio-option removals). Read AGENTS.md, CONTINUATION.md, LINEAR_FILTER.md,
HIGHRES.md §§8/9/13 and engine CLAUDE.md/PRINCIPLES.md/DEBUG.md. Preserve
existing applied submodule patches before any reset; prefer a fresh checkout
for this investigation. No ROM-derived artifacts or generated C in git.

## Investigation

Trace saved/live Linear Filter through the runtime UI and final SDL sampling
path, comparing native menu versus 1P race with S3 Off/On. Check engine
patches 0025, 0033, 0035 and 0050, active picture dimensions/stride, texture
recreation and scale mode when changing scenes or toggling the option.

S3 nearest-expands native art into an N× canvas before repainting road runs.
At an exact 1:1 canvas/output size, a final bilinear sampler may legitimately
produce no change. Distinguish that from a lost toggle or wrong sampler,
rather than assuming a framework defect. Investigate Deck-like 1280×800
output and fractional scaling with short directed cases in 1×/2×/4× as
needed; there is no reason to rerun the full S3 track matrix.

Use final SDL/window-output captures (diagnostics added by patch 0025), not
guest screenshots alone: guest framebuffer hashes exclude the filter. Run
headless/software or hidden Cocoa/Metal as appropriate, no visible desktop
window. Show a same-frame On/Off comparison and report the first divergence.
Do not guess a Deck GPU result from a software-renderer-only test.

## Fix and acceptance

Fix a verified defect at its source, keeping game-specific rendering in
`game/` and genuine framework corrections in a numbered engine patch with a
README reason. Preserve the active texture-boundary fix, nearest/Linear Off
appearance, saved preferences, S3 smooth road, native menus/2P and stock 1×
hashes. Do not downscale the whole high-resolution picture simply to force
blur or add a new independent filter setting without discussing that policy.
If the report is explained by 1:1 final sampling and the desired fix requires
changing how native art is sampled inside S3, send the coordinator concrete
evidence and a scoped proposal before changing that visual contract.

Validate same-frame final presentation for menu/race and real live/persisted
toggle, using integer and fractional output ratios where informative. Check
Off hashes `60=2A0B972960C5E325`, `300=1131D937D70234FD`, all four manifests,
and focused S3 geometry/2P guards affected by the change. Record commands,
exit codes, capture paths, quantitative differences and limitations. Build
with ≤3 jobs and shared `flock ~/.cache/tg2-heavy.lock`; one runtime at a time.

Commit/push coherent fixes and documentation on the worker branch, then
report with worker_done. No worker CI, tags, release or merge into main.
Do not start S4 or rewrite the existing draft's source identity. A new Deck
candidate, if needed, will be handled by the coordinator after review.
