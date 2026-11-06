# Music and sound effects at the same time

Top Gear 2 (USA) ships two complete sound systems. The SOUND menu's
`RACE SOUND` item picks one of them with a single word. This document maps
both systems, explains why the cartridge makes them exclusive, and describes
the `BOTH` choice added by the port.

All addresses are guest 24-bit addresses. ROM evidence is raw disassembly;
runtime evidence is TCP probes and the engine's always-on audio write dump
(`GENESIS_AUDIO_WRITEDUMP`, which records the writer PC for every FM/PSG
write). Nothing here is copied from another game.

## 1. The setting

| Address | Size | Meaning |
|---|---|---|
| `$FF240E` | word | Race sound mode. `0` = SOUND EFFECTS, `1` = MUSIC. A3-relative `-$5FFA(a3)`. |
| `$FF2554` | struct | Menu controller object that owns the SOUND pages. |
| `$FF2560` | word | Current value of the RACE SOUND page (`A4+$0C`). `0` = SOUND EFFECTS, `1` = MUSIC. |

The RACE SOUND page is entered from the SOUND submenu (`RACE SOUND`,
`MUSIC TEST`, `EFFECTS TEST`). Its value handler is the leaf at `$01F0D4`:
up/down adjust the word at `A4+$0C`, A/B/C leave the page. The generic page
enter/leave helpers at `$01ED3A` / `$01ED60` copy between `A4+$0C` and
`$FF240E`, so the word that the race reads is the value shown on the page.

Readers of `$FF240E` (raw-ROM scan of `-$5FFA(a3)`):

| Address | Role |
|---|---|
| `$001FBE/$001FC2/$001FF4/$002104` | boot/sound-test save and restore |
| `$01ED3A/$01ED60` | menu enter/leave value copy |
| `$0048E2` | race V-int: tick the 68k SFX engines |
| `$006530` | race init: upload the race SFX driver and start engine sound |
| `$023062` | scene transition: install IRQs when SFX mode |
| `$02503A/$02504A` | sound helper: stop music / reset SFX |
| `$0250E2/$025114` | SFX command gates |
| `$0251F4/$02522E` | music start/refresh |
| `$025298` | SFX reset gate |
| `$0252CC` | per-frame engine-SFX gate |

## 2. The drivers

### Music: 8 KB Z80 driver ("Genesis Music / FX by Sound Images v1.4")

* Image: ROM `$02589A..$027899`, copied to `$A00000..$A01FFF` by
  `$024C76` (called once from reset at `$002090`).
* Reset vector: `DI; LD SP,$1FF0; JP $0042`; the ASCII banner sits inside
  the image at `$0258B8`.
* Mailbox: `$A00080` = command, `$A00081` = status, `$A00084` = pause/stop
  flag, `$A00087..$A0008A` = little-endian work pointer (`$0F0000`),
  `$A00091..$A00093` = volume/pan.
* 68k veneers: `$024CD4` (send command), `$024D22` (read status),
  `$024D04` (command `$FF` = stop music), `$024D50/$024D64`
  (`$A00084` = 1/0).
* The race track is chosen by `$0251F4` (also reached from `$025090`
  inside the engine-sound update): it reads the current attract/track index
  at `$FF16BE`, masks to 2 bits, and sends track `{1,2,3,6}` from the table
  at `$02522A`.

### Race SFX: 68k FM/PSG engine plus a small Z80 image

* FM engine: `$070A12` starts a channel, `$070AC0` updates six FM channels,
  `$070B48` services a channel's stream, `$0708E0` resets PSG state.
  State bases are `$FF862E` (FM) and `$FF8622` (PSG).
* PSG engine: `$07090E` starts a PSG effect, `$07092C` updates four PSG
  channels, `$0709FC` clears state.
* Per-frame ticks: `$070010` (PSG) and `$07001C` (FM), called from the race
  V-int at `$0048F2/$0048FE`.
* Small Z80 image: ROM `$0701F6..$0708DF` (0x6EA bytes), copied to
  `$A00000` by `$0700C8`, with command bytes at `$A0025E..$A00261`
  written by `$07018A`.
* The image initialises `$A00194` from the table at `$070FF0` and
  `$A00004`/`$A000CC` from `$070FA8`. Its reset path is
  `DI; LD SP,$1000; ... LD A,($025E); AND A; JR Z` - it only reacts to
  `$A0025E`.
* **The command writer `$07018A` has no caller and `$A0025E` is never
  written after upload.** A write log across the race shows no writes to
  `$A0025E..$A00261` after the upload itself. This image is vestigial in the
  race. Its only effect is that it overwrites the first 0x6EA bytes of the
  8 KB music driver in Z80 RAM.

