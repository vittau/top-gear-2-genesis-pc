/*
 * tg2_highres.c — high-resolution rendering S1/S2 (docs/HIGHRES.md §7).
 *
 * S1  compact per-row capture of the picture's presentation state, paid for
 *     only when the render scale is above 1 (TG2_HIGHRES_SCALE for tests);
 * S2  the presented-height builder seam plus a temporary synthetic provider
 *     that presents 2x the native height so the seam can be verified without
 *     any road/sprite/HUD work yet.
 *
 * Everything here is presentation only: it reads the live VDP snapshot the row
 * renderer already owns and writes host pixels. No guest RAM, VRAM, CRAM, CPU,
 * SAT or scheduling state is touched.
 */
#include "tg2_highres.h"

#include "video/genesis_vdp.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)
#include <windows.h>
static double highres_now_us(void) {
    static LARGE_INTEGER freq;
    LARGE_INTEGER t;
    if (!freq.QuadPart) QueryPerformanceFrequency(&freq);
    QueryPerformanceCounter(&t);
    return (double)t.QuadPart * 1e6 / (double)freq.QuadPart;
}
#else
#include <time.h>
static double highres_now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1e6 + (double)ts.tv_nsec / 1e3;
}
#endif

/* ── Render scale (the one place the port reads it) ──────────────────────── */

int tg2_highres_scale(void) {
    /* Row work calls this; resolve once instead of on every row. */
    static int resolved, scale = 1;
    if (!resolved) {
        resolved = 1;
        int requested = 1; /* S7: g_app_config.internal_scale (decision 4) */
        const char *env = getenv("TG2_HIGHRES_SCALE");
        if (env && *env) requested = atoi(env);
        if (requested >= 1 && requested <= TG2_HIGHRES_MAX_SCALE) scale = requested;
        if (scale > 1)
            fprintf(stderr, "[tg2] high-res: render scale %dx (presentation only)\n", scale);
    }
    return scale;
}

/* ── Compact per-row capture (S1) ────────────────────────────────────────── */

static Tg2RowState s_rows[TG2_HIGHRES_ROWS];
static unsigned short s_row_serial[TG2_HIGHRES_ROWS];
static unsigned s_serial;
static unsigned s_capture_frames, s_capture_rows;
static int s_timing = -1;
static double s_capture_us, s_clock_overhead;

static int capture_timing(void) {
    if (s_timing < 0) {
        const char *env = getenv("TG2_HIGHRES_TIMING");
        s_timing = env && *env && env[0] != '0';
        if (s_timing) {
            /* Subtract the two clock reads a row measurement costs, so the
             * reported capture time is the capture work, not the timer. */
            double best = 1e9;
            for (int i = 0; i < 1000; ++i) {
                double a = highres_now_us();
                double b = highres_now_us();
                if (b - a < best) best = b - a;
            }
            s_clock_overhead = best;
        }
    }
    return s_timing;
}

/* Plane B samples. The atlas rules (road texels, palette banks) are the ones
 * docs/HIGHRES.md §1.4 measured and tg2_video.c draws; this file only needs
 * the per-row classification and the road's palette bank, never a full strip. */
static int tile_count(int n) { return n == 1 ? 64 : n == 3 ? 128 : 32; }

static unsigned plane_word(const GVDP *v, unsigned address) {
    return (v->vram[address & 65535] << 8) | v->vram[(address + 1) & 65535];
}

static unsigned plane_pixel(const GVDP *v, unsigned base, int x, int y,
                            unsigned *attr) {
    int wt = tile_count(v->reg[16] & 3), ht = tile_count((v->reg[16] >> 4) & 3);
    unsigned a = plane_word(v, base +
        (((y >> 3) & (ht - 1)) * wt + ((x >> 3) & (wt - 1))) * 2);
    unsigned px = x & 7, py = y & 7;
    if (a & 0x800) px ^= 7;
    if (a & 0x1000) py ^= 7;
    unsigned b = v->vram[((a & 2047) * 32 + py * 4 + px / 2) & 65535];
    unsigned c = px & 1 ? b & 15 : b >> 4;
    *attr = a;
    return c;
}

/* Road silhouette palette nibbles, measured in docs/HIGHRES.md §1.4:
 * 6 = border, 13 = lane mark, 14 = asphalt. */
static int road_texel(unsigned nibble) {
    return nibble == 6 || nibble == 13 || nibble == 14;
}

/* Palette-bank bit (tile attribute bit 13) of the outermost road texel found
 * walking out from the atlas seam. The road always covers the seam, so 0 is a
 * valid probe start; a row whose seam texel is not road keeps bank 0. */
static unsigned edge_bank(const GVDP *v, unsigned base, int py, int step) {
    unsigned attr;
    unsigned nibble = plane_pixel(v, base, 0, py, &attr);
    if (!road_texel(nibble))
        return 0;
    unsigned bank = (attr >> 13) & 1;
    for (int x = step; x > -256 && x < 256; x += step) {
        nibble = plane_pixel(v, base, x, py, &attr);
        if (!road_texel(nibble))
            break;
        bank = (attr >> 13) & 1; /* nearest to the edge */
    }
    return bank;
}

void tg2_highres_reset(void) {
    memset(s_rows, 0, sizeof s_rows);
    memset(s_row_serial, 0, sizeof s_row_serial);
    s_serial = 0;
    s_capture_frames = s_capture_rows = 0;
    s_capture_us = 0;
}

