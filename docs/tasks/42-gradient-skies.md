# Task 42 — Gradient skies

Fog horizon amendment: the owner approved `dLh = 0, kh = 1` to join the
flat fog panorama without a seam; top and 60% stops are unchanged.
The correction, all 64 flat-camera captures and seam table are recorded in
[the follow-up audit](42-sky-seam-audit.md).

Owner-approved colour proposal: https://claude.ai/artifact/5DpWnnC8DNjBjkcEe6qSYs

## Specification

Add an optional game-owned race-sky ramp, default Off, in launcher Presentation
mods and the in-game Mods page, persisted in `[mods.skies] enabled`. The toggle
is live. Menus, intro panels, results and shop must remain untouched. Off must
match the existing regression goldens and main framebuffer hashes; never
re-record goldens. No engine changes or generated-C edits.

Classify once per race from descriptor flags and the ROM base sky colour
(palette 3 entry 15, descriptor `+0x6C`). Night means Genesis `001`, including
Paris without the night-road-emitter flag. Use the live presented-row CRAM
colour for every ramp so fades, lightning and pause dimming follow it.

Convert to OKLCH `(L,C,h)`. Top is `(L+dLt,C*kt,h)`, original colour is at
60% of the band, horizon is `(L+dLh,C*kh,h)`; interpolate in OKLab. Clamp
stop L to [0,0.97], reduce chroma by ×0.97 repeatedly until in sRGB gamut.
Never change hue or re-tune the approved numbers.

| Class | Selection | dLt | kt | dLh | kh |
|---|---|---:|---:|---:|---:|
| night | base 001, no precipitation | -0.07 | 0.90 | +0.10 | 0.70 |
| nightrain | base 001, bit 5 | -0.06 | 0.90 | +0.06 | 0.70 |
| fog | bit 3 | -0.035 | 1.00 | 0.00 | 1.00 |
| snow | bits 5+6 | -0.07 | 0.90 | +0.06 | 0.60 |
| rain | bit 5 only | -0.09 | 0.85 | +0.05 | 0.70 |
| overcast | otherwise, C < 0.03 | -0.07 | 1.00 | +0.05 | 0.80 |
| day | otherwise | -0.10 | 1.25 | +0.07 | 0.60 |

Only replace pixels whose winning source is the flat plane-B sky or sky
backdrop. Retain skyline silhouettes, road, ground, HUD, sprites, player car,
weather, tunnels and window priority. Anchor to the current frame's first
panorama row, starting at the visible picture top after overscan crop; each
split-screen half owns its own ramp. Widescreen margins share the per-line
ramp. N× draws at output resolution, never by expanding native gradient rows;
60-fps synthesis uses the same presented raster state as the original layers.

Qualification requires all seven classes, both named night tracks, lightning
if present, hills, tunnel, split screen, 16:9/21:9, 2×/4× and 60 fps; compare
measured stops within ±2 RGB channels at 1× before dithering. Keep captures
and contact sheets under ignored `build/`, report all execution manifests,
build and regression exit codes, branch and commits. No CI, tags or releases.

## Approved reference colours