### Race init

`$006530`:

```
move.w -$5FFA(a3),d0       ; $FF240E
or.w   -$6BCE(a3),d0       ; attract/demo flag
bne    keep_music
jsr    $0253EE             ; upload the race SFX Z80 image, reset SFX state
jsr    $025418             ; start the engine-sound FM effect
keep_music:
```

`$0253EE` is exactly: upload image (`$070000` -> `$0700C8`), PSG reset
(`$070008`), FM state clear (`$070014`).

## 3. Root cause of the exclusivity

It is **policy plus shared hardware**, not a channel count enforced by a
driver allocator:

1. One `$FF240E` word drives every sound decision. In MUSIC mode the game
   skips the SFX image upload, never starts engine sound, and the race
   V-int never ticks the 68k FM/PSG engines. In SFX mode it skips the music
   start (and actively stops the driver with command `$FF`).
2. Both engines program the *same* YM2612 and SN76489. There is no channel
   allocator between them: the 68k engine keys and voices all six FM
   channels and the PSG directly, exactly as if music were not running.
3. The 68k engine must request the Z80 bus (`$A11100`) to reach the chip
   registers. Every SFX update stalls the Z80 music driver while the 68k
   owns the bus.
4. The race SFX Z80 image is uploaded into `$A00000`, overwriting the music
   driver. Only one of the two can occupy Z80 RAM.

So the cartridge could be made to run both code paths, but they would share
one chip and one bus. That is the real limit the owner suspected, and it is
also why the simplest implementation is a shared-chip mix rather than a
clean layered mix.

## 4. What happens today

| Mode | Music driver A | SFX driver image B | 68k FM/PSG engine |
|---|---|---|---|
| MUSIC | runs, race track started | not uploaded | never ticked |
| SOUND EFFECTS | stopped (`$A00080=$FF`), still resident | uploaded (idle) | ticked, all channels |

SFX commands are not "sent and dropped" at the driver. They are never sent:
the wrappers return early on `tst.w -$5FFA(a3)`.

## 5. Chosen technique: policy split with a host menu value

The port adds a third SOUND menu state, `BOTH`. The cartridge's own
`$FF240E` word is kept in its valid range (MUSIC = 1) so every stock reader
stays safe; a host flag records that the player picked BOTH. At race time
the SFX-side reads are presented as `0` and the music-side reads keep `1`,
so both engines execute.

Game-only change; no engine patch. See `game/tg2_audio_both.c` and the
`game_hook` sites in `game/game.toml`.

### Menu

* `$01F0D4` (the RACE SOUND value handler) is replaced by a host handler.
  It keeps the stock `0`/`1` word, cycles SOUND EFFECTS -> MUSIC -> BOTH,
  and stores BOTH only in host state.
* The value row is 8x16 glyph tiles painted into dynamic VRAM tiles. While
  BOTH is selected, `on_frame_post` repaints the four value glyphs as
  `BOTH` (plus a blank) in the menu's own palette, and leaves a one-pixel
  palette-1 outline like the stock font. Sprite positions, palette,
  priority and the `RACE SOUND` header are untouched.
* Screenshot: `build/audio/sound-menu-both.png`.

### Race policy

While BOTH is selected, the audio write stream shows both engines active.
The hook sites make the SFX side see `0` and restore the word before the
dependent branch:

| Patch site | Restore site | Effect |
|---|---|---|
| `$006530` | `$006538` | race init uploads SFX state and starts engine sound |
| `$0048E2` | `$0048EA` | race V-int ticks `$070010` / `$07001C` |
| `$0250E2` | `$0250E6` | SFX command gate opens |
| `$02511C` | `$025120` | second SFX command gate opens |
| `$02503A` | `$02503E` | helper stops music / resets SFX as SFX mode |
| `$02504A` | `$02504E` | SFX reset gate opens |
| `$02529A` | `$02529E` | SFX reset gate opens |
| `$0252CC` | `$0252D0` | per-frame engine-SFX update runs |

`$0700C8` (the race SFX Z80 image upload) is skipped in BOTH: the image is
never commanded, and it would overwrite the live music driver. Verified at
race frame 4300: `$A00000` still contains `F3 31 F0 1F C3 42`, i.e. the
music driver's reset vector, in BOTH.

Music-side sites (`$025088`, `$0251F4`, `$02522E`, `$0252CC`'s music
counterparts) are deliberately not patched: BOTH keeps the stock MUSIC
value there, so `$0251F4` still starts the race track.

### Why not a second virtual chip

