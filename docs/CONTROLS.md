# Controls: fixed TYPE 1 and analog pedals

The port owns controller remapping. The launcher's binding table
(`[input.pN]` in `settings.ini`) and the in-game runtime menu are the only
places a player changes which physical input drives a Genesis button. The
cartridge's own CONTROL TYPE choice is therefore removed, and the two features
below are game-side policy on top of the shared runner's input path.

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

## Why TYPE 1

The cartridge maps raw pad bits to car actions through a per-player table.
Raw-ROM evidence:

| Address | Meaning |
|---|---|
| `$007942` | Four 7-word presets; row 0 is TYPE 1. Read as `[LEFT, RIGHT, UP, DOWN, A, B, C]` → output bit |
| `$00797A` | Applier: reads the player's type word, copies that preset into the raw-pad table |
| `$FF1BC6` / `$FF201E` | Player 1 / player 2 type word (0 = TYPE 1) |
| `$FF19AE` / `$FF1E06` | Applied table: `UP, DOWN, LEFT, RIGHT, B, A, C` = `5, 6, 0, 1, 3, 2, 4` for TYPE 1 |
| `$FF18FA` | Remapped controls produced from that table (bit 3 ACCEL, bit 2 BRAKE, bit 4 NITRO) |
| `$FF2554` | Setup carousel's menu-controller struct |
| `$FF2562` / `$FF25D0` | TYPE 1..4 value word the CONTROL page edits (P1 / P2) |
| `$021860` | Leaving the setup screen copies the menu fields into `$FF1BC6`/`$FF201E` and the player config |
| `$021A62` | Carousel input handler: rows 0..4 = RACE, PLAYER, GEARS, SPEED, CONTROL, wrapping 0..4 |
| `$021E14` | Carousel row-list draw leaf (also runs the palette fade) |
| `$021CB2` | CONTROL page value handler: clamps the edited type to 0..3 |

TYPE 1 is the cartridge default and the mapping the launcher's face-button
bindings already describe (B = accelerate, A = brake, C = nitro). The port
holds it for both players:

* `$FF1BC6` and `$FF201E` are clamped to 0 on every VBlank and again at the
  applier (`$00797A`), so the CONTROL page's value can never reach the car;
* a quickstate load forces both players' applied tables back to TYPE 1
  (`tg2_controls_state_loaded`), because a restored RAM image may carry a
  table built from another type;
* the first time a non-zero type word or table is corrected, one line is
  written to stderr (`[tg2] control type ... holding TYPE 1`), which is the
  debug assertion for the lock.

Passwords do not encode a control type (`docs/PASSWORDS.md`), and a saved
2P setup only reaches the game through the same menu fields, which are
clamped. The only real hole would be a directly written table, and the
quickstate path covers that.

## The removed CONTROL row

The carousel used to offer a fifth row, CONTROL, whose page is a static pad
diagram plus a `TYPE 1 2 3 4` selector. With remapping owned by the port the
page has no meaning, so it is gone:

* the carousel input handler is replaced (`$021A62`, same START/row rules as
  stock) with four rows: RACE, PLAYER, GEARS, SPEED, wrapping 0..3;
* the button art is part of the page bitmap the cartridge streams into tiles,
  so the port omits the row in the presented picture on the one screen that
  draws it: the row-list draw hook marks the frame and
  `game/tg2_video.c` paints the button's native rectangle with the screen's
  backdrop colour. Navigation, the game's own palette fades and every other
  screen are untouched.

`build/trigger-pedals/carousel-before-after.png` (ignored build output) shows
the stock five-row list next to the port's four-row list. The stock
framebuffer gates at frames 60 and 300 do not include the carousel, so they
stay identical.

## Verifying it

```sh
flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh
build/venv/bin/python tools/test_tg2_controls.py --label "fresh install"
build/venv/bin/python tools/test_tg2_controls.py --label "existing settings.ini" \
    --settings tools/test-data/settings-existing.ini
build/venv/bin/python tools/test_tg2_controls.py --label "B remapped to Y" \
    --settings tools/test-data/settings-override.ini --b-face y
```

The test attaches two synthetic SDL controllers through the engine's dev
probes (`virtual_pad` / `virtual_axis`), drives RT/LT through SDL's real
gamecontroller axis path and the player's deadzone, and checks the resulting
Genesis pad mask over TCP. In a race it also reads the cartridge's own remapped
control byte (`$FF18FA`): RT alone sets ACCEL (bit 3) and LT alone sets BRAKE
(bit 2). It also proves the carousel rows, the removed button's pixels, the
TYPE 1 clamp, the quickstate correction, the stock framebuffer hashes and empty
dispatch/floor manifests.

Not verified in CI: real Steam Deck / DualSense / Xbox hardware. The trigger
axes are read through `SDL_GameControllerGetAxis`, which is the same call the
analog sticks already use on those devices.
