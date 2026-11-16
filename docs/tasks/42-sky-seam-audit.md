# Task 42 — fog horizon correction and 64-track seam audit

The owner approved a fog-only correction: the top remains `L − 0.035, C × 1`,
the original colour stays at 60%, and the horizon now uses **`dLh = 0, kh = 1`**.
All four fog references therefore end at **`#929292`**, joining the original
flat grey scene. No coefficient, reference colour or renderer behaviour for
another class was changed.

Implementation commit: `465fefc` on `vittau/sky-gradients`; the completion
commit adds the audit tool, table and evidence. The task's approved reference
table and `tools/check_gradient_colours.py` both enforce the new fog horizon.

**Other tracks flagged:** 41 (Japan / Kyoto), 58 (Switzerland / Lucerne)

## Method

`tools/audit_sky_seams.py` boots each track through the real password/setup
flow in its own native process; later slots use the existing documented
setup-only selector. Every selected capture is **1×, 16:9, 60 fps Off, zero
player slope, live CRAM 63 equal to the descriptor's base sky**. Controller
input seeks a flat section before capture. Descriptor and class are checked
against the ROM/reference table; no race-time RAM or palette writes occur.

The same command batch captures a screenshot, presented row states, sky
ownership counts, VRAM and CRAM. The checker decodes actual plane-B texels,
including the native wrap and margin clamp, and only counts an opaque
non-sky texel when its palette colour and displayed screenshot pixel both
equal the original sky RGB. This prevents equal-coloured sky texels or
weather from being mistaken for flat scene artwork.

The audit examines rows after the pinned sky band with a visible gradient
row directly above. A structural join means **more than half the whole
356-pixel viewport** below that row is opaque non-sky original colour.
A threshold candidate is flagged when the approved horizon differs by more than two channel
codes. The table retains the strongest matching transition even below the
majority threshold, so negative results have measurable evidence.

The first non-sky scene row may be panorama, ground or road at a raster atlas
jump. The fog emitter makes its first road rows flat grey too; restricting the
check to atlas Y ≥ 448 would miss the reported fog defect. For example, Loch
Ness's selected flat capture joins at native row 165
(atlas Y 177, road).
The gradient and the original-grey part of that row now both equal 146 in
every channel. Image Y is native Y minus the eight cropped overscan rows.

## Full audit table

`Original below` is the percentage of the full viewport meeting both source
and screenshot checks; `sky above` is the number of visible gradient pixels
on the immediately preceding row. `Δ RGB` is the maximum channel difference
between the horizon stop and the original sky. All slopes are zero.

