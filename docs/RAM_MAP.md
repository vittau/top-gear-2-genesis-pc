# Top Gear 2 USA RAM map

All addresses are guest 24-bit addresses. ROM disassembly is authoritative;
unknown fields remain zero in `game/game.toml` rather than borrowing Sonic data.

| Address | Size | Meaning | Evidence |
|---|---|---|---|
| `$FF8408` | base | A3 game-global addressing base | Reset `$001D4E`, scene handlers restore A3 |
| `$FFFFFE` | stack | Reset SSP, downward-growing | ROM vector `$000000` |
| `$FF01EA` | 6 bytes | V-int `JMP abs.l` trampoline | Installer `$00204C` |
| `$FF01EC` | long | Current V-int ROM target | Immediate store `$002054`, then scene installers |
| `$FFF9FE` | 6 bytes | H-int `JMP abs.l` trampoline | Installer `$00205E` |
| `$FFFA00` | long | Current H-int ROM target | Immediate store `$002066`, then scene installers |
| `$FF01C6` | word | Interrupt frame counter / VBlank wait handshake | `$002070` clear, `$0020B6` increment, `$002082` wait |
| `$FF16BE` | word | Attract/demo selection index (0..63) | `$001E58`, `$001E9E..001EAC`, indexes ROM `$01B8E8` |
| `$FF241C` | long | Selected attract descriptor pointer | `$001E5E` stores through A3-$5FEC |
| `$FF9F3C` | buffer | Graphics/decompression working buffer | `$01E816..01E840` |

The canonical game-mode field has not yet been established. Race timing,
player speed, road/raster and input state are listed below.
The frame counter is 16-bit; generic runner telemetry treats its configured
address as a long, so raw word reads are the reliable counter measurement.

Further raw-ROM evidence from the race interrupt path:

| Address | Size | Meaning | Evidence |
|---|---|---|---|
| `$FF0000` | word | DMA command staging scratch | `$001222`, `$001228`, `$00123A`, `$001240` |
| `$FF0002` | word | Queued DMA command count | `$001278`, increment `$0012E0` |
| `$FF0006` | buffer | Queued VDP DMA register commands | `$001272..0012E0` |
| `$FF0108` | word | VDP mode-register command shadow | `$004732..00473A`, `$004880..004888` |
| `$FF01E6` | long | Alternate raster-list pointer | `$0048DC`, read by copied H-int `$0046FC` |
| `$FFF9FE..FFFA7F` | 130 bytes | Copied self-modifying raster H-int code | ROM `$004682..004703` copied by `$004654..00466A` |
| `$FF231E` | long | Primary raster-list pointer, loaded into A5 | A3-$60EA at `$004898` / `$0049D6` |
| `$FF2324` | long | Alternate raster-list offset | A3-$60E4 at `$0048D8` |
| `$FF232C` | long | Alternate raster-list base | A3-$60DC at `$0048CA` / `$0048D4` |
| `$FF238C` | word | Race V-int counter (parity schedules work) | A3-$607C increment `$004748`, tested `$00490A` |
| `$FF2734` | word | Active small-object callback count (bounded 64) | A3-$5CD4 at `$003CFA..003D04`, `$00E418` |
| `$FF2736` | 16-byte slots | Small objects with function pointer at +12 | `$003D12..003D18`, dispatcher `$00E422..00E430` |

The last two entries helped diagnose the now-fixed moving-race corruption: at frame
3445, its indirect call unexpectedly targets noncode `$00058C` / `$0002C6`.
Do not add these to discovery: raw ROM contains invalid instructions there.

Controller evidence from ROM `$00D7A6..00D872`:

| Address | Size | Meaning | Evidence |
|---|---|---|---|
| `$FF18CA` | base | Player-1 record | LEA A3-$6B3E,A4 at `$00D7AC` |
| `$FF19BE` | byte | Raw player-1 pad mask (active high) | `$00D806` stores D0 at +$F4(A4) |
| `$FF18FA` | byte | Remapped player-1 controls | `$00D872` stores D0 at +$30(A4) |
| `$FF18FC` | byte | Previous remapped player-1 controls | `$00D86C` copies +$30 to +$32(A4) |
| `$FF19AE..FF19BA` | words | Direction/button remapping indices | `$00D80C..00D858`, +$E4..$F0(A4) |

Race timing fields verified by raw ROM and per-frame native snapshots
(see `FRAMERATE.md` for cadence measurements):

