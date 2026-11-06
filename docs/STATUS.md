# Project status (overnight autonomous run, 2026-11-06)

Overall estimate: about **85%** of the goal, which is a native Top Gear 2
on Windows, Linux/Steam Deck and macOS, with widescreen and true 60 fps,
plus music and SFX together. Everything below has been verified headlessly.
The owner has played two short sessions (Linux, Ryzen 5 3500U).

## On `main`

| Area | State | Docs |
|---|---|---|
| Native 4:3 baseline | Boot → menus → full 4-lap race → results/shop/next race; 2P split-screen; 33.7-min soak. 0 dispatch misses. | `BRINGUP.md`, `VALIDATION.md` |
| All 16 tracks | Password codec reversed (`PASSWORDS.md`, `tools/tg2_password.py`). All 16 countries raced for 62 s in Off and 16:9+Edges, 0 manifest entries; rain, night, fog and snow covered. Nitro = C button. | `VALIDATION.md` |
| Widescreen | Adaptive / 16:9 / 21:9 race renderer: road, background, sprites in the margins. HUD Centered or Edges. Off is byte-identical to stock. | `WIDESCREEN.md` |
| Widescreen fixes from playtests | Black bands on downhills, the top-window line, tunnel margins (now follow the walls), and the motion-only flicker in 60 fps synthesized frames. Full-presented-frame margin audit: 1019 → 0. | `WIDESCREEN.md` |
| Hide overscan | New option, default On: blanks the stock red marks in the top band, in every mode. | `WIDESCREEN.md` |
| 60 fps | Stock simulation plus host-only interpolation. Identical WRAM over 16000 frames; 60 pictures/s; no road artefacts; adds 50 ms display latency. | `FRAMERATE.md` |
| Music + SFX (BOTH) | A third RACE SOUND value, **BOTH**, in the game's own SOUND menu. Stock MUSIC and SFX WAVs are byte-identical to stock. Limitation: a shared-chip mix, so music notes can be stolen by SFX; a clean second virtual chip is future work. | `AUDIO.md` |
| Options | Widescreen / 60 fps / HUD / Hide overscan in the launcher and the in-game overlay (gamepad: Back+RB), persisted in `settings.ini [mods.*]`. | `RELEASING.md` |
| CI | `build.yml`: Linux (glibc ≤ 2.35, Deck), Windows x64, macOS universal2. The ROM comes from the private repo via deploy key; artifacts are gated against ROM or generated C. | `RELEASING.md` |
| ROM | Auto-detected by CRC next to the executable, whatever the file name. | `BRINGUP.md` |

Engine changes live as patches in `patches/segagenesisrecomp/`. The
submodule pin is upstream `dd520f1`.

## Still in progress

| Task | Worktree / branch | State |
|---|---|---|
| 12 Performance + audio pacing (owner bug) | `tg2-performance` | Music tempo wobbles during races under CPU load; the release build is better than dev. Also asked: decouple music from frame pacing, and fix the feedback replay being written to `~/.local/bin/logs`. |

## Questions for the owner (queued for 09:00)

1. Is the 50 ms display latency of 60 fps acceptable on the controller?
2. Does BOTH sound acceptable on real speakers? Music notes can be stolen
   by SFX. If not, the next step is a second virtual sound chip just for
   SFX.
3. After task 12 lands: is the music tempo steady?

## Open items

- Real-device checks: Steam Deck (Gamescope, controller only), Windows,
  macOS (unsigned; the payload is a folder, not a `.app`).
- Each country's second championship race is still unvisited (it needs
  progression).
- First public release: the owner decides when to make the repo public.
  `vittau/top-gear-2-private-inputs` must stay private forever.

## For playtests

Release-config build: `~/Games/TG2-play-<sha>/` (ROM next to the binary),
or download the latest `build.yml` artifact. Dev build:
`build-main/TG2Recomp ~/roms/genesis/tg2.bin`.