| Idx | Country / track | Class | Native row / atlas Y | Original below | Sky above | Δ RGB | Result |
|---:|---|---|---|---:|---:|---:|---|
| 0 | Australasia / Auckland | day | 94 / 449 (panorama) | 0.00% | 344 | 24 | Clear |
| 1 | Australasia / Ayers Rock | day | 90 / 449 (panorama) | 0.00% | 323 | 32 | Clear |
| 2 | Australasia / Canterbury Plains | night | 139 / 499 (panorama) | 27.53% | 236 | 29 | Clear |
| 3 | Australasia / Sydney | rain | 156 / 160 (road) | 3.09% | 32 | 15 | Clear |
| 4 | Britain / Loch Ness | fog | 165 / 177 (road) | 69.66% | 320 | 0 | Fog joined |
| 5 | Britain / London | day | 94 / 449 (panorama) | 0.00% | 346 | 31 | Clear |
| 6 | Britain / Sheffield | day | 96 / 449 (panorama) | 0.00% | 356 | 31 | Clear |
| 7 | Britain / Stonehenge | day | 82 / 449 (panorama) | 0.00% | 292 | 52 | Clear |
| 8 | Canada / Banff | day | 97 / 449 (panorama) | 0.00% | 356 | 26 | Clear |
| 9 | Canada / Niagara | rain | 94 / 449 (panorama) | 0.00% | 340 | 27 | Clear |
| 10 | Canada / Toronto | day | 95 / 449 (panorama) | 0.00% | 356 | 32 | Clear |
| 11 | Canada / Vancouver | night | 108 / 449 (panorama) | 0.00% | 356 | 29 | Clear |
| 12 | Egypt / Abu Simbel | day | 94 / 449 (panorama) | 0.00% | 344 | 24 | Clear |
| 13 | Egypt / Aswan | day | 94 / 449 (panorama) | 0.00% | 344 | 23 | Clear |
| 14 | Egypt / Cairo | night | 135 / 490 (panorama) | 1.97% | 50 | 29 | Clear |
| 15 | Egypt / Hush Sitton | day | 94 / 449 (panorama) | 0.00% | 344 | 24 | Clear |
| 16 | France / Bordeaux | day | 101 / 449 (panorama) | 0.00% | 356 | 31 | Clear |
| 17 | France / Monaco | night | 94 / 449 (panorama) | 0.00% | 346 | 29 | Clear |
| 18 | France / Nice | day | 94 / 449 (panorama) | 0.00% | 344 | 106 | Clear |
| 19 | France / Paris | nightrain | 95 / 449 (panorama) | 0.00% | 341 | 20 | Clear |
| 20 | Germany / Bavaria | rain | 94 / 449 (panorama) | 0.00% | 335 | 34 | Clear |
| 21 | Germany / Cologne | day | 113 / 449 (panorama) | 0.00% | 356 | 32 | Clear |
| 22 | Germany / Frankfurt | fog | 152 / 291 (road) | 98.03% | 339 | 0 | Fog joined |
| 23 | Germany / Munich | snow | 94 / 449 (panorama) | 0.00% | 338 | 54 | Clear |
| 24 | Greece / Athens | night | 99 / 449 (panorama) | 0.00% | 356 | 29 | Clear |
| 25 | Greece / Meteora | day | 98 / 449 (panorama) | 0.00% | 356 | 23 | Clear |
| 26 | Greece / Mykanos | day | 107 / 449 (panorama) | 0.00% | 356 | 31 | Clear |
| 27 | Greece / Santorini | day | 105 / 449 (panorama) | 0.00% | 356 | 23 | Clear |
| 28 | India / Amber Port | day | 94 / 449 (panorama) | 0.00% | 344 | 32 | Clear |
| 29 | India / Bombay | day | 93 / 449 (panorama) | 0.00% | 341 | 31 | Clear |
| 30 | India / Delhi | day | 95 / 449 (panorama) | 0.00% | 356 | 24 | Clear |
| 31 | India / Taj Mahal | day | 94 / 449 (panorama) | 0.00% | 344 | 23 | Clear |
| 32 | Ireland / Dublin | day | 102 / 449 (panorama) | 0.00% | 356 | 31 | Clear |
| 33 | Ireland / Galway | overcast | 97 / 449 (panorama) | 0.00% | 356 | 16 | Clear |
| 34 | Ireland / Killarney | rain | 85 / 449 (panorama) | 0.00% | 287 | 16 | Clear |
| 35 | Ireland / Limerick | day | 97 / 449 (panorama) | 0.00% | 356 | 25 | Clear |
| 36 | Italy / Florence | day | 97 / 449 (panorama) | 0.00% | 356 | 38 | Clear |
| 37 | Italy / Pisa | day | 106 / 449 (panorama) | 0.00% | 356 | 106 | Clear |
| 38 | Italy / Rome | night | 94 / 449 (panorama) | 0.00% | 344 | 29 | Clear |
| 39 | Italy / Sicily | day | 94 / 449 (panorama) | 0.00% | 344 | 31 | Clear |
| 40 | Japan / Hiroshima | day | 94 / 449 (panorama) | 0.00% | 344 | 89 | Clear |
| 41 | Japan / Kyoto | night | 151 / 501 (panorama) | 51.97% | 8 | 29 | **FLAG candidate — unchanged** |
| 42 | Japan / Tokyo | day | 99 / 449 (panorama) | 0.00% | 356 | 34 | Clear |
| 43 | Japan / Yokohama | day | 94 / 449 (panorama) | 0.00% | 344 | 35 | Clear |
| 44 | Scandinavia / Copenhagen | day | 94 / 449 (panorama) | 0.00% | 344 | 24 | Clear |
| 45 | Scandinavia / Helsinki | snow | 101 / 449 (panorama) | 0.00% | 346 | 29 | Clear |
| 46 | Scandinavia / Reykjavik | snow | 94 / 449 (panorama) | 0.00% | 330 | 39 | Clear |
| 47 | Scandinavia / Stockholm | fog | 152 / 291 (road) | 92.13% | 348 | 0 | Fog joined |
| 48 | South America / Chile | day | 97 / 449 (panorama) | 0.00% | 356 | 31 | Clear |
| 49 | South America / Mexico | day | 104 / 449 (panorama) | 0.00% | 356 | 38 | Clear |
| 50 | South America / Peru | day | 101 / 449 (panorama) | 0.00% | 356 | 30 | Clear |
| 51 | South America / Brazil | night | 97 / 449 (panorama) | 0.00% | 356 | 29 | Clear |
| 52 | Spain / Andalusia | overcast | 94 / 449 (panorama) | 0.00% | 344 | 16 | Clear |
| 53 | Spain / Barcelona | night | 94 / 449 (panorama) | 0.00% | 344 | 29 | Clear |
| 54 | Spain / Madrid | rain | 110 / 449 (panorama) | 0.00% | 344 | 23 | Clear |
| 55 | Spain / Seville | day | 107 / 449 (panorama) | 0.00% | 356 | 23 | Clear |
| 56 | Switzerland / Geneva | day | 117 / 449 (panorama) | 0.00% | 350 | 31 | Clear |
| 57 | Switzerland / Grindelwald | day | 94 / 449 (panorama) | 0.00% | 344 | 23 | Clear |
| 58 | Switzerland / Lucerne | night | 152 / 509 (panorama) | 51.69% | 1 | 29 | **FLAG candidate — unchanged** |
| 59 | Switzerland / Zurich | snow | 101 / 449 (panorama) | 0.00% | 350 | 22 | Clear |
| 60 | U.S.A. / Las Vegas | night | 134 / 489 (panorama) | 9.27% | 17 | 29 | Clear |
| 61 | U.S.A. / Los Angeles | day | 101 / 449 (panorama) | 0.00% | 356 | 106 | Clear |
| 62 | U.S.A. / New York | snow | 94 / 449 (panorama) | 0.00% | 332 | 31 | Clear |
| 63 | U.S.A. / San Francisco | fog | 152 / 291 (road) | 85.39% | 296 | 0 | Fog joined |

