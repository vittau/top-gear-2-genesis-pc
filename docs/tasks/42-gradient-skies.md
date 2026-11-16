# Task 42 — Gradient skies

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
| fog | bit 3 | -0.035 | 1.00 | +0.025 | 1.00 |
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
| 4 | Britain / Loch Ness | `0x08` | `444` | fog | `#878787` | `#929292` | `#9a9a9a` |
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
| 22 | Germany / Frankfurt | `0x08` | `444` | fog | `#878787` | `#929292` | `#9a9a9a` |
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
| 47 | Scandinavia / Stockholm | `0x09` | `444` | fog | `#878787` | `#929292` | `#9a9a9a` |
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
| 63 | U.S.A. / San Francisco | `0x0A` | `444` | fog | `#878787` | `#929292` | `#9a9a9a` |

## Implementation and results

Validation in progress. Evidence will be recorded here before completion.
