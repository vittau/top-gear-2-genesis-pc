# Weather across the race viewport

The USA ROM installs weather through `$002B20..$002BEC`. Bit 5 of
track descriptor byte 3 enables it; bit 6 selects the variant. The code
unpacks the map from `$0C9996`, adds high priority (`$8000`) plus the
allocated pattern index, and writes it into plane A at `$C800` and `$C840`.
These are the two 256-pixel halves of the 512-pixel name table, starting
at atlas Y=128. Non-weather scene initialization fills the table with
transparent pattern 2 (`$002A52..$002A6A`).

`$0068C8/$006912/$006956` call `$0087FC/$0087EA` when weather is enabled
(RAM `$FF2418`). `$00880C..$00887A` generates its horizontal and vertical
scroll records, with a 256-line vertical wrap. Thus the streaks are plane A
texels animated by the raster program, rather than SAT sprites.

Previously the widescreen renderer continued plane B and captured objects,
while plane A only continued a solid eight-pixel edge run for tunnel walls.
The earlier weather-smear fix correctly prevented isolated particles from
turning into horizontal lines, but did not draw weather in the margins.

`weather_pixel()` now samples the actual plane A weather atlas (Y=128..383)
at the unwrapped output X using that scanline's original H/V scroll and
palette. High-priority weather beats low-priority sprites; high-priority
sprites keep their native ordering. The native centre is copied unchanged.
No guest state, pattern data, simulation, or engine code is modified.
The 60 fps path uses the same discrete source picture for weather and the
native centre, so weather timing also follows the existing synthesis policy.

Validation evidence is recorded below after running the probes.
