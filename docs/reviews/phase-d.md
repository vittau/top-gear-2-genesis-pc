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
The native rewrite is pending the continuation/page-profile scope decision.