## Other-track candidate evidence

- **41 — Japan / Kyoto**: row 151 / atlas 501, 185/356 (51.97%) opaque original-colour pixels below, 8/356 gradient pixels above; original `[0, 0, 49]`, horizon `[14, 29, 64]`, maximum channel difference 29. Capture: `build/task42/seam-audit/41/on.png`; source counts and every tested transition are in its `audit.json`. The rule and reference remain unchanged.
- **58 — Switzerland / Lucerne**: row 152 / atlas 509, 184/356 (51.69%) opaque original-colour pixels below, 1/356 gradient pixels above; original `[0, 0, 49]`, horizon `[14, 29, 64]`, maximum channel difference 29. Capture: `build/task42/seam-audit/58/on.png`; source counts and every tested transition are in its `audit.json`. The rule and reference remain unchanged.

The detector deliberately retains candidates even when very little gradient
remains above a mostly opaque skyline. Such a candidate is a local sky-hole
join, not evidence of a full-width fog-like band; the explicit sky-above count
and the image distinguish these cases. The owner decides whether to change it.

## Validation and images

All heavy commands used the machine-wide lock and builds used at most three
jobs. The host is macOS arm64; the native development build and all runtimes
used SDL dummy and ports 4740–4742. No CI, tag or release was triggered.

| Check | Command / evidence | Exit |
|---|---|---:|
| Build | `flock ~/.cache/tg2-heavy.lock env JOBS=3 tools/build-linux.sh`; `build/task42/fog-build.log` | 0 |
| Updated colours | `flock ~/.cache/tg2-heavy.lock build/sky-venv/bin/python tools/check_gradient_colours.py --out build/task42/fog-fix/colour-check`; **64/64 exact**, max RGB error 0 | 0 |
| 64 captures | `flock ~/.cache/tg2-heavy.lock build/sky-venv/bin/python tools/audit_sky_seams.py`; `build/task42/seam-audit.log` | 0 |
| Final source audit | same command with `--analyse-only`; `build/task42/fog-fix/seam-analysis.log`, `seam-audit/summary.json` | 0 |
| Off identity spot | `build/task42/fog-fix/off-spot.py` under the lock; `fog-fix/off-identity/result.json` | 0 |

The Off spot check matches **75/75** framebuffer hashes against the preserved
main executable (`d494357`), including boot/menu and race pictures; frame 60
remains `2A0B972960C5E325`, frame 300 `1131D937D70234FD`. No golden was changed.
All four execution manifests are empty for **each of the 64 audit runs** and
the Off spot check: dispatch misses, floor coverage, interior-label misses and
unsafe floor entries all have zero entries.

Fog captures, each with zero slope and horizon RGB **(146,146,146)**:
`build/task42/seam-audit/{04,22,47,63}/on.png` (Loch Ness, Frankfurt,
Stockholm, San Francisco). Each directory contains the full row/CRAM data,
private VRAM dump and source-count audit. The measured top / 60% / horizon
are **`#878787 / #929292 / #929292`** in all four selected screenshots.

Updated contact sheets (private, not committed):

- **`build/task42/contact/classes.png`** — original class overview with the
  corrected fog capture; other class captures remain unchanged.
- **`build/task42/fog-fix/fog-contact.png`** — all four corrected fog tracks.
- **`build/task42/fog-fix/all-64-contact.png`** — all 64 audited captures.
- **`build/task42/fog-fix/flagged-contact.png`** — Kyoto and Lucerne, unchanged;
  `candidate-41.png` and `candidate-58.png` add boundary-row pixel strips.
- `build/task42/fog-fix/before-after.png` — previous Loch Ness capture and a
  new replay from its saved race state (separate presented frames).

Harness development first hit the TCP VRAM-read size limit, then confirmed
that a setup-screen save is parked until a resumable race boundary and cannot
be reused to select another race. Those preliminary harness attempts failed
and were discarded. The final 64 captures use fresh boots and `dump_vram`,
and every final check above completed successfully.

This is a one-frame-per-track, flat-camera, stock-palette seam audit. It does
not assert absence of every possible join on hills, during flashes/fades or
on other devices. Other classes were only audited; any future colour change
still belongs to the owner.
