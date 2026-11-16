/* Game-owned, optional sky composition; no guest state writes. */
#pragma once
#include <stdint.h>
#include "video/genesis_vdp.h"
void tg2_video_set_gradient_skies(int on);
int tg2_sky_enabled(void);
void tg2_sky_begin_row(const GVDP *v, int line, int width);
void tg2_sky_native(const GVDP *v, int line, const uint32_t *native,
                    const uint32_t *out, int nw, int width);
extern unsigned char *tg2_sky_mask;
int tg2_sky_source(unsigned index, int atlas_y, unsigned backdrop);
void tg2_sky_paint(uint32_t *pixels, int stride, int width, int scale, int first);
int tg2_sky_pixel(int line, int x);
int tg2_sky_json(char *out, int size);

int tg2_sky_rows_json(char *out, int size);