A second YM2612+SN76489 would give a clean layered mix, but it needs an
engine change to tag every chip write by origin, instantiate a second copy
of both chip models, render/mix it, and keep save-state/rollback state for
it. It also does not by itself stop the 68k engine from stalling the Z80
bus. That is a larger engine feature than this task's scope; the current
implementation is game-only and stock-compatible. The shared-chip character
is documented under limitations.

## 6. Evidence

### Stock modes are unchanged

Deterministic `.input` scripts and `--wav` (capture from boot) for the same
route, before and after the change (the SOUND EFFECTS route waits the same
250 frames on the page as the BOTH route so all captures have one timeline; an
unpadded SOUND EFFECTS run also matched stock exactly) (stock binary built from the parent
commit in a separate worktree):

| Capture | SHA-256 |
|---|---|
| MUSIC, stock | `bc15c3b401f19cdc66d2c5a290189a44cc9150ac08671477d095a6c7ef390156` |
| MUSIC, this build | `bc15c3b401f19cdc66d2c5a290189a44cc9150ac08671477d095a6c7ef390156` |
| SOUND EFFECTS, stock | `af1f9fd5387edd998722665bc5c9117ab3a0ed74b600203fdc2878a1467e76ff` |
| SOUND EFFECTS, this build | `af1f9fd5387edd998722665bc5c9117ab3a0ed74b600203fdc2878a1467e76ff` |

Cold boot framebuffer fingerprints are unchanged:
frame 60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD`.

### Captures

All three use the same deterministic route (title -> SOUND -> RACE SOUND ->
race -> hold accelerate) and `--wav`, at 223721 Hz stereo:

| Capture | Frames | Peak | RMS | Race peak | Race RMS |
|---|---:|---:|---:|---:|---:|
| `build/audio/race-music.wav` | 23,888,532 | 9711 | 0.04399 | 7862 | 0.04308 |
| `build/audio/race-sfx.wav` | 23,925,852 | 9774 | 0.04446 | 6142 | 0.04362 |
| `build/audio/race-both.wav` | 23,851,212 | 9730 | 0.04715 | 9217 | **0.05090** |

`race peak/RMS` is measured from sample 15,300,000 (race running). BOTH is
louder than either single mode and has the highest peak.

### Both command streams execute

`GENESIS_AUDIO_WRITEDUMP` (writer PC per FM/PSG write), counts for race
frames >= 4100:

| Capture | 68k-origin writes (`pcz=$FFFF`) | Z80-origin writes |
|---|---:|---:|
| BOTH | 6,300 | 82,829+ |
| MUSIC | **0** | 83,530+ |
| SOUND EFFECTS | 6,332 | (driver-B image active; no music PC family) |

MUSIC has no 68k SFX writes; SOUND EFFECTS has no music-driver write
family; BOTH has both. The Z80 state dump at race frame 4300 also shows the
music driver alive in BOTH (same command/track state as MUSIC, differing
only in a few tempo counters).

### Spectral evidence that both are audible together

FFT peaks (Hz, relative magnitude) in a race window at t = 93.87 s:

| Capture | Music-only peaks | SFX-region peaks |
|---|---|---|
| MUSIC | **157.0 (1.00), 163.9, 232.1, 239.0** | - |
| SFX | - | **102.4 (1.00), 109.2, 116.1, 150.2** |
| BOTH | **157.0 (1.00), 163.9, 232.1, 239.0** | **116.1, 122.9** |

The music fundamental series survives at full relative level in BOTH, and
the engine/SFX region is also present. At other race windows the same
pattern repeats (e.g. t = 75.99 s: MUSIC 61.4 + 942/949 vs SFX 116.1/122.9,
BOTH contains 61.4, 942/949 and 116.1-class energy).

### Manifests

`dispatch_misses.toml`, `floor_coverage.toml`,
`interior_label_misses.toml` and `floor_unsafe.toml` contain zero entries
after the deterministic BOTH/MUSIC/SFX runs.

## 7. Limitations

* BOTH is a **shared-chip mix**, not a layered mix. The 68k SFX engine
  programs the same six FM channels and the same PSG, and it owns the Z80
  bus while updating them. Music notes can be stolen or delayed. The
  command-stream and spectral evidence proves both are present; owner
  listening confirmation on real speakers is still required.
* The host BOTH flag is session state, not written to SRAM or settings. It
  persists while the process runs; a fresh boot starts in the stock SOUND
  EFFECTS selection, exactly as the cartridge does.
* The synthetic "BOTH" glyphs use the menu palette and outline but are
  drawn by the port, not by a ROM string. A stock font tile for `B`/`H`
  is not available in the dynamic font bank.
* A second virtual YM2612+PSG (clean layered mix) remains the next step if
  the shared-chip mix is not acceptable by ear.