| idx | country / track | flags b3 | Genesis sky | class | top | original (60%) | horizon |
|---:|---|---|---|---|---|---|---|
| 0 | Australasia / Auckland | `0x00` | `556` | day | `#8f8eb5` | `#aeaece` | `#c5c6d9` |
| 1 | Australasia / Ayers Rock | `0x00` | `456` | day | `#6d8fb6` | `#92aece` | `#b2c3d7` |
| 2 | Australasia / Canterbury Plains | `0x10` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 3 | Australasia / Sydney | `0xA5` | `333` | rain | `#5d5d5d` | `#777777` | `#868686` |
| 4 | Britain / Loch Ness | `0x08` | `444` | fog | `#878787` | `#929292` | `#929292` |
| 5 | Britain / London | `0x00` | `345` | day | `#547596` | `#7792ae` | `#96a6b8` |
| 6 | Britain / Sheffield | `0x00` | `345` | day | `#547596` | `#7792ae` | `#96a6b8` |
| 7 | Britain / Stonehenge | `0x01` | `135` | day | `#07598f` | `#3177ae` | `#658bac` |
| 8 | Canada / Banff | `0x44` | `667` | day | `#adace8` | `#ceceff` | `#e8e8ff` |
| 9 | Canada / Niagara | `0xA4` | `124` | rain | `#203f6e` | `#315792` | `#4c6790` |
| 10 | Canada / Toronto | `0x00` | `456` | day | `#6d8fb6` | `#92aece` | `#b2c3d7` |
| 11 | Canada / Vancouver | `0x11` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 12 | Egypt / Abu Simbel | `0x00` | `556` | day | `#8f8eb5` | `#aeaece` | `#c5c6d9` |
| 13 | Egypt / Aswan | `0x00` | `445` | day | `#747395` | `#9292ae` | `#a9a9ba` |
| 14 | Egypt / Cairo | `0x10` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 15 | Egypt / Hush Sitton | `0x01` | `556` | day | `#8f8eb5` | `#aeaece` | `#c5c6d9` |
| 16 | France / Bordeaux | `0x00` | `345` | day | `#547596` | `#7792ae` | `#96a6b8` |
| 17 | France / Monaco | `0x10` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 18 | France / Nice | `0x00` | `046` | day | `#0c73a1` | `#0092ce` | `#6aa5c9` |
| 19 | France / Paris | `0xA5` | `001` | nightrain | `#000013` | `#000031` | `#061435` |
| 20 | Germany / Bavaria | `0x24` | `246` | rain | `#4677a8` | `#5792ce` | `#79a1cb` |
| 21 | Germany / Cologne | `0x00` | `234` | day | `#335b7b` | `#577792` | `#778a9b` |
| 22 | Germany / Frankfurt | `0x08` | `444` | fog | `#878787` | `#929292` | `#929292` |
| 23 | Germany / Munich | `0x65` | `256` | snow | `#4b97b3` | `#57aece` | `#8dbcd0` |
| 24 | Greece / Athens | `0x90` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 25 | Greece / Meteora | `0x00` | `445` | day | `#747395` | `#9292ae` | `#a9a9ba` |
| 26 | Greece / Mykanos | `0x00` | `345` | day | `#547596` | `#7792ae` | `#96a6b8` |
| 27 | Greece / Santorini | `0x01` | `445` | day | `#747395` | `#9292ae` | `#a9a9ba` |
| 28 | India / Amber Port | `0x00` | `456` | day | `#6d8fb6` | `#92aece` | `#b2c3d7` |
| 29 | India / Bombay | `0x00` | `345` | day | `#547596` | `#7792ae` | `#96a6b8` |
| 30 | India / Delhi | `0x00` | `556` | day | `#8f8eb5` | `#aeaece` | `#c5c6d9` |
| 31 | India / Taj Mahal | `0x01` | `445` | day | `#747395` | `#9292ae` | `#a9a9ba` |
| 32 | Ireland / Dublin | `0x00` | `455` | day | `#6e9191` | `#92aeae` | `#b1c2c1` |
| 33 | Ireland / Galway | `0x00` | `555` | overcast | `#989898` | `#aeaeae` | `#bebebe` |
| 34 | Ireland / Killarney | `0x24` | `334` | rain | `#5e5e74` | `#777792` | `#87879a` |
| 35 | Ireland / Limerick | `0x01` | `544` | day | `#937272` | `#ae9292` | `#bcabab` |
| 36 | Italy / Florence | `0x00` | `125` | day | `#0a32a0` | `#3157ae` | `#5770a4` |
| 37 | Italy / Pisa | `0x00` | `046` | day | `#0c73a1` | `#0092ce` | `#6aa5c9` |
| 38 | Italy / Rome | `0x10` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 39 | Italy / Sicily | `0x01` | `345` | day | `#547596` | `#7792ae` | `#96a6b8` |
| 40 | Japan / Hiroshima | `0x00` | `035` | day | `#005984` | `#0077ae` | `#598aab` |
| 41 | Japan / Kyoto | `0x10` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 42 | Japan / Tokyo | `0x00` | `235` | day | `#32589b` | `#5777ae` | `#798dae` |
| 43 | Japan / Yokohama | `0x01` | `236` | day | `#3354c0` | `#5777ce` | `#7a90c5` |
| 44 | Scandinavia / Copenhagen | `0x00` | `224` | day | `#3c377f` | `#575792` | `#6d6f93` |
| 45 | Scandinavia / Helsinki | `0x64` | `234` | snow | `#47627a` | `#577792` | `#748798` |
| 46 | Scandinavia / Reykjavik | `0x64` | `356` | snow | `#6798b4` | `#77aece` | `#9ebed2` |
| 47 | Scandinavia / Stockholm | `0x09` | `444` | fog | `#878787` | `#929292` | `#929292` |
| 48 | South America / Chile | `0x00` | `345` | day | `#547596` | `#7792ae` | `#96a6b8` |
| 49 | South America / Mexico | `0x00` | `125` | day | `#0a32a0` | `#3157ae` | `#5770a4` |
| 50 | South America / Peru | `0x00` | `344` | day | `#547676` | `#779292` | `#95a5a5` |
| 51 | South America / Brazil | `0x11` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 52 | Spain / Andalusia | `0x00` | `555` | overcast | `#989898` | `#aeaeae` | `#bebebe` |
| 53 | Spain / Barcelona | `0x10` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 54 | Spain / Madrid | `0x24` | `234` | rain | `#435d73` | `#577792` | `#6e8598` |
| 55 | Spain / Seville | `0x01` | `445` | day | `#747395` | `#9292ae` | `#a9a9ba` |
| 56 | Switzerland / Geneva | `0x44` | `345` | day | `#547596` | `#7792ae` | `#96a6b8` |
| 57 | Switzerland / Grindelwald | `0x00` | `445` | day | `#747395` | `#9292ae` | `#a9a9ba` |
| 58 | Switzerland / Lucerne | `0x10` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 59 | Switzerland / Zurich | `0x65` | `667` | snow | `#b8b8e3` | `#ceceff` | `#e4e4ff` |
| 60 | U.S.A. / Las Vegas | `0x10` | `001` | night | `#00000e` | `#000031` | `#0e1d40` |
| 61 | U.S.A. / Los Angeles | `0x00` | `046` | day | `#0c73a1` | `#0092ce` | `#6aa5c9` |
| 62 | U.S.A. / New York | `0x64` | `337` | snow | `#6565dc` | `#7777ff` | `#8f96e6` |
| 63 | U.S.A. / San Francisco | `0x0A` | `444` | fog | `#878787` | `#929292` | `#929292` |

