/*
 * tg2_highres.h — high-resolution rendering, steps S1/S2 (docs/HIGHRES.md §7).
 *
 * The guest VDP, the raster program, the simulation and the font/tile data
 * stay native. What changes is what this port writes into the presented
 * picture and how many rows it has. Nothing here reads or writes guest state
 * other than the live VDP snapshot the row renderer already owns.
 *
 * S1: compact per-row capture (RowState) and the render-scale skeleton, with
 *     output identical to the stock 1x picture.
 * S2: the presented-picture builder seam (engine patch 0033) plus a temporary
 *     synthetic test provider so the taller picture can be verified without
 *     any road/sprite/HUD work yet.
 */
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct GVDP;

/* Presented render scale: 1 = stock, up to 4 (docs/HIGHRES.md §6). The single
 * place the whole port reads the scale from. Default 1; TG2_HIGHRES_SCALE
 * overrides it for automated captures. The owner chose the engine's
 * "Internal resolution" row as the user-facing control (decision 4), wired in
 * S7: that step replaces the `requested` source below with
 * g_app_config.internal_scale and removes nothing else. */
#define TG2_HIGHRES_MAX_SCALE 4
int tg2_highres_scale(void);

/* Per-row classification. Values are stable for capture dumps and tools. */
enum {
    TG2_ROW_ROAD     = 1u << 0, /* plane B atlas row is a road template  */
    TG2_ROW_GROUND   = 1u << 1, /* atlas Y 432..447: ground/separator    */
    TG2_ROW_PANORAMA = 1u << 2, /* atlas Y 448..511: skyline/sky         */
    TG2_ROW_WINDOW   = 1u << 3, /* the window plane hides plane A here   */
    TG2_ROW_BANK1    = 1u << 4, /* road palette bank bit (pair second)   */
};

/* Compact per-row presentation state (docs/HIGHRES.md §7.2): ~165 bytes per
 * row instead of the 60 fps path's full 64 KiB GVDP copy. Captured only when
 * the render scale is above 1, so the stock 1x path pays nothing, and only for
 * rows of a qualified single-player race picture (the row renderer's race-row
 * branch), which is why there is no separate "race" flag. */
typedef struct Tg2RowState {
    unsigned char reg[24];      /* VDP registers at this line            */
    unsigned short vsram[2];    /* plane A / plane B vertical scroll     */
    unsigned short cram[64];    /* palette at this line (raster changes) */
    unsigned short hscroll[2];  /* plane A / plane B H-scroll, this row  */
    unsigned char bank[2];      /* road palette bank at the left/right edge */
    short width_k;              /* normalised atlas row used by the road */
    unsigned char flags;        /* TG2_ROW_*                             */
} Tg2RowState;

#define TG2_HIGHRES_ROWS 224

/* Clear every capture buffer and cost counter (reset / state load). */
void tg2_highres_reset(void);

/* Called by the row renderer for each row of a qualified race picture, after
 * the row's scroll words were read, when the scale is above 1. */
void tg2_highres_capture_row(const struct GVDP *v, int line, int ha, int hb);

/* Called on the first row of a qualified race picture: a new capture serial
 * starts and the per-picture cost counters reset. */
void tg2_highres_picture_start(void);

/* Latest captured picture and its bookkeeping, for the TCP dump. The row
 * array is TG2_HIGHRES_ROWS long; NULL before the first capture. `serial`
 * increments on every captured picture and row_serial[line] names the picture
 * the stored row belongs to, so a dump can tell a row captured this picture
 * from one left over from an earlier one. */
const Tg2RowState *tg2_highres_rows(void);
unsigned tg2_highres_serial(void);
const unsigned short *tg2_highres_row_serial(void);
unsigned tg2_highres_capture_frames(void);
/* Capture cost accumulated while TG2_HIGHRES_TIMING=1 (0 otherwise), in
 * microseconds, and the number of captured rows it covers. */
double tg2_highres_capture_us(void);
unsigned tg2_highres_capture_rows_done(void);

/* S2 temporary test provider: present a synthetic pattern at 2x the native
 * height so the presented-height seam can be verified before S3 draws real
 * geometry. Off unless the test explicitly sets TG2_HIGHRES_TEST_PROVIDER=1;
 * it must never be enabled by a player-facing path. */
int tg2_highres_test_provider(void);

/* Scale the builder will actually present at: 1 until a real Nx builder
 * exists (S3), then the render scale when it is above 1. The presentation
 * canvas follows this, so a scale above 1 with nothing to draw stays exactly
 * the stock picture. */
int tg2_highres_present_scale(void);

/* Build a taller presented picture in place (engine patch 0033 seam).
 * pixels/stride/width describe the runner framebuffer the provider owns.
 * Returns the number of complete rows written: > native_h selects that
 * presented height, 0 keeps the stock picture. */
int tg2_highres_build(uint32_t *pixels, int stride, int width,
                      int native_w, int native_h);

#ifdef __cplusplus
}
#endif