| Address | Size | Meaning | Evidence |
|---|---|---|---|
| `$FF1838` | word | Main picture-build marker, advances twice per completed iteration | `$006810`, `$00681A` |
| `$FF1866` | word | Race phase/countdown counter; negative before Go, increments then wraps `$0200` to `$0100` | `$00DE52`, `$00E146..00E152` |
| `$FF186C` | word | VDP region bit: 0 NTSC, 1 PAL, selects per-IRQ scaling | `$00DB02..00DB0A` |
| `$FF18CA` | long | Player 1 track position | +0(A4), integrated `$00D4C6..00D4F2` |
| `$FF18CE` | long | Player 1 lateral position | +4(A4), `$00D4C6`, `$00D5CE..00D5D2` |
| `$FF18D2` | long | Player 1 view/track sample position | +8(A4), copied from physical position `$0088C4` |
| `$FF18D8` | word | Player 1 speed, raw units (HUD converts separately) | +$0E(A4), `$00CFD0`, `$00D43A`, HUD `$00F5F8` |
| `$FF198C` | word | Player 1 speed used for track integration | +$C2(A4), `$00D42E`, `$00D4CE` |
| `$FF1994` | word | Player 1 lap index (starts -1) | +$CA(A4), `$007612`, `$00DAB2..00DAB8`, HUD `$00F71E` |
| `$FF053C` | 12-byte slots | Opponents: +0 long track position, +4 lateral word, +6 speed word, +8 steering/target long | `$00D9A6..00DA80` |
| `$FF217E` | word | Opponent count minus one | A3-$628A at `$00D9AA` |
| `$FF22FA` | word | Palette fade phase: 1 in, 0 finished, 2 out | `$0065E2`, `$006630`, `$006728`, `$006736` |
| `$FF22FC` | word | Palette fade step | `$00668A..00668E` |
| `$FF23B4` | word | Completed main picture-build count (when not paused) | `$006988..006990` |
| `$FF23B8` | long | 16.16 race clock in 50 Hz units; NTSC increment `$D555` per V-int | `$00770E`, `$00DF3A..00DF4A` |
| `$FF23C2` | byte | Countdown stage delay | `$00DE04`, `$00DE0C`, `$00DE42` |
| `$FF23C5` | byte | Pending palette upload | `$00671E`, consumed `$004774..004788` |
| `$FF2424` | byte | Main picture ready for V-int submission | `$006982` sets, `$004762` tests, `$00476C` clears |
| `$FF2425` | byte | Low byte of per-V-int race counter used beside ready flag | `$00474C` |
| `$FF2426` | word | V-int-latched ready/counter pair | `$004750`, tested `$0048BE`, `$004954` |

Fields added while mapping the main-loop -> IRQ-physics feedback
(`docs/FRAMERATE.md`), all verified against the ROM and against stock/60 fps
runtime captures:

| Address | Size | Meaning | Evidence |
|---|---|---|---|
| `$FF1996` | long | Track segment-table base for the sampled segment | written `$0088E8`, read by road/scenery builders |
| `$FF199A` | long | Second segment-table base (same value) | written `$0088EC` |
| `$FF18CA`+`$70` | word | Picture snapshot: steering input | `$00683A` copies `+$20` |
| `$FF18CA`+`$74` | long | Picture snapshot: physical track position | `$00682E` copies `+0` |
| `$FF18CA`+`$78` | long | Picture snapshot: secondary position | `$006834` copies `+$4A` |
| `$FF18CA`+`$7C` | long | Picture snapshot: view position used to draw the road | `$006822` copies `+8` |
| `$FF18CA`+`$80` | word | Picture snapshot: state word | `$006828` copies `+$52` |
| `$FF18CA`+`$84` | word | Picture snapshot: track slope | `$006846` copies `+$16` |
| `$FF18CA`+`$86` | word | Picture snapshot: track curvature | `$006840` copies `+$14` |
| `$FF189E` | word | Two-player race active; non-zero makes `$00CD76` run record `$FF1D22` instead of `$00CD84` running `$FF18CA` | `$00CD76..$00CD82` |
| `$FF1D22` | record | Second player record (`$FF18CA` + `$458`), zero in a single-player race | `$00CD7E`, `$00684C` |
| `$FF168E` | word | Deferred VRAM block work gate/counter; zero disables `$00E4A0` | `$00E4A0..$00E4AA` |
| `$FF233A` | word | Deferred work call counter; its parity selects block list A or B | `$00E4C0..$00E4D2` |
| `$FF238E` | long | Deferred VRAM block mask, list A | `$00E4D0`, uploaded by `$00E696` |
| `$FF2392` | long | Deferred VRAM block mask, list B | `$00E4EE`, uploaded by `$00ED0A` |
| `$FF23C4` | byte | Queued VRAM block upload pending | `$0047B2..$0047B8`, serviced by `$0052C2` |
| `$FF23B6` | word | VDP command staging word during a deferred block upload | `$00E6BE..$00E6C4` |

VRAM layout in the race mode (VDP registers 2/4/5/13 = `$30`/`$07`/`$5F`/`$2E`):
sprite attribute table `$BE00` (640 bytes), H-scroll table `$B800` (896
bytes), plane A `$C000`, plane B `$E000`.

## Password screen and nitro (all-track coverage task)

Verified against the ROM and against a live run (see `docs/PASSWORDS.md` for
the full encoding).

