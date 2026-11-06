# Music and sound effects at the same time

Top Gear 2 (USA) ships two complete sound systems and one policy word that
selects between them. The port adds a third `RACE SOUND` choice, **BOTH**,
which runs both systems during a race. The stock choices keep their exact
stock behaviour.

All addresses are guest 24-bit addresses. ROM evidence is raw disassembly;
runtime evidence is TCP probes, deterministic `--input-script` runs, WAV
captures, Z80 RAM dumps and the engine's whole-run FM/PSG write dump
(`GENESIS_AUDIO_WRITEDUMP`, which records the writer PC for every write).
Nothing here is copied from another game.

**Status:** implemented and verified headless (stock parity, both command
streams, both audible sources present in the capture). Owner listening
confirmation on real speakers is still required; BOTH is a shared-chip mix,
not a layered mix (see *Limitations*).

## 1. The setting

| Address | Size | Meaning |
|---|---|---|
| `$FF240E` | word | Race sound mode. `0` = SOUND EFFECTS, `1` = MUSIC. A3-relative `-$5FFA(a3)`. |
| `$FF2554` | struct | Menu controller object that owns the SOUND pages. |
| `$FF2560` | word | Current value of the RACE SOUND page (`A4+$0C`). `0` = SOUND EFFECTS, `1` = MUSIC. |

The main menu's `SOUND` item opens a three-row submenu: `RACE SOUND`,
`MUSIC TEST`, `EFFECTS TEST`. `RACE SOUND` opens a value page whose leaf is
`$01F0D4`:

```
01F0D4  andi.w #$FF,d0     ; button mask
01F0D8  bne.s  $01F0DC
01F0DA  rts                ; no button
01F0DC  move.w d0,$14(a4)  ; remember the mask
01F0E0  move.w $0C(a4),d1  ; current value
...
01F0F4  tst.w  d1          ; UP: floor at 0
01F0FC  cmpi.w #1,d1       ; DOWN: ceiling at 1
01F104  addq.w #1,$02(a4)  ; request page redraw
01F108  move.w #2,$18(a4)
01F10E  move.w d1,$0C(a4)  ; commit value
01F116  andi.w #$70,d0     ; A/B/C leave the page
01F11C  move.w #3,$02(a4)
01F122  clr.w  d0
01F124  rts
```

The enter/leave helpers `$01ED3A` / `$01ED60` copy between `A4+$0C` and
`$FF240E`, so the word the race reads is the value shown on the page. The
menu renders text from dynamic 8×16 glyph tiles (two 8×8 VRAM tiles per
glyph) addressed by the sprite attribute table; there is no ROM string for
the value row that can be edited independently of the tile uploader.

Readers of `$FF240E` (raw-ROM scan of `-$5FFA(a3)`):

| Address | Role |
|---|---|
| `$001FBE/$001FC2/$001FF4/$002104` | boot/sound-test save and restore |
| `$01ED3A/$01ED60` | menu enter/leave value copy |
| `$0048E2` | race V-int: tick the 68k SFX engines |
| `$006530` | race init: upload the race SFX driver and start engine sound |
| `$023062` | scene transition: install IRQs when SFX mode |
| `$02503A/$02504A` | sound helper: stop music / reset SFX |
| `$0250E2/$02511C` | SFX command gates |
| `$0251F4/$02522E` | music start/refresh |
| `$025298` | SFX reset gate |
| `$0252CC` | per-frame engine-SFX gate |

## 2. The drivers

### Music: 8 KB Z80 driver ("Genesis Music / FX by Sound Images v1.4")

* Image: ROM `$02589A..$027899`, copied to `$A00000..` by `$024C76`
  (called once from reset at `$002090`).
* Reset vector: `DI; LD SP,$1FF0; JP $0042`; the ASCII banner sits inside
  the image.
* Mailbox: `$A00080` = command, `$A00081` = status, `$A00084` = pause/stop
  flag, `$A00087..$A0008A` = little-endian work pointer (initialised to
  `$0F0000`), `$A00091..$A00093` = volume/pan.
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
  `$A00004`/`$A000CC` from `$070FA8`. Its reset path only reacts to
  `$A0025E`.
* **The command writer `$07018A` has no caller** (checked in the generated
  dispatch: the address is only a table entry, never a `RECOMP_CALL_NATIVE`
  target), and a whole-race write log shows no writes to `$A0025E..$A00261`
  after upload. This image is vestigial in the race; its only real effect is
  that it overwrites the first 0x6EA bytes of the 8 KB music driver in Z80
  RAM.

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

