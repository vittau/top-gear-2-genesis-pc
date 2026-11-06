# Top Gear 2 Recomp (Sega Genesis → native PC)

A native PC port of **Top Gear 2 (USA)** for the Sega Genesis / Mega Drive,
made by static recompilation with the
[segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) framework.
The original 68000 code is translated to C and compiled into a native
executable. No emulator core is involved.

**Status: beta.** The full game plays on Linux, verified with automated
runs. Windows and macOS builds come out of CI but haven't been played on
real hardware yet.

> This repository contains **no ROM, no game code and no game assets**.
> You need your own legally obtained dump of *Top Gear 2 (USA)*
> (CRC32 `BD3074D2`).

## Features

- **Widescreen**: Adaptive (fits the window), 16:9 or 21:9. The road,
  scenery, opponents and roadside objects extend into the extra space.
  The HUD can stay centred or move to the screen edges.
- **True 60 fps races**: the original shows ~30 new pictures per second.
  This mode presents 60, with gameplay, physics and lap times identical
  to the original. The cost is 50 ms of display latency.
- **Music and SFX together**: a new **BOTH** choice in the game's own
  *Sound → Race Sound* menu.
- **Hide overscan**: hides the stray marks at the top edge that a CRT
  never showed.
- Controller support, a launcher, an in-game options overlay
  (F1/Esc, or Back + RB on a gamepad), save states and rewind.
- With every option off, the output is byte-identical to the original
  game.

## Playing

1. Download a build for your platform (Linux x86_64 / Steam Deck,
   Windows x64, macOS universal) from Releases.
2. Put your ROM **in the same folder as the executable**. Any file name
   works; the game finds it by content.
3. Run `TG2Recomp`.

Steam Deck: add the Linux build as a non-Steam game in Desktop Mode, with
the ROM in the same folder. Details and the macOS first-run (Gatekeeper)
steps are in [docs/RELEASING.md](docs/RELEASING.md).

Default keyboard: arrows to steer, **X** accelerate (B), **Z** brake (A),
**C** nitro, **Enter** start.

## Building from source

The build generates C from your ROM, so the ROM is needed at build time
(it's never copied into the repo or the output).

```sh
git clone --recursive https://github.com/vittau/top-gear-2-genesis-pc.git
cd top-gear-2-genesis-pc
tools/build-linux.sh /path/to/your/tg2.bin build
build/TG2Recomp /path/to/your/tg2.bin
```

Release packaging for each platform lives in `tools/release/`, and the CI
workflow in `.github/workflows/build.yml`.

## Documentation

| Doc | Content |
|---|---|
| [docs/STATUS.md](docs/STATUS.md) | Current state and open items |
| [docs/BRINGUP.md](docs/BRINGUP.md) | How the recompilation was brought up |
| [docs/WIDESCREEN.md](docs/WIDESCREEN.md) | Widescreen renderer design |
| [docs/FRAMERATE.md](docs/FRAMERATE.md) | 60 fps design and parity proof |
| [docs/AUDIO.md](docs/AUDIO.md) | Sound driver map and the BOTH option |
| [docs/PERFORMANCE.md](docs/PERFORMANCE.md) | Frame timing and audio pacing |
| [docs/VALIDATION.md](docs/VALIDATION.md) | Test ledger: all 16 tracks, soaks |
| [docs/RAM_MAP.md](docs/RAM_MAP.md), [docs/PASSWORDS.md](docs/PASSWORDS.md) | Reverse-engineering notes |

## Credits

- [segagenesisrecomp](https://github.com/mstan/segagenesisrecomp) and
  [recomp-ui](https://github.com/mstan/recomp-ui) by Matthew Stanley and
  contributors. The recompiler, runtime and launcher this port is built on.
- *Top Gear 2* © 1994 Kemco / Gremlin Graphics Software. This is an
  unofficial fan project, not affiliated with or endorsed by the rights
  holders.

## License

[PolyForm Noncommercial 1.0.0](LICENSE.md): free for non-commercial use.
The submodules keep their own licenses (see `LICENSE.md`).