| Address | Size | Meaning | Evidence |
|---|---|---|---|
| `$FF2570` | 0x60 | Password work struct: symbols at `+0`, packed 80-bit block at `+$10`, plaintext record at `+$1A`, demanded picker index at `+$24`, decoded fields at `+$26..$54` | breakpoint on `$023594` shows `A0 = $FF2570`; RDB writes from `$02396A`/`$0238D2`/`$02371A` |
| `$FF2570+$24` | word | Country index the screen demands; `-1` from the CONTINUE → PASSWORDS row, the picker index from CONTINUE → COUNTRY SELECT | `cmp.w $28(a0),$24(a0)` at `$0235B6` |
| `$FF2570+$26` | word | Password checksum (8 bits used), compared as a word against the field sum | `cmp.w $26(a0),d7` at `$0235A4` |
| `$FF2570+$28` | word | Password country/track index (4 bits) | loaded intro panel changes with it |
| `$FF2570+$2C` | word | Password stage (2 bits), validator rejects `> 2` | `cmpi.w #2,$2c(a0)` at `$0235AA` |
| `$FF2570+$2E` | word | Money in thousands (10 bits) | `Money $255000` for field 255 |
| `$FF18CA+$2D4` | word | **Nitro tank**: 1536 at the race start, decrements while the nitro button is held | see below |
| `$FF18CA+$2D8` | word | Nitro/boost active flag tested by the speed model | `tst.w $38(a4)` at `$00CF7A`, `$00D126` |
| `$FF18CA+$34/$36` | words | Boost speed accumulator / decay set by the boost branch | `$00CF80..$00CFAE` |
| `$FF18FA` | byte | Remapped controls: bit0 LEFT, bit1 RIGHT, bit2 BRAKE, bit3 ACCEL, bit4 **NITRO**, bit5 UP, bit6 DOWN, bit7 START | `$00D80A..$00D872`; measured per button over TCP |
| `$FF19AE..$FF19BA` | 7 words | Raw-pad bit index per control: `[UP DOWN LEFT RIGHT B A C]` → output bit | default TYPE 1 is `[5,6,0,1,3,2,4]` |

**Nitro input.** Canonical bit 4, which the default CONTROL TYPE 1 maps from
the raw `C` button. Holding `C` with throttle on an unmodified car drains the
tank (1536 → 1280 → 1024 over ~2 s) and raises the speed from ~3 800 to
6 544 raw units (+73 %); the same run's peak with the button released is
~4 000. The nitro does not need to be bought: every race starts with the
1536-unit tank. `docs/VALIDATION.md` section 3 records the measurement.


## Closed-loop driving fields (qualification driver)

Found and verified while writing the automated race driver
(`tools/tg2_race_driver.py`, `tools/tg2_runner.py`). Every value below was read
over TCP during real races and cross-checked against the raw-ROM routines named
in the evidence column; the driver only ever writes controller input.

| Address | Size | Meaning | Evidence |
|---|---|---|---|
| `$FF1690` | long | Lateral clamp minimum, read by `$00D5B8` (`cmp.w` on the swapped accumulator) | Constant `-288` during the Auckland race; car sits on the left grass at that value |
| `$FF1694` | long | Lateral clamp maximum, read by `$00D5C2` | Constant `+288`; car sits on the right grass at that value |
| `$FF18CA`+`$04` | long | Player lateral position, 16.16; `0` is the road centre, `RIGHT` raises it, `LEFT` lowers it | `$00D4C6` integration (`$D51A` steering term, `$D59C` curve term), `$00D5B6..D5D2` clamp; measured 1 frame of steering moves it ~1.7 units, 288 = grass |
| `$FF18CA`+`$20` | word | Surface flag A: cleared each frame by `$00CE18`, set to 1 when the sampled surface code is 2 | `$00CE34..CE44`; stayed 0 for every on-road frame of the qualification races |
| `$FF18CA`+`$22` | word | Surface flag B: set to 1 when the sampled surface code is 3 | `$00CE46..CE56`; also 0 on the asphalt |
| `$FF18CA`+`$14` | word | Track curvature at the sampled segment (physics copy; picture snapshot copy is `+$86`) | `$00D644`→`$00D65E` stores `+$14`; identical to `+$86` in every sampled race frame |
| `$FF18CA`+`$CA` | word | Lap counter: `-1` on the grid, `+1` at every start/finish crossing; the *finishing* crossing does not increment it | `$00DAB2..DAB8`; four complete races showed `-1,0,1,2,3` then the finish freeze with the counter still at 3 |
| `$FF23B8` | long | Race clock, 16.16 50 Hz ticks; freezes when the player's race ends | `$00DF40`; lap boundaries land at exact `$D555`-multiples and the value stops changing on the results screen |

Race phase (`$FF1866`) runs negative through the countdown, reaches 0 at "GO",
then advances by 1 per V-int and wraps at `$0200`. The driver starts the race
schedule when the clock (`$FF23B8`) first becomes non-zero, which is one frame
after "GO".

The player record's A4/A3 base was confirmed at runtime: `get_registers`
returns A3 = `$FF8408` during a race, which reproduces every `A3-$xxxx`
displacement used above.

### Race length and lap timing

A race is four laps after the initial run from the grid to the line. Measured on
Auckland (length 1.6 miles, 4 laps): the grid is 1.31 M position units before
the line, one lap is 9.44 M units, and the results screen's own "TIME" column
matches the sum of the clock deltas (run-up included). `tools/tg2_race_driver.py`
reports the run-up separately from the four timed laps.
