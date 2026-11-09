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

**Status:** BOTH is a layered mix on two virtual chips (music driver on chip A;
the 68K SFX engine **and** the race SFX Z80 PCM player — engine loop, nitro,
impacts — on chip B, the latter on a second Z80 core). Verified headless, on a
null sink, and with the persisted-BOTH boot regression. Stock modes are
byte-identical. Owner listening confirmation is required.

Task 30 (§13) adds four player options on top of that: **Music volume**,
**SFX volume**, **Clean FM** (YM3438 core, no ladder distortion) and **Clean
engine samples** (band-limited reconstruction of the DAC stream). All four
default to the stock sound, which stays byte-identical.

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
* **This image is the car's sample player, not vestigial** (task 20
  correction of the earlier reading). Its entry `JP $0410` polls `$A0025E` and
  runs a table-driven PCM/DAC player (`$042F`..`$0660`): during a race it
  writes `$2A`/`$2B` and feeds the YM2612 DAC at ~6.6 kHz, in bursts whose rate
  swings between 0 and ~12,000 writes/s — the engine loop and every nitro
  burst. That is why stock SOUND EFFECTS races have car sounds and MUSIC races
  do not: the image shares the 8 KB of Z80 RAM with the music driver, so only
  one of them can be resident. (The `$07018A` command writer at `$0701C8` is
  the 68K-side command path; no writes to `$A0025E` occur after the upload in
  the captures, so the player runs from its own tables.)

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

## 5. Chosen technique: two virtual chips, routed by writer

BOTH is a *layered* mix, not a shared-chip mix. On real hardware both drivers
program the same YM2612 and SN76489; the port instead gives each writer its own
virtual chip while BOTH is selected:

| Virtual chip | Receives | Driver | Timer/status reads |
|---|---|---|---|
| **A** (canonical) | every write from the **first Z80** (music driver) | the resident music driver, exactly as in MUSIC mode | first Z80 reads: chip A. Its timer B is the music clock (patch 0010's free-running grid). |
| **B** (second) | every **68K**-origin FM/PSG write **and** every write from the **second Z80** (race SFX PCM image) | 68K SFX engine + the SFX image, exactly as in SOUND EFFECTS mode | 68K and second-Z80 reads: chip B (its own status/timer model). |

Engine changes:
`patches/segagenesisrecomp/0011-writer-routed-second-sound-chip.patch` (two
virtual chips) and
`patches/segagenesisrecomp/0014-second-z80-core-race-sfx-pcm.patch` (the second
Z80 core for the race SFX image).

* `AudioEvent` carries the writer (`AUDIO_ORIGIN_68K`, `AUDIO_ORIGIN_Z80` for the
  music driver, `AUDIO_ORIGIN_Z80_SFX` for the second core); `audio_event_push()`
  stays the 68K writer and the Z80 bus push sites use
  `audio_event_push_origin()`.
* `ym2612_*_chip(i)` / `psg_*_chip(i)` make both chip models instantiable twice.
  Chip 0's arithmetic, scratch ring, sample-clock remainder and output LPF are
  unchanged, so its own output is the single-chip output.
* CPU-visible timer/status state is per chip (`YmTimerState`): the bus copy is
  chip A's (Z80 music clock); a second instance answers the 68K side and the
  second core.
* **Second Z80 core.** The race engine and nitro are not 68K FM: a resident Z80
  PCM/DAC player in the race SFX image (ROM `$0701F6`, YM2612 part-2 `$2A`/`$2B`
  at ~6.6 kHz) plays them. The 68K's upload (`$0700C8`) overwrites all 8 KB of
  Z80 RAM and pulses the reset line, so it cannot coexist with the music driver
  in one core. In BOTH the machine therefore runs a second superzazu Z80 next to
  the first: its own 8 KB RAM, bank register, cycle debt and
  bus-request/reset state (`GenesisBus.z80_sfx_*`, `GenesisMachine.z80_sfx`).
  A game-owned predicate (`game/tg2_audio_both.c: z80_route`) sends the 68K's
  upload access (RAM writes plus `$A11100`/`$A11200`) and its later PCM command
  ports (`$A0025E..$A00261`) to the second core; every other 68K Z80-space access
  still reaches the music driver. The upload's writes, reset pulse and image can
  no longer stop the music driver — the failure mode of the first prototype.
  The second core is stepped per scanline with the same cycle accounting as the
  first, halts on its own BUSREQ (faithful SOUND EFFECTS timing) and is reset and
  frozen when BOTH is left. Its CPU state and RAM live in the machine image, so
  quickstates and rollback snapshots include them.
* Chip A is fed from the first Z80's writes in its own push order. Chip B is fed
  from the 68K engine **and** the second core in the **stock merged stamp order**
  (stable sort + FM address/data pair guard): that is exactly the register
  stream SOUND EFFECTS mode feeds to one chip, which is why chip B reproduces
  that mode. The single-chip path keeps the old merge untouched.
* Both chips advance across the whole frame, so each emits exactly the number of
  samples the stock single chip would; the outputs are summed at unity gain and
  clamped to int16. Measured peaks leave the headroom unused (BOTH peak 10702 of
  32767), so no limiter is applied. **Mix gain: 1.0 for both chips.**
* BUSREQ keeps halting the Z80 while routing is on. Patch 0011 had released the
  music driver from BUSREQ in BOTH; that let the Z80 read the music mailbox while
  the 68K was writing it, so a persisted BOTH silenced the title/menu music.
  Halting is the hardware behaviour and costs the music nothing measurable (the
  68K engine's BUSREQ window is a few hundred cycles per frame). Regression
  capture: boot with `[mods.racesound] mode = both`, title/menu music correlates
  0.9952 with MUSIC mode (≥ 0.99 required).

Stock modes (MUSIC, SOUND EFFECTS) never enable routing or the second core: one
chip, one core, the old merged-stamp path, byte-identical output (verified
below).

`GENESIS_AUDIO_CHIPDUMP=<prefix>` writes `<prefix>A.wav` / `<prefix>B.wav`, each
chip's stream through the same mix that feeds the main WAV, for the acceptance
comparison.

### Race policy hooks (unchanged, still required)

The cartridge has one policy word, `$FF240E`, and both drivers must run, so the
host still presents the value each reader expects. BOTH exists only in host
state; `$FF240E` never leaves `{0,1}` and is only different for the instruction
that reads it (present/restore on a small stack, re-entrant).

| Present site | Stock instruction | Side | Restore site | Effect |
|---|---|---|---|---|
| `$006530` | `move.w -$5FFA(a3),d0` | SFX | `$006538` (`bne.s`) | race init uploads SFX state and starts engine sound |
| `$0048E2` | `move.w -$5FFA(a3),d0` | SFX | `$0048EA` (`bne.s`) | race V-int ticks `$070010` / `$07001C` |
| `$0250E2` | `tst.w -$5FFA(a3)` | SFX | `$0250E6` (`beq.s`) | SFX command gate opens |
| `$02511C` | `tst.w -$5FFA(a3)` | SFX | `$025120` (`beq.s`) | second SFX command gate opens |
| `$02504A` | `tst.w -$5FFA(a3)` | SFX | `$02504E` (`bne.s`) | SFX reset gate opens |
| `$02529A` | `tst.w -$5FFA(a3)` | SFX | `$02529E` (`bne.s`) | SFX reset gate opens |
| `$0252CC` | `tst.w -$5FFA(a3)` | SFX | `$0252D0` (`bne.s`) | per-frame engine-SFX update runs |
| `$025088` | `tst.w -$5FFA(a3)` | music | `$02508C` | music start/refresh gate stays open |
| `$025200` | `tst.w -$5FFA(a3)` | music | `$025204` (`beq.s`) | race music track start is not skipped |
| `$02523A` | `tst.w -$5FFA(a3)` | music | `$02523E` (`beq.s`) | music command 6 is not skipped |
| `$02503A` | `tst.w -$5FFA(a3)` | **music** | `$02503E` | stops the menu music before the race track starts |

`$02503A` is the one site that must see **1**, not 0: it calls the music stop
(`$024D04`, command `$FF`). Stock SOUND EFFECTS skips it because no music is
playing; BOTH has the menu music running, so with 0 the stop was skipped and the
race track command was layered on the old track. That was one of the sources of
the owner's "sounds repeating".

`$023062` is deliberately **not** hooked (it selects the boot IRQ pair; the race
scenes are qualified with the stock MUSIC path). `$001FBE/$001FF4` (boot sound
test) save and force the word on their own stack and are left alone.

`$0700C8` (the race SFX Z80 image upload) is skipped while BOTH is live: the
image would overwrite the resident music driver in Z80 RAM. See *Limitations*
for what that costs (the car's PCM sample player).

### Menu value page (and the re-entry bug)

`$01F0D4` is replaced by `menu_value_handler()`:

* It owns the three-state choice: DOWN walks SOUND EFFECTS → MUSIC → BOTH, UP
  walks back; the page value written to `A4+$0C` stays in `{0,1}` (BOTH uses the
  MUSIC value) so the page state machine, the sprite builder and the menu
  teardown that stores `$0C(a4)` into `$FF240E` all keep working unchanged.
* It leaves `D0=0` and the stock flags (`Z=1`, `N=V=C=0`, `X` preserved) on
  every exit path, matching the stock leaf's `clr.w d0` return.

`tg2_frame_post()` no longer depends on a button press: it reads the menu
controller's page index (`$FF2554 == 4`, the RACE SOUND page) every frame and,
while BOTH is the choice, forces the page value to 1 and repaints the row. The
page's entry path reloads its value from `$FF240E`, which can only be 0/1, so a
re-entered page used to redraw "MUSIC" and stay there. Now the page always shows
the current host choice, whichever route entered it — including after backing
out to the main menu and re-entering SOUND → RACE SOUND (PNG below).

### Persistence

The choice is a player option, `[mods.racesound] mode = sfx|music|both`
(default `sfx`, the cartridge's own boot value), saved with the other options
in `settings.ini` and editable from the launcher Mods page and the in-game
overlay. `TG2_RACE_SOUND=sfx|music|both` overrides it for automated captures.
The in-game page updates the option in memory, so the next save writes it.

Guest reset and state load (`tg2_audio_reset`) clear the pending patch and the
tile cache but **keep** the player's choice.

## 6. Why the first implementation did not engage in real play

The first version (task 05) required the cartridge word to still read MUSIC:

```c
static int both_active(void) { return s_both && ram_read16(0xFF240E) == 1; }
```

That is the wrong source of truth, because `$FF240E` is **not** the menu value.
It is written in exactly four places in the whole ROM:

| Address | Writer |
|---|---|
| `$002104` | boot: store 0 (SOUND EFFECTS default) |
| `$001FC2` / `$001FF4` | boot sound test: force 1, then restore the pushed value |
| `$01ED60` | **menu scene teardown only** (`$01EC84`/`$01ECC2` → `$01ED46`) |

`$01ED3A` loads it into the controller at menu scene entry; the value page
only keeps it in `A4+$0C`.  Live probe on the RACE SOUND page (TCP, one frame
apart while the player cycles and leaves the page):

| Point | `$FF240E` | page `$FF2554` | page value `$FF2560` |
|---|---:|---:|---:|
| RACE SOUND page open | 0 | 4 | 0 |
| DOWN → MUSIC | 0 | 4 | 1 |
| DOWN → BOTH | 0 | 4 | 1 |
| leave page | 0 | 2 | 1 |
| back on the main menu | **0** | 0 | 1 |
| menu teardown → game setup | **1** | 180 | 0 |

So while the page is open the host flag is set but the cartridge word is still
0.  Every path that reaches a race without the menu scene teardown — a guest
reset, a state load, or any future route that starts a race from another scene
— left the word at 0, `both_active()` false, and the eight hooked SFX-side
sites alone meant **stock SOUND EFFECTS**: the music driver stopped and only
the 68k SFX engine ran.  The same hole existed on the music side, unseen: the
old build left the three music-side reads unhooked, so with the word at 0 the
music gate `$025088` skipped the race track entirely and even a BOTH selection
that did engage could lose its music.

Two more real-play defects followed from the same mistake:

* The page value was reloaded from the cartridge word at menu entry, so any
  visit to the page before the teardown showed the stale 0 while the host
  still painted "BOTH" — the text and the setting disagreed.
* Nothing persisted: after a restart the player had to find the page again.

What was **not** wrong, and what the owner's report cannot be pinned on: on
the plain menu route the engines really do both run.  The write dump of a
BOTH race contains 12,600 68k-origin chip writes and 226,910 Z80-origin
writes; MUSIC contains 0 68k writes and SOUND EFFECTS 12,614, and the three
offline WAV captures of the same route are byte-identical before and after
this change (see *Evidence*).  The noise the owner heard came from running both
streams on one register file (task 20, §5): the music driver writes the same six
FM channels about twenty times as often as the SFX engine, so each engine
re-keyed and re-voiced the other's notes.

## 7. The "BOTH" text

### Where the menu font lives

The value row is **sprites**, not the name table: sprite attribute entries at
`y=$0104`, palette 3, 8x16 glyphs over two 8x8 VRAM tiles, tile numbers
allocated per draw (MUSIC: tiles 479..488; SOUND EFFECTS: 455..478).  The
tile pixel encoding is exact:

* one 8x16 cell per character on an 8-pixel column grid,
* 2-pixel strokes, one outline pixel in palette entry **1**,
* the stroke body uses entry **3** on rows 0..7 and entry **2** on rows 8..15.

Searching the raw ROM for the glyph bitmaps found nothing in any plausible
encoding (4bpp 8x8 and 8x16 tiles, 1bpp 8x16 row-major and column-major, 2bpp
pair-planes, bit-reversed variants, all 24 colour permutations, and the text
itself as glyph-code strings).  The menu font is part of the packed graphics
archive the game unpacks at run time, so there is no raw table to index.

### How the glyphs are made

`game/tg2_audio_both.c` therefore reproduces the font's own construction:

| Letter | Source |
|---|---|
| `O` | the menu font's own O, transcribed from the value page's SOUND EFFECTS row (tile 457) |
| `T` | the menu font's own T, same row (tile 475) |
| `B` | that font's `D` bowl (tile 463) plus the `E` middle bar (tile 465) |
| `H` | that font's two stems (any stem letter) plus the `M` crossbar (tile 479) |

The 16 bytes per letter are the stroke shape; the tile generator adds the
outline, the 3/2 body split and writes the two VRAM tiles.  Regenerating the
font's own O with this generator reproduces tile 457 except for six pixels in
the bottom outline row, i.e. the shapes are the game's, not an approximation
of them.

Placement matches how the game centres its own values: the four letters are
painted as one continuous 16-row band and centred on `x = 160`, which lands
them at 144..175 against MUSIC's 141..178 and SOUND EFFECTS' 108..211 (all
three centre on 159.5).  The sprite entries are **not** moved: the game re-DMAs
its shadow attribute table every frame from RAM, so a sprite move does not
stick; painting across the row's own columns is stable and keeps the palette,
priority and vertical alignment the game chose.

The stock row is cached the first frame BOTH is painted and written back when
BOTH is left (BOTH and MUSIC share the page value, so the game does not redraw
that row by itself), and the cache is re-captured whenever the game rebuilds
the row.

![RACE SOUND page with BOTH selected](images/audio-sound-menu-both.png)

## 8. Evidence

Every capture below is controller input only (`tools/tg2_both_route.py`,
`tools/tg2_menu_capture.py`, `tools/tg2_audio_compare.py`); nothing writes
guest memory.  The write dump is the engine's `GENESIS_AUDIO_WRITEDUMP`
(`pcz=$FFFF` is a 68k-origin chip write), windowed to the last 1800 sound
frames of each run, which is the race.

### Writer-routed acceptance

Same deterministic route for all three modes (menu → SOUND → RACE SOUND →
BOTH/MUSIC/SOUND EFFECTS → leave → 1P race), offline capture, throttled with a
nitro press (`C`) every 2 s. Chip dumps are `GENESIS_AUDIO_CHIPDUMP`
(`<prefix>A.wav` / `<prefix>B.wav`); every number is measured on the last 2400
frames (40 s) of the race.

| Comparison | Correlation | Gain | Residual RMS |
|---|---:|---:|---:|
| Chip A vs MUSIC mode | **0.998455** | 0.998242 | 82.16 |
| Chip B vs SOUND EFFECTS | **0.994714** | 0.994632 | 158.78 |
| **BOTH mix vs chip A + chip B** | **1.000000** | 1.000000 | **0.00** |

* **Chip A is MUSIC.** The music driver's write stream is identical and the only
  difference is the sub-sample phase of its writes. Per-second RMS is within
  1.2 % of MUSIC mode and the race never drops below 970 RMS, so no SFX write
  leaks into chip A.
* **Chip B is SOUND EFFECTS.** Its writers are exactly the 68K engine plus the
  second Z80 running the race SFX image, applied in the same merged-stamp order
  the stock single-chip path uses. The 68K PCM command stream is identical
  frame-for-frame: 373 commands in both modes, identical IDs and timestamps
  (`GENESIS_AUDIO_SFXPCM_TRACE`). Per-second RMS over the last 20 s differs by at
  most 7.1 (0.4 %), including the nitro and impact bursts.
* **The mix is exactly A + B at unity gain**: sample-by-sample maximum difference
  0 (no samples clamped) over the 40 s window. Peaks: chip A 7880, chip B 6059,
  mix 10702 of 32767 — no clipping and no limiter needed.

### The race SFX image's command bank

The image's player indexes three tables that the 68K upload patches in; decoding
them from the raw ROM (`ROM $070FA8` + entry offsets, lengths at `$070FF0`) gives
18 commands (0–17, durations 0.20–1.25 s at the player's rate). The race engine
uses six of them on this route, identified from the command trace plus the 68K
state:

| Command | Events in 40 s race | What it is |
|---|---:|---|
| 6 | 312 | engine loop (continuous while the throttle is down; 562 without nitro) |
| 3 | 23 | engine start / gear change |
| 4 | 13 | **nitro** (0 events on the identical route without `C`; appears at the `C` press frame in a single-press control) |
| 5 | 6 | **impact** (9–13 frames before each sampled speed drop, e.g. 6298 → 6311) |
| 7 | 12 | impact / skid (5 frames before a speed drop at 6486 → 6491) |
| 2 | 7 | impact (at the last collisions, 7651/7670) |

Commands 0, 1 and 8–17 are handled by the player but not requested on this
route (duplicate samples and other events). The acceptance point is that every
command the 68K engine issues in SOUND EFFECTS is issued at the same frame in
BOTH: the trace files are byte-identical.

### Stock modes are sample-identical

Same scripts, same build settings. Whole-run WAV MD5, this branch (patches
0001–0016, with 0014) against a `main` 2e42151 build of the same scripts:

| Capture | main build | this branch |
|---|---|---|
| MUSIC | `9faab80d68d1b80caa500420a9b301e6` | `9faab80d68d1b80caa500420a9b301e6` |
| SOUND EFFECTS | `ec4a9c819a0ec93772abe9741fb0ce16` | `ec4a9c819a0ec93772abe9741fb0ce16` |

The 4:3 cold-boot fingerprints still match the documented stock values: frame
60 `2A0B972960C5E325`, frame 300 `1131D937D70234FD` (identical before/after).
The miss/floor manifests (`dispatch_misses.toml`, `floor_coverage.toml`,
`interior_label_misses.toml`, `floor_unsafe.toml`) contain zero entries after
every run.

### Real device (null sink), 3-minute BOTH race

`tools/audio_device_capture.py` on a `tg2_test` null sink (PERFORMANCE §10; the
game's own stream is moved onto it, the default device is untouched), then the
last 3 minutes of the race through `tools/audio_glitch_detect.py`:

| Metric | BOTH race, 180 s |
|---|---:|
| pops | **0** |
| digital-silence dropouts | **0** |
| DC-hold dropouts | **0** |
| envelope-collapse events | 71 (23.7/min) |

The envelope class is the music's own note gaps, not a device path defect: on the
same 40 s offline race window MUSIC mode alone reports 296 of them, BOTH 24 and
SOUND EFFECTS 3 (the SFX PCM and the second chip fill the gaps). Offline BOTH
reports **0 pops, 0 digital-silence dropouts and 0 DC-hold dropouts**. No
underrun, conceal or overflow event was logged during the device capture.

### Persisted BOTH: title and menu music

Boot with `[mods.racesound] mode = both` in `settings.ini` (no menu visit) and
compare against MUSIC mode on the same boot:

| Window | BOTH vs MUSIC correlation | RMS BOTH / MUSIC |
|---|---:|---:|
| boot (frames 120–300) | 0.992670 | 1387 / 1262 |
| title/menu (400–900) | **0.995227** | 1448 / 1343 |
| menu late (600–900) | 0.993112 | 1481 / 1392 |

The +6 % RMS is a constant DAC bias: each idle YM2612 model emits a fixed +380
offset, stock modes carry one chip's worth (mean 193) and BOTH carries two
(mean 569). It is inaudible DC, costs no headroom, and is left uncorrected so
chip B stays bit-comparable with SOUND EFFECTS and the mix stays exactly A + B.

Selecting BOTH mid-session is the acceptance route above (menu → RACE SOUND →
BOTH → race); the music never stops at the switch and the race starts with both
layers. The game does not return to the main menu after a race (known cartridge
behaviour), so a post-race menu check is not reachable.

### CPU

Release configuration, 16:9, HUD edges, 60 fps on, same route, CPU work =
frame interval minus pacer wait, race window 3300–4300, measured on a machine
shared with another qualification run:

| Mode | CPU p50 | CPU p95 | p95 / 16.683 ms budget |
|---|---:|---:|---:|
| MUSIC | 6.80 ms | 11.75 ms | 70.4 % |
| **BOTH (second chip + second Z80)** | **6.93 ms** | **11.49 ms** | **68.9 %** |

The second Z80 interpreter and the second YM2612+PSG cost +0.13 ms at p50; the
p95 difference is inside the run-to-run noise of the shared machine. No
underrun or conceal event in either run.

### Save states

The second core's CPU state, 8 KB RAM, bank register and bus-request/reset
state are fields of `GenesisMachine`/`GenesisBus`, i.e. inside the raw machine
image that `machine_save_state()` and `machine_rb_save()` write and
`machine_load_state()`/`machine_rb_load()` restore (pointers re-wired on load).
The size guards in `rb_state.c` were updated (GenesisBus 32864, GenesisMachine
98872 bytes). Stock modes are unaffected; a state saved in BOTH carries both
cores and both chips.

### The menu page, re-entered

The page after backing out to the main menu and re-entering SOUND → RACE SOUND
with BOTH selected — the reported bug ("going back shows MUSIC") is gone:

![RACE SOUND page re-entered with BOTH selected](images/audio-sound-menu-both-reenter.png)

### The menu page

![stock RACE SOUND pages and BOTH at 1x](images/audio-sound-menu-compare-1x.png)

![stock RACE SOUND pages and BOTH at 3x](images/audio-sound-menu-compare-3x.png)

Three pages from one run of the same build: stock MUSIC (141..178), stock
SOUND EFFECTS (108..211) and the new BOTH (144..175); all three centre on
159.5 and share palette entry 1 for the outline and entries 3/2 for the body.

![BOTH before and after, with stock MUSIC for reference](images/audio-sound-menu-before-after-3x.png)

Left: the task 05 host-drawn glyphs (white body, dark outline, left aligned on
the MUSIC column grid).  Middle: the new font-derived glyphs.  Right: the
game's own MUSIC row.

## 9. Reproduction

```sh
JOBS=3 tools/build-linux.sh ~/roms/genesis/tg2.bin build

# Persisted-BOTH boot regression (blocker: music silent when BOTH was saved):
# boots BOTH/MUSIC/SFX from clean settings dirs and requires correlation >=0.99.
python3 tools/verify_both_boot.py --exe build/TG2Recomp

# Second Z80 acceptance: same nitro route, final build, per-chip export and the
# SFX engine's command trace (identical IDs/frames in SFX and BOTH).
for m in music sfx both; do
  SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy \
  GENESIS_AUDIO_CHIPDUMP=build/accept/$m/chip \
  GENESIS_AUDIO_SFXPCM_TRACE=build/accept/$m/pcm.txt \
  build/TG2Recomp ~/roms/genesis/tg2.bin --no-launcher --wav build/accept/$m/run.wav \
      --input-script build/nitro/$m.input
done
python3 tools/audio_glitch_detect.py --device build/accept/both/run.wav

# Interactive route capture on a trace-enabled build (TCP, port 4550):
python3 tools/tg2_both_route.py --mode both --out build/final/route-both
python3 tools/tg2_both_route.py --mode both --widescreen 16:9 --60fps \
    --out build/final/route-both-169
python3 tools/tg2_both_route.py --mode both --route password --out build/final/route-password
python3 tools/tg2_both_route.py --mode both --exit A --out build/final/route-exit-a

# Menu page captures (stock values plus BOTH, 1x and 3x):
python3 tools/tg2_menu_capture.py --sheet

# Deterministic release-config runs (no command server):
python3 tools/tg2_both_route.py --mode both --script-out build/rel-route-both/route.input --script-race
GENESIS_AUDIO_WRITEDUMP=build/rel-route-both/writes.txt \
SDL_AUDIODRIVER=dummy TG2_RACE_60FPS=1 build-rel/TG2Recomp ~/roms/genesis/tg2.bin \
    --no-launcher --widescreen 16:9 --wav build/rel-route-both/race.wav \
    --input-script build/rel-route-both/route.input --hash-frames 60

# Audibility numbers:
python3 tools/tg2_audio_compare.py --music .../route-music/race.wav \
    --sfx .../route-sfx/race.wav --both .../route-both/race.wav

# Writer-routed acceptance: per-chip export for the same route in each mode.
# (Routes: build/base/{music,sfx,both}.input from tg2_both_route.py --script-out.)
for m in music sfx both; do
  GENESIS_AUDIO_CHIPDUMP=build/accept/$m/chip \
  SDL_AUDIODRIVER=dummy build/TG2Recomp ~/roms/genesis/tg2.bin --no-launcher \
      --widescreen off --wav build/accept/$m/run.wav \
      --input-script build/base/$m.input
done
# chipA.wav vs music/run.wav and chipB.wav vs sfx/run.wav: correlate the last
# 2400 frames (40 s); the mix is chipA + chipB bit-for-bit.

# Real device (§10 of PERFORMANCE.md; null sink, stream moved, speaker untouched):
pactl load-module module-null-sink sink_name=tg2_test
python3 tools/audio_device_capture.py --exe build-rel/TG2Recomp \
    --out build/device/both3min --frames 17000 --mode on \
    --route build/device/both3min.input
python3 tools/audio_glitch_detect.py --device build/device/both3min/race180.wav
pactl unload-module <id>
```

`TG2_RACE_SOUND=sfx|music|both` forces the choice without touching
`settings.ini`; `TG2_RACE_60FPS` and `--widescreen` behave as before.

## 10. Limitations

* **One cartridge sound engine runs on a virtual second Z80.** Real hardware has
  one Z80 and one pair of sound chips; BOTH is the documented accuracy
  concession. The second core is a superzazu interpreter (the music core is the
  same core in these builds), only stepped while BOTH is selected. Its timing is
  the same per-scanline cycle accounting as the first core; the engine/impact
  samples land within a frame of SOUND EFFECTS. The command stream is identical;
  the 0.9947 chip-B correlation is dominated by sub-sample phase, not missing or
  extra events.
* **The second Z80 does not exist in stock modes.** MUSIC and SOUND EFFECTS keep
  one core and one chip; their whole-run WAV MD5s are byte-identical to a
  `main` build of the same scripts (see §8).
* **A constant DAC bias adds one extra chip's worth in BOTH.** Each idle
  YM2612 model carries a fixed +380 sample offset; stock modes have one chip
  (mean 193 in the title theme), BOTH has two (mean 569). It is inaudible DC and
  is left uncorrected so chip B stays comparable with SOUND EFFECTS and the mix
  stays exactly A + B.
* Chip A is the music driver alone: in the acceptance race its per-second RMS
  matches MUSIC within 1.2 %, and the two writers never mix (mix = A + B
  exactly, maximum difference 0). The MUSIC race never drops below 970 RMS, so
  there is no music-silent moment where an SFX write could leak into chip A.
* The whole BOTH layer is selected at the next race start (the in-game page
  applies the choice to the option immediately; routing and the second core are
  re-asserted every frame from the host choice).
* **Save states include both cores and both chips** (the machine image carries
  `GenesisMachine.z80_sfx`, its RAM/bank/control fields in `GenesisBus`, and both
  virtual chip models; `rb_state.c`'s size guards were updated). A state saved in
  BOTH reloads a running second core; stock modes are unaffected.
* The game does not return to the main menu after a race, so BOTH cannot be
  re-checked there; the in-game RACE SOUND page repaints from host state on
  every frame and still shows BOTH.
* The `BOTH` glyphs are drawn by the port from the menu font's own geometry,
  not from a ROM string (the font is packed; see section 7). B and H are
  composed from the font's own parts because the game never renders those
  letters on this page.

## 11. Tempo fidelity: the timer-B grid, the owner's VGM rips, and the music logic (tasks 18-19)

The owner's report was "the music still changes speed sometimes, and it sounds
slightly slower than normal", and then, after the task-15 fix, "especially in
the menu, I still feel the music oscillating in speed". This section answers it
at register level instead of by ear or by envelope: the music clock is the
YM2612 timer B overflow, so a timestamped log of the driver's register writes
contains the tempo exactly.

### 11.1 The reference: the owner's VGM rips

Four VGM v1.5 files (`~/roms/genesis/tg2-vgm/`, read-only, **never** copied
into the repository; only the numbers below are):

| File | Length | Loop | YM2612 clock | GD3 |
|---|---|---|---|---|
| `01 - Title Theme.vgm` | 51.84 s | 44.37 s | 7,670,453 Hz | `Top Gear 2` / `Sega Mega Drive` / `1994-05-24` / ripper `2ch-N` |
| `02 - Canterbury Plains.vgm` | 125.23 s | 118.92 s | 7,670,453 Hz | same |
| `03 - Ayers Rock.vgm` | 154.48 s | 151.42 s | 7,670,453 Hz | same |
| `04 - Auckland.vgm` | 197.91 s | none | 7,670,453 Hz | same |

They are a register-level record of the *same driver on the same cartridge*:
73,779 YM2612 writes for the title theme, 2,665 timer-B reloads, 1,970 key-on
writes. That is the ground truth for two things no audio comparison can settle
cleanly: the exact tick grid, and the exact ordered event sequence (the
soundtrack's own loop defeats envelope alignment - a 7 % warp aliases onto
exactly one loop, which is what produced the false "-7 %" in task 18).

The rips are not perfect records of the machine: their wait commands are a
44,100 Hz sample grid (22.7 us), and 130 `0xE0` "seek PCM bank" commands plus
350 reserved `0x00` no-op bytes appear around the DAC bursts. `tools/vgm_compare.py`
counts those and reports them instead of silently skipping them, so the
provenance stays visible in every run.

### 11.2 `tools/vgm_compare.py`

Both sides become a timestamped `(t, port, value)` bus-write stream and then a
`(t, bank, register, value)` stream with the YM2612 address latch resolved:

* **VGM side:** commands `0x52/0x53` (addr+data), `0x50/0x51` (data), waits
  `0x61/0x62/0x63/0x70-0x8F`, data blocks `0x67`, DAC-stream control
  `0x90-0x95`, `0x68`, `0xE0`.
* **Port side:** `GENESIS_AUDIO_WRITEDUMP`, whose `f=` (sound frame) and `mc=`
  (master cycles inside the frame) give **exact guest time**:
  `t = (frame * 262 * 3420 + mc) / 53,693,175`. Host time never enters.

From that it reports:

| Measurement | How |
|---|---|
| timer-B tick train | every `$27` write with the load bit set (bit 1); mean, median, p05/p95, ticks/s |
| global tempo, method A | ratio of mean tick intervals (reference / port) |
| global tempo, method B | linear regression of matched key-on times (`t_port = a + b t_ref`, ratio `1/b`), with outliers dropped at 4 MADs |
| global tempo, method C | loop period: the rip's own loop length against the port's, found by self-matching the port's key-on train |
| local drift | the same regression in 1 s windows, reported as mean/std/p05/p95/max deviation |
| logic | the ordered event sequence with timing ignored: key on/off per channel, the 11-bit block+fnum per channel, `$B0-$B6`, `$30-$9F`, `$2A/$2B`; a bounded-lookahead diff gives the match ratio per class and the first divergences |
| Z80 accounting | optional `GENESIS_YM_TICKLOG`: Z80 cycles executed between two timer reloads versus the wall time between them, plus BUSREQ-held scanlines |

`--selftest` synthesises a driver-like stream, writes it as a VGM and as a
write dump warped by +1.5 %, -1.0 % and 0 %, and corrupts one event. The tool
recovers every ratio to 0.02 % with a 100 % logic match, and reports the
corrupted event as a divergence, so the measurement is qualified rather than
trusted.

### 11.3 What the driver really does, and what the timer must do

Disassembling the resident 8 KB driver (ROM `$02589A..$027899` -> Z80
`$A00000`) shows the main loop is the **DAC sample loop**, and the music tick
is inside it:

```
0CA8  ld a,($4000) / rla / jr c,$0CA8   ; wait for YM BUSY
0CAC  ld a,$2A / ld (de),a              ; DAC data register
0CB0  ld a,(hl) / ld (de),a / inc l     ; next sample byte
0CCB  ld a,$20 / dec a / jr nz          ; per-sample delay (~500 T)
0CD0  ld a,($0096) / or a / jr nz,$0D2B ; pending command?
0CDB  ld a,($4000) / and 2 / jr z,$0CB0 ; <<< timer B flag, checked per sample
0CE4  call $0D2B                        ; program the Z80 bank register
0CE7  call $0627                        ; the music tick
0CEA  call $0D4D / call $0C0D           ; bank again, then $27=$2E (reload)
0CF5  jp $0CA8                          ; back to streaming
```

So the tempo is the **timer B period**, and the driver polls its overflow flag
between DAC samples. `$26=$BE` gives

```
period = 16 * (256 - $BE) * 144 YM clocks = 152,064 clocks = 19.825 ms
```

which is exactly what ymfm computes (`fm_engine_base::update_timer`:
`16*(256-value) * OPERATORS * clock_prescale` = `1056 * 24 * 6`). The port's
CPU-visible model used the same number (`(256-$BE) * 16*144*7` master cycles =
1,064,448 = 19.8247 ms), so the *period* was never wrong.

What was wrong is the **phase rule**. In ymfm (and on the chip) the `$27` load
bit starts a stopped timer and does **not** re-phase one that is already
running; the overflow flag is a *level* on a free-running grid. A driver that
reloads the timer on every tick therefore has its polling lateness repaid by
the following shorter tick. The port re-armed the deadline on every `$27`
write, so no tick could ever be shorter than the period and every late tick
became permanent tempo loss.

The rips prove hardware behaves the phase-locked way: the title theme has 124
ticks at 23.8-24.4 ms and 188 at 14.8-17.9 ms - the long ones are paid back by
the short ones - and the tick *median* sits on the 19.84 ms grid. The port,
before the fix, had **not one** interval below 19.87 ms in 3,034 ticks.

### 11.4 Root cause of "slower than normal" and of the wobble

One defect explains both halves of the report. Measured on the same route
(cold boot -> title screen -> SOUND -> MUSIC TEST -> play), title theme,
`tools/vgm_compare.py`, 66.8 s of port capture against the rip:

| Quantity | Before patch 0010 | After patch 0010 |
|---|---|---|
| timer-B ticks | 3,034 | 3,253 |
| mean tick interval | **21.252 ms** (47.06/s) | **19.825 ms** (50.44/s) |
| median tick interval | 19.875 ms | 19.823 ms |
| intervals > 22 ms | 31 % | 4.7 % (the rip: 4.8 %) |
| intervals < 19.8 ms | **0** (one 0.1 ms artifact) | 141 at 14.8-15.6 ms + 150 at 17.7-19.4 ms |
| global tempo, key-on regression | **-6.991 %** | **+0.194 %** |
| global tempo, mean tick rate | -6.517 % | +0.212 % |
| global tempo, median tick | -0.172 % | +0.094 % |
| local 1 s windows: mean / std | -6.613 % / **2.224 %** | +0.073 % / 0.827 % |
| local 1 s windows: p05 .. p95 | -10.118 % .. -3.789 % | +0.184 % .. +0.198 % |
| key-on regression residual (rms) | 49.6 ms | **0.0 ms** |

Read it as: the *period* was right (median -0.17 %), but every hesitation was
banked instead of repaid, so the music ran 7 % slow on average and its speed
wandered by +-2 % (the worst 1 s windows 10 % slow). That is exactly the two
things the owner described, and it is worst in the menus because the title
theme is the song that plays there.

**It is not Z80 starvation.** `GENESIS_YM_TICKLOG` (a temporary instrument,
not committed) records the Z80's executed cycle counter at every timer reload.
Between two reloads the Z80 executed *exactly* the wall time (mean 21.252 ms of
Z80 cycles for a 21.252 ms interval, and 19.825 for 19.825 after the fix), so
no cycles are lost; BUSREQ cost 367 scanlines in 4,000 frames (1,048,000
scanlines = **0.035 %**). Task 18's 99.75 % figure was measured in a race; in
the menus the Z80 loses 0.03 %. The music driver's own clock, not its cycle
budget, was the bug - which is also why the task-18 "design C" decoupled clock
domain would not have fixed it.

**Fix:** engine patch
`patches/segagenesisrecomp/0010-ym-timer-b-free-running-phase.patch` - arm the
deadline only on the 0 -> 1 transition of the load bit. Three lines.

The fix deliberately changes the offline WAV: the music is 7 % faster in the
menus, which is what the owner asked for. Video is untouched - frame 60
`2A0B972960C5E325`, frame 300 `1131D937D70234FD`, and the miss/floor manifests
(`dispatch_misses.toml`, `floor_coverage.toml`,
`interior_label_misses.toml`, `floor_unsafe.toml`) are empty after the run.
Nothing else in the guest is affected: the patch only changes when the
CPU-visible timer-B overflow flag is raised, and this game is the only software
reading it.

**The residual +0.19 %.** It is constant in time (all 1 s windows between
+0.18 % and +0.20 %, rms residual 0.0 ms), so it is a scale, not a wobble.
The rip's own steady-state grid is 19.867 ms (its sections 10-51 s average
19.855-19.871 ms) against the hardware formula's 19.825 ms, i.e. the rip runs
0.21 % slower than the documented timer; the port's grid matches the formula to
0.01 %. Matching the rip exactly would mean slowing the port by 0.2 % against
the chip's own arithmetic, so the port is left on the formula and the residual
is attributed to the rip's time base (its waits are a 44.1 kHz sample grid and
the GD3 gives no clock provenance beyond the YM2612 frequency).

### 11.5 All four tracks

Route: SOUND -> MUSIC TEST -> value -> START (controller input only,
`tools/tg2_music_route.py` emits the same timeline for the port and for the
reference renderer). 9,600 frames (160 s) per track, i.e. about 137 s of each
song after the menu route - longer than the title theme's and Canterbury's
loops, and 137 of Auckland's 198 s. `MUSIC TEST` value 1 is the title theme;
the other three were identified by the logic match, not by the menu label.

| Port capture | Rip it matches | Logic match | Key-on | Tempo: key-on regression | Tempo: mean tick | Tempo: median tick | Local 1 s p05 .. p95 | Local std |
|---|---|---|---|---|---|---|---|---|
| MUSIC TEST 1 | `01 - Title Theme` | 51.6 % (98.6 % key-on) | 98.58 % | +0.194 % | +0.212 % | +0.094 % | +0.184 .. +0.198 % | 0.83 % |
| MUSIC TEST 2 | `02 - Canterbury Plains` | 99.5 % | 97.10 % | +0.194 % | +0.204 % | +0.080 % | +0.186 .. +0.203 % | 0.54 % |
| MUSIC TEST 3 | `03 - Ayers Rock` | 99.2 % | 99.76 % | +0.194 % | +0.200 % | +0.070 % | +0.186 .. +0.199 % | 0.41 % |
| MUSIC TEST 4 | `04 - Auckland` | 89.7 % | 69.19 % | +0.194 % | +0.197 % | +0.083 % | +0.186 .. +0.197 % | 0.31 % |

Every track lands on the same **+0.194 %** by key-on regression, to three
decimals, over spans of 52-140 s - the residual is a property of the reference
set's time base, not of any song or of the port's clock. The `local std`
column is dominated by the first window (the song's own intro, where the
regression has few pairs); from 5 s on, every 1 s window sits between +0.18 %
and +0.20 % on all four tracks, i.e. the wobble is gone.

**Cross-check against a third reference.** The rips are one reference; the
cycle-accurate emulator of task 18 is another. `tools/audio_tempo_compare.py`
(envelope tempo, which aliases on this soundtrack's loop but not on a 40 s
window of one song) compares the port's after-fix render with a Genesis Plus GX
render of the identical route:

| Track | Global tempo | Local mean | Local std | Max deviation | Pitch |
|---|---|---|---|---|---|
| Title Theme | -0.020 % | +0.032 % | 0.048 % | 0.152 % | +0.5 c |
| Canterbury Plains | 0.000 % | -0.020 % | 0.024 % | 0.030 % | +0.5 c |
| Ayers Rock | -0.020 % | -0.070 % | 0.000 % | 0.000 % | +0.5 c |
| Auckland | -0.020 % | -0.070 % | 0.000 % | 0.000 % | +0.5 c |

So the port agrees with an independent cycle-accurate emulator to **0.02 %** on
every track, while the four VGM rips sit 0.19 % away from the port *and from
each other's own tick grid by less than 0.02 %*. The residual in the table
above is therefore the rip set's time base, not the port: its waits are a
44.1 kHz sample grid and the GD3 gives no clock provenance beyond the YM2612
frequency. Slowing the port by 0.2 % to match the rips would move it away from
the chip's documented timer arithmetic and away from the emulator.

**Loop period.** `tools/vgm_compare.py` also reports the tempo from the loop
period, but only when the key-on train really repeats (>= 97 % of a 200-event
probe). On this soundtrack it does not: the title theme's phrases repeat 95 %
at 43.8 s while the true loop is 44.37 s (the same aliasing that produced task
18's false "-7 %"), and the melody's pitch train self-matches at only 52 %. The
tool therefore reports "not resolvable" here rather than a number, and the
tempo comes from the two measures that cannot alias: the tick rate and the
key-on regression. Both agree to 0.02 % on all four tracks (the key-on
regression is the stricter one: rms residual 0.03 ms over 140 s).

### 11.6 Music logic: what the port plays against what the rip recorded

The logic comparison ignores time and compares the ordered musical events, so a
wrong note, a wrong patch or a missing channel shows up even when the tempo is
right. Title theme, over the same musical span:

| Class | Title | Canterbury | Ayers Rock | Auckland |
|---|---|---|---|---|
| overall (DAC excluded) | 51.6 % | **99.5 %** | **99.2 %** | 89.7 % |
| key-on (`$28`, per channel) | 98.58 % | 97.10 % | **99.76 %** | 69.19 % |
| key-off | 98.49 % | **99.78 %** | **99.64 %** | **99.77 %** |
| block+fnum (`$A0-$A6`, per channel) | 98.25 % | **99.09 %** | **99.50 %** | 98.36 % |
| algorithm/feedback (`$B0-$B2`) | 96.77 % | 95.75 % | 98.51 % | **99.09 %** |
| stereo/AMS/PMS (`$B4-$B6`) | 98.20 % | **99.19 %** | **99.19 %** | **99.22 %** |
| operator loads (`$30-$9F`) | 65.31 % | 78.98 % | **99.14 %** | 88.65 % |
| DAC data (`$2A`) | 0.02 % | 0.01 % | 0.00 % | 0.02 % |
| DAC enable (`$2B`) | 98.78 % | 95.86 % | 98.36 % | **99.77 %** |
| other | 95.17 % | 96.68 % | 93.69 % | 94.21 % |
| events compared (rip) | 72.6 k | 180.3 k | 193.6 k | 192.2 k |

The audible content matches: every note starts and stops in the same order, on
the same channel, at the same pitch, with the same algorithm and stereo
setting. The two classes that diverge are driver *state* for channels that are
never keyed:

* **`$30-$9F` (65 %).** The driver writes all 24 operator slots every tick, but
  this song only ever keys channels 1-4 (`$28` key-ons: ch1 288, ch2 304,
  ch3 77, ch4 60, ch5 0, ch6 0). Channels 5-6 therefore carry idle envelope
  state, and the port's idle values differ from the rip's (`TL=$7F` on two
  carrier slots instead of the rip's 8-20). No key-on ever reaches them, so
  they are silent on both sides; the divergence is the driver's own idle state,
  not a wrong patch on a sounding note.
* **`$2A` (the DAC channel).** The rip contains 359 DAC writes in one burst
  near 8.4 s; the port streams ~4,600 DAC writes/s for the whole song
  (`Z80 $0CB2`, the sample loop above). Channel 6 is never keyed on either
  side, so the streamed sample is inaudible, but the driver spends its time in
  the DAC loop, which is where the 4.7 % of 24 ms ticks come from. It is a
  genuine behavioural difference from the rip and the next thing to pin down;
  it no longer costs tempo because patch 0010 repays the lateness.

The `$28`/`$A0` divergences on the title theme (about 1.4 %) are single events
at the song's start and at the loop seam, where the port's capture begins a few
ticks before the rip's recording does.

**Auckland is the one real logic divergence.** Its key-off, block+fnum,
algorithm, stereo and DAC-enable classes all match at 98-99.8 %, but only
69.19 % of its key-ons do, with the same total count (3,053 rip / 3,066 port
over the compared span): the port *re-attacks* channels 1-2 more often than the
rip in the first ticks of the song (rip: `ch0 ch1 ch3` at 48/49/50 ms; port:
`ch0 ch1 ch0 ch1 ch0 ch1 ch3` at the same tick). The DAC loop is the prime
suspect - the driver enters its event parser from the sample loop, and the port
is in that loop ~4,600 times a second where the rip is not - and it is the next
thing to pin down. Nothing else on that track diverges.

### 11.7 Listening files

`~/Music/tg2-ab/` (outside the repository, contains game music on purpose) is
described by its own `README.txt`; task 19 added one reference render and one
after-fix port render per track plus the menu before/after pair, all at
44.1 kHz/16-bit stereo. The port's offline tap writes at the PSG's native
223,721 Hz, so `tools/audio_wav_convert.py` converts it (box pre-filter plus
linear interpolation, streamed in blocks).

### 11.8 Reproduce

```sh
JOBS=3 tools/build-linux.sh ~/roms/genesis/tg2.bin build

# the route for both back ends (controller input only)
python3 tools/tg2_music_route.py --song 0 --frames 9600 \
    --port-script build/music0/route.txt --gpgx-script build/music0/route.json

# port capture: exact guest-timed register stream + offline WAV
GENESIS_AUDIO_WRITEDUMP=build/music0/writes.txt \
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy build/TG2Recomp ~/roms/genesis/tg2.bin \
    --no-launcher --widescreen off --max-frames 9600 --turbo \
    --input-script build/music0/route.txt --wav build/music0/port.wav

# comparison against a rip (also --selftest)
python3 tools/vgm_compare.py --vgm "$HOME/roms/genesis/tg2-vgm/01 - Title Theme.vgm" \
    --dump build/music0/writes.txt --json build/music0/compare.json

# reference render of the same route (no window, no host mixer)
cc -O2 -o build/gpgx_render tools/gpgx_render.c -ldl -lm
build/gpgx_render --core ~/tools/retroarch/cores/genesis_plus_gx_libretro.so \
    --rom ~/roms/genesis/tg2.bin --frames 4000 --script build/music0/route.json \
    --wav build/music0/ref.wav

# 223,721 Hz tap -> 44.1 kHz for listening
python3 tools/audio_wav_convert.py build/music0/port.wav ~/Music/tg2-ab/t19-port-title.wav \
    --rate 44100 --tail 60
```

## 12. Feasibility map: a decoupled Z80 + YM2612 + PSG clock domain

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

## 13. Separate Music and SFX volumes (task 30)

Two player faders, in the **real-time** pipeline (the mixer that synthesises
sound while the game runs), switchable from the in-game Esc menu and the
launcher, and defaulting to the stock sound:

| Option | settings.ini | Env override for captures | Default |
|---|---|---|---|
| Music volume | `[mods.musicvol] level` (0..100, step 5) | `TG2_MUSIC_VOL` | 100 |
| SFX volume | `[mods.sfxvol] level` (0..100, step 5) | `TG2_SFX_VOL` | 100 |

At 100 % the three stock captures are **byte-identical** to a `main` build of
the same scripts (whole-run WAV MD5):

| Capture | MD5 |
|---|---|
| MUSIC | `fbfc0da19dac55b01046a39e75256f06` |
| SOUND EFFECTS | `592cb1a1d695d9e799c2b7aa441e585c` |
| BOTH | `e58ce500809454a64e645881553be714` |

The 4:3 Off-mode frame hashes are unchanged: frame 60 `2A0B972960C5E325`,
frame 300 `1131D937D70234FD`.

Engine patches: `0040-separate-music-sfx-volumes.patch` (writer classification
and the two faders) and `0042-live-audio-option-toggles.patch` (the gain ramp
that makes a live move safe, and the input-script `OPTION` directive the probe
uses). `0041` was withdrawn: it carried the two chip-model options that the
owner dropped after listening (13.5).

### 13.1 Classifying a write by source

Both sliders need to know what a chip write *plays*, and that is a property of
the writer:

| Writer (`AudioEvent.origin`) | Source |
|---|---|
| first Z80 core, while the resident music driver is in Z80 RAM | music |
| first Z80 core, after the 68K has uploaded the race SFX PCM image over it | sound effects |
| 68K FM/PSG engine (and boot-time 68K writes) | sound effects |
| second Z80 core (BOTH mode, race SFX PCM image) | sound effects |

The first-core case is the only ambiguous one, because the cartridge puts two
different programs in the same 8 KB. Both images have a distinct entry stub at
`$A00000` — the music driver starts `DI; LD SP,$1FF0` (`F3 31 F0 1F C3 42`) and
the race image starts `JP $0410` (`C3 10 04`) — so `game/tg2_audio_both.c`
reads the first core's RAM header every frame and calls
`audio_set_first_z80_is_sfx()`. That is a host-side *read* of the machine image:
nothing in guest RAM is written, and the stock modes never see a difference.

### 13.2 How the faders are applied

The fader is a fixed-point gain (`256 = 100 %`) on the *generated* stream, i.e.
before the WAV tap and before the speaker master Volume, so a capture measures
exactly what a player hears at the same master setting.

* **The fader never changes routing.** Chip routing is the game's: one chip in
  MUSIC and SOUND EFFECTS, two chips in BOTH.
* **A frame with writes** whose writes are all one source — every stock
  MUSIC-mode frame, every stock SOUND EFFECTS race frame, the menus, the boot —
  is that source's gain applied to the one chip's stock stream. A frame that
  carries both sources belongs to the source that wrote most of it.
* **A frame with no writes at all** keeps sounding with the previous frame's
  source: the chip's voices keep playing, so the fader follows the sounding
  source, not the empty frame.
* **A change ramps.** The new gain is reached linearly across the next frame
  (16.7 ms, last sample already at the new value), so a live move cannot click
  and the frame after a switch back to 100 % is byte-identical to an
  uninterrupted capture. A fader moved while nothing is sounding snaps.
* **In BOTH mode** each chip has its own ramp (music gain on chip A, SFX gain on
  chip B), summed as before.

At 100 %/100 % every ramp is identity and none of this arithmetic runs.

### 13.3 Slider measurements

Same deterministic route for every capture (menu → SOUND → RACE SOUND → leave →
1P race, then accelerate), 9000 wall frames, offline WAV at the mixer's
223 721 Hz. "Ratio" is per-second RMS against the same run with the option at
100 % (median over the capture).

| Run | Ratio median | What it shows |
|---|---:|---|
| MUSIC mode, Music 50 % | **0.4999** | music-only mode: exactly half |
| SOUND EFFECTS mode, SFX 50 % | **0.4999** | race window (the menu keeps the music at 1.000) |
| BOTH mode, Music 50 % | menu 0.4999, race 0.72-0.82 | only chip A is scaled; the SFX layer keeps its level |
| MUSIC mode, SFX 50 % | 1.0000, **0 s of the capture differ** | the SFX slider has nothing to act on in music-only playback |
| SOUND EFFECTS mode, SFX 0 % | race RMS **0.0** | a muted source is silent, and the stream is exactly zero |
| MUSIC mode, Music 0 % | menu/race RMS **0.0** | same for music |

All captures report **0 pops** and **0 digital-silence dropouts** from
`tools/audio_glitch_detect.py`; a 15 s realtime run with the faders engaged
logged `underruns=0 overflows=0 conceals=0` from the DRC bridge.

### 13.4 Live switching

`tools/tg2_live_toggle_probe.py` drives the standard route and rewrites its
script to insert `OPTION <key> <value>` directives (a runner input-script
directive that calls the same setter the in-game menu uses) at six frames: the
menu music, the pre-race screens (setup / shop / track intro), the countdown,
the race start and two mid-race points. Each option goes on → off → on → off →
on → off, and every capture is compared with an uninterrupted run of the same
route. It requires: byte-identical output before the first toggle; byte-identical
output in the stretches where the fader is back at stock; byte-identical output
after the last switch back (one frame of ramp allowed); the option's own effect
only while it is on, with a per-mode/per-source level band; no new pops; and
nothing collapsing to silence. Two more cases: a **cold start** with both faders
already at 50 % in `settings.ini` (no toggles: the whole run must sit at half the
reference level), and a mid-race **RACE SOUND** switch, which must be
audio-neutral because its routing layer is adopted at the next race.

Result on the shipped build (3 modes x 2 faders + cold start + mid-race RACE
SOUND; "diff" is how much of the 120 s capture differs while the fader is on,
i.e. its own documented effect):

| Mode | Music volume | SFX volume | Cold start (both 50 %) | RACE SOUND mid-race |
|---|---|---|---|---|
| MUSIC | PASS, menu 0.500, 46 s diff | PASS, 0 s diff | PASS, 0.500 | PASS, 0 s diff |
| SOUND EFFECTS | PASS, menu 0.500, 25 s diff | PASS, 22 s diff | PASS, 0.500 | PASS, 0 s diff |
| BOTH | PASS, menu 0.500, pre-race/race 0.73-0.83, 46 s diff | PASS, 42 s diff | PASS, 0.500 | PASS, 0 s diff |

Every run is byte-identical again once the fader is back at stock (including
both "off" stretches between toggles), and 0 pops were added anywhere. The BOTH
rows read 0.73-0.83 rather than 0.50 because only the music layer is halved
while the SFX layer keeps its level - that is the expected partial mix. The pre-fix build failed this probe: the faders engaged a
second chip mid-stream (a chip that had never received the current voices) and
the stream did not return to stock; a live Clean FM switch reset the chip and
silenced a SOUND EFFECTS race (0.29 x the reference = idle DC only). Both
mechanisms are gone.

### 13.5 Withdrawn: Clean FM and Clean engine samples

Task 30 also shipped two chip-model options, both removed on **2026-11-09** by
the owner after listening: Clean FM (ymfm's YM3438 core) was inaudible to him,
and the DAC reconstruction made the engine sound *muffled* rather than more
detailed, which is expected - a 6.6 kHz sample stream has nothing above
3.3 kHz to recover. They are recorded here because the measurements and the
mode handling they needed are part of the portrait of the sound system.

Two owner reports on the resulting release were investigated before removing
them, and the measurements say what each option did:

* **"Clean engine samples muffles the music."** The option was applied to *every*
  `$2A` write on the chip, and Top Gear 2's **music driver streams the DAC
  channel continuously** (its main loop is the sample player; `AUDIO.md` §11.6
  counts ~4,600 `$2A` writes/s in the title theme). Measured in the menu music
  alone: **170,063 reconstructed DAC writes in 40 s** (about 4,250/s), a mean
  difference of 200-500 LSB and a peak of 6,942 LSB against the stock capture,
  i.e. the music's own DAC/percussion content was low-passed at 3.3 kHz. That is
  the "closed/muffled" sound he heard. The engine/nitro stream was never the
  only DAC user, so there is no cutoff that suits both.
* **"Wrong notes in the pre-race screen music."** Clean FM alone changed no
  pitch: the dominant frequency matched in 24 of 25 frames of the pre-race span
  and the log-spectrum correlation against the stock chip was **0.9999** (only
  the documented ladder/DC difference). The note-level change came from the
  reconstruction rewriting the music's DAC stream, not from the FM core; with
  both options removed the pre-race music is byte-identical to the stock build
  (the probe's cold-start case now runs the route with the withdrawn sections
  still in `settings.ini` and requires exactly that).

An older `settings.ini` may still contain `[mods.cleanfm]` or
`[mods.dacresample]`: loading ignores them and the next save drops them (the
probe seeds a settings file with both and checks the file after a menu save).

### 13.6 What is not verified

* The launcher rows: the game offers Music volume / SFX volume / RACE SOUND as
  launcher mod features (integer sliders in the `Sound` group). The launcher
  needs OpenGL, which the dummy video driver on this macOS host cannot provide,
  so the launcher UI was not exercised here - the in-game Esc menu was (rows
  read back over TCP, a value changed through the real key path, and the change
  persisted into `settings.ini`). The rows live in the in-game **Audio** section
  directly under the master Volume.
* The 100 %/50 % numbers are levels, not a listening judgement; the owner hears
  the final mix himself.
* There is no PipeWire null sink on this host, so the "real device" numbers are
  offline streams plus one realtime session through SDL's dummy device.
* The live-toggle probe runs headless with the real option setters; it does not
  drive a physical gamepad through the menu, and the owner's own session used
  key presses at unknown frames.

### 13.7 Reproduce

```sh
JOBS=3 tools/build-linux.sh ~/roms/genesis/tg2.bin build

# live option switching: menu, pre-race screens, countdown, race start and
# two mid-race points, in all three sound modes, plus a cold start and a
# mid-race RACE SOUND switch
python3 tools/tg2_live_toggle_probe.py --exe build/TG2Recomp --out build/livetoggle

# per-source levels of a capture pair
python3 tools/tg2_audio_levels.py ratio build/t/opt.wav build/t/stock.wav
python3 tools/tg2_audio_levels.py bands build/t/run.wav 85 6
python3 tools/audio_glitch_detect.py --device build/t/run.wav
```