It is **policy plus shared hardware**, not a channel-count allocator:

1. One `$FF240E` word drives every sound decision. In MUSIC mode the game
   skips the SFX image upload, never starts engine sound, and the race
   V-int never ticks the 68k FM/PSG engines. In SFX mode it skips the music
   start (and stops the driver with command `$FF`).
2. Both engines program the *same* YM2612 and SN76489. There is no channel
   allocator between them: the 68k engine keys and voices all six FM
   channels and the PSG directly, exactly as if music were not running.
3. The 68k engine must request the Z80 bus (`$A11100`) to reach the chip
   registers. Every SFX update stalls the Z80 music driver while the 68k
   owns the bus.
4. The race SFX Z80 image is uploaded into `$A00000`, overwriting the music
   driver. Only one of the two can occupy Z80 RAM.

So the cartridge *can* be made to run both code paths, but they share one
chip and one bus. That is the real limit the owner suspected, and it is why
the simplest implementation is a shared-chip mix rather than a clean
layered mix.

## 4. What stock modes do

| Mode | Music driver A | SFX driver image B | 68k FM/PSG engine |
|---|---|---|---|
| MUSIC | runs, race track started | not uploaded | never ticked |
| SOUND EFFECTS | stopped (`$A00080=$FF`), still resident | uploaded (idle) | ticked, all channels |

SFX commands are not "sent and dropped" at the driver. They are never sent:
the wrappers return early on `tst.w -$5FFA(a3)`.

Measured with `GENESIS_AUDIO_WRITEDUMP` over race frames 3000–5600 (writer
PC from the engine, `pcz=$FFFF` means the 68k):

| Mode | Z80-origin writes | 68k-origin writes | Z80 writer PCs |
|---|---:|---:|---:|
| MUSIC | 333,691 | **0** | 8 (`$0CB2`, `$0C4C`, `$0C4F`, …) |
| SOUND EFFECTS | 244,797 | 17,912 | 12 (`$067F`, `$068E`, `$0494`, …) |
| **BOTH** | **332,691** | **17,804** | **8** (`$0CB2`, `$0C4C`, `$0C4F`, …) |

BOTH reproduces 99.7 % of the MUSIC Z80 write stream and 99.4 % of the SFX
68k write stream, in the same run, from the *same* chip. At race frame 4300
the Z80 reset vector also proves which image is resident:

| Mode | `$A00000..` |
|---|---|
| MUSIC | `F3 31 F0 1F C3 42` (music driver `DI; LD SP,$1FF0; JP $0042`) |
| SOUND EFFECTS | `C3 10 04` (SFX image `JP $0410`) |
| BOTH | `F3 31 F0 1F C3 42` (music driver kept resident) |

## 5. Chosen technique: policy split plus a host-only menu value

The port adds a third SOUND menu state, `BOTH`. The cartridge's own
`$FF240E` word is kept in its valid range (`1` = MUSIC) so every stock reader
stays safe; a host flag records that the player picked BOTH. At race time
the SFX-side policy reads are presented as `0` and the music-side reads keep
`1`, so both engines execute. The race-time SFX Z80 image upload is skipped:
that image is never commanded after upload and it would overwrite the music
driver.

Game-only change; no engine patch. See `game/tg2_audio_both.c` and the
`game_hook` sites in `game/game.toml`.

### Race policy hook sites

All sites were audited against raw ROM disassembly and are generated block
labels, so the hook fires at that instruction. `present 0` rewrites the word
just before the `move.w`/`tst.w`; `restore 1` runs after the flags are set
and before the dependent branch (restoring the RAM word does not change
flags).

| Present site | Stock instruction | Restore site | Effect |
|---|---|---|---|
| `$006530` | `move.w -$5FFA(a3),d0` | `$006538` (`bne.s`) | race init uploads SFX state and starts engine sound |
| `$0048E2` | `move.w -$5FFA(a3),d0` | `$0048EA` (`bne.s`) | race V-int ticks `$070010` / `$07001C` |
| `$0250E2` | `tst.w -$5FFA(a3)` | `$0250E6` (`beq.s`) | SFX command gate opens |
| `$02511C` | `tst.w -$5FFA(a3)` | `$025120` (`beq.s`) | second SFX command gate opens |
| `$02503A` | `tst.w -$5FFA(a3)` | `$02503E` | helper skips the music stop, resets SFX |
| `$02504A` | `tst.w -$5FFA(a3)` | `$02504E` (`bne.s`) | SFX reset gate opens |
| `$02529A` | `tst.w -$5FFA(a3)` | `$02529E` (`bne.s`) | SFX reset gate opens |
| `$0252CC` | `tst.w -$5FFA(a3)` | `$0252D0` (`bne.s`) | per-frame engine-SFX update runs |

