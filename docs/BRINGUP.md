# Native 4:3 bring-up

Target: stock Top Gear 2 (USA), native `TG2Recomp`, no widescreen or game-rate
changes. Baseline engine pin: `dd520f1f975a80b080cddc569f3f49035f054101`.

## ROM and build

The read-only input is `~/roms/genesis/tg2.bin`, 1,048,576 bytes, CRC32
`BD3074D2`, SHA-256
`b41909d53090e28c1d1e50941dad01676dd3d19caf26c75f66aac6a3ad689ba6`.
Reset SSP is `$00FFFFFE`, reset PC `$000200`, V-int `$FF01EA`, H-int `$FFF9FE`.

`tools/build-linux.sh [ROM] [BUILD_DIR]` configures Ninja Release and generates
C exclusively in the build directory. The private ROM is referenced by path,
never staged in the repository. TCP and reverse-debug rings stay enabled for
bring-up, and IPO is disabled to keep discovery iterations practical.
The UI submodule is linked; probes use `--no-launcher`.

## Interrupt installation

Reset performs the checksum, region check and WRAM clear, then calls `$00204C`
from `$001DDA`. This installer writes the `JMP abs.l` opcode `$4EF9` at
`$FF01EA` and `$FFF9FE` and the ROM targets `$002098` and `$0020C0` at the
following longwords. It sets SR to `$2500` and waits for the word at `$FF01C6`
to change. `$002098` saves D0/D7, increments that counter and returns with RTE;
`$0020C0` is bare RTE. Later scenes replace the target longwords in the same
RAM trampolines; these are not a single boot-time code copy.

`recomp_call_addr` follows live RAM JMP trampolines before generated dispatch.
The native IRQ targets need independent discovery roots: the initial heuristic
walk wrongly owned them as interior code. `tools/discover_irqs.py` identifies
immediate `MOVE.L #handler,<trampoline operand>` writes in the raw ROM and
validates both the installer instruction and the target prologue with Capstone.
Its committed output contains only addresses and installer locations.

## Discovery ledger

| Stage | Functions | Runtime evidence |
|---|---:|---|
| Reset seed + heuristic jump-table discovery | 361 | 600-frame cold boot stalled black; 0 external misses, 2 interior misses (`$002098`, `$01E722`); floor declined both |
| Raw-ROM IRQ installer roots | 433 | Validation pending |

Initial 600-frame run exited 0; its black framebuffer hash was
`2A0B972960C5E325` at both frames 60 and 300. These describe the failed
initial configuration, not a verified stock rendering baseline.
