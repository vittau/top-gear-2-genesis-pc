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

## 9. Tempo fidelity (task 18)

The owner's report after the real-device fix was: no pops any more, but the
music still changes speed sometimes, and it sounds slightly slower than
normal. This section measures the music's tempo and pitch against an
independent reference instead of trusting the ear or the engine's counters.

### 9.1 Reference: an accurate emulator, rendered offline

`tools/gpgx_render.c` is a headless libretro frontend (about 400 lines) used
only for this measurement. It loads a core (`genesis_plus_gx_libretro.so`,
installed under `~/tools/retroarch`, never committed), drives the pad from the
same exact-wall-frame JSON route the port uses, steps the core one frame at a
time, and writes the core's own audio callback stream to a WAV (native 44100
Hz, no host resampling) plus PPM screenshots at the route's shot frames. It
opens no window and never touches the host mixer, so a 93 s reference render
takes 2.7 s and is bit-reproducible.

Provenance: Genesis Plus GX (libretro nightly, 2025-11-05 build) on the
owner's cartridge dump, NTSC, region autodetect, no filters, no overclock.
The reference is a *record*, not a claim about the emulator's own accuracy:
GPGX is cycle-accurate for the Z80/YM2612 timing this measurement depends on.

The route reaches the same game state in both: title screen (frame 600), main
menu (1350), and - with the extra SOUND page steps described below - a race
with RACE SOUND = MUSIC at frame ~3900. Screenshots from both sides are in
`build/ref/`.

### 9.2 `tools/audio_tempo_compare.py`

Both recordings are turned into a 100 Hz envelope on log-spaced bands (each
band z-scored, so a level or mix difference between the port and the emulator
does not bias the comparison). The measured envelope is then warped over a
tempo-ratio grid and correlated against the reference, with a lag search, which
gives

