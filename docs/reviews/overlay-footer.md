# Runtime overlay footer wrapping

Branch: `vittau/overlay-footer-wrap`, based on merged Phase B `5affd81`.

The software runtime overlay now wraps help at word boundaries, splitting an
overlong word when necessary. It measures the selected description before
laying out the settings viewport and reserves nine bitmap-pixel rows per help
line. The list retains its font, colours, spacing and selection treatment;
when help needs more height, the list scrolls to keep the selected row visible.
The existing status area remains reserved below the help. Drawing is bounded
by the panel; arbitrarily long third-party descriptions are vertically limited
to the available area rather than painting over settings rows.

`ui-0002-runtime-footer-wrap.patch` is a new git-format UI patch, applied after
`ui-0001` by the existing applicator. No other patch or submodule pin changed.
The hardware/ImGui backend does not use this selected-description footer:
its footer contains navigation/status text and already measures wrapped height
and uses `PushTextWrapPos` in a separate child region. Descriptions there are
inline beneath rows, so that backend was left unchanged; no hardware ImGui
qualification is claimed.

## Before and after captures

All 20 live row descriptors were inspected. The bitmap panel offers 38 glyph
cells per help line at both tested window sizes. These 15 descriptions were
clipped before (including the missing final punctuation on Window scale):

| Section | Row | Screenshot key | Help lines after, at both sizes |
| --- | --- | --- | --- |
| VIDEO | Window scale | `display.window_scale` | 2 |
| MODS | Widescreen | `mods.widescreen.enabled` | 3 |
| MODS | Aspect ratio | `mods.widescreen.aspect` | 2 |
| AUDIO | Unfiltered audio | `audio.bypass_filter` | 3 |
| MODS | Diagnostics (bug report) | `mods.diagnostics.enabled` | 5 |
| VIDEO | Internal resolution (restart) | `video.internal_resolution` | 8 |
| SAVE STATES | Slot | `states.slot` | 2 |
| SAVE STATES | Save state | `states.save` | 3 |
| SAVE STATES | Load state | `states.load` | 3 |
| AUDIO | Music volume | `mods.musicvol.level` | 5 |
| AUDIO | SFX volume | `mods.sfxvol.level` | 6 |
| MODS | 60 fps races | `mods.race60.enabled` | 5 |
| MODS | HUD | `mods.hud.placement` | 5 |
| MODS | Hide overscan | `mods.overscan.hidden` | 10 |
| AUDIO | RACE SOUND | `mods.racesound.mode` | 6 |

Each listed row has before/after presented screenshots at the game's actual
default **597×448** window and at **1280×800**:

```text
build/footer/before/default-<key>.png
build/footer/after/default-<key>.png
build/footer/before/deck-<key>.png
build/footer/after/deck-<key>.png
```

For example, `after/default-mods.overscan.hidden.png` shows the longest
paragraph in full, with its selected row above the separator; its Deck-size
counterpart is `after/deck-mods.overscan.hidden.png`. There are 60 row screenshots
in total, plus four root-navigation footer screenshots (`default-root.png`,
`deck-root.png` in each directory). All remain ignored under `build/`.

Bitmap glyph decoding of all screenshots confirms that all 30 after row
screenshots contain the complete description, all 30 before row screenshots
truncate it, and every selected-row background ends above the footer separator.
The previously clipped root navigation hint also fits in full after wrapping.
Evidence: `build/footer/{before,after}/summary.json`, `text-validation.json`
and `text-validation.log`. The 5×7 font and its existing glyph fallbacks are
unchanged. Capture navigation selects rows without activating any setting.
The original executable was saved before edits as `build/footer/base-exe`.

## Verification

All builds, runtime captures and pixel analysis ran under the shared heavy
lock, with three build jobs and one runtime at a time.

```sh
flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh
flock ~/.cache/tg2-heavy.lock /opt/homebrew/bin/python3.14 tools/regression.py \
  --out build/footer/regression --uncapped
```

Both commands exit **0**. The build reapplied the full patch stack, including
`ui-0001` then `ui-0002`, and the resulting UI source is byte-identical to the
authored patch tree. `tools/apply-engine-patches.py --check` exits 0.
`build/footer/verify.log` records build, regression, after captures and checks.

With the overlay closed, all **356 framebuffer hashes and four WAV SHA-256
hashes** match the committed golden. All dispatch, floor, interior-label and
unsafe-floor manifest counts are **zero**, including both screenshot sessions
and the one-frame inventory run. All **35 generated C hashes** remain identical
to the base (`build/footer/generated-comparison.json`). No WAV remains.

A standalone C test against the applied UI implementation checks word breaks,
exact-width lines, hard splits, explicit newlines and the font's ignored UTF-8
bytes: exit 0 (`build/footer/test-wrap.c`, `unit.log`, also repeated in
`verify.log`). It uses the real wrapping code, with explicit expected spans.

This is local macOS arm64 / SDL dummy-software evidence, including a 1280×800
headless drawable; it is not a physical Deck, Windows/Linux runtime or hardware
ImGui playtest. No CI, release packaging, merge or engine fork was performed.
