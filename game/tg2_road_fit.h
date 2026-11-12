/* Internal bounded scanline-geometry fit, shared by the N x rasteriser and
 * its numeric qualification. Arrays may have at most 224 rows. Missing
 * observations must lie between two observed endpoints; n < 3 is unchanged. */
#pragma once
#define TG2_ROAD_FIT_ROWS 224
#define TG2_ROAD_FIT_LIMIT 2.0
void tg2_road_fit(const double *raw, const unsigned char *seen, int n, double *out);
