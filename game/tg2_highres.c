/*
 * tg2_highres.c — high-resolution rendering (docs/HIGHRES.md §7).
 *
 * S1  compact per-row capture of the picture's presentation state, paid for
 *     only when the render scale is above 1.
 * S2  the presented-height seam (engine patch 0033), used by the builder.
 * S3  the road strip rasteriser: road rows are redrawn at N x from the game's
 *     own per-line width/centre/atlas/palette numbers with analytic edges.
 *     Everything else in the picture is the native picture's content,
 *     nearest-scaled by N (the row renderer expands it before this runs).
 *
 * Everything here is presentation only: it reads the live VDP snapshot the row
 * renderer already owns and writes host pixels. No guest RAM, VRAM, CRAM, CPU,
 * SAT or scheduling state is touched.
 */
#include "tg2_highres.h"

#include "app_config.h"
#include "video/genesis_vdp.h"
#include "video/genesis_dac.h"

#include <math.h>
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
        int requested = g_app_config.internal_scale; /* the engine's row */
        const char *env = getenv("TG2_HIGHRES_SCALE");
        if (env && *env)
            requested = atoi(env);
        if (requested >= 1 && requested <= TG2_HIGHRES_MAX_SCALE) {
            scale = requested;
        } else if (requested != 1) {
            fprintf(stderr, "[tg2] high-res: internal_scale %d is outside 1..%d; "
                            "using 1x\n", requested, TG2_HIGHRES_MAX_SCALE);
        }
        if (scale > 1)
            fprintf(stderr, "[tg2] high-res: render scale %dx (presentation only)\n", scale);
    }
    return scale;
}

int tg2_highres_present_scale(void) { return tg2_highres_scale(); }

/* ── Cost measurement (only with TG2_HIGHRES_TIMING=1) ───────────────────── */

static int s_timing = -1;
static double s_clock_overhead;

