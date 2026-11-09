/*
 * tg2_highres.h — high-resolution rendering (docs/HIGHRES.md §7).
 *
 * The guest VDP, the raster program, the simulation and the font/tile data
 * stay native. What changes is how this port fills the presented picture and
 * how many rows/columns it has.
 *
 * S1  compact per-row capture of the picture's presentation state, paid for
 *     only when the render scale is above 1.
 * S2  the presented-height seam (engine patch 0033): a provider may compose a
 *     picture taller than the VDP geometry and report its height.
 * S3  the road strip rasteriser: the road rows are redrawn at N x from the
 *     game's own per-line numbers (width, centre, atlas row, palette), with
 *     analytic edges. Everything else (sky, sprites, HUD, plane-A effects)
 *     stays the native picture's content, nearest-scaled by N.
 */
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct GVDP;

/* Presented render scale: 1 = stock, up to 4 (docs/HIGHRES.md §6). The single
 * place the whole port reads the scale from: the engine's "Internal
 * resolution" row (decision 4, GameSpec.internal_scale) or the
 * TG2_HIGHRES_SCALE environment override for automated captures. Cached at
 * first use, so a change applies on the next launch (the row says so). */
#define TG2_HIGHRES_MAX_SCALE 4
int tg2_highres_scale(void);

/* Scale the builder will actually present at: 1 at the stock scale, otherwise
 * the render scale. */
int tg2_highres_present_scale(void);

/* Per-row classification. Values are stable for capture dumps and tools. */
enum {
    TG2_ROW_ROAD     = 1u << 0, /* plane B atlas row is a road template  */
    TG2_ROW_GROUND   = 1u << 1, /* atlas Y 432..447: ground/separator    */
    TG2_ROW_PANORAMA = 1u << 2, /* atlas Y 448..511: skyline/sky         */
    TG2_ROW_WINDOW   = 1u << 3, /* the window plane hides plane A here   */
    TG2_ROW_BANK1    = 1u << 4, /* road palette bank bit (pair second)   */
};

/* Compact per-row presentation state (docs/HIGHRES.md §7.2). Captured only
 * when the render scale is above 1, so the stock path pays nothing, and only
 * for rows of a qualified single-player race picture (the row renderer's
 * race-row branch), which is why there is no separate "race" flag. */
typedef struct Tg2RowState {
    unsigned char reg[24];      /* VDP registers at this line            */
    unsigned short vsram[2];    /* plane A / plane B vertical scroll     */
    unsigned short cram[64];    /* palette at this line (raster changes) */
    unsigned short hscroll[2];  /* plane A / plane B H-scroll, this row  */
    unsigned char bank[2];      /* road palette bank at the left/right edge */
    short left, right;          /* road silhouette in atlas x, road rows */
    short width_k;              /* normalised atlas row used by the road */
    unsigned char flags;        /* TG2_ROW_*                             */
} Tg2RowState;

#define TG2_HIGHRES_ROWS 224

/* Clear every capture buffer and cost counter (reset / state load). */
void tg2_highres_reset(void);

/* Called on the first row of a qualified race picture: a new capture serial
 * starts and the per-picture cost counters reset. */
void tg2_highres_picture_start(void);

/* Called by the row renderer for each row of a qualified race picture, after
 * the row's scroll words were read, when the scale is above 1. */
void tg2_highres_capture_row(const struct GVDP *v, int line, int ha, int hb);

/* Latest captured picture and its bookkeeping, for the TCP dump. The row
 * array is TG2_HIGHRES_ROWS long; `serial` increments on every captured
 * picture and row_serial[line] names the picture the stored row belongs to. */
const Tg2RowState *tg2_highres_rows(void);
unsigned tg2_highres_serial(void);
const unsigned short *tg2_highres_row_serial(void);
unsigned tg2_highres_capture_frames(void);
/* Capture cost accumulated while TG2_HIGHRES_TIMING=1 (0 otherwise), in
 * microseconds, and the number of captured rows it covers. */
double tg2_highres_capture_us(void);
unsigned tg2_highres_capture_rows_done(void);
/* Builder cost: total microseconds and frames, same env gate. */
double tg2_highres_build_us(void);
unsigned tg2_highres_build_frames(void);

/* Build the taller presented picture in place (engine patch 0033 seam).
 * `pixels`/`stride`/`width` describe the runner framebuffer the provider
 * owns; the row renderer has already written the 1x canvas picture into it,
 * nearest-expanded by the scale. Returns the number of complete rows written:
 * > native_h selects that presented height, 0 keeps the stock picture. */
int tg2_highres_build(const struct GVDP *vdp, uint32_t *pixels, int stride,
                      int width, int native_w, int native_h);

#ifdef __cplusplus
}
#endif