## Implementation and results

Implementation commits on `vittau/sky-gradients`: `b0f46b7` (renderer,
option and colour checker), `f2fd249` (clipped split skies, black fades,
HUD priority and the owner's final **SKY GRADIENTS / ON / OFF** wording).
The completion commit records the final split-boundary guard and evidence.
No engine patch, generated-C edit, CI, tag or release was made.

`game/tg2_sky.c` records a compact per-row sky mask, live CRAM and atlas row.
The native mask uses the captured compositor's actual priority inputs; margin
and relocated-HUD writes maintain the same ownership. Only winning B index
63 / sky backdrop texels in the panorama domain qualify. A colour comparison
is an extra guard, never the source classifier. The N× pass paints at output
resolution before native-art filtering and promoted actors; the filter treats
sky as underlay. The ordinary Off path has no raster capture or sky painting.

The leading atlas-448 run defines the moving band. It never searches beyond
the first panorama/road row into a later split raster setup. Each split half
owns its own top and bottom; when the short camera already starts inside the
panorama, visible sky holes use the horizon stop (a clipped, zero-height band).
The blanked first window band is excluded from split player 1's top. No
horizon smoothing or ordered dither is used. A completely black palette
retains completely black output; intermediate fades use the live rule.

The approved reference colours are reproduced exactly by the production
colour code for **all 64 tracks**. Gamut reduction uses a `1e-4` linear-sRGB
boundary tolerance to reproduce those references (strict zero changes the
night top by four channel codes). Hue and all approved rule coefficients
are unchanged.

### Commands and exit codes

All builds/heavy runs used `flock ~/.cache/tg2-heavy.lock`; builds used at most
three jobs. The host was macOS arm64; `build-linux.sh` is the existing portable
development build entry point. All runtime captures used SDL dummy, one
owned process at a time, ports 4740–4743.

| Check | Command / evidence | Final exit |
|---|---|---:|
| Build | `flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh`; `build/task42/final-build.log` | 0 |
| Existing golden | `flock ~/.cache/tg2-heavy.lock /opt/homebrew/bin/python3.14 tools/regression.py --uncapped --out build/task42/regression`; `regression.log` | 0 |
| Main identity | `build/sky-venv/bin/python build/task42/compare-main.py`; `main-comparison/result.json` | 0 |
| 64 colour references | `build/sky-venv/bin/python tools/check_gradient_colours.py`; `colours/result.json` | 0 |
| Nine class captures | `build/sky-venv/bin/python tools/verify_gradient_skies.py`; `classes/summary.json`, `classes-final.log` | 0 |
| Aspect / N× / 60 fps / HUD / uncropped / linear | `build/task42/variants.py`; `variants/summary.json` | 0 |
| Live toggle and persistence | `build/task42/live-options.py`; `live-options-qualified.log` | 0 |
| Split cameras | `build/task42/split-detail.py`, `split-both.py`; `split-final.log` | 0 |
| Tunnel pairs | `build/task42/tunnel-pairs.py`; `tunnel-pairs/summary.json` | 0 |
| Hill/tunnel drive | `build/task42/tunnel-drive.py`; `tunnel-drive/summary.json` | 0 |
| Lightning / pause | `build/task42/extra-scenes.py`; `weather-motion/summary.json` | 0 |
| Fade-in | `build/task42/fade.py`; `fade/samples.json` | 0 |
| N× temporal stability / UI | `build/task42/steady-and-ui.py`; `steady/samples.json`, `option-ui/mods.png` | 0 |
| Non-race On identity | `build/task42/nonrace.py`; `nonrace/result.json` | 0 |

Private capture/replay scripts and all images/states remain under ignored
`build/task42/`. The two reusable checkers are committed under `tools/`.
During harness development an early measurement-mode quit returned 2 because
its requested frame budget was incomplete, one split launch combined mutually
exclusive frame-limit switches, and temporary checker/summary setup errors
returned 1. Those harness faults were corrected and the final checks above
were rerun successfully; no failed game/manifests/golden check was waived.

### Off and non-race identity

The preserved baseline executable was built before editing from main
`d49435743d34b4b610f507a57ef1eb41a5aa04c3` and is under
`build/task42/baseline/`. With SKY GRADIENTS Off, **89/89** sampled frame hashes
match main with presentation options Off, and **89/89** with the normal
16:9 / overscan / 60-fps presentation options On. Stock frames 60 and 300
remain `2A0B972960C5E325` and `1131D937D70234FD`. The complete existing
regression passes all frame/WAV/SOUND-page hashes and load-state audio checks;
no golden was re-recorded. With SKY GRADIENTS On, **43/43** pre-race hashes
(boot, menus, setup and intro) also match main.

### Colour captures at 1×

These are measured modal sky RGB values from the actual screenshot rows,
not just calculated stop values. Quantising the 60% row gives at most **one**
channel code of error; the standalone 64-track production-code check has
**zero** error against every approved reference.

| Track | Class | Measured top / 60% / horizon | Max channel error | Capture under `build/task42/classes/` |
|---|---|---|---:|---|
| Auckland (0) | day | `8f8eb5 / aeaece / c5c6d9` | 0 | `day-auckland/on.png` |
| Canterbury Plains (2) | night | `00000e / 000031 / 0e1d40` | 0 | `night-canterbury/on.png` |
| Las Vegas (60) | night | `00000e / 000031 / 0e1d40` | 0 | `night-vegas/on.png` |
| Paris (19) | nightrain | `000013 / 000031 / 061435` | 0 | `nightrain-paris/on.png` |
| Bavaria (20) | rain | `4677a8 / 5892ce / 79a1cb` | 1 | `rain-bavaria/on.png` |
| Sydney (3) | rain/storm | `5d5d5d / 777777 / 868686` | 0 | `storm-sydney/on.png` |
| Munich (23) | snow | `4b97b3 / 57aece / 8dbcd0` | 0 | `snow-munich/on.png` |
| Loch Ness (4) | fog | `878787 / 929292 / 929292` | 0 | `fog-lochness/on.png` |
| Galway (33) | overcast | `989898 / aeaeae / bebebe` | 0 | `overcast-galway/on.png` |

Every class has live CRAM equal to its descriptor base in the selected stock
capture, a nonempty source-qualified sky mask, and zero execution misses.
The source mask is based on plane B / backdrop index 63, so equal-coloured
HUD/weather/sprite pixels cannot qualify. `tg2_video {"rows":1}` also exports
`sky_rows` as `[atlas_y, live_cram63, visible_sky_count]` for each presented row.

### Other visible evidence

- Contact sheets: **`build/task42/contact/classes.png`** and
  **`build/task42/contact/overcast-lightning.png`**; one labelled PNG per
  captured class/track lives beside them. Images are deliberately uncommitted.
- Widescreen/N×: `variants/21x9/shot.png` (467×200),
  `scale2/shot.png` (712×400), `scale4/shot.png` (1424×800),
  `scale4-60fps/shot.png` (1868×800). In the same top-sky sample region,
  1× has 62 distinct row colours, 2× 93, and 4× 115: N× evaluates sub-rows
  directly rather than expanding 1× bands. Linear On and HUD Edges are also
  captured. Eight 4× / 60-fps pictures spanning phases 0/1 and 1/2 have
  identical sky samples whenever horizon/palette match (`steady/samples.json`).
- Hills: the closed-loop Auckland drive records both slope signs and leading
  sky-band bottoms from 38 through 110 (`tunnel-drive/summary.json` and its
  `f*.png` images). Exact-frame hill pairs at 5100/5135/5140 are under
  `hill-tunnel/{0,1}/`; changed pixels all come from the original sky RGB
  `(174,174,206)`, with silhouettes/HUD/road untouched.
- Tunnel: `tunnel-drive/tunnel.png` is inside the real black plane-A tunnel.
  Replayed exact-frame pairs under `tunnel-pairs/{16x9,21x9}-{0,1}/shot.png`
  change 5108 sky pixels in each width, exclusively from original sky RGB;
  **every black wall pixel remains identical**. The earlier baseline-route
  frames named 8112–8200 were not tunnel frames because that route released
  throttle at 5200; the closed-loop drive provides the actual tunnel evidence.
- Split: `contact/split-player1.png` shows player 1's nonempty leading sky band;
  `contact/split-player2.png` captures the lower camera's nonempty band while both
  pads drive. Other short-camera views begin inside the panorama and use
  the clipped horizon stop. Each half has its own recorded band; the stock
  split layout and native resolution remain intact.
- Lightning: `weather-motion/flash-*.png` captures Sydney with CRAM 63
  changing from stock `0x666` to `0xCCC` and back; the class stays rain.
  Paris also produced a real flash (`classes/nightrain-paris/flash.png`,
  `flash.json`) while its class stayed nightrain. No palette-4 assumption.
- Fade/pause: `fade/` captures a completely black race palette with zero
  gradient pixels, then live `0x666`, then stock `0xCAA` during Auckland's
  fade-in. `weather-motion/pause.png` and its JSON retain the live race ramp
  and weather ordering while paused.
- Option: `option-ui/mods.png` shows **SKY GRADIENTS — OFF** with the other
  presentation mods. Both live directions match fixed-setting captures
  exactly after toggling, and both values are persisted in settings.ini.
  The launcher uses the same registry label/status and existing Mods provider.

### Verification limits

This is local macOS arm64 headless evidence, not release/device qualification.
Owner visual/play acceptance, Windows/Linux/Deck/Intel-macOS playtests and
launcher visual inspection remain outstanding. Results/shop have the existing
race-picture eligibility guard and no new drawing path; their complete
post-finish flow was not replayed separately in this task. No screenshots,
ROMs, states, generated code or audio were committed.