`$0700C8` (entry of the race SFX Z80 image upload) is hooked as a whole
function: the hook returns 1 at its first instruction, so the upload is
skipped and the music driver survives. `$01F0D4` (the RACE SOUND leaf) is
replaced by a host handler (below).

Music-side sites (`$025088`, `$0251F4`, `$02522E` and `$0252CC`'s music
counterparts) are deliberately not patched: BOTH keeps the stock MUSIC value
there, so `$0251F4` still starts the race track.

### Menu entry and the "BOTH" text

`$01F0D4` is replaced by `menu_value_handler()`:

* It keeps the stock `0`/`1` page value and stock redraw request, so every
  stock reader and the page's own state machine see a valid value.
* It cycles SOUND EFFECTS → MUSIC → BOTH → MUSIC → …; BOTH is reachable only
  from MUSIC and stores no value above `1` in RAM. An unexpected value read
  from the page is clamped to `1` before use.
* It leaves `D0=0` and the stock flags (`Z=1`, `N=V=C=0`, `X` preserved) on
  every exit path, matching the stock leaf's `clr.w d0` return.

While BOTH is selected, `on_frame_post` repaints the value row's own 8×16
glyph tiles as `BOTH ` in the menu's palette (white strokes, one-pixel
palette-1 outline), using the sprite positions the page already has. Sprite
attributes, palette, priority and the `RACE SOUND` header are untouched.

MUSIC and BOTH both use page value `1`, so the game does not redraw the row
when cycling between them. The first frame BOTH is painted, the original
tiles are cached; when BOTH is deselected the cached stock `MUSIC` tiles are
written back. This is why `BOTH → UP` shows the game's own `MUSIC` text
rather than a stale `BOTH`.

![RACE SOUND page with BOTH selected](images/audio-sound-menu-both.png)

### Safety and lifecycle

* `$FF240E` is never written outside `{0,1}`; BOTH exists only in host
  state, so an unexpected value cannot reach a stock reader.
* `both_active()` requires the stock word to still be `MUSIC`; any stock
  mode change or menu write disables the BOTH behaviour immediately.
* Guest reset and state load call `tg2_audio_reset()` (clears the host flag,
  the pending patch and the cached tiles).
* BOTH is session state, like the cartridge's own sound selection: it is not
  written to SRAM or `settings.ini`, and a fresh boot starts at the stock
  SOUND EFFECTS choice.

### Why not a second virtual chip

A second YM2612+SN76489 would give a clean layered mix, but it needs an
engine change to tag every chip write by origin, instantiate a second copy
of both chip models, render/mix it, and keep save-state/rollback state for
it. It also does not by itself stop the 68k engine from stalling the Z80
bus. That is a larger engine feature than this task's scope; the current
implementation is game-only and stock-compatible. The shared-chip character
is documented under *Limitations*.

## 6. Evidence

### Stock modes are sample-identical to before the change

Stock binary: `origin/main` built in a separate tree with the same engine
patches (`build/stock-build/TG2Recomp`). Route: the same deterministic
`--input-script` (`build/route-music.input` / `build/route-sfx.input`),
5600 frames, 4:3 (`--widescreen off`), `--wav` from boot.

| Capture | SHA-256 |
|---|---|
| MUSIC, stock | `c8737f998c5b9fa5b15f9ad65105ef68370001dd3e95d31c1467fbeaeeb1d2aa` |
| MUSIC, this build | `c8737f998c5b9fa5b15f9ad65105ef68370001dd3e95d31c1467fbeaeeb1d2aa` |
| SOUND EFFECTS, stock | `b145db5e1b9c262e5c8ee4ecff43a09a276e41808684c2765f5ef84133ee84cd` |
| SOUND EFFECTS, this build | `b145db5e1b9c262e5c8ee4ecff43a09a276e41808684c2765f5ef84133ee84cd` |

Every `[FBHASH]` line of the route is also identical between the two builds
(91 lines for MUSIC, 92 for SOUND EFFECTS), and the cold-boot fingerprints
match the documented stock values:

| Cold boot frame | Active framebuffer | FNV-1a-64 |
|---:|---|---|
| 60 | 320 × 224 | `2A0B972960C5E325` |
| 300 | 320 × 224 | `1131D937D70234FD` |

