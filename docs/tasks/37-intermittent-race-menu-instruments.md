# Task 37: intermittent missing instruments in race-menu music

**Status: done (2026-11-10).** Root-caused, fixed, verified at runtime and
merged into `main`. The owner listened to the fixed build from a clean boot
with his own BOTH settings and approved it ("Está certo").

After manually testing the current local macOS build containing the S3 Linear
Filter and unified runtime menu, the owner approved those changes ("Está tudo
certo") and then reported that some instruments sometimes seemed absent in the
race-menu music. His saved settings at the report: RACE SOUND **BOTH**,
Music/SFX 100 %, bypass filter Off; the withdrawn Clean FM / Clean engine
samples sections were not present.

## Root cause

In BOTH, `z80_route()` (`game/tg2_audio_both.c`) sent *every* 68K access to Z80
RAM `$A0025E..$A00261` to the second Z80 core, not only the race SFX engine's
command writes. Those four offsets are also entries `$37..$3A` of the resident
music driver's note → octave table at Z80 `$0227` (96 entries, 8 octaves × 12
semitones, value `octave << 3`, read at Z80 `$0151` / ORed at `$0161`).

The 68K uploads that driver byte by byte at boot (`$024C76`, ROM
`$02589A..$027899` → `$A00000..`), and `tg2_audio_frame_pre()` adopts the mode
before the guest's first instruction. With **BOTH persisted in `settings.ini`**,
routing was therefore live during the boot upload: the four `$20` bytes went
into the second core's RAM and the driver's table kept zeros. Note indices
`$37..$3A` (octave 4, semitones G..A♯) then played block 0 instead of block 4 —
four octaves down, below audibility, i.e. the line *disappears*.

Selecting BOTH after boot, or from the RACE SOUND page, leaves the driver
intact; that is why every earlier acceptance capture and the live-toggle probe
(which all visit the page) passed, and why the report needed the owner's saved
setting.

## Fix

`z80_route()` now routes the command ports only while the second core actually
holds the race SFX image, tested from guest state (its first three bytes are the
image's `JP $0410`, `C3 10 04`), mirroring `first_z80_runs_sfx_image()`. No host
flag, so it self-corrects on cold reset (both cores return to the pre-boot
image), on a quickstate load and across races; the upload itself still routes
through the existing `s_sfx_upload` window (`$0700C8` → RTS `$070188`).

## Result (see `docs/AUDIO.md` §5 and §8 "Task 37")

* First-core Z80 RAM `$25E..$261` after a persisted-BOTH boot: `00 00 00 00`
  before, `20 20 20 20` (= ROM = MUSIC = SFX) after; whole-image diff count 97 →
  96, i.e. MUSIC's own work variables. Second-core RAM: `20 20 20 20` before,
  empty after.
* Chip A vs MUSIC, same route: 0.973–0.997 before, **1.000000 with maximum
  sample difference 0** after, for title, main menu, 1P setup, track intro and
  shop. `tools/verify_both_boot.py`'s 400–900 window (the 0.995227 of the old
  record) now reads 1.000000. Race window 0.9883 → 0.9953 with an identical
  note stream (the residual is BOTH's extra BUSREQ/tick timing, not pitch).
* Register level: 24 of 25 diverging note writes were `$A5 = $04` (block 0)
  where MUSIC wrote `$24` (block 4) for note `$37` on FM channel 2; 0 pitch
  divergences after the fix.
* Affected screens on the captured route: title, main menu, 1P setup, track
  intro and shop (the owner's "race menu"), plus the race music; one note every
  ~221 frames on channel 2.
* Same-session proof without a code change: poking the four bytes back to `$20`
  at frame 800 moved chip A from 0.994834 to **1.000000** against MUSIC.

## Caveats

* A quickstate saved in an affected session keeps the corrupted driver bytes
  until the next boot re-uploads the driver.
* The comment above `step_z80()` in the engine's `genesis_machine.c` still
  describes the withdrawn BUSREQ release; code and docs say the Z80 is halted on
  BUSREQ. Comment only — not changed here (it would need its own engine patch).
* Owner listening: approved on the local macOS build (2026-11-10). Steam Deck
  audio was not listened to separately.