* the **global tempo ratio** (measured/reference), in % and in BPM (the
  reference BPM comes from the envelope's autocorrelation, not from a guess);
* the **local tempo ratio** in 1 s steps from sliding 8 s windows, with the
  weighted standard deviation and the largest deviation;
* the **pitch offset in cents**, from the maximum of the long-term log-spectrum
  cross-correlation over a cents-shift grid.

`--selftest` synthesises a melody with known note times and pitches and then
three tempo variants (+1.5 %, -1.0 %, +0.1 %) and two pitch variants (+25 c,
-40 c, event times unchanged). All five are recovered within 0.02 % tempo and
1 cent pitch, and each variant is reported in its own dimension only, so the
tool is qualified rather than trusted.

### 9.3 What the Z80 actually does (ROM evidence)

Disassembling the resident driver (`tools/z80_disasm.py`, a 200-line
bring-up disassembler; the image is ROM `$02589A..$027899` copied to
`$A00000`) shows the music clock is **not** the 68k and **not** the Z80's
vblank IRQ:

```
A00042  call $0D30        ; init
A00045  call $0BE1        ; stop timer B, write reg $26=$BE, start timer B
A00048  ld a,($8006)
A0004B  ld ($0080),a      ; publish the mailbox status byte ($A00080)
A0004E  ei
A0004F  call $0BFC        ; wait for YM2612 status bit 1 (timer B), reload
A00052  call $0627        ; process one music tick
A00055  jr   $0A4F
...
A00038  push af / push hl / inc ($008C) / pop hl / pop af / ei / ret   ; vblank
```

The vblank handler only bumps a counter at `$008C`; the sequencer tick is
`call $0BFC` waiting for `ld a,($4000) / and $02` - the YM2612 **timer B
overflow flag** - and then restarting the timer. So the music tempo is the
timer B period, which the engine models synchronously for CPU-visible status
reads (`runner/video/genesis_bus.c`, `ym_timer_update`).

Measured from the chip-write stream (`GENESIS_AUDIO_WRITEDUMP`, tick = the
`$27=$2E` reload written at Z80 PC `$0C4F`): 452 ticks over 9.41 s = 48.0
ticks/s, median interval 19.87 ms, against the modelled timer B period
`(256-$BE) * 16 * 144 * 7` master cycles = 19.83 ms. The guest-side clock is
therefore within 0.2 % of the model, and scaling the modelled period by 2 or
0.5 scales the tick rate by exactly 2 or 0.5 (`GENESIS_YM_TIMER_SCALE`, a
measurement-only knob, not committed): the driver is timer-bound, not
processing-bound.

### 9.4 H1 audit: is the Z80 starved?

The candidate H1 mechanisms were BUSREQ held longer than hardware, a wrong Z80
cycle budget per line, a wrong timer rate, and bank/wait-state accounting. A
temporary instrument in `step_z80` counted every slice (removed before commit;
the numbers are reproduced here):

```
[Z80-STATS] steps=183400 cycles=33898128 skipped_reset=34349 skipped_busreq=375
```

Over 700 wall frames that is 262 slices per frame (228 Z80 cycles each =
59,736 cycles/frame = 3.579545 MHz exactly). 34,349 slices were skipped
because the Z80 is held in reset before the driver upload (frames 0-131) and
**375 because the 68k held BUSREQ**, i.e. 0.66 lines per frame = **0.25 % of
the Z80's cycles**, and those are the frames where the 68k really requests the
bus. `Z80_PER_LINE 228` and `MASTER_PER_LINE 3420` are the exact hardware
ratio (53.693175/3.579545 = 15.0). No cycle budget is lost: the debt carries
across slices, so whole-instruction overshoot is repaid rather than dropped.

So the guest side had one genuine clock defect, and it is in the **audio
sample clock**, not the CPU budget: the mixer was drained with
`895780` master cycles per frame while the machine runs `262 * 3420 = 896040`,
and the PSG's sub-sample divider remainder was discarded at every frame
boundary. That is `3732` samples per frame instead of `3733.5`: the whole
stream ran **-402 ppm** (0.04 %, 0.7 cents) against hardware, and the DRC had
to absorb it as a permanent correction. Patch `0008` fixes both (exact frame
length, remainder carried); the offline tap is now exactly `3733.5`
samples/frame and the framebuffer hashes are unchanged (frame 60
`2A0B972960C5E325`, frame 300 `1131D937D70234FD`).

## 10. Feasibility map: a decoupled Z80 + YM2612 + PSG clock domain

The owner asked whether the 68k/Z80 coupling can be loosened so the music no
longer depends on 68k or video timing (design C: run the Z80 and both sound
chips on the audio device clock, in realtime mode only). This is the map the
implementation would need; it is a feasibility study, not a change: nothing in
this section is implemented, and the offline deterministic mode stays coupled.

### 10.1 Every 68k <-> Z80 interaction in this game

ROM evidence (disassembly in `docs/AUDIO.md` §2 and the driver image above) plus
the `GENESIS_AUDIO_WRITEDUMP` stream and the `[SND-TRACE]` ring:

| Interaction | Site | Frequency | Needs the bus? |
|---|---|---|---|
| Z80 RAM mailbox writes (command, pause/stop, work pointer, volume/pan) | 68k veneers `$024CD4`, `$024D04`, `$024D50/$024D64` writing `$A00080..$A00093` | on a track change / stop, not per frame in MUSIC mode | yes, BUSREQ |
| Z80 RAM mailbox read (driver status byte `$A00081`) | `$024D22` | once per race-init / track change, not per frame | yes, BUSREQ |
| YM2612 register writes from the 68k | SFX engine `$070A12/$070AC0`, PSG `$07090E/$07092C` | **0 in MUSIC mode** during a race; ~18k writes per 2600 frames in SFX/BOTH | yes, BUSREQ |
| YM2612 status reads from the 68k | none in these drivers (the 68k engines do not poll the chip) | - | - |
| BUSREQ (68k owns the Z80 bus) | `$A11100` writes around every mailbox/chip access | measured 375 held scanlines in 568 active frames = **0.25 % of Z80 cycles** | - |
| Z80 -> 68k | nothing: the Z80 writes only its own RAM and the chips | - | - |
| Z80 vblank IRQ (VDP) | handler `$0038` = `inc ($008C)` only | 60/s, and the count is not the music clock | - |
| Z80 YM2612 status reads | 4 sites; the sequencer loop `$0BFC` polls status bit 1 (timer B overflow) | once per music tick (~50/s) | - |

### 10.2 What can be answered from a snapshot, and what cannot

* **Mailbox writes and the status-byte read (68k side).** These are
  "start track N", "stop", "set volume" and one acknowledged handshake. Applying
  them at the next Z80 slice (<= one video frame, 16.7 ms) changes nothing that
  is audible or observable: the track still starts, the stop still stops. A
  timestamped mailbox can therefore answer them with no synchronous handshake.
* **68k chip writes (SFX/BOTH).** Already timestamped on the shared audio event
  queue; a decoupled domain would apply them into the audio clock with the same
  stamps. They are fire-and-forget, so late application is safe.
* **The Z80's own YM2612 status poll.** This one *cannot* be answered from
  another domain: the sequencer waits for the chip's timer-B flag, and the flag
  is produced by the chip that renders the music. That is exactly why the
  decoupled design has to move the Z80 *and* the chips together, and it is the
  only place a split domain would need care (a poll must never see a flag from
  a different time base, or the tick count changes).
* **BUSREQ.** In a decoupled domain the 68k never stops the Z80; the mailboxes
  absorb the interaction instead. That is the whole point, and it costs the
  music nothing because the measured cost today is 0.25 %.

### 10.3 SFX latency

A 68k SFX command applied at the next audio-domain boundary adds at most one
audio block (21 ms at 1024 frames / 48 kHz, 16.7 ms at the frame cadence).
Engine sound and one-shot effects are already mixed a frame ahead of the
speaker, so this is inside the existing latency budget and under the ~30 ms
audio/visual sync threshold.

### 10.4 Verdict

No blocking synchronous dependency exists in MUSIC mode, so design C is
feasible. It is nevertheless a large change: a second scheduler timebase, a
timestamped mailbox, and save-state/rollback state for both domains, plus the
rule that the offline deterministic capture stays coupled (so the offline WAV
and framebuffer hashes remain reproducible). Its value is immunity to
68k/video stalls; it would *not* by itself change the music tempo, because the
measurements above show the Z80 already receives 99.75 % of its cycles and the
sequencer clock is the YM2612 timer, not the 68k. It is therefore proposed as a
follow-up, not as this task's fix.

### 10.5 Why not implement it now

The measurable guest-side defects this task did find are ordinary clock bugs
(fixed in patches 0008 and 0009), and the real-device wobble is a host-side
control-loop problem that design C does not address: a decoupled Z80 removes
starvation, but the speaker still gets the music through the same DRC bridge,
so the ratio controller is what has to be tempo-stable either way. Landing a
second timebase and a mailbox first would add save-state risk without fixing
the symptom the owner reported.

### 9.5 Measurements

Route: the SOUND page selects `RACE SOUND = MUSIC`, then a race is started and
accelerated - both sides play the *music*, not the engine SFX, which is what the
owner's report is about. Device captures are the PipeWire null sink of
PERFORMANCE §10 (16:9, 60 fps on, no CPU burners), 11 000 frames = 183 s.

**Guest side (offline, deterministic).**

| Quantity | Before | After |
|---|---|---|
| PSG samples per guest frame | 3732 (fixed) | 3733.5 (exact, 3733/3734 alternating) |
| Audio stream rate error vs hardware | **-402 ppm** | **0 ppm** |
| Music tick (chip-write stream, median) | 19.87 ms = 50.3/s | 19.87 ms = 50.3/s |
| Modelled YM2612 timer B period | 19.83 ms | 19.83 ms (tick is timer-bound: verified by scaling it 2x / 0.5x and watching the tick rate follow exactly) |
| Z80 cycles delivered | 33 898 128 in 148 676 slices, 375 BUSREQ lines lost = **99.75 %** | unchanged |
| Framebuffer hashes, frames 60 / 300 | `2A0B972960C5E325` / `1131D937D70234FD` | **identical** |

**Pitch.** The port is in tune with the reference: 0.0 +/- 0.5 cents on the
long-term spectrum of the title music, and +0.5 cents between the two device
captures of the same route. The tool's selftest recovers +25 and -40 cents
within 1 cent. There is no transposition defect; the "slower" impression is not
a pitch shift.

**Real-device tempo stability (H2).** Same 183 s music route, same build, only
the controller differs (`GENESIS_AUDIO_DRC_CLASSIC=1` restores the pre-fix
servo for the A/B). The playback ratio is what the ear hears as speed:

| Controller | ratio p05..p95 | ratio span | fastest ratio change | ring fill p05/p50/p95 | dropouts |
|---|---|---:|---:|---|---:|
| pre-task-18 proportional servo (classic) | -211..+519 ppm | 1986 ppm | **1233 ppm/s** | 72 / 82 / 92 ms | 0 |
| task-18 tempo-stable controller | **-337..+723 ppm** | **1330 ppm** | **37 ppm/s** | 70 / 82 / 94 ms | 0 |

The new controller's ratio moves **30x slower** (37 ppm/s worst case = 0.0037 %
per second, a fraction of a cent) while the ring fill stays where task 15 put
it and there are still zero underruns, zero conceals and zero pops. Comparing
the two device recordings of the same 3-minute route through
`tools/audio_tempo_compare.py`: global tempo ratio **1.000000**, local tempo at
1 s steps over 170 windows: mean -0.005 %, **std 0.060 %, max deviation
0.155 %** - i.e. the two builds play the same music and differ only by the
slow wander the classic servo had.

