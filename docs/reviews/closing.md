# Review closing work

Branch `vittau/review-closing`, based on main `597f287`. No CI or merge.

## Live RACE SOUND row

The runtime setter now updates the native open page's own value word
`$FF2560`, just as its native UP/DOWN handler does. It leaves the global
`$FF240E` sound-mode word to the stock menu teardown and does not touch VRAM.
The existing native row renderer reads the page value normally. The race-policy
freeze guards against treating overlapping race RAM as a menu page. No new
hook/seed, generated-code change, engine patch or per-frame repaint is needed.

Before/after images for the owner to inspect:

| Presentation | Before (incorrect MUSIC) | After (correct SOUND EFFECTS) |
| --- | --- | --- |
| Options off | `build/closing/before/off/live-sfx.png` | `build/closing/e1/off-sound-page/live-sfx.png` |
| Default on | `build/closing/before/on/live-sfx.png` | `build/closing/e1/on-sound-page/live-sfx.png` |

Only fourteen golden leaves were updated, with an explicit allowlist rather
than a full re-record. Both presentations change SOUND-page frame hashes at
1860, 1920, 1980, 2040, 2100 and 2160 (after the live SFX selection), plus their
`live-sfx` PNG SHA-256. Every other field compares exactly to Phase D's golden,
including all ten WAV hashes and all race/live-race pictures.

| Hash | Before | After |
| --- | --- | --- |
| Off page frames 1860..2160 | `658E07DCF7B02CAB` | `F84D070042B7081B` |
| On page frames 1860..2160 | `5DC7B2F499A400FF` | `47EB0D241D51D2DF` |
| Off `live-sfx.png` | `8f5685a654a8805d498dad31b72298839a3c555f9c9a2b142fed35327e361bb4` | `879dc874b0f88d33b65f3d0de1aff330f7dedf485c19249c21429fd4b72c7082` |
| On `live-sfx.png` | `bf9086d7e493a81bcb421b160c9db3775f60ec264df675e2db6fcb89c5798848` | `2dadc58718d858518497dcb71622fc5d50431c2ea9ca6b26bdccee87b3f9c594` |

The additional input-script OPTION sequence covers every directed pair among
SFX/MUSIC/BOTH, including SFX→MUSIC, SFX→BOTH, MUSIC→BOTH and BOTH→SFX. Its
sixteen images (eight changes per presentation) are in
`build/closing/sequences/{off,on}/`. Each PNG equals the canonical page PNG for
the selected value; all manifests are zero. The OPTION directive uses the
same setter as the runtime menu.

Commands/evidence under `build/closing/`:

- Locked `JOBS=3 tools/build-linux.sh`: exit 0, `e1-build.log`.
- Locked `tools/regression.py --out build/closing/e1 --uncapped`: expected exit 1 against the old golden; only the fourteen approved leaves differ (`e1-diff.json`).
- Locked `/opt/homebrew/bin/python3.14 build/closing/e1-sequences.py`: updates only the allowlisted leaves and checks the extra sequences; `e1-sequences.log` and `e1-sequences.json`.
- Locked `/opt/homebrew/bin/python3.14 tools/regression.py --out build/closing/e1-verify --uncapped`: exit 0, all 784 frame, ten WAV and sixteen page hashes match; all manifests zero.

Screenshots/dumps/audio remain under ignored `build/`; only hashes are committed.

The locked trace-OFF release build and full regression also exit 0
(`e1-release-build.log`, `e1-release.log`), with the same updated golden and
zero manifests. The additional sequence checker exits 0; an initial ignored
harness typo shadowed Python's `next` builtin, was corrected, then all sixteen
sequence images passed. No game/output change was involved in that setup fix.

## HUD checker diagnosis and repair

This is a stale evidence-pairing assumption in the tool, not a HUD regression.
The exact failure is reproduced with:

```sh
flock ~/.cache/tg2-heavy.lock build/phase-b/venv/bin/python tools/verify_hud.py \
  --out build/phase-b/hud --check-only
# exit 1, e2-before.log:
# AssertionError: (3300, 'HUD ownership missing')
```

The checker selected the nearest periodic TCP raster sample, which happened to
be `state-3444.json`, to decode frame 3300's image/VRAM. During that later frame
the cartridge moves the instrument cluster off plane A and draws it as sprites
(the renderer already handles this, documented in `tg2_video_world.c`). The
sample's plane-A scroll maps the tested rows to a non-HUD name-table row.
Applying it to frame 3300 finds **zero plane HUD texels**; using the matching
baseline layout on frame 3300's own VRAM finds **2,880 opaque plane texels**.
The old check added map-marker sprites only, not the temporary instrument
sprites, then rejected its incomplete mask at the unchanged `>500` threshold.

The fix decodes ownership from the same frame's VRAM/SAT and the audited fixed
baseline layout (plane A at `$C000`, x scroll 0, HUD row zero at screen y=14),
never from a different frame's TCP scroll sample. It honors the instrument
cluster columns and decodes full HUD sprites as well as map markers, including
sprite dimensions/flips. TCP state dumps remain optional context collected by
the probe, without influencing validation. Frame **3450** is added explicitly
and must contain at least eight HUD instrument sprites, exercising the branch
the original probe omitted. This is a fixed-route HUD test, not a general
raster reconstructor for arbitrary tracks/screens.

