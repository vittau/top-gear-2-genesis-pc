# Phase D native BOTH sound policy

Branch `vittau/review-phase-d`, based on untouched main `332744c`.

## Golden extension before the rewrite

The untouched base executable is retained at `build/phase-d/base-TG2Recomp`.
Only regression tooling and hashes were changed for this checkpoint; game and
engine implementation bytes are unchanged. The original four SFX/MUSIC JSON
objects compare equal, including every frame dimension/hash and WAV digest,
to `build/phase-d/golden-before.json`.

The official tool now captures ten cases: options off/default on crossed with
SFX, MUSIC and BOTH races, plus a live-switch race and a SOUND-page route for
each presentation. The live race starts BOTH and calls the runtime option
setter at frames 4200 (SFX), 4500 (MUSIC) and 4800 (BOTH); all directives log
`ok`, and the frozen race audio stays identical to uninterrupted BOTH.

The SOUND-page route asserts page index 4, captures the stock SFX value, then
uses the cartridge's controller handler to visit MUSIC, BOTH, MUSIC and SFX.
It also calls the runtime option setter on the open page for BOTH/MUSIC/SFX.
Eight screenshots per presentation remain under `build/phase-d/d0/` and only
their SHA-256 hashes are committed. Baseline limitation preserved: a runtime
switch to SFX on the open page leaves the MUSIC row visible (the live-SFX and
MUSIC screenshot hashes are equal); controller switching shows SFX correctly.
No fix for that pre-existing behavior is part of this checkpoint.

Commands (shared lock; streamed WAV hashing and deletion):

```sh
flock ~/.cache/tg2-heavy.lock /opt/homebrew/bin/python3.14 tools/regression.py \
  --exe build/phase-d/base-TG2Recomp --out build/phase-d/d0 --uncapped --record
flock ~/.cache/tg2-heavy.lock /opt/homebrew/bin/python3.14 tools/regression.py \
  --exe build/phase-d/base-TG2Recomp --out build/phase-d/d0-repeat --uncapped
```

Recording and the independent comparison both exit 0. The recorded baseline has 784 framebuffer hashes, ten WAV hashes and sixteen
SOUND-page screenshot hashes. Every dispatch/floor/interior/unsafe manifest
count is zero. BOTH WAV SHA-256 (options off and on, uninterrupted and live):
`171df2eff5b2a12604f7b24694b4010661f050a824aa182c44716462f0d72f97`.
The first recording attempt rejected the menu cadence (36 emitted vs 35
expected); choosing an end frame just past the last cadence point fixed that
tool expectation before the successful recording.

## ROM evidence and implementation planning

Raw-ROM disassembly uses `build/phase-b/venv/bin/python tools/disasm_tg2.py`;
outputs remain under `build/phase-d/`, not in Git. `$6530` is inside race-init
routine `$64C2`, and `$48E2` is inside V-int `$4714`. Each reads the sound word,
ORs the demo/attract flag at `A3-$6BCE`, then conditionally runs the SFX side.
The independent stock continuations are `$654C` and `$490A` respectively.
The existing generated functions contain 926 and 1599 lines respectively;
replacing these complete functions would also rewrite unrelated scene/IRQ code.

Music/SFX policy routines are `$25032`, `$25078`, `$250E2`, `$2511C`,
`$251F4`, `$2522E`, `$25298`, `$252CC`. The page profile loader is `$1ED2C`:
its final copy at `$1ED3A` currently needs the host selection in all three
modes, including MUSIC selected at boot while guest `$FF240E` remains zero.
The coordinator approved the two continuation entries and the all-mode page
profile replacement before implementation; the D0 golden remains the acceptance
criterion, including the stale live-SFX page behavior.

## Native replacements and ROM evidence

All addresses below were checked against the raw USA ROM using the existing
Capstone disassembler, with the generated base used to cross-check instruction
cycle retirement. No generated C was edited. The hook returns 1 after its
native replacement; policy hooks return 0 in SFX/MUSIC. The approved page
profile replacement runs in all modes. The existing three-choice input handler
at `$1F0D4` and upload/trace observation hooks remain.

