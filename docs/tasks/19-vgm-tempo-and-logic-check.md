# Task 19: pin music tempo and check the music logic against the owner's VGM rips

Read `AGENTS.md` (follow its "CI budget" rules: never trigger CI),
`docs/AUDIO.md` (§11 "Tempo fidelity" and §12) and `docs/PERFORMANCE.md`
§10. Also read the tools `tools/audio_tempo_compare.py` and
`tools/gpgx_render.c`, and the engine's `GENESIS_AUDIO_WRITEDUMP` support.

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- build with `JOBS=8 tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Other agents may run TG2Recomp:
- use **TCP port 4580** only;
- kill only your own PIDs.

**Never play sound on the owner's speakers**: dummy audio or offline
capture only. No visible windows. No sudo. Commit often and push your
branch.

The owner says **small accuracy concessions are acceptable** for a better
experience. The stock path (all options off) must still stay
byte-identical in video. Audio tempo corrections are welcome even if they
change the offline WAV; document them.

## Inputs

The owner supplied 4 VGM v1.5 rips (YM2612 @ 7670453 Hz, NTSC 60 Hz, GD3
dated 1994/05/24). They're read-only at `~/roms/genesis/tg2-vgm/`:

| File | Total | Loop |
|---|---|---|
| `01 - Title Theme.vgm` | 51.8 s | 44.4 s |
| `02 - Canterbury Plains.vgm` | 125.2 s | 118.9 s |
| `03 - Ayers Rock.vgm` | 154.5 s | 151.4 s |
| `04 - Auckland.vgm` | 197.9 s | no loop |

They're game-derived. **Never commit them, or anything rendered from
them, to git.** Only derived numbers go in docs.

## Open question from task 18

The port is in tune and the Z80 isn't starved, but the race music measured
**-1.7 %** (pulse autocorrelation, 118 ms emulator vs 120 ms port). The
suspect is the exact YM2612 timer-B period for the value the driver
writes (`$26=$BE`) and how the port models the timer-B tick. The driver
polls timer B at Z80 `$0BFC`; the port models 19.83 ms, task 18 measured
19.87 ms. An audio-alignment approach failed because loops aliased, which
is exactly what register-level timing avoids.

## Steps

1. **A VGM parser and comparator.** Write `tools/vgm_compare.py`. Parse
   VGM wait/YM commands into a timestamped register-write stream at
   44100 Hz. From the port, capture the same stream with exact guest
   timestamps: the write dump, or a `.vgm` logger in the engine
   (opt-in, off by default).
2. **Tempo from register events.**
   - Use key-on events (YM reg `$28`) per channel, and timer-B writes
     (`$26`/`$27`).
   - Compute the global tempo ratio port/VGM: from the loop period and
     from linear regression of matched key-on times. Compute the local
     drift over time too.
   - Do it for the Title Theme (sound test or title screen) and for the
     race tracks you can reach (Auckland is track 1; use
     `tools/tg2_password.py` for the others). The SOUND → MUSIC TEST
     menu, if it can select each song, is the easiest route.
3. **Logic double-check.**
   - Compare the ordered sequence of musical events (key-on/off per
     channel, frequency writes `$A0-$A6`, algorithm/instrument loads
     `$B0-$B6` and `$30-$9F`), ignoring absolute timing.
   - Report the match percentage and the first divergences. That
     catches wrong notes, wrong instrument patches and missing channels
     in the port's Z80/YM path.
   - A DAC/PCM channel (reg `$2A`) may exist. Compare it too, if
     present.
4. **Fix.** If the port is off by more than ±0.2 % against the VGMs, find
   the cause and fix it (timer-B period, YM clock divider, Z80 polling
   cadence, sample clock). Re-measure. Target: |tempo error| ≤ 0.1 %
   against every VGM you can align. If the logic check finds wrong
   notes or patches, root-cause them too.
5. **Listening files for the owner.** In `~/Music/tg2-ab/`, outside the
   repo, add:
   - a VGM rendering of each track (libvgm/vgmplay built under
     `~/tools`, or the existing gpgx path);
   - the port's after-fix rendering of the same track;
   - an update to the README.

## Evidence required

- `docs/AUDIO.md` §11 updated with:
  - the VGM provenance (GD3 fields, no files);
  - the per-track tempo ratio before and after (loop-period and
    regression methods);
  - the logic-match table;
  - the root cause and the fix.
- Engine patch changes recorded in `patches/segagenesisrecomp/README.md`.
- Video stock hashes unchanged: frame 60 `2A0B972960C5E325`, frame 300
  `1131D937D70234FD`. Manifests empty.
- Nothing left running. Report what was installed under `~/tools`.