**What is verified and what is not.** Verified: the sample-clock error (-402 ppm)
and its fix; the Z80 cycle budget; the timer-B-driven tick rate; the pitch; the
30x reduction of playback-ratio slew; unchanged video hashes. Not established:
an absolute tempo number for the race music against the emulator. My alignment
attempts on this soundtrack are defeated by its own loop period (a 7 % warp
aliases onto exactly one loop over a 35 s window, which produced a convincing
but false "-7 %" before I checked the loop period). The one direct comparison
that does not alias - a 500 fps autocorrelation of the rhythmic pulse - gives
118 ms on the reference and 120 ms on the port (-1.7 %), and the port's
*measured* tick rate (50.3/s) leaves no room for more than a couple of percent.
A guest-side timer-model error of that order is possible and is the next thing
to pin down (the exact hardware timer-B divisor for `$26=$BE`); it is not
explained by anything this task fixed.

### 9.6 Reproduce

```sh
# Reference (no window, no host mixer, bit-reproducible):
cc -O2 -o build/gpgx_render tools/gpgx_render.c -ldl -lm
build/gpgx_render --core ~/tools/retroarch/cores/genesis_plus_gx_libretro.so \
    --rom ~/roms/genesis/tg2.bin --frames 6000 \
    --script game/baseline-route.json --wav build/ref/race-music.wav

# Port, deterministic:
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy build/TG2Recomp ~/roms/genesis/tg2.bin \
    --no-launcher --widescreen off --max-frames 6000 \
    --input-script build/ref/music-route.input --wav build/ref/port.wav

# Comparison (also --selftest):
python3 tools/audio_tempo_compare.py build/ref/race-music.wav build/ref/port.wav

# Real device, before/after the controller change:
pactl load-module module-null-sink sink_name=tg2_test
python3 tools/audio_device_capture.py --exe build/TG2Recomp \
    --out build/device/after --frames 11000 --mode on \
    --route build/ref/music-route.input
python3 tools/audio_device_capture.py --exe build/TG2Recomp \
    --out build/device/before --frames 11000 --mode on \
    --route build/ref/music-route.input --env GENESIS_AUDIO_DRC_CLASSIC=1
python3 tools/audio_drc_stats.py build/device/after/frame-stats.csv \
    build/device/before/frame-stats.csv
pactl unload-module <id>
```