| Hook / original routine | ROM behavior and native BOTH policy |
| --- | --- |
| `$6530` inside `$64C2` | `MOVE.W A3-$5FFA,D0; OR.W A3-$6BCE,D0; BNE $654C` gates SFX initialization. Native BOTH initializes the SFX image when not in demo mode, then enters `$654C`. |
| `$48E2` inside `$4714` | Same policy test, `BNE $490A`, gates the per-V-int calls to `$70010`/`$7001C`. Native BOTH ticks SFX and resumes `$490A`; the resident music driver continues separately. |
| `$25032` | Stops music through `$24D04` only in MUSIC, SFX through `$2525C`/`$2527A` only in SFX. Native BOTH stops each independent writer, retaining the demo/2P guards and instruction order. |
| `$25078` | Refreshes race music through `$251F4`, then initializes the SFX channels. Native BOTH executes both paths. |
| `$250E2` | Ordinary sound-command gate checks sound mode, demo/pause/cooldown/channel flags, then tail-calls `$24D3A`. Native BOTH preserves the SFX-side eligibility and command path. |
| `$2511C` | Urgent command gate checks sound mode/demo/pause, sets the cooldown and tail-calls `$24D36`. Native BOTH retains those non-mode checks. The existing stock `$25114` pre-check remains. |
| `$251F4` | Selects the race music track using the course index and table at `$2522A`, or stops music in SFX. Native BOTH keeps the MUSIC behavior. |
| `$2522E` | Selects finish/result track 6, or stops music in SFX. Native BOTH keeps the MUSIC behavior. |
| `$25298` | Stops SFX when enabled, respecting demo/2P state. Native BOTH executes the SFX stop path. |
| `$252CC` | Sound-mode/demo/activity gate tail-calls `$254B8`. Native BOTH uses SFX eligibility. |
| `$1ED2C` | Copies page profile words and finally `$FF240E` into `A4+$0C`. The native loader copies the same profile words and the session's two-state page value directly; it never changes `$FF240E`. |
| `$206AE` | Emits a row's sprite descriptors through `$1CE0`. Only row 18 on the RACE SOUND page with host BOTH selected is replaced: native code builds BOTH tiles and emits the same geometry/palette/priority with a separate tile allocation. All other rows use stock code. |

The two approved new function seeds are original control-flow joins, not new
ROM routines: `$654C` is the `4EB9 000012E8` JSR after `$6546`'s LEA and the
target of `$6538`'s BNE; `$490A` is `302B 9F84`, after `$4904`'s LEA and the
target of `$48EA`'s BNE. The discovered base code has no callable entry or
external call to either tail. Their incoming branches are in the replaced
policy blocks. `game.toml` records this evidence. In stock modes the generated
split transfers preserve the original execution; in BOTH the native block
calls the same continuation. The V-int tail receives the existing 56-byte
MOVEM frame's stack accounting. The resumable race-loop entry `$65F2` stays
unchanged, and quickstate tests below exercise its continuation.

Native helpers preserve the ROM operation order, guest stack slots, condition
codes and per-instruction cycle retirement, including return addresses on calls
to stock sound drivers. There is no instruction interpreter, ROM patch, engine
change or extra submodule patch. Live routing still uses `adopt_mode()` and
`tg2_race_audio_policy_frozen()`, and each Z80's resident image is still read
from guest RAM every frame. Reset/state-load routing and mid-race policy freeze
retain their previous behavior. The SFX PCM trace and engine chip-dump code
remain; their individual diagnostic captures were not rerun.

## Native menu row and removed adapter

The decoded menu descriptors at RAM `$FF2ADE` identify row 18 as two sprites,
covering five 8x16 columns at screen x=141 through 180. The native row uses this
geometry but emits BOTH directly with tiles `$4F0..$4F9`, in the audited unused
menu gap `$9E00..$9F3F` (before SAT `$A800`). The baseline plane A/B/window/SAT
captures contain no references to these tiles. Original MUSIC/SFX glyphs remain
intact. Selection changes therefore require no saved tile cache or restoration.
The generated glyph allocation is written only if its bytes differ, including
after state load; it is not repainted by a frame callback.

