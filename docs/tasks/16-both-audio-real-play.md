# Task 16: BOTH sound mode doesn't work in real play, and its menu text looks wrong (owner bug)

Read `AGENTS.md` (follow its "CI budget" rules: never trigger CI),
`docs/AUDIO.md`, `game/tg2_audio_both.c`, `game/tg2_spec.c`,
`docs/RAM_MAP.md`, `docs/PASSWORDS.md`, and the qualification tools
`tools/tg2_runner.py` and `tools/tg2_race_driver.py`.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Also build a release-config binary, the same as the owner plays:
`cmake -S . -B build-rel -G Ninja -DCMAKE_BUILD_TYPE=Release
-DGENESIS_RECOMP_ROOT=$PWD/segagenesisrecomp -DTG2_ROM=$HOME/roms/genesis/tg2.bin
-DGEN_ENABLE_TRACE=OFF -DSONIC_REVERSE_DEBUG=OFF -DTG2_BUILD_VERSION=0.1.0-dev`,
then `ninja -C build-rel TG2Recomp`.

Other agents run TG2Recomp in parallel:
- use **TCP port 4550** only;
- kill only your own PIDs.

**Never play sound on the real speakers**, because the owner is at the
desktop. Use dummy audio or WAV capture. No visible windows. Another
agent (task 15) is fixing real-device audio pacing in the engine audio
path. Stay out of that and touch only BOTH logic and menu rendering.
Commit often and push your branch.

## Owner report

In a release-config build of main c27839b, the owner chose
**SOUND → RACE SOUND → BOTH** in the main menu and raced:

> the text "BOTH" looks strange, and the feature didn't seem to work in
> practice. I only heard the music.

His audio also had pops and dropouts (task 15). Those could mask quiet
SFX, but "only music" suggests BOTH really didn't engage.

## Investigate

1. **Reproduce the owner's flow exactly, with input only.**
   - Cold boot.
   - Press START at the title.
   - Main menu → SOUND → RACE SOUND → BOTH.
   - Back out the way a player does: press whatever button leaves the
     page, and also try leaving via the other buttons (A/B/C/START).
   - 1P GAME → START → race.
   Also test the route via the password/CONTINUE screens, and a second
   race after the first. Capture WAV and the FM/PSG write dump per run.
   Does BOTH actually engage? Check the host flag, `$FF240E` and the SFX
   command stream during the race.
2. **Compare with the evidence route** that task 05 used
   (`docs/AUDIO.md`). Find what differs: menu exit path, a reset or
   reload of the setting at race start, the `$FF240E` save/restore at
   `$001FBE/$001FF4/$002104`, an attract-mode pass, the 60 fps option, or
   the widescreen renderer path (the owner plays 16:9 + 60 fps; task 05
   may have qualified only Off).
3. **Fix it** so BOTH engages on every path a player can take, and stays
   selected for the session. Persisting it in `settings.ini` like the
   other options is a plus, as long as stock MUSIC/SFX remain exactly
   stock.

## The "BOTH" text

It currently uses port-drawn glyphs from the menu palette (see
`docs/AUDIO.md`), and it looks off next to the game's own font.
- Render "BOTH" using **the game's own menu font**. The menu uploads
  8×16 glyphs dynamically from a font table in ROM; find that table
  and its glyph indexing, then compose B, O, T and H from the real
  glyphs.
- Colour, shading and placement must match how the game draws "MUSIC"
  and "SOUND EFFECTS" on the same page: same palette, same
  vertical/horizontal alignment, centred like the stock values.
- Produce PNGs comparing the stock value pages (MUSIC, SOUND EFFECTS)
  and the new BOTH page at 1× and 3× zoom.

## Constraints

- Stock MUSIC and SFX choices stay byte-identical. Offline WAVs are
  unchanged, and the Off framebuffer hashes are frame 60
  `2A0B972960C5E325`, frame 300 `1131D937D70234FD`.
- Manifests stay empty.

## Evidence required

- `docs/AUDIO.md` updated: root cause, fix, the real-play route and the
  glyph source.
- For each route (menu exit buttons, password route, second race, 16:9 +
  60 fps on): WAV captures in MUSIC/SFX/BOTH, with SFX stream presence
  proven in BOTH (write-dump counts by writer, engine-noise and
  collision SFX events present).
- Before/after PNGs of the BOTH menu page beside the stock pages.