No threshold was reduced and no game code was changed. The original assertions
still require each owned texel to translate exactly, no old-position ghost,
unchanged world/top rows, identical RAM/VRAM, unchanged centered reference
pictures, canonical off-mode boot hashes and six distinct consecutive 60-fps
pictures. Captures now isolate settings and explicitly select 1× resolution,
SFX, uncropped overscan and the requested HUD/fps settings; `--uncapped` avoids
host pacing while retaining full runtime work. The old dataset also passes
with the corrected nine-frame ownership decoder (`e2-check-old.log`), before
adding the new sprite-phase capture.

Fresh verification commands:

```sh
flock ~/.cache/tg2-heavy.lock build/phase-b/venv/bin/python tools/verify_hud.py \
  --exe build/closing/base-TG2Recomp --out build/closing/hud --uncapped --record-baseline
flock ~/.cache/tg2-heavy.lock build/phase-b/venv/bin/python tools/verify_hud.py \
  --out build/closing/hud --uncapped
```

Both exit **0** (`e2-baseline.log`, `e2-final.log`): two reference runs and all
eight qualification runs complete with all four manifests zero; all thirty
translation checks pass, including the new sprite phase. Evidence and pixel
counts are in `build/closing/hud/summary.json`. The historical Phase B report
already established the original failure identically on untouched `34c43b1`
and 174/174 base/final capture artifacts equal; this repair changes the checker,
not those pictures. Pillow was installed as a binary wheel in the ignored
probe venv; the first attempts used a venv without Pillow and an unavailable
historical venv path, before the recorded reproduction above.

Representative extra live-page images (the same filenames also exist under
`build/closing/sequences/on/`):

| Transition | Options-off PNG |
| --- | --- |
| SFX → MUSIC | `build/closing/sequences/off/0-0-to-1.png` |
| MUSIC → SFX | `build/closing/sequences/off/1-1-to-0.png` |
| SFX → BOTH | `build/closing/sequences/off/2-0-to-2.png` |
| BOTH → SFX | `build/closing/sequences/off/3-2-to-0.png` |
| MUSIC → BOTH | `build/closing/sequences/off/5-1-to-2.png` |
| BOTH → MUSIC | `build/closing/sequences/off/6-2-to-1.png` |

## Current-state continuation document

`docs/CONTINUATION.md` is now 101 lines instead of 373: recorded shipped state,
post-release main/review work, open items, resume commands and evidence links.
It no longer simultaneously says S4 is pending and merged, revives old worker
handles, or treats obsolete Deck drafts as current assignments. Current open
items retain poles (38), the daytime Ayers stage-2 audit diagnosis (41), S5–S7,
the owner-paused NTSC/licence gate (28), real-platform/physical-trigger checks
and the remaining roadmap backlog. It preserves the reduced high-resolution
qualification recipe, Deck tarball/shortcut continuity, withdrawn-option
constraints and visible-launch environment caveat.

Facts were checked against `release/v0.3.0.md`, task status headers, the old log
and Git history. `v0.3.0^{}` resolves to
`7e19228fa7edbd683270f05b71f19416a486d265`; `git merge-base --is-ancestor` exits 0
for the S3 (`a205759`), S4 (`a8041a2`), continuous (`9f8345a`), extra-kind
(`06335bd`) and trigger/menu (`6f05d76`) commits against that tag. Thus these
features shipped, while the subsequent A–D review commits are not in v0.3.0.
The document describes the release recorded in this repository, without
claiming that online release metadata was rechecked.

The full previous text is copied **verbatim**, including its historical
contradictions, into `docs/history/continuation-log-2026-11.md`; the new document
has a one-line pointer marking it historical. Byte equality against
`git show 597f287:docs/CONTINUATION.md` passes: **24,643 bytes**, SHA-256
`92acd7ed3c7358b371ada79631c96ddb0e860f2c1aaa23c0333191fb00332db0`.
All relative file links in the new document resolve. The only AGENTS change
is its one-line description of CONTINUATION's purpose. Evidence checks exit 0
and are recorded in `build/closing/e3-checks.json`; `git diff --check` also
exits 0. No rebuild is needed for these documentation changes.

## Commits and limits

- `f0c9050`: native live-page fix and the fourteen authorized golden updates.
- `f384db3`: HUD evidence/ownership checker repair with fresh passing captures.
- The continuation/archive/report update is committed separately after those.

All completed captures have empty dispatch/floor/interior/unsafe manifests;
all builds use the shared outer lock and at most three jobs. E1 dev and
trace-OFF release pass the complete golden, with all ten WAV hashes unchanged.
There is no new hook/seed, generated-C edit, engine patch/pin change, CI action,
tag, release or merge. PNGs, dumps and local probe scripts stay under `build/`.
Unverified: real hardware listening/controllers, actual Linux/Windows/Deck
runtime/packaging and CI. The HUD check is qualified for its fixed baseline
route/layout; it does not claim arbitrary-track raster reconstruction.
