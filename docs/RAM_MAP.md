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

Canonical game-mode and player-speed fields have not yet been established;
known road/raster and input state is listed below.
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

The HUD proves that vehicle speed changes (97 MPH at frame 3300), but its
canonical RAM speed field is not yet identified; no guessed address is set.

## Sound driver and SOUND menu (see docs/AUDIO.md)

| Address | Size | Meaning | Evidence |
|---|---|---|---|
| `$FF240E` | word | Race sound mode; `0`=SOUND EFFECTS, `1`=MUSIC; A3-relative `-$5FFA` | Readers `$0048E2`, `$006530`, `$023062`, `$0251F4`; writers `$01ED60`, `$002104` |
| `$FF2554` | struct | Menu controller object; RACE SOUND page uses `A4+$0C` | Handler `$01F0D4`, enter/leave `$01ED3A/$01ED60` |
| `$FF2560` | word | RACE SOUND page value word (`A4+$0C`): 0=SFX, 1=MUSIC | `$01F0D4`; runtime diff at the page |
| `$FF8622` | struct | 68k PSG SFX engine state base | `$0253EE` loads A4 here; `$070008/$070014` |
| `$FF862E` | struct | 68k FM SFX engine state base | `$0253EE` loads A4 here; `$070018/$07001C` |
| `$FF16BE` | word | Race/attract index used to pick music track `{1,2,3,6}` | `$0251F4` masks `&3`, table `$02522A` |
| `$A00080` | byte | Music driver A command mailbox (Z80 RAM) | Writers `$024CD4/$024D04` |
| `$A00081` | byte | Music driver A status | `$024D22` |
| `$A00084` | byte | Music driver A pause/stop flag | `$024D50/$024D64` |
| `$A00087` | long | Music driver A work pointer, initialised `$0F0000` | `$024C96..$024CB4` |
| `$A0025E` | byte | Race SFX Z80 image command byte (vestigial; writer `$07018A` has no callers) | `$07018A`, `$0701D4` |
| `$A00260` | byte | Race SFX Z80 image command queue counter | `$070160`, `$0701AA/$0701CA` |
