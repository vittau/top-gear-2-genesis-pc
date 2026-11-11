/*
 * tg2_highres.c — high-resolution rendering (docs/HIGHRES.md §7).
 *
 * S1  compact per-row capture of the picture's presentation state, paid for
 *     only when the render scale is above 1.
 * S2  the presented-height seam (engine patch 0033), used by the builder.
 * S3  the road strip rasteriser: road rows are redrawn at N x from the game's
 *     own per-line width/centre/atlas/palette numbers: fitted silhouettes,
 *     analytic coverage on every colour boundary of the road.
 *     Everything else keeps the native picture's detail and size. Linear Off
 *     nearest-expands it; Linear On filters RGB with explicit layer coverage.
 *
 * Everything here is presentation only: it reads the VDP snapshot the row
 * renderer is drawing from and writes host pixels. No guest RAM, VRAM, CRAM, CPU,
 * SAT or scheduling state is touched.
 */
#include "tg2_highres.h"
#include "tg2_actors.h"

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

/* Source art and explicit plane/sprite coverage. Only Linear On captures it;
 * Off keeps the accepted S3 colour-mask and nearest expansion unchanged. */
static uint32_t s_native_rgb[TG2_HIGHRES_ROWS][4096];
static unsigned char s_native_foreground[TG2_HIGHRES_ROWS][4096];
static unsigned s_native_serial[TG2_HIGHRES_ROWS];
static int s_native_width[TG2_HIGHRES_ROWS];
static unsigned s_filtered_frames, s_filter_incomplete;
int tg2_highres_linear_filter(void) {
    return g_app_config.linear_filter && tg2_highres_present_scale() > 1;
}
unsigned tg2_highres_filtered_frames(void) { return s_filtered_frames; }
unsigned tg2_highres_filter_incomplete(void) { return s_filter_incomplete; }

static unsigned char s_actor_occluder[TG2_HIGHRES_ROWS][4096];
static unsigned short s_actor_front[TG2_HIGHRES_ROWS][4096];
static unsigned char s_actor_row_ok[TG2_HIGHRES_ROWS];
static uint32_t s_reference[TG2_HIGHRES_ROWS][4096];
void tg2_highres_capture_actors(int line,const unsigned char *foreground,
    const unsigned char *occluder,const unsigned short *front,
    const uint32_t *reference,int width,int actor_free) {
    if(line<0 || line>=TG2_HIGHRES_ROWS || width>4096)return;
    memcpy(s_actor_occluder[line],occluder,width);
    memcpy(s_actor_front[line],front,width*sizeof *front);
    if(tg2_highres_native_dump_active()) memcpy(s_reference[line],reference,width*sizeof *reference);
    s_actor_row_ok[line]=actor_free;
}

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
/* Same width as s_serial: truncating row tags at 16 bits silently stopped
 * matching fresh rows after 65,535 captured pictures. */
static unsigned s_row_serial[TG2_HIGHRES_ROWS];
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

/* Road silhouette palette nibbles, measured in docs/HIGHRES.md §1.4:
 * 6 = border, 13 = lane mark, 14 = asphalt. */
static int road_texel(unsigned nibble) {
    return nibble == 6 || nibble == 13 || nibble == 14;
}

/* One atlas row as the builder needs it: the run-length list of the 512 texels
 * the row can show (atlas x -256..255, tg2_video's road_x() domain), taken from
 * the very VDP snapshot the row was rendered with. A 60 fps synthesized row is
 * rendered from an older picture's VRAM, so this must be recorded at row time,
 * not read back from the live VRAM when the frame ends. Run `i` covers atlas x
 * start[i]..start[i+1]-1 and shows palette index index[i] (0 = backdrop);
 * runs first..last are the road silhouette around the seam. */
#define ROAD_MAX_RUNS 64
typedef struct {
    short start[ROAD_MAX_RUNS + 1];
    unsigned char index[ROAD_MAX_RUNS];
    unsigned char count, first, last, valid;
} RoadRuns;
static RoadRuns s_runs[TG2_HIGHRES_ROWS];

/* Decode the atlas row tile by tile (64 name-table reads instead of 512). */
static void atlas_row(const GVDP *v, const Tg2RowState *r, int py,
                      unsigned char texel[512]) {
    unsigned base = (unsigned)(r->reg[4] & 7) << 13;
    int wt = tile_count(r->reg[16] & 3), ht = tile_count((r->reg[16] >> 4) & 3);
    unsigned line = base + (unsigned)(((py >> 3) & (ht - 1)) * wt) * 2;
    for (int tx = -32; tx < 32; ++tx) {
        unsigned a = plane_word(v, line + (unsigned)(tx & (wt - 1)) * 2);
        unsigned ty = (unsigned)py & 7;
        if (a & 0x1000) ty ^= 7;
        const unsigned char *data = &v->vram[((a & 2047) * 32 + ty * 4) & 65535];
        unsigned bank = (a >> 9) & 48;
        unsigned char *out = texel + (tx + 32) * 8;
        for (int px = 0; px < 8; ++px) {
            unsigned sx = a & 0x800 ? 7u - (unsigned)px : (unsigned)px;
            unsigned b = data[sx >> 1];
            unsigned c = sx & 1 ? b & 15 : b >> 4;
            out[px] = (unsigned char)(c ? bank | c : 0);
        }
    }
}