static int highres_timing(void) {
    if (s_timing < 0) {
        const char *env = getenv("TG2_HIGHRES_TIMING");
        s_timing = env && *env && env[0] != '0';
        if (s_timing) {
            /* Subtract the two clock reads a measurement costs. */
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

/* ── Compact per-row capture (S1/S3) ─────────────────────────────────────── */

static Tg2RowState s_rows[TG2_HIGHRES_ROWS];
static unsigned short s_row_serial[TG2_HIGHRES_ROWS];
static unsigned s_serial;
static unsigned s_capture_frames, s_capture_rows;
static double s_capture_us;
static double s_build_us;
static unsigned s_build_frames;

/* Plane B samples at 1x. The atlas rules (road texels, palette banks) are the
 * ones docs/HIGHRES.md §1.4 measured and tg2_video.c draws. */
static int tile_count(int n) { return n == 1 ? 64 : n == 3 ? 128 : 32; }

static unsigned plane_word(const GVDP *v, unsigned address) {
    return (v->vram[address & 65535] << 8) | v->vram[(address + 1) & 65535];
}

/* Plane B pixel with an explicit plane base and name-table size, so a captured
 * row's registers can drive it instead of the live end-of-frame state.
 * `attr` receives the tile attribute (palette bank bits). */
static unsigned plane_pixel(const GVDP *v, unsigned base, int size_reg,
                            int x, int y, unsigned *attr) {
    int wt = tile_count(size_reg & 3), ht = tile_count((size_reg >> 4) & 3);
    unsigned a = plane_word(v, base + (((y >> 3) & (ht - 1)) * wt + ((x >> 3) & (wt - 1))) * 2);
    unsigned px = x & 7, py = y & 7;
    if (a & 0x800) px ^= 7;
    if (a & 0x1000) py ^= 7;
    unsigned b = v->vram[((a & 2047) * 32 + py * 4 + px / 2) & 65535];
    unsigned c = px & 1 ? b & 15 : b >> 4;
    if (attr) *attr = a;
    return c ? ((a >> 9) & 48) | c : 0;
}

static unsigned row_plane_pixel(const GVDP *v, const Tg2RowState *r,
                                int x, int y, unsigned *attr) {
    return plane_pixel(v, (unsigned)(r->reg[4] & 7) << 13, r->reg[16], x, y, attr);
}

/* Road silhouette palette nibbles, measured in docs/HIGHRES.md §1.4:
 * 6 = border, 13 = lane mark, 14 = asphalt. */
static int road_texel(unsigned nibble) {
    return nibble == 6 || nibble == 13 || nibble == 14;
}

/* Walk out from the atlas seam until the road silhouette ends. Returns the
 * palette bank bit (tile attribute bit 13) of the outermost road texel through
 * `*bank` and the extreme x through `*edge`. The road always covers the seam;
 * a row whose seam texel is not road falls back to a full 512-column scan. */
static int road_edges(const GVDP *v, const Tg2RowState *r, int py,
                      int *left, int *right, unsigned char *bank) {
    unsigned base = (unsigned)(r->reg[4] & 7) << 13, attr;
    int size = r->reg[16];
    int l = 0, rr = 0;
    for (int side = -1; side <= 1; side += 2) {
        int edge = 0;
        unsigned nib = plane_pixel(v, base, size, 0, py, &attr);
        unsigned b = (attr >> 13) & 1;
        if (!road_texel(nib)) {
            /* Not centred on the seam (rare): scan the whole row. */
            int found_l = 0, found_r = 0;
            for (int x = -256; x < 256; ++x) {
                unsigned n = plane_pixel(v, base, size, x, py, &attr);
                if (!road_texel(n)) continue;
                if (!found_l) { found_l = 1; l = x; bank[0] = (unsigned char)((attr >> 13) & 1); }
                rr = x; found_r = 1; bank[1] = (unsigned char)((attr >> 13) & 1);
            }
            *left = found_l ? l : 0;
            *right = found_r ? rr : 0;
            return found_r;
        }
        for (int x = side; x > -256 && x < 256; x += side) {
            nib = plane_pixel(v, base, size, x, py, &attr);
            if (!road_texel(nib)) break;
            edge = x;
            b = (attr >> 13) & 1;
        }
        if (side < 0) { l = edge; bank[0] = (unsigned char)b; }
        else { rr = edge; bank[1] = (unsigned char)b; }
    }
    *left = l;
    *right = rr;
    return 1;
}

void tg2_highres_reset(void) {
    memset(s_rows, 0, sizeof s_rows);
    memset(s_row_serial, 0, sizeof s_row_serial);
    s_serial = 0;
    s_capture_frames = s_capture_rows = 0;
    s_capture_us = s_build_us = 0;
    s_build_frames = 0;
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
    int timing = highres_timing();
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
    r->left = r->right = 0;
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
    r->bank[0] = r->bank[1] = 0;
    if (flags & TG2_ROW_ROAD) {
        /* The second member of each authored pair carries the palette-bank
         * bit (lane-mark phase). Measured from the live name table. */
        if (!road_edges(v, r, py, &r->left, &r->right, r->bank)) {
            r->left = r->right = 0;
            flags &= (unsigned char)~TG2_ROW_ROAD;
        } else if (r->bank[0]) {
            flags |= TG2_ROW_BANK1;
        }
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
double tg2_highres_build_us(void) { return s_build_us; }
unsigned tg2_highres_build_frames(void) { return s_build_frames; }

/* ── Road strip rasteriser (S3) ──────────────────────────────────────────── */

/* A row's authored pair family: 0 = atlases at 0..287 (width 4 + 2k),
 * 1 = 288..431 (the wider ramp). Widths may only be interpolated inside one
 * family (docs/HIGHRES.md §2.1). */
static int road_family(int py) {
    return py < 288 ? 0 : py < 432 ? 1 : -1;
}

/* The game's own road centre: the atlas seam position the H-scroll names,
 * unwrapped exactly like tg2_video.c's road_x(). */
static int road_centre(unsigned scroll) {
    return 128 + (((int)(scroll & 511) - 128 + 256) & 511) - 256;
}

/* Blend two ARGB pixels by `alpha` (0..1). */
static uint32_t blend(uint32_t a, uint32_t b, double alpha) {
    unsigned w = (unsigned)(alpha * 256.0 + 0.5);
    unsigned lo = ((a & 0xFF) * (256 - w) + (b & 0xFF) * w) >> 8;
    unsigned mid = (((a >> 8) & 0xFF) * (256 - w) + ((b >> 8) & 0xFF) * w) >> 8;
    unsigned hi = (((a >> 16) & 0xFF) * (256 - w) + ((b >> 16) & 0xFF) * w) >> 8;
    return 0xFF000000u | (hi << 16) | (mid << 8) | lo;
}

/* Terrain mask: one entry per 1x canvas column of a road row, true where the
 * native picture shows this row's plane B (sky/ground/road) rather than a
 * sprite, the HUD, the car or a plane-A effect. The comparison is exact
 * against the plane-B colour the row's own captured state produces, so any
 * overlay pixel is preserved by construction; a sprite texel whose colour
 * coincides with the scenery underneath is the one false positive. */
static unsigned char s_terrain[4096];

static void build_terrain(const GVDP *v, const Tg2RowState *r, int src,
                          int origin, int native_w, int w1, int scale,
                          const uint32_t *row) {
    int vb = r->vsram[1] & 511;
    int y = src + vb;
    int hb = r->hscroll[1] & 1023;
    uint32_t pal[64];
    for (int i = 0; i < 64; ++i)
        pal[i] = genesis_dac_cram_to_argb(r->cram[i], 0);
    uint32_t backdrop = pal[r->reg[7] & 63];
    for (int u = 0; u < w1; ++u) {
        int nx = u - origin, ax;
        if (nx >= 0 && nx < native_w) {
            ax = nx - (int)hb;              /* the VDP's own plane-B fetch */
        } else {
            /* tg2_video's margin continuation: same row, clamped exterior. */
            int py = y & 511;
            if (py >= 448) ax = nx - (int)hb;
            else if (py >= 432) ax = (nx < 0 ? 0 : nx > 255 ? 255 : nx) - (int)hb;
            else {
                int center = road_centre(hb);
                int x = nx - center;
                ax = x < -256 ? -256 : x > 255 ? 255 : x;
            }
        }
        unsigned attr;
        unsigned index = row_plane_pixel(v, r, ax, y, &attr);
        uint32_t colour = index ? pal[index] : backdrop;
        s_terrain[u] = row[u * scale] == colour;
    }
}

/* ── N x road audit (qualification stream, docs/HIGHRES.md §8 S3) ─────────
 * One record per presented picture under TG2_ROAD_AUDIT_DIR, at native row
 * granularity (lines 140..212, last sub-row of each). The checker verifies the
 * built silhouette against the two authored neighbours, the stripe phase, and
 * row-to-row continuity. Only written when a qualification run asks for it. */
#define NX_AUDIT_FIRST 140
#define NX_AUDIT_ROWS  73
typedef struct {
    uint32_t line, py_src, py_next;
    int32_t centre_src, centre_next, left_src, right_src, left_next, right_next;
    int32_t el_x256, er_x256;          /* interpolated strip edges           */
    int32_t measured_left, measured_right;
    uint32_t stripes, stripes_src, flags;
} NxAuditRow;
enum { NX_FLAG_ROAD = 1, NX_FLAG_INTERPOLATED = 2 };

static int32_t nx_lane_runs(const GVDP *v, const Tg2RowState *r, int py,
                            int from, int to) {
    int runs = 0, prev = 0;
    for (int x = from; x <= to; ++x) {
        unsigned attr;
        unsigned nib = row_plane_pixel(v, r, x, py, &attr) & 15;
        int lane = nib == 13;
        if (lane && !prev) ++runs;
        prev = lane;
    }
    return runs;
}

/* Measure the painted row at native sampling: road-colour extent and lane-mark
 * runs. Colours come from the row's own palette, so interior texels match
 * exactly; an antialiased edge column can miss by one native pixel. */
static void nx_measure(const uint32_t *row, int scale, int w1,
                       const uint32_t *pal, unsigned char bank,
                       int *left, int *right, unsigned *stripes) {
    uint32_t border = pal[(bank << 4) | 6];
    uint32_t lane = pal[(bank << 4) | 13];
    uint32_t asphalt = pal[(bank << 4) | 14];
    int l = -1, r = -1, prev = 0;
    unsigned runs = 0;
    for (int u = 0; u < w1; ++u) {
        uint32_t c = row[u * scale];
        if (c == border || c == lane || c == asphalt) {
            if (l < 0) l = u;
            r = u;
        }
        if (c == lane && !prev) ++runs;
        prev = c == lane;
    }
    *left = l;
    *right = r;
    *stripes = runs;
}

static void nx_audit_write(const GVDP *v, uint64_t frame, int scale,
                           const uint32_t *pixels, int stride, int w1,
                           int native_w, const NxAuditRow *rows) {
    static int checked;
    static const char *dir;
    if (!checked) {
        checked = 1;
        dir = getenv("TG2_ROAD_AUDIT_DIR");
    }
    if (!dir || !*dir) return;
    char path[1024];
    snprintf(path, sizeof path, "%s/frame-%06llu.nxroad", dir, (unsigned long long)frame);
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); return; }
    uint32_t header[7] = {0x3152584Eu /* "NXR1" little-endian tag */, (uint32_t)frame,
                          (uint32_t)scale, (uint32_t)stride, (uint32_t)w1,
                          (uint32_t)native_w, NX_AUDIT_ROWS};
    fwrite("TG2NXR01", 1, 8, f);
    fwrite(header, sizeof header, 1, f);
    for (int i = 0; i < NX_AUDIT_ROWS; ++i)
        fwrite(&rows[i], sizeof rows[i], 1, f);
    fclose(f);
    (void)v; (void)pixels;
}

/* Paint one output row of a road row. `row` is the nearest-expanded 1x row
 * (and the output row); the caller guarantees `row` is writable. */
static void paint_road_row(const GVDP *v, int src, int j, int scale, int w1,
                           int native_w, uint32_t *row, const uint32_t *native_row,
                           NxAuditRow *audit) {
    const Tg2RowState *s = &s_rows[src];
    int origin = (w1 - native_w) / 2;
    int vb = s->vsram[1] & 511;
    int py = (src + vb) & 511;
    int y = src + vb;
    int hb = s->hscroll[1] & 1023;
    int centre_s = road_centre(hb);
    int left_s = s->left, right_s = s->right;
    int centre_n = centre_s, left_n = left_s, right_n = right_s;
    int interpolate = 0;

    if (src + 1 < TG2_HIGHRES_ROWS && s_row_serial[src + 1] == s_serial) {
        const Tg2RowState *t = &s_rows[src + 1];
        int py_n = (src + 1 + (t->vsram[1] & 511)) & 511;
        if ((t->flags & TG2_ROW_ROAD) && road_family(py_n) == road_family(py)) {
            interpolate = 1;
            centre_n = road_centre(t->hscroll[1] & 1023);
            left_n = t->left;
            right_n = t->right;
        }
    }
    double frac = interpolate ? (double)j / (double)scale : 0.0;
    double el = origin + (centre_s + left_s) + frac * (double)((centre_n + left_n) - (centre_s + left_s));
    double er = origin + (centre_s + right_s) + frac * (double)((centre_n + right_n) - (centre_s + right_s));
    double ec = origin + centre_s + frac * (double)(centre_n - centre_s);
    double own_l = origin + centre_s + left_s;
    double own_r = origin + centre_s + right_s;

    uint32_t pal[64];
    for (int i = 0; i < 64; ++i)
        pal[i] = genesis_dac_cram_to_argb(s->cram[i], 0);
    uint32_t backdrop = pal[s->reg[7] & 63];

    for (int u = 0; u < w1; ++u) {
        if (!s_terrain[u])
            continue;                        /* sprite / HUD / car / plane A */
        uint32_t native = native_row[u * scale];
        for (int k = 0; k < scale; ++k) {
            int x = u * scale + k;
            double u0 = (double)x / (double)scale;
            double u1 = (double)(x + 1) / (double)scale;
            double lo = u0 > el ? u0 : el, hi = u1 < er ? u1 : er;
            double coverage = hi > lo ? (hi - lo) * scale : 0.0;
            if (coverage > 1.0) coverage = 1.0;
            int inside_own = u1 > own_l && u0 < own_r;
            if (coverage <= 0.0) {
                /* Between the interpolated edge and the row's own (wider)
                 * silhouette: show the row's verge, not its road art. */
                if (!inside_own)
                    continue;
                unsigned attr;
                int ax = u0 < ec ? left_s - 1 : right_s + 1;
                if (ax < -256) ax = -256;
                if (ax > 255) ax = 255;
                unsigned c = row_plane_pixel(v, s, ax, y, &attr);
                row[x] = c ? pal[c] : backdrop;
                continue;
            }
            double ua = 0.5 * (u0 + u1) - ec;
            int ax = (int)(ua >= 0.0 ? ua + 0.5 : ua - 0.5);
            if (ax < left_s) ax = left_s;
            if (ax > right_s) ax = right_s;
            unsigned attr;
            unsigned c = row_plane_pixel(v, s, ax, y, &attr);
            uint32_t road = c ? pal[c] : backdrop;
            row[x] = coverage >= 1.0 ? road : blend(native, road, coverage);
        }
    }
    if (audit) {
        int left = -1, right = -1;
        unsigned stripes = 0;
        nx_measure(row, scale, w1, pal, s->bank[0], &left, &right, &stripes);
        audit->line = (uint32_t)src;
        audit->py_src = (uint32_t)py;
        audit->py_next = (uint32_t)py;
        audit->centre_src = centre_s;
        audit->centre_next = centre_n;
        audit->left_src = left_s;
        audit->right_src = right_s;
        audit->left_next = left_n;
        audit->right_next = right_n;
        audit->el_x256 = (int32_t)(el * 256.0 + (el >= 0 ? 0.5 : -0.5));
        audit->er_x256 = (int32_t)(er * 256.0 + (er >= 0 ? 0.5 : -0.5));
        audit->measured_left = left;
        audit->measured_right = right;
        audit->stripes = stripes;
        audit->stripes_src = (uint32_t)nx_lane_runs(v, s, py, left_s, right_s);
        audit->flags = NX_FLAG_ROAD | (interpolate ? NX_FLAG_INTERPOLATED : 0);
    }
}

int tg2_highres_build(const GVDP *vdp, uint64_t frame, uint32_t *pixels, int stride,
                      int width, int native_w, int native_h) {
    int scale = tg2_highres_present_scale();
    if (scale <= 1 || !vdp || !pixels || width <= 0 || stride < width)
        return 0;
    if (width % scale || native_h <= 0 || native_h > TG2_HIGHRES_ROWS)
        return 0;
    int w1 = width / scale;
    if (w1 < native_w || w1 > 4096)
        return 0;
    int timing = highres_timing();
    double started = timing ? highres_now_us() : 0;

    /* The row renderer produced one row per native line, already expanded
     * horizontally by N; each becomes N presented rows. Walk bottom-up so
     * reading native row `src` is never overwritten by the rows above it. */
    static uint32_t s_src_row[4096];
    NxAuditRow audit[NX_AUDIT_ROWS];
    memset(audit, 0, sizeof audit);
    for (int src = native_h - 1; src >= 0; --src) {
        const uint32_t *native = pixels + (size_t)src * stride;
        memcpy(s_src_row, native, (size_t)width * sizeof *s_src_row);
        int road = s_row_serial[src] == s_serial &&
                   (s_rows[src].flags & TG2_ROW_ROAD) &&
                   ((src + s_rows[src].vsram[1]) & 511) < 432;
        if (road)
            build_terrain(vdp, &s_rows[src], src, (w1 - native_w) / 2, native_w,
                          w1, scale, s_src_row);
        for (int j = 0; j < scale; ++j) {
            uint32_t *row = pixels + (size_t)(src * scale + j) * stride;
            if (!road) {
                memcpy(row, s_src_row, (size_t)width * sizeof *row);
                continue;
            }
            NxAuditRow *entry = NULL;
            if (j == scale - 1 && src >= NX_AUDIT_FIRST && src < NX_AUDIT_FIRST + NX_AUDIT_ROWS)
                entry = &audit[src - NX_AUDIT_FIRST];
            paint_road_row(vdp, src, j, scale, w1, native_w, row, s_src_row, entry);
        }
    }
    nx_audit_write(vdp, frame, scale, pixels, stride, w1, native_w, audit);
    ++s_build_frames;
    if (timing) {
        double elapsed = highres_now_us() - started - s_clock_overhead;
        if (elapsed > 0) s_build_us += elapsed;
    }
    return native_h * scale;
}