void tg2_highres_picture_start(void) {
    if (tg2_highres_scale() <= 1)
        return;
    ++s_capture_frames;
    ++s_serial;
    s_capture_rows = 0;
    s_capture_us = 0;
}

void tg2_highres_capture_row(const GVDP *v, int line, int ha, int hb) {
    if (!v || line < 0 || line >= TG2_HIGHRES_ROWS || tg2_highres_scale() <= 1)
        return;
    int timing = capture_timing();
    double started = timing ? highres_now_us() : 0;
    s_row_serial[line] = (unsigned short)s_serial;
    Tg2RowState *r = &s_rows[line];
    memcpy(r->reg, v->reg, sizeof r->reg);
    r->vsram[0] = v->vsram[0] & 1023;
    r->vsram[1] = v->vsram[1] & 1023;
    memcpy(r->cram, v->cram, sizeof r->cram);
    r->hscroll[0] = (unsigned short)(ha & 1023);
    r->hscroll[1] = (unsigned short)(hb & 1023);

    int py = (line + r->vsram[1]) & 511;
    unsigned char flags = 0;
    short k = -1;
    if (py < 288) {                       /* templates 1/2: width 4 + 2k   */
        k = (short)(py < 144 ? py : py - 144);
        flags |= TG2_ROW_ROAD;
    } else if (py < 432) {                /* templates 3/4: wider ramp     */
        k = (short)(py < 360 ? py - 288 : py - 360);
        flags |= TG2_ROW_ROAD;
    } else if (py < 448) {
        flags |= TG2_ROW_GROUND;
    } else {
        flags |= TG2_ROW_PANORAMA;
    }
    if (flags & TG2_ROW_ROAD) {
        /* The second member of each authored pair carries the palette-bank
         * bit (lane-mark phase). Both probes read the live name table. */
        unsigned base = (v->reg[4] & 7) << 13;
        r->bank[0] = (unsigned char)edge_bank(v, base, py, -1);
        r->bank[1] = (unsigned char)edge_bank(v, base, py, 1);
        if (r->bank[0])
            flags |= TG2_ROW_BANK1;
    } else {
        r->bank[0] = r->bank[1] = 0;
    }
    if (((v->reg[18] & 128) ? line >= (v->reg[18] & 31) * 8
                            : line < (v->reg[18] & 31) * 8))
        flags |= TG2_ROW_WINDOW;
    r->width_k = k;
    r->flags = flags;
    ++s_capture_rows;
    if (timing) {
        double elapsed = highres_now_us() - started - s_clock_overhead;
        if (elapsed > 0) s_capture_us += elapsed;
    }
}

const Tg2RowState *tg2_highres_rows(void) { return s_rows; }
unsigned tg2_highres_serial(void) { return s_serial; }
const unsigned short *tg2_highres_row_serial(void) { return s_row_serial; }
unsigned tg2_highres_capture_frames(void) { return s_capture_frames; }
double tg2_highres_capture_us(void) { return s_capture_us; }
unsigned tg2_highres_capture_rows_done(void) { return s_capture_rows; }

/* ── Presented-picture builder (S2) ──────────────────────────────────────── */

int tg2_highres_test_provider(void) {
    static int enabled = -1;
    if (enabled < 0) {
        const char *env = getenv("TG2_HIGHRES_TEST_PROVIDER");
        enabled = env && *env && env[0] != '0';
        if (enabled)
            fprintf(stderr, "[tg2] high-res: SYNTHETIC test provider on "
                            "(2x native height; tests only)\n");
    }
    return enabled;
}

int tg2_highres_present_scale(void) {
    int scale = tg2_highres_scale();
    if (scale <= 1)
        return 1;
    /* Until S3's road/background builder lands, the only thing that presents
     * a taller picture is the temporary test provider; everything else must
     * keep the stock canvas even when the scale is raised for testing. */
    return tg2_highres_test_provider() ? scale : 1;
}

/* Every row is distinct and every column changes with x, so a truncated,
 * reordered or squashed picture is obvious in a screenshot. */
static void paint_test_pattern(uint32_t *pixels, int stride, int width, int height) {
    for (int y = 0; y < height; ++y) {
        uint32_t *row = pixels + (size_t)y * stride;
        int band = (y / 16) & 1;
        for (int x = 0; x < width; ++x) {
            unsigned r = (unsigned)(255 * x / (width > 1 ? width - 1 : 1));
            unsigned g = (unsigned)(255 * y / (height > 1 ? height - 1 : 1));
            unsigned b = band ? 0x30u : 0xD0u;
            if (((x >> 3) ^ (y >> 3)) & 1)
                b ^= 0x80u;
            row[x] = 0xFF000000u | (r << 16) | (g << 8) | b;
        }
        row[y % width] = 0xFFFFFFFFu;              /* diagonal marker */
        if (y % 32 == 0)
            for (int x = 0; x < width; ++x) row[x] = 0xFF00FFFFu; /* row ruler */
        row[0] = 0xFFFF00FFu;
        row[width - 1] = 0xFFFF00FFu;
    }
}

int tg2_highres_build(uint32_t *pixels, int stride, int width,
                      int native_w, int native_h) {
    (void)native_w;
    if (tg2_highres_present_scale() <= 1 || !pixels || width <= 0 || stride < width)
        return 0;
    if (tg2_highres_test_provider()) {
        int height = native_h * 2;
        paint_test_pattern(pixels, stride, width, height);
        return height;
    }
    /* S1/stock: the builder owns no Nx geometry yet (that is S3), so the
     * picture keeps the native rows the row renderer produced. The native
     * height and every option-off hash stay exactly as before. */
    return 0;
}
