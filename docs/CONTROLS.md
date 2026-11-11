# Controls: four-row carousel and analog pedals

The port owns controller remapping. The launcher's binding table
(`[input.pN]` in `settings.ini`) and the in-game runtime menu are the only
places a player changes which physical input drives a Genesis button. The
cartridge's own CONTROL TYPE choice is gone, and the two features below are
native game code on top of the shared runner's input path — the recompiled
routine itself is replaced, not painted over.

## What the player gets

| Input | Genesis | Effect in a race |
|---|---|---|
| Gamepad **RT** | **B** | accelerate |
| Gamepad **LT** | **A** | brake |
| Any binding already set for B | B | accelerate (unchanged) |
| Any binding already set for A | A | brake (unchanged) |
| Any binding already set for C | C | nitro (unchanged) |

Triggers are **additive**: they press the same Genesis buttons the face buttons
press, they never replace a binding, and nothing new is written to
`settings.ini`. A fresh install, an existing `settings.ini` from an earlier
build (including one with recorded pad bindings) and a user-remapped B/A all
behave the same way, because the feature has no key of its own.

Triggers are evaluated by the shared runner's per-player deadzone
(`[input.pN] deadzone`, default 25 %), the same threshold the analog sticks
use. A trigger must be pulled past that point to count as pressed; releasing
it clears the button. Player 1's and player 2's gamepads are resolved
independently, so each player gets their own pedals.

The mapping is in the game adapter, not the engine:
`GameSpec.pad_trigger_bits` (engine patch `0054-pad-trigger-bindings.patch`)
passes LT/RT already compared against the player's deadzone, and
`game/tg2_controls.c` returns `GPAD_B` for RT and `GPAD_A` for LT.

## The four-row carousel

The setup screen's carousel is a native replacement of two cartridge routines
in `game/tg2_controls.c` (one `[[widescreen_site]]` game hook each, returning 1
to replace the routine):

* **`$021A62`, the input handler.** Stock moves a cursor over five rows
  (RACE, PLAYER, GEARS, SPEED, CONTROL) and wraps 0..4. The native version
  keeps every START and row rule and wraps 0..3.
* **`$021F54`, the row/page draw.** Stock reads the state's record at
  `$21F40 {block, value adjust, d6 adjust, d7 adjust}`, emits the page block
  and then the selected row's highlight block through `$0206AE`/`$001CE0`.
  The native version does exactly that, except that for the row list (state 0)
  it emits only the first four rows — entries 0..7 of the page's block 0
  (`RACE+PLAYER` and `GEARS+SPEED`) instead of all twelve, so the CONTROL
  pieces (`$2157`/`$215F`/`$2167`/`$216F`, 32x16 each) never enter the
  descriptor stack, the SAT or the picture. States 2..4 (the GEARS/SPEED/
  CONTROL pages) keep the stock emission byte for byte, and the page 1
  (PLAYER) draw at `$021F96` is untouched.

The row list's page table (`$FF53A0`) has block 0 = 12 pieces and blocks 1..5
= the per-row highlight; the native draw clamps the highlight to the last kept
row for the row list, so a snapshot that restored the old fifth selection
cannot leave a border over the removed row.

There is no presentation mask and no per-frame correction pass: the button is
never drawn, so no frame timing can expose it.

Raw-ROM evidence for the whole chain:

| Address | Meaning |
|---|---|
| `$007942` | Four 7-word control presets; row 0 is TYPE 1, read as `[LEFT, RIGHT, UP, DOWN, A, B, C]` |
| `$FF1BC6` / `$FF201E` | Applied type words (0 = TYPE 1); boot writes 0, the setup screen's copy at `$021860` is the only other writer |
| `$FF19AE` / `$FF1E06` | Applied raw-pad tables; TYPE 1 = `5,6,0,1,3,2,4` |
| `$FF18FA` | Remapped controls (bit 3 ACCEL, bit 2 BRAKE, bit 4 NITRO) |
| `$FF2554` | Setup carousel menu-controller base (`$FF2556` P1 state, `$FF25C4` P2 state) |
| `$21F2C` | State → draw routine (`0,2,3,4` → `$21F54`; `1` → `$21F96`) |
| `$21F40` | State → record (`block`, value adjust, d6 adjust, d7 adjust) |
| `$21E6E` | Per-player SAT linker: player number, both blocks, SAT DMA |
| `$FF48BA` | Descriptor stack (count, free list, 8-byte pieces at +`$56`) |
| `$FF53A0` | Page table: 6-byte directory at +8, payload pieces `{y,size,tile,x}` |
| `$001CE0` / `$0206AE` | Append one descriptor / emit one page block |
| `$021CB2` | CONTROL page value handler (page unreachable now) |

Passwords do not encode a control type (`docs/PASSWORDS.md`), and with the
selector unreachable and boot writing 0, the applied type is TYPE 1 for both
players. The port deliberately has no correction pass.

## Verifying the picture

Every presented frame is captured from the presentation provider
(`TG2_CONTROL_CAPTURE`) with the CONTROL rectangles' non-backdrop pixel
counts, the carousel state and the number of CONTROL tiles in the live SAT:

```sh
build/venv/bin/python tools/tg2_carousel_capture.py --out build/carousel-capture/after-1p
build/venv/bin/python tools/tg2_carousel_capture.py --two-player \
    --out build/carousel-capture/after-2p
```

The run spans frames before the menu opens, entry, 14 cursor moves each way
(with wraps) and leaving, in one- and two-player layouts. The fixed build
reports 0 frames with any CONTROL pixel and 0 frames with a CONTROL tile in
the display list. The same capture on the previous mask-based build shows 238
offending frames in one-player (14 at entry, then 8 per cursor move) and 14 at
two-player entry, which is the owner's flicker.

## Verifying the controls

```sh
flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh
build/venv/bin/python tools/test_tg2_controls.py --label "fresh install"
build/venv/bin/python tools/test_tg2_controls.py --label "existing settings.ini" \
    --settings tools/test-data/settings-existing.ini
build/venv/bin/python tools/test_tg2_controls.py --label "B remapped to Y" \
    --settings tools/test-data/settings-override.ini --b-face y
build/venv/bin/python tools/test_tg2_controls.py --label "two-player" --two-player
```

The test attaches two synthetic SDL controllers through the engine's dev
probes (`virtual_pad` / `virtual_axis`), drives RT/LT through SDL's real
gamecontroller axis path and the player's deadzone, and checks the resulting
Genesis pad mask over TCP. In a race it also reads the cartridge's own
remapped control byte (`$FF18FA`): RT alone sets ACCEL (bit 3) and LT alone
sets BRAKE (bit 2), and the applied table is TYPE 1 for both players. It also
proves the four carousel rows, the removed button's pixels, the stock
framebuffer hashes and empty dispatch/floor manifests. The two-player pass
drives player 2's pad too, so both stacked carousels wrap 0..3.

Not verified in CI: real Steam Deck / DualSense / Xbox hardware. The trigger
axes are read through `SDL_GameControllerGetAxis`, which is the same call the
analog sticks already use on those devices.