The **320 glyph bytes match the former BOTH row exactly** (old tiles
`479..488`, new allocation at `$9E00`), SHA-256:
`13e0d780163fa529fc29131261c6fa0a8e8367a1c538b246ceda3eaad3bd40c7`.
The palette and sprite geometry are unchanged. Baseline/new VRAM evidence is
`build/phase-d/menu.vram` and `menu-new.vram`; page PNGs are under
`build/phase-d/d0/` and `final-dev/`/`final-release/`. None is committed.

Deleted: the eight-deep present/restore stack, all temporary `$FF240E` writes,
`present_session_value`, the saved glyph buffers, row restoration and the
`tg2_frame_post` callback/declaration. `tg2_audio_both.c` is **646 → 710 lines**:
the explicit native routines replace the smaller input/output-masking adapter.
Its other public audio interfaces are unchanged.

Write proof:

```sh
rg -n -i '240e|5ffa|a006|RAM_SOUND_MODE' game --glob '*.[ch]'
# exit 0: only the explanatory $FF240E comment at tg2_audio_both.c:2
rg -n 'present_value|present_sfx|present_music|present_session_value|restore_value|s_patch_stack|restore_row|paint_both|tg2_frame_post' game
# exit 1: no matches
```

No native game writer remains for the sound-mode word. The cartridge's own
menu teardown at `$1ED60` still copies `A4+$0C` to `A3-$5FFA` (`$FF240E`) through
unchanged generated stock code; that is the original menu's setting commit.
Native menu-input writes target the page control/value words at `$FF2554` plus
offsets, including `$FF2560`, rather than the global sound word.

Pre-existing page bug, deliberately preserved: open SOUND → RACE SOUND, then
use the runtime menu to select BOTH, MUSIC and finally SOUND EFFECTS while the
page remains open. The runtime option changes, but the cartridge's value row
continues to show MUSIC after that final change. Using the page's own UP/DOWN
controls shows SOUND EFFECTS correctly. D0's `live-sfx.png` and `music.png`
hashes remain equal after this rewrite; no independent fix was made.

## Generated-code changes

A function-body comparison against the untouched base finds **589 existing
functions byte-identical**, ten existing functions changed only by added/removed
hook calls, and two existing functions changed by the approved splits:

- `$64C2` → existing prefix plus new `$654C` tail.
- `$4714` → existing prefix plus new `$490A` tail.

The ten hook-only bodies are `$1ED2C`, `$206AE`, `$25032`, `$25078`, `$250E2`,
`$2511C`, `$251F4`, `$2522E`, `$25298`, `$252CC`. No function was removed.
`build/phase-d/generated-diff.py` and `generated-diff.json` record the comparison.
Both configurations are regenerated by the builds; generated C is neither
hand-edited nor committed. SFX/MUSIC race output and all SOUND-page values match
D0 at runtime, including the approved all-mode page loader.

## Final verification commands

Commands below exit **0**, unless explicitly noted. Builds and captures run
sequentially under `flock ~/.cache/tg2-heavy.lock`, never nested, at most three
build jobs and one runtime. The official tool streams WAV SHA-256 and deletes
the WAVs even on failure. No ROM/dump/state/PNG/WAV/generated C was committed.

