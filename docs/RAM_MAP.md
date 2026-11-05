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

