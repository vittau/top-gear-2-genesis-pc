# Runtime menu organization

The Esc menu has exactly these categories, in this display and controller-focus
order: **VIDEO, AUDIO, SYSTEM, MODS, SAVE STATES**. The launcher is unchanged.
The layout maps the effective shared and game descriptors before menu creation;
all setting keys, defaults, value callbacks and restart requirements are retained.

| Previous category | Current category | Existing rows |
|---|---|---|
| Display | VIDEO | Fullscreen; Window scale |
| Graphics | VIDEO | Linear filter |
| Video | VIDEO | Internal resolution (restart) |
| Audio | AUDIO | Volume; Unfiltered audio; Music volume; SFX volume |
| Sound | AUDIO | RACE SOUND |
| System | SYSTEM | Resume game; Quit game |
| Mods | MODS | Widescreen; Aspect ratio; Diagnostics (bug report); 60 fps races; HUD; Hide overscan |
| Save states | SAVE STATES | Slot; Save state; Load state |

The shared UI exposes an optional section-name mapping plus an explicit section
order. TG2 selects that policy through `GameSpec.runtime_ui_layout`; a host with
no policy keeps the previous UI behavior. Section ordering moves section rows,
not descriptors, so item order, confirmation prompts and callbacks stay aligned.
The patches live in `patches/segagenesisrecomp/{0051-*,ui-0001-*}`. Both the
shell and Windows Python application scripts apply `ui-*` to `recomp-ui/` and include its pinned revision in the stamp;
neither submodule pin changes.

Focused evidence is under `build/linear-s3/menu-{before,after}/`: real controller
navigation at 1280×800, every original row visited, root/page captures and JSON
inventories. The initial before/after inventories contain the same 20 labels and
values. Controller changes save Linear filter Off→On, Internal resolution 2×→3×,
Music volume 75→70 and SFX volume 60→55; relaunch shows those saved values.
The restart row changes the next launch's value, retaining its existing latch.
These are local hidden-window checks; owner acceptance and Deck playtest remain
separate. See the worker report for exact commands, exits and the final SDL build.

Validation commands (each returned 0):

```sh
tools/apply-engine-patches.sh --reset
flock ~/.cache/tg2-heavy.lock cmake --build build --target TG2Recomp -j3
flock ~/.cache/tg2-heavy.lock python3 build/linear-s3/menu-probe.py before
flock ~/.cache/tg2-heavy.lock python3 build/linear-s3/menu-probe.py after
```

The retained local probe drives SDL's virtual controller through the actual
runtime UI, queries `ui_rows`, and captures `screenshot presented=1`. `before`
used the original executable; final `after` used statically linked SDL2 2.28.5
and hidden Cocoa/Metal. Root capture: `build/linear-s3/menu-after/root.png`;
VIDEO/AUDIO page captures and controller-visit lists are beside it. Both final
processes (change/save and reopen) exited 0 with all four manifests empty.
The Off→On filter behavior is independently checked by the S3 presentation probe;
this menu-only change does not alter game composition or sampler semantics.