| Command | Result / retained evidence under `build/phase-d/` |
| --- | --- |
| Raw-ROM `build/phase-b/venv/bin/python tools/disasm_tg2.py ADDRESS --size SIZE` for `$25018/0x2F0`, `$6520/0x50`, `$48C0/0x65`, `$1ED00/0x90`, `$1EF80/0x1C0`, `$1EE34/0x148`, `$1680/0x2A0`, `$1EB70/0x164`, `$1F258/0x228`, `$1F316/0x400`, `$206AE/0x1BE`, `$1EACA/0xA6` | ROM policy, profile, descriptor and renderer evidence |
| `flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh` | `d1-policy-build.log`: first native policy build |
| `flock ~/.cache/tg2-heavy.lock /opt/homebrew/bin/python3.14 tools/regression.py --out build/phase-d/d1-policy --uncapped` | all ten D0 cases pass before replacing the menu row |
| Same locked build after row replacement / cycle review | `d1-row-build.log`, `d1-row-build2.log` |
| `flock ~/.cache/tg2-heavy.lock /opt/homebrew/bin/python3.14 tools/regression.py --out build/phase-d/d1-row --uncapped` | all ten D0 cases pass with native row |
| `flock ~/.cache/tg2-heavy.lock sh build/phase-d/final-check.sh` | `final-check.log`: final dev build/regression, release build/regression and quickstates all pass |
| `python3 build/phase-d/generated-diff.py` | comparison above |
| Baseline and new locked headless `--input-script build/phase-d/menu[-new]-dump.input --max-frames 2000 --turbo --fresh-evidence --debug` | matching 320-byte glyph payload; all four manifests zero |
| `python3 -m py_compile tools/regression.py` | syntax passes |
| `git diff --check` | no whitespace errors |

`final-check.sh` runs these subcommands under its single outer lock:

```sh
JOBS=3 tools/build-linux.sh
/opt/homebrew/bin/python3.14 tools/regression.py --out build/phase-d/final-dev --uncapped
cmake --build build/phase-b/release --target TG2Recomp -j3
/opt/homebrew/bin/python3.14 tools/regression.py \
  --exe build/phase-b/release/TG2Recomp --out build/phase-d/final-release --uncapped
/opt/homebrew/bin/python3.14 build/phase-d/state-check.py
```

The reused release configuration has `GEN_ENABLE_TRACE=OFF`,
`SONIC_REVERSE_DEBUG=OFF`, Release optimization and native IPO, matching the
release-script settings with the existing macOS Freetype workaround. Both final
regressions match **784 framebuffer hashes, ten WAV hashes and sixteen PNG
hashes**. Every completed regression case has zero dispatch misses, floor
coverage, interior-label misses and unsafe-floor addresses. The unchanged
SFX/MUSIC race WAV hashes remain:

- SFX: `1d0ab92b32b7f6ba7ac3e63e42f9c0fdfb8d8dff4dbfdbc20b02220faf7442a6`.
- MUSIC: `431338f523a9b0d54d1145b38c5a28657b712b9b23b0ca0ae312b15e2486b343`.

An additional run without `--uncapped` (`--out build/phase-d/final-default`)
completed the off-SFX case with identical frame/WAV hashes and zero manifests;
it was then deliberately interrupted with SIGINT (exit 130) during off-MUSIC
rather than spending another full paced ten-case run. Complete acceptance
coverage above uses the supported full-runtime `--uncapped` path, which retains
rendering and WAV work; it is not the engine's audio-suppressing benchmark mode.

Quickstates use the same input-script save/load commands as the runner's
queued state operations. A race state is saved at frame 3600, loaded at frame
4000, then checked at 4010 and 4300. Both dev and release restore a newly saved
state and a state saved by the pre-rewrite executable. All four load cases
roll the race clock from `44018078` back to `28234921`, advance to `44072691`,
and show two distinct race pictures, with every manifest count zero.
`state-check/summary.json` records the results. **Old race states do load in
these checks**; old menu states and other historic build configurations were
not qualified. The host state schema/resume loop entry was not changed.

## Commits and limits

Pushed branch: `vittau/review-phase-d`, based on `332744c`.

- `ef1bafb` — untouched-base golden extension, separately committed before native changes.
- `75847ab` — native sound policies and approved continuation entries.
- `9f0d1b4` — native BOTH row; present/restore/repaint adapter removed.
- Final evidence is committed separately after verification.

Verified on macOS: dev and trace-OFF release builds, full deterministic picture/
audio/page/live-switch acceptance, generated-function boundaries and hook-only
changes, exact glyph bytes, zero manifests and race quickstate compatibility.
Unverified: real-device listening, actual Genesis hardware, Linux/Windows/Deck
runtime/packaging, interactive controller use and CI. No engine fork, upstream
push, pin change, CI trigger, tag, release or merge was performed.