/* Build the row's runs and its road silhouette. Returns 0 when the row shows
 * no road. The road always covers the seam (atlas x 0); a row whose seam texel
 * is not road keeps the first..last road texel as its silhouette for the
 * capture dump but is not redrawn (runs->valid stays 0). */
static int road_runs(const GVDP *v, const Tg2RowState *r, int py, RoadRuns *runs,
                     short *left, short *right, unsigned char *bank) {
    unsigned char texel[512];
    atlas_row(v, r, py, texel);
    runs->count = runs->first = runs->last = runs->valid = 0;
    int l = 0, rr = 0, found = 0;
    if (road_texel(texel[256] & 15)) {
        for (l = 0; l > -256 && road_texel(texel[256 + l - 1] & 15); --l) {}
        for (rr = 0; rr < 255 && road_texel(texel[256 + rr + 1] & 15); ++rr) {}
        found = 2;
    } else {
        for (int x = -256; x < 256; ++x)
            if (road_texel(texel[256 + x] & 15)) {
                if (!found) l = x;
                rr = x;
                found = 1;
            }
    }
    if (!found)
        return 0;
    *left = (short)l;
    *right = (short)rr;
    bank[0] = (unsigned char)((texel[256 + l] >> 4) & 1);
    bank[1] = (unsigned char)((texel[256 + rr] >> 4) & 1);
    if (found != 2)
        return 1;
    int count = 0;
    for (int x = -256; x < 256; ++x) {
        /* The silhouette edges always start a run, so runs first..last are
         * exactly the road. */
        if (x == -256 || texel[256 + x] != texel[255 + x] || x == l || x == rr + 1) {
            if (count == ROAD_MAX_RUNS)
                return 1;                   /* too busy to model: stay nearest */
            runs->start[count] = (short)x;
            runs->index[count] = texel[256 + x];
            if (x == l) runs->first = (unsigned char)count;
            if (x <= rr) runs->last = (unsigned char)count;
            ++count;
        }
    }
    runs->start[count] = 256;
    runs->count = (unsigned char)count;
    runs->valid = 1;
    return 1;
}

void tg2_highres_capture_native(int line, const uint32_t *pixels,
                                const unsigned char *foreground, int width) {
    if (!tg2_highres_linear_filter() || line < 0 || line >= TG2_HIGHRES_ROWS ||
        !pixels || !foreground || width <= 0 || width > 4096) return;
    memcpy(s_native_rgb[line], pixels, (size_t)width * sizeof *pixels);
    memcpy(s_native_foreground[line], foreground, (size_t)width);
    s_native_width[line] = width;
    s_native_serial[line] = s_serial;
}

void tg2_highres_reset(void) {
    memset(s_rows, 0, sizeof s_rows);
    memset(s_row_serial, 0, sizeof s_row_serial);
    memset(s_runs, 0, sizeof s_runs);
    s_serial = 0;
    memset(s_native_serial, 0, sizeof s_native_serial);
    s_filtered_frames = s_filter_incomplete = 0;
    s_capture_frames = s_capture_rows = 0;
    s_capture_us = s_build_us = 0;
    s_build_frames = 0;
}

void tg2_highres_picture_start(void) {
    if (tg2_highres_scale() <= 1)
        return;
    ++s_capture_frames;
    ++s_serial;
    memset(s_actor_row_ok,0,sizeof s_actor_row_ok);
    s_capture_rows = 0;
    s_capture_us = 0;
}