### Three-mode captures

`build/audio/run-{music,sfx,both}/race-*.wav`: same deterministic route
(title → SOUND → RACE SOUND → race → hold accelerate), capture started at
frame 3000 and stopped at frame 5400, 223,721 Hz stereo, 40.069 s each.
`race peak/RMS` is measured from 2 s (race running).

| Capture | Peak | RMS | Race peak | Race RMS | SHA-256 (first 16) |
|---|---:|---:|---:|---:|---|
| `race-music.wav` | 7836 | 1394.03 | 7836 | 1403.79 | `c88e56a9606df0f2` |
| `race-sfx.wav` | 6074 | 1461.17 | 6074 | 1464.74 | `8473716d6c801e70` |
| `race-both.wav` | **9379** | **1657.99** | **9379** | **1672.20** | `d4e3f65637aa4e7c` |

BOTH is the loudest of the three and has the highest peak. Audio stats for
every capture: `dropped_flushes = 0`, `underrun_flushes = 0`.

### Both sources are present in the BOTH capture

20 ms RMS envelope correlation over the race (SFX aligned by the measured
6-frame race-start offset):

| Band | MUSIC envelope RMS | SFX envelope RMS | BOTH envelope RMS | corr(BOTH, MUSIC) |
|---|---:|---:|---:|---:|
| 50–200 Hz | 1058.2 | 1022.4 | 1005.5 | **0.791** |
| 200–500 Hz | 713.7 | 710.9 | **819.8** | 0.542 |
| 500–1000 Hz | 268.3 | **640.5** | 414.7 | 0.447 |
| 1000–2000 Hz | 250.3 | 242.5 | **416.8** | 0.429 |
| 2000–4000 Hz | 169.3 | 88.9 | **307.7** | 0.424 |

BOTH carries the music's bass envelope (0.79 correlation in 50–200 Hz) and
exceeds *both* single modes in the 200–500 Hz, 1000–2000 Hz and 2000–4000 Hz
bands. In the 10 % of race windows where the MUSIC capture is quietest, the
BOTH capture is **1.61×** its RMS (799 → 1260) because the engine SFX is
still playing; the SFX capture in those windows is 1458, i.e. the extra
energy is the engine, not music.

The music envelope correlation is the meaningful audibility check; a
sample-level correlation between the captures is not expected because the
68k engine stalls the Z80 bus and both engines write the same chip
registers, so BOTH is a shared-chip mix, not a sample-wise sum.

### Manifests

`dispatch_misses.toml`, `floor_coverage.toml`, `interior_label_misses.toml`
and `floor_unsafe.toml` contain zero entries after every BOTH/MUSIC/SFX
run, including the deterministic 5600-frame route.

## 7. Reproduction

```sh
JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build

# Deterministic stock-parity runs (see build/route-*.input):
cd build
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy ./TG2Recomp ~/roms/genesis/tg2.bin \
  --no-launcher --widescreen off --max-frames 5600 --hash-frames 60 \
  --wav audio/cli-ours-music/race-music.wav \
  --input-script route-music.input --fresh-evidence

# Whole-run chip write provenance:
GENESIS_AUDIO_WRITEDUMP=$PWD/audio/writes/writes-music.txt ... (same run)

# Interactive TCP captures on port 4430:
python3 build/route_capture.py both    # build/audio/run-both/race-both.wav
```

The deterministic scripts are generated by `build/make_input.py`; they
select SOUND EFFECTS, MUSIC or BOTH at fixed frames, leave the page, start
the race and hold accelerate at frame 3050.

## 8. Limitations

* BOTH is a **shared-chip mix**, not a layered mix. The 68k SFX engine
  programs the same six FM channels and the same PSG, and it owns the Z80
  bus while updating them. Music notes can be stolen or delayed (measured:
  the BOTH music write stream is 0.3 % smaller than MUSIC's, the SFX write
  stream 0.6 % smaller than SFX's). Owner listening confirmation on real
  speakers is still required.
* The host BOTH flag is session state, not written to SRAM or settings. It
  persists while the process runs; a fresh boot starts in the stock SOUND
  EFFECTS selection, exactly as the cartridge does.
* The `BOTH` glyphs are drawn by the port from the menu palette, not from a
  ROM string. The menu's own tiles for `MUSIC` are cached and restored when
  BOTH is deselected.
* A second virtual YM2612+PSG (clean layered mix) remains the next step if
  the shared-chip mix is not acceptable by ear.
