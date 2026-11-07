# Task 21: crop the race's black bands (owner request) + HUD Edges map split

Read `AGENTS.md` (follow its "Machine resources" and "CI budget" rules: at
most 3 build jobs, `flock ~/.cache/tg2-heavy.lock` around every build and
heavy run, never trigger CI), `docs/WIDESCREEN.md` (all of it, especially
"Hide overscan" and the HUD sections), `game/tg2_video.c`,
`game/tg2_options.c` and the runner's presentation path
(`segagenesisrecomp/runner/main.c`: `update_render_logical_size`,
`ws_canvas_w/h`, `display_logical_height`).

## Setup in this worktree

You are in a fresh worktree:
- run `git submodule update --init --recursive`;
- run `tools/apply-engine-patches.sh`;
- build with `JOBS=3 flock ~/.cache/tg2-heavy.lock tools/build-linux.sh ~/roms/genesis/tg2.bin build`.

Another worker (task 20, audio) runs in parallel on port 4590 and may be
building. Use **TCP port 4600** only, and kill only your own PIDs. No visible
windows, no sound on the owner's speakers: dummy video and audio drivers
only. Commit often and push your branch. Merge `origin/main` before
reporting.

## Owner request

> You say you hide the overscan, but can't you also remove the black bars
> that are still left?

Every race picture has **8 black lines at the top and 16 at the bottom**:
only lines 8–207 of the 224 carry the picture. This was measured on the
baseline route in Off, 16:9 and 21:9. The owner chose to **crop** them, not
to fill them with synthesized scenery.

## Change

When **Hide overscan** is On (the default), race screens present only the
active picture lines, and the image fills the window height:
- **Off widescreen:** the race shows 256 × 200 instead of 256 × 224.
- **Widescreen:** the canvas width follows the cropped height. For example,
  16:9 at 200 lines is about 356 px wide, and Adaptive fits the window. The
  renderer's margins, sprite capture and the margin audit must work on the
  cropped geometry. HUD Centered and Edges must stay anchored correctly.
- **60 fps synthesized frames** crop identically, with no one-frame flashes
  of the bands.

Rules:
- Find the active line range from evidence, not a guess. Check whether it is
  constant in every race situation:
  - all 16 tracks, including rain, night, fog and snow;
  - race start countdown, finish, the pause screen and pit stops;
  - nitro and messages such as the speech bubbles and "FINAL LAP";
  - tunnels and hills;
  - **2-player split screen**.

  If any situation draws into lines 0–7 or 208–223, either crop
  per situation (with evidence) or leave that situation uncropped. Never
  cut off visible game content.
- Menus, the shop, results and other non-race screens are unchanged:
  pillarboxed and letterboxed exactly as today. Don't resize the OS window
  when entering or leaving a race; only the logical canvas changes.
- **Hide overscan Off** must keep today's full 224-line race picture,
  including the stock top band. With every option off (widescreen Off,
  60 fps Off, Hide overscan Off) the output stays byte-identical to stock:
  frame 60 `2A0B972960C5E325` and frame 300 `1131D937D70234FD`
  (`tools/verify_widescreen.py --modes off`). Find out how today's Hide
  overscan keeps those hashes and keep the same guarantee.
- Update the option's description text in `game/tg2_options.c`, and in the
  launcher if it shows one, so it says it also crops the empty bands.
- Keep the change game-side (`game/`) if possible. If the engine
  presentation path must change, make it a patch in
  `patches/segagenesisrecomp/` with a README line.

## Second item: HUD Edges map split

On the baseline route in 16:9 with `TG2_HUD_MODE=edges`, at frame 3480, the
track-map tiles are drawn away from their position markers (the `1ST` and
`1P` dots, which are sprites). At frames 3840 and 3900 they line up. Find
the cause, fix it, and prove it across a sweep of race frames in 16:9 and
21:9 with HUD Edges. Use an automated check comparing the map's tile
position with its marker sprites' positions, not just eyeballing.

## Evidence required

- Before/after PNGs (outside git, under `build/`) at the same route frames
  for each case:
  - Off, 16:9 and 21:9, each with Hide overscan On and with it Off;
  - one 2-player split-screen frame;
  - one menu frame showing it is unchanged.
- The active-line evidence: a table showing, for each situation checked
  above, which lines are non-black, with the tool used.
- Margin audit (`--margin-audit`): 0 failures in 16:9 and 21:9 with the crop
  active.
- Off hashes unchanged; manifests empty; `tools/check_road_artifacts.py`
  clean with 60 fps.
- `docs/WIDESCREEN.md` "Hide overscan" section rewritten for the crop, and
  the HUD Edges fix documented.