void tg2_highres_capture_row(const GVDP *v, int line, int ha, int hb) {
    if (!v || line < 0 || line >= TG2_HIGHRES_ROWS || tg2_highres_scale() <= 1)
        return;
    int timing = highres_timing();
    double started = timing ? highres_now_us() : 0;
    s_row_serial[line] = s_serial;
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
    s_runs[line].valid = 0;
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
        if (!road_runs(v, r, py, &s_runs[line], &r->left, &r->right, r->bank)) {
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
const unsigned *tg2_highres_row_serial(void) { return s_row_serial; }
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

/* Per-picture road model. Rows that belong to one continuous piece of road
 * form a band; inside a band the two silhouette edges are fitted across rows,
 * because the game's per-line numbers are integers (centre) and a 2/4 px
 * saw-tooth (width): followed literally they give an edge that wobbles at
 * N x. The fit is a local quadratic over +-FIT_REACH rows, so a straight or
 * evenly curving edge is reproduced exactly and only the quantisation goes;
 * the result is held within FIT_LIMIT native pixels of the authored edge. */
#define FIT_REACH 5
#define FIT_LIMIT 1.5
typedef struct {
    int painted;                /* row is redrawn by the strip rasteriser   */
    int band;                   /* rows of one continuous road share this   */
    int centre;                 /* canvas x of the atlas seam               */
    double raw_l, raw_r;        /* authored silhouette, canvas x            */
    double fit_l, fit_r;        /* fitted silhouette, canvas x              */
} RoadRow;
static RoadRow s_road[TG2_HIGHRES_ROWS];

static int road_row_k(int line) {
    return s_rows[line].width_k;
}

static int road_row_py(int line) {
    return (line + s_rows[line].vsram[1]) & 511;
}

/* Quadratic least-squares value at `at` of f over the band rows within
 * FIT_REACH, tricube-ish weights. Falls back to lower orders when the band is
 * too short to determine a parabola. */
static double fit_edge(int at, int lo, int hi, int right) {
    double s0 = 0, s1 = 0, s2 = 0, s3 = 0, s4 = 0, t0 = 0, t1 = 0, t2 = 0;
    int from = at - FIT_REACH < lo ? lo : at - FIT_REACH;
    int to = at + FIT_REACH > hi ? hi : at + FIT_REACH;
    for (int y = from; y <= to; ++y) {
        double x = y - at, d = fabs(x) / (FIT_REACH + 1.0);
        double w = 1.0 - d * d;
        double f = right ? s_road[y].raw_r : s_road[y].raw_l;
        s0 += w; s1 += w * x; s2 += w * x * x; s3 += w * x * x * x;
        s4 += w * x * x * x * x;
        t0 += w * f; t1 += w * f * x; t2 += w * f * x * x;
    }
    double own = right ? s_road[at].raw_r : s_road[at].raw_l;
    int n = to - from + 1;
    double value = own;
    if (n >= 5) {
        /* Solve the 3x3 normal equations for the constant term. */
        double det = s0 * (s2 * s4 - s3 * s3) - s1 * (s1 * s4 - s3 * s2) +
                     s2 * (s1 * s3 - s2 * s2);
        if (fabs(det) > 1e-9)
            value = (t0 * (s2 * s4 - s3 * s3) - s1 * (t1 * s4 - s3 * t2) +
                     s2 * (t1 * s3 - s2 * t2)) / det;
    } else if (n >= 3) {
        double det = s0 * s2 - s1 * s1;
        if (fabs(det) > 1e-9)
            value = (t0 * s2 - s1 * t1) / det;
    }
    if (value < own - FIT_LIMIT) value = own - FIT_LIMIT;
    if (value > own + FIT_LIMIT) value = own + FIT_LIMIT;
    return value;
}

static void model_road(int origin, int native_h) {
    int band = 0;
    for (int y = 0; y < native_h; ++y) {
        RoadRow *m = &s_road[y];
        const Tg2RowState *r = &s_rows[y];
        m->painted = s_row_serial[y] == s_serial && (r->flags & TG2_ROW_ROAD) &&
                     s_runs[y].valid && road_row_py(y) < 432;
        if (!m->painted)
            continue;
        m->centre = origin + road_centre(r->hscroll[1]);
        m->raw_l = m->centre + s_runs[y].start[s_runs[y].first];
        m->raw_r = m->centre + s_runs[y].start[s_runs[y].last + 1];
        /* A new band starts where the road is not continuous with the row
         * above: another pair family, or a jump in the atlas row no single
         * surface produces (a crest hiding part of the road). */
        int joined = y > 0 && s_road[y - 1].painted &&
                     road_family(road_row_py(y)) == road_family(road_row_py(y - 1)) &&
                     abs(road_row_k(y) - road_row_k(y - 1)) <= 8;
        m->band = joined ? s_road[y - 1].band : ++band;
    }
    for (int y = 0; y < native_h; ++y) {
        if (!s_road[y].painted)
            continue;
        int lo = y, hi = y;
        while (lo > 0 && s_road[lo - 1].painted && s_road[lo - 1].band == s_road[y].band) --lo;
        while (hi + 1 < native_h && s_road[hi + 1].painted &&
               s_road[hi + 1].band == s_road[y].band) ++hi;
        for (int at = lo; at <= hi; ++at) {
            s_road[at].fit_l = fit_edge(at, lo, hi, 0);
            s_road[at].fit_r = fit_edge(at, lo, hi, 1);
            if (s_road[at].fit_r < s_road[at].fit_l + 1.0) {
                s_road[at].fit_l = s_road[at].raw_l;
                s_road[at].fit_r = s_road[at].raw_r;
            }
        }
        y = hi;
    }
}

/* Two rows whose road shows the same sequence of texel kinds: their interior
 * boundaries (border, lane marks) correspond one to one. */
static int same_structure(const RoadRuns *a, const RoadRuns *b) {
    if (a->last - a->first != b->last - b->first)
        return 0;
    for (int i = 0; i <= a->last - a->first; ++i)
        if ((a->index[a->first + i] & 15) != (b->index[b->first + i] & 15))
            return 0;
    return 1;
}

/* Terrain mask: one entry per 1x canvas column of a road row, true where the
 * native picture shows this row's plane B (road/verge) rather than a sprite,
 * the HUD, the car or a plane-A effect. The comparison is exact against the
 * colour the row's own captured atlas runs produce, so any overlay pixel is
 * preserved by construction; a sprite texel whose colour coincides with the
 * scenery underneath is the one false positive. */
static unsigned char s_terrain[4096];
/* The colour the row's own atlas runs put at each 1x column (audit only). */
static uint32_t s_model[4096];

/* ── N x road audit (qualification stream, docs/HIGHRES.md §8 S3) ─────────
 * One file per presented picture under TG2_ROAD_AUDIT_DIR: one record per
 * presented row of every redrawn road row, with the authored geometry, the
 * edges the builder aimed for and what the BUILT pixels show (edges, lane
 * marks, holes, and pixels the native row cannot explain). Only written when
 * a qualification run asks for it. Linear On records the analytic road
 * underlay here, before native-art coverage is composited; the coverage
 * capture separately verifies that uncovered final road pixels stay intact. */
typedef struct {
    int32_t line, sub, py, flags, neighbour;
    int32_t own_l, own_r, nb_l, nb_r;   /* authored silhouettes, canvas x   */
    int32_t el_x256, er_x256;           /* edges drawn, canvas x * 256      */
    int32_t seen_l, seen_r;             /* road pixels found, output x      */
    int32_t lanes, lanes_src, holes;
    int32_t outliers, margin_outliers, band;
    int32_t lane_error_x256;           /* worst measured stripe-centre error */
} NxAuditRow;
enum { NX_FLAG_INTERPOLATED = 1, NX_FLAG_FULL = 2, NX_FLAG_STRUCTURE = 4,
       NX_FLAG_AMBIGUOUS = 8, NX_FLAG_LANE_AMBIGUOUS = 16,
       NX_FLAG_LANE_CLASSIFIED = 32 };

static const char *nx_audit_dir(void) {
    static int checked;
    static const char *dir;
    if (!checked) {
        checked = 1;
        dir = getenv("TG2_ROAD_AUDIT_DIR");
        if (dir && !*dir) dir = NULL;
    }
    return dir;
}

static NxAuditRow *s_audit;
static int s_audit_count;

static int colour_distance(uint32_t a, uint32_t b) {
    int d = 0;
    for (int shift = 0; shift < 24; shift += 8) {
        int c = (int)((a >> shift) & 255) - (int)((b >> shift) & 255);
        d += c * c;
    }
    return d;
}

/* Measure one built row back from its pixels. */
static void nx_measure(NxAuditRow *a, const RoadRuns *runs, const uint32_t *colour,
                       const uint32_t *row, const uint32_t *native_row, int scale,
                       int w1, int origin, int native_w, int reach, int centre,
                       const double *boundaries) {
    /* Pixel kinds by nearest run colour: 0 verge, 1 road, 2 lane mark. A lane
     * colour that equals asphalt (the "off" phase) is plain road. */
    unsigned char kind[ROAD_MAX_RUNS];
    int lanes_src = 0, previous = 0;
    for (int i = 0; i < runs->count; ++i) {
        int road = i >= runs->first && i <= runs->last;
        kind[i] = (unsigned char)road;
        if (road && (runs->index[i] & 15) == 13) {
            int visible = 1;
            for (int j = runs->first; j <= runs->last; ++j)
                if ((runs->index[j] & 15) == 14 && colour[j] == colour[i]) visible = 0;
            if (visible) kind[i] = 2;
        }
        if (road) {
            if (kind[i] == 2 && previous != 2) ++lanes_src;
            previous = kind[i];
        }
    }
    a->lanes_src = lanes_src;
    a->flags |= NX_FLAG_LANE_CLASSIFIED;
    double lane_centres[ROAD_MAX_RUNS];
    int lane_count = 0;
    for (int i = runs->first; i <= runs->last; ++i) {
        if (kind[i] != 2) continue;
        int first = i;
        while (i < runs->last && kind[i + 1] == 2) ++i;
        lane_centres[lane_count++] = (boundaries[first] + boundaries[i + 1]) * scale * 0.5;
    }
    int lane_begin = -1, lane_seen = 0;
    double lane_error = 0;
    /* A white border can share the lane colour. Its authored interval, with
     * one output pixel of coverage allowance, separates it from a lane.
     * At tiny widths where those intervals touch, pixels cannot distinguish
     * them reliably, so exclude the row from geometry/stripe measurement. */
    for (int i = runs->first; i <= runs->last; ++i) {
        if (kind[i] != 2) continue;
        for (int j = runs->first; j <= runs->last; ++j) {
            if ((runs->index[j] & 15) != 6 || colour[i] != colour[j]) continue;
            double gap = j < i ? boundaries[i] - boundaries[j + 1]
                               : boundaries[j] - boundaries[i + 1];
            if (gap * scale < 2.0)
                a->flags |= NX_FLAG_AMBIGUOUS | NX_FLAG_LANE_AMBIGUOUS;
        }
    }
    /* A verge that shares a colour with the road (fades, some palettes) cannot
     * be told from it in the picture: the row's geometry is not measurable. */
    for (int i = 0; i < runs->count; ++i)
        for (int j = runs->first; j <= runs->last; ++j)
            if (!kind[i] && colour[i] == colour[j]) a->flags |= NX_FLAG_AMBIGUOUS;
    a->seen_l = a->seen_r = -1;
    a->lanes = a->holes = a->outliers = a->margin_outliers = 0;
    int holes_pending = 0, last_kind = 0;
    for (int u = 0; u < w1; ++u) {
        if (!s_terrain[u]) { last_kind = 0; continue; }
        /* What the native row holds near this column bounds what may appear:
         * its pixels, and the scenery a sprite may be hiding there. */
        int lo[3] = {255, 255, 255}, hi[3] = {0, 0, 0};
        for (int n = u - reach; n <= u + reach; ++n) {
            /* Past the canvas edge only the row's own continuation exists. */
            uint32_t pair[2];
            if (n < 0 || n >= w1) {
                int x = n - centre, run = 0;
                x = x < -256 ? -256 : x > 255 ? 255 : x;
                while (run + 1 < runs->count && runs->start[run + 1] <= x) ++run;
                pair[0] = pair[1] = colour[run];
            } else {
                pair[0] = native_row[n * scale];
                pair[1] = s_model[n];
            }
            for (int e = 0; e < 2; ++e)
                for (int ch = 0; ch < 3; ++ch) {
                    int value = (int)((pair[e] >> (ch * 8)) & 255);
                    if (value < lo[ch]) lo[ch] = value;
                    if (value > hi[ch]) hi[ch] = value;
                }
        }
        for (int k = 0; k < scale; ++k) {
            int x = u * scale + k;
            uint32_t c = row[x];
            int out = 0;
            for (int ch = 0; ch < 3; ++ch) {
                int value = (int)((c >> (ch * 8)) & 255);
                if (value < lo[ch] - 1 || value > hi[ch] + 1) out = 1;
            }
            if (out) {
                ++a->outliers;
                if (u < origin || u >= origin + native_w) ++a->margin_outliers;
            }
            int best = 0, best_d = 1 << 30;
            for (int i = 0; i < runs->count; ++i) {
                int d = colour_distance(c, colour[i]);
                if (d < best_d || (d == best_d && kind[i] > kind[best])) { best_d = d; best = i; }
            }
            int kd = kind[best];
            /* Snow/verge can be the same white as a lane. Count lanes only
             * inside the road interval; road-edge geometry remains separately
             * marked ambiguous when its colours cannot identify the verge. */
            if (kd == 2 && (x + 0.5 < boundaries[runs->first] * scale ||
                            x + 0.5 >= boundaries[runs->last + 1] * scale)) kd = 0;
            if (kd == 2) {
                for (int i = runs->first; i <= runs->last; ++i) {
                    if ((runs->index[i] & 15) == 6 && colour[i] == colour[best] &&
                        x + 0.5 >= boundaries[i] * scale - 1.0 &&
                        x + 0.5 <= boundaries[i + 1] * scale + 1.0) {
                        kd = 1;             /* border, not an extra lane */
                        break;
                    }
                }
            }
            if (kd == 2 && lane_begin < 0) lane_begin = x;
            if (kd != 2 && lane_begin >= 0) {
                if (lane_seen < lane_count) {
                    double error = fabs((lane_begin + x) * 0.5 - lane_centres[lane_seen]);
                    if (error > lane_error) lane_error = error;
                }
                ++lane_seen;
                lane_begin = -1;
            }
            if (kd) {
                if (a->seen_l < 0) a->seen_l = x;
                a->seen_r = x;
                a->holes += holes_pending;
                holes_pending = 0;
                if (kd == 2 && last_kind != 2) ++a->lanes;
            } else if (a->seen_l >= 0) {
                ++holes_pending;
            }
            last_kind = kd;
        }
    }
    /* Clipped stripes are excluded by the checker's full/unclipped-row gate. */
    a->lane_error_x256 = (int32_t)floor(fmin(lane_error, 1e6) * 256.0 + 0.5);
}

static void nx_audit_write(uint64_t frame, int scale, int w1, int native_w) {
    const char *dir = nx_audit_dir();
    if (!dir || !s_audit) return;
    char path[1024];
    snprintf(path, sizeof path, "%s/frame-%06llu.nxroad", dir, (unsigned long long)frame);
    FILE *f = fopen(path, "wb");
    if (!f) { perror(path); return; }
    uint32_t header[6] = {(uint32_t)frame, (uint32_t)scale, (uint32_t)w1,
                          (uint32_t)native_w, (uint32_t)s_audit_count,
                          (uint32_t)sizeof(NxAuditRow)};
    fwrite("TG2NXR03", 1, 8, f);
    fwrite(header, sizeof header, 1, f);
    fwrite(s_audit, sizeof *s_audit, (size_t)s_audit_count, f);
    fclose(f);
}

/* Everything about a road row that does not depend on the sub-row. */
typedef struct {
    const RoadRuns *runs;
    double edge[ROAD_MAX_RUNS + 1];     /* authored run boundaries, canvas x */
    uint32_t colour[ROAD_MAX_RUNS];
} RowPlan;

static void plan_row(int src, RowPlan *p) {
    const Tg2RowState *s = &s_rows[src];
    p->runs = &s_runs[src];
    uint32_t pal[64];
    for (int i = 0; i < 64; ++i)
        pal[i] = genesis_dac_cram_to_argb(s->cram[i], 0);
    uint32_t backdrop = pal[s->reg[7] & 63];
    for (int i = 0; i < p->runs->count; ++i) {
        p->edge[i] = s_road[src].centre + p->runs->start[i];
        p->colour[i] = p->runs->index[i] ? pal[p->runs->index[i]] : backdrop;
    }
    p->edge[p->runs->count] = s_road[src].centre + 256;
}

static void build_terrain(int src, const RowPlan *p, int origin, int native_w,
                          int w1, int scale, const uint32_t *row) {
    const RoadRuns *runs = p->runs;
    int centre = s_road[src].centre, run = 0;
    for (int u = 0; u < w1; ++u) {
        int x = u - centre;                 /* atlas x this column shows */
        int native = u >= origin && u < origin + native_w;
        if (x < -256 || x > 255) {
            /* Inside the native picture the VDP wraps the plane there; the
             * margins continue the clamped exterior (tg2_video's road_x()). */
            if (native) { s_terrain[u] = 0; s_model[u] = row[u * scale]; continue; }
            x = x < -256 ? -256 : 255;
        }
        while (run + 1 < runs->count && runs->start[run + 1] <= x) ++run;
        s_terrain[u] = row[u * scale] == p->colour[run] &&
            !(s_native_serial[src] == s_serial && s_native_foreground[src][u]);
        s_model[u] = p->colour[run];
    }
}

/* Paint one presented row of a road row. `row` holds the nearest-expanded
 * native row and is rewritten where it shows scenery. */
static void paint_road_row(int src, int j, int scale, int w1, int native_w,
                           const RowPlan *p, uint32_t *row, const uint32_t *native_row, int filtered) {
    const RoadRuns *runs = p->runs;
    const RoadRow *m = &s_road[src];
    int origin = (w1 - native_w) / 2;
    /* Sub-row centre relative to the native row's centre, in rows. */
    double t = ((double)j + 0.5) / (double)scale - 0.5;
    int nb = t < 0 ? src - 1 : src + 1;
    double w = fabs(t);
    int interpolate = w > 0 && nb >= 0 && nb < TG2_HIGHRES_ROWS &&
                      s_road[nb].painted && s_road[nb].band == m->band;
    double el = m->fit_l, er = m->fit_r;
    if (interpolate) {
        el += w * (s_road[nb].fit_l - el);
        er += w * (s_road[nb].fit_r - er);
    }
    double own_l = p->edge[runs->first], own_r = p->edge[runs->last + 1];
    int structure = interpolate && same_structure(runs, &s_runs[nb]);
    const RoadRuns *other = structure ? &s_runs[nb] : NULL;
    double nb_l = 0, nb_w = 1;
    if (other) {
        nb_l = s_road[nb].raw_l;
        nb_w = s_road[nb].raw_r - s_road[nb].raw_l;
    }

    /* Where each run boundary is drawn. Road boundaries keep their relative
     * place inside the silhouette (moving toward the neighbour's when both
     * rows show the same structure); verge boundaries travel with the edge. */
    double q[ROAD_MAX_RUNS + 1];
    q[0] = -1e30;
    q[runs->count] = 1e30;
    for (int i = 1; i < runs->count; ++i) {
        if (i <= runs->first) {
            q[i] = p->edge[i] + (el - own_l);
        } else if (i > runs->last) {
            q[i] = p->edge[i] + (er - own_r);
        } else {
            double place = (p->edge[i] - own_l) / (own_r - own_l);
            if (other) {
                double there = (s_road[nb].centre + other->start[other->first + i - runs->first] -
                                nb_l) / nb_w;
                place += w * (there - place);
            }
            q[i] = el + place * (er - el);
        }
    }

    int run = 0;
    double inv = 1.0 / (double)scale;
    for (int u = 0; u < w1; ++u) {
        if (!s_terrain[u] && !filtered)
            continue;                        /* sprite / HUD / car / plane A */
        while (q[run + 1] <= u) ++run;
        uint32_t *out = row + u * scale;
        if (q[run + 1] >= u + 1) {           /* the whole column is one run */
            for (int k = 0; k < scale; ++k) out[k] = p->colour[run];
            continue;
        }
        int at = run;
        for (int k = 0; k < scale; ++k) {
            double x0 = u + k * inv, x1 = x0 + inv;
            while (q[at + 1] <= x0) ++at;
            if (q[at + 1] >= x1) {
                out[k] = p->colour[at];
                continue;
            }
            /* Analytic coverage of every run this output pixel overlaps. */
            double red = 0, green = 0, blue = 0, a = x0;
            for (int r = at; a < x1; ++r) {
                double b = q[r + 1] < x1 ? q[r + 1] : x1;
                double part = (b - a) * scale;
                uint32_t c = p->colour[r];
                red += part * ((c >> 16) & 255);
                green += part * ((c >> 8) & 255);
                blue += part * (c & 255);
                a = b;
            }
            out[k] = 0xFF000000u | ((uint32_t)(red + 0.5) << 16) |
                     ((uint32_t)(green + 0.5) << 8) | (uint32_t)(blue + 0.5);
        }
    }

    if (s_audit) {
        NxAuditRow *a = &s_audit[s_audit_count++];
        memset(a, 0, sizeof *a);
        a->line = src;
        a->sub = j;
        a->py = road_row_py(src);
        a->neighbour = interpolate ? nb - src : 0;
        a->band = m->band;
        a->own_l = (int32_t)own_l;
        a->own_r = (int32_t)own_r;
        a->nb_l = interpolate ? (int32_t)s_road[nb].raw_l : a->own_l;
        a->nb_r = interpolate ? (int32_t)s_road[nb].raw_r : a->own_r;
        a->el_x256 = (int32_t)floor(el * 256.0 + 0.5);
        a->er_x256 = (int32_t)floor(er * 256.0 + 0.5);
        /* "full": no sprite, HUD or car covers the strip or its two verges,
         * so the measured geometry is the whole strip. */
        int full = 1;
        int first = (int)floor((el < own_l ? el : own_l)) - 1;
        int last = (int)ceil((er > own_r ? er : own_r)) + 1;
        if (first < 0) first = 0;
        if (last > w1 - 1) last = w1 - 1;
        for (int u = first; u <= last; ++u)
            if (!s_terrain[u]) { full = 0; break; }
        a->flags = (interpolate ? NX_FLAG_INTERPOLATED : 0) | (full ? NX_FLAG_FULL : 0) |
                   (structure ? NX_FLAG_STRUCTURE : 0);
        /* Scenery may only move as far as the silhouette did. */
        double moved = fabs(el - own_l) > fabs(er - own_r) ? fabs(el - own_l) : fabs(er - own_r);
        nx_measure(a, runs, p->colour, row, native_row, scale, w1, origin, native_w,
                   (int)ceil(moved) + 1, m->centre, q);
    }
}

/* Qualification only: while a path is set, every built picture also writes
 * its native (1x) canvas there as a binary PPM, so a check can compare the
 * very same frame at 1x and at N x. Set over TCP (tg2_highres {"dump":"path"});
 * an empty path stops it. */
static char s_dump_path[1024];

int tg2_highres_native_dump_active(void) { return s_dump_path[0] != 0; }
void tg2_highres_request_native_dump(const char *path) {
    snprintf(s_dump_path, sizeof s_dump_path, "%s", path ? path : "");
}

static void native_dump(const uint32_t *pixels, int stride, int scale, int w1, int h) {
    FILE *f = fopen(s_dump_path, "wb");
    if (!f) { s_dump_path[0] = 0; return; }
    fprintf(f, "P6\n%d %d\n255\n", w1, h);
    for (int y = 0; y < h; ++y)
        for (int u = 0; u < w1; ++u) {
            uint32_t c = s_native_serial[y] == s_serial ? s_reference[y][u] : pixels[(size_t)y * stride + u * scale];
            unsigned char rgb[3] = {(unsigned char)(c >> 16), (unsigned char)(c >> 8),
                                    (unsigned char)c};
            fwrite(rgb, 1, 3, f);
        }
    fclose(f);
}

/* Bilinear RGB on native art, with premultiplied binary layer coverage.
 * The analytic road is the destination, never a source of this filter. A
 * footprint containing only plane B leaves the road byte-identical. */
static void filter_native(uint32_t *pixels, int stride, int w1, int scale,
                          int first, int last, FILE *coverage) {
    unsigned char mask_row[4096];
    int den = 2 * scale, area = den * den;
    for (int y = first * scale; y < last * scale; ++y) {
        int sy = y / scale, fy = 2 * (y % scale) + 1 - scale;
        if (fy < 0) { --sy; fy += den; }
        int y0 = sy < first ? first : sy, y1 = sy + 1 >= last ? last - 1 : sy + 1;
        const uint32_t *r0 = s_native_rgb[y0], *r1 = s_native_rgb[y1];
        const unsigned char *a0 = s_native_foreground[y0], *a1 = s_native_foreground[y1];
        uint32_t *row = pixels + (size_t)y * stride;
        for (int x = 0; x < w1 * scale; ++x) {
            int sx = x / scale, fx = 2 * (x % scale) + 1 - scale;
            if (fx < 0) { --sx; fx += den; }
            int x0 = sx < 0 ? 0 : sx, x1 = sx + 1 >= w1 ? w1 - 1 : sx + 1;
            int w00 = (den - fx) * (den - fy) * a0[x0];
            int w10 = fx * (den - fy) * a0[x1];
            int w01 = (den - fx) * fy * a1[x0];
            int w11 = fx * fy * a1[x1];
            int alpha = w00 + w10 + w01 + w11;
            if (coverage) mask_row[x] = (unsigned char)((alpha * 255 + area / 2) / area);
            if (!alpha) continue;
            uint32_t c00 = r0[x0], c10 = r0[x1], c01 = r1[x0], c11 = r1[x1];
            uint32_t out = 0xFF000000, under = row[x];
            for (int shift = 0; shift <= 16; shift += 8) {
                unsigned c = ((c00 >> shift) & 255) * w00 + ((c10 >> shift) & 255) * w10 +
                             ((c01 >> shift) & 255) * w01 + ((c11 >> shift) & 255) * w11 +
                             ((under >> shift) & 255) * (area - alpha);
                out |= ((c + area / 2) / area) << shift;
            }
            row[x] = out;
        }
        if (coverage) fwrite(mask_row, 1, (size_t)w1 * scale, coverage);
    }
}

int tg2_highres_build(uint64_t frame, uint32_t *pixels, int stride, int width,
                      int native_w, int native_h, int first, int last) {
    int scale = tg2_highres_present_scale();
    if (scale <= 1 || !pixels || width <= 0 || stride < width)
        return 0;
    if (width % scale || native_h <= 0 || native_h > TG2_HIGHRES_ROWS)
        return 0;
    int w1 = width / scale;
    if (w1 < native_w || w1 > 4096)
        return 0;
    int timing = highres_timing();
    double started = timing ? highres_now_us() : 0;
    int origin = (w1 - native_w) / 2;

    if (nx_audit_dir() && !s_audit)
        s_audit = malloc(sizeof *s_audit * TG2_HIGHRES_ROWS * TG2_HIGHRES_MAX_SCALE);
    s_audit_count = 0;
    if (s_dump_path[0])
        native_dump(pixels, stride, scale, w1, native_h);
    model_road(origin, native_h);
    int filtered = tg2_highres_linear_filter();
    if (filtered) {
        for (int y = 0; y < native_h; ++y)
            if (s_native_serial[y] != s_serial || s_native_width[y] != w1) {
                filtered = 0; ++s_filter_incomplete; break;
            }
    }
    if (filtered) {
        for (int y = 0; y < native_h; ++y) {
            if (!s_road[y].painted)
                memset(s_native_foreground[y], 1, (size_t)w1);
            else for (int u = origin; u < origin + native_w; ++u)
                if (u - s_road[y].centre < -256 || u - s_road[y].centre > 255)
                    s_native_foreground[y][u] = 1; /* native plane-B wrap */
        }
    }

    /* The row renderer produced one row per native line, already expanded
     * horizontally by N; each becomes N presented rows. Walk bottom-up so
     * reading native row `src` is never overwritten by the rows above it. */
    static uint32_t s_src_row[4096];
    static RowPlan plan;
    for (int src = native_h - 1; src >= 0; --src) {
        const uint32_t *native = pixels + (size_t)src * stride;
        memcpy(s_src_row, native, (size_t)width * sizeof *s_src_row);
        int road = s_road[src].painted;
        if (road) {
            plan_row(src, &plan);
            build_terrain(src, &plan, origin, native_w, w1, scale, s_src_row);
        }
        for (int j = 0; j < scale; ++j) {
            uint32_t *row = pixels + (size_t)(src * scale + j) * stride;
            /* Vertical nearest expansion first. The road pass then repaints
             * only scenery pixels; sprites, the HUD, the car and plane-A
             * effects keep this native row's pixels. */
            memcpy(row, s_src_row, (size_t)width * sizeof *row);
            if (road)
                paint_road_row(src, j, scale, w1, native_w, &plan, row, s_src_row, filtered);
        }
    }
    if (filtered) {
        if (first < 0 || first >= last || last > native_h) { first = 0; last = native_h; }
        /* Optional one-frame coverage evidence, aligned with the runner's
         * completed-frame capture number (the simulation tick is zero-based).
         * Stream rows; no full-frame diagnostic allocation or normal I/O. */
        FILE *coverage = NULL;
        const char *mask_frame = getenv("TG2_HIGHRES_FILTER_MASK_FRAME");
        const char *mask_path = getenv("TG2_HIGHRES_FILTER_MASK_PATH");
        if (mask_frame && mask_path && strtoull(mask_frame, NULL, 10) == frame + 1) {
            coverage = fopen(mask_path, "wb");
            if (coverage) fprintf(coverage, "P5\n%d %d\n255\n", width, (last - first) * scale);
        }
        filter_native(pixels, stride, w1, scale, first, last, coverage);
        if (coverage) fclose(coverage);
        ++s_filtered_frames;
    }
    const unsigned char *occluder[TG2_HIGHRES_ROWS];
    const unsigned short *front[TG2_HIGHRES_ROWS];
    for(int y=0;y<native_h;++y){occluder[y]=s_actor_occluder[y];front[y]=s_actor_front[y];}
    Tg2ActorCanvas actors={pixels,stride,width,scale,w1,origin,native_h,occluder,front,s_actor_row_ok,s_rows};
    tg2_actors_paint(&actors);
    nx_audit_write(frame, scale, w1, native_w);
    ++s_build_frames;
    if (timing) {
        double elapsed = highres_now_us() - started - s_clock_overhead;
        if (elapsed > 0) s_build_us += elapsed;
    }
    return native_h * scale;
}
