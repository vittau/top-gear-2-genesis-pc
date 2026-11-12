/* TG2 video: world (pure extraction from tg2_video.c). */
#include "tg2_video_internal.h"

int tg2v_tiles(int n) { return n == 1 ? 64 : n == 3 ? 128 : 32; }
unsigned tg2v_pixel(const GVDP *v, unsigned base, int x, int y, unsigned *attr) {
    int wt = tg2v_tiles(v->reg[16] & 3), ht = tg2v_tiles((v->reg[16] >> 4) & 3);
    unsigned a = tg2_word(v->vram, base + (((y >> 3) & (ht - 1)) * wt + ((x >> 3) & (wt - 1))) * 2);
    unsigned px = x & 7, py = y & 7;
    if (a & 0x800)
        px ^= 7;
    if (a & 0x1000)
        py ^= 7;
    unsigned b = v->vram[((a & 2047) * 32 + py * 4 + px / 2) & 65535];
    unsigned c = px & 1 ? b & 15 : b >> 4;
    *attr = a;
    return c ? ((a >> 9) & 48) | c : 0;
}
Tg2VideoScrollRow tg2v_rows[240];
unsigned tg2v_wide_lines, tg2v_native_lines, tg2v_frame_margin_pixels;
#ifdef GEN_ENABLE_TRACE
/* Read-only evidence for the race's transitional top raster/window band. */
Tg2VideoTopRow tg2v_top_rows[8];
#endif
/* The 512x512 B atlas holds four road templates in rows 0..431,
 * followed by ground separators and the skyline. The road's center is the atlas seam (X=0),
 * with exterior ground at X=256. Extend that exterior, never another road.
 * The skyline is an authored repeating panorama and retains its wrap. */
int tg2v_road_x(int nx, int scroll, int py) {
    py &= 511;
    if (py >= 448)
        return nx - scroll;
    /* Rows 432..439 are solid ground; 440..441 contain the hill's
     * half-width grass strip (the other half is transparent), followed by
     * blank separator rows. They are not a repeating panorama. Continue
     * each native edge through these rows without wrapping into the empty
     * half of the atlas. Keep the real road's unwrapped domain below. */
    if (py >= 432)
        return (nx < 0 ? 0 : nx > 255 ? 255 : nx) - scroll;
    int center = 128 + ((scroll - 128 + 256) & 511) - 256;
    int x = nx - center;
    return x < -256 ? -256 : x > 255 ? 255 : x;
}
/* Single-player HUD name-table ownership, verified from the race dumps:
 * $0004..$003C = left instruments, $003D..$0084 = map/lap/position.
 * The game changes their pattern data, not these cell identities. Testing
 * the live cells (rather than screen rectangles) follows every raster split
 * without accidentally moving the player car or the skyline effect cells. */
int tg2v_hud_tile(unsigned attr) {
    unsigned tile = attr & 2047;
    return (attr & 0x8000) && tile >= 4 && tile <= 0x84
               ? (tile < 0x3D ? -1 : 1) : 0;
}
/* The instrument clusters sit in fixed columns: the left one at x 16..79 and
 * the right one (map, lap, position) at x 176..239 (SAT at baseline frame
 * 180). The overtake popup ("18TH" rising over your car, x ~112..145) uses
 * the same font cells, so a tile match alone carried it to the right edge.
 * Only texels in the cluster columns move. Columns, not lines, so a split
 * screen's lower HUD keeps working. */
int tg2v_hud_region(int x, int side) {
    return side < 0 ? x < 96 : x >= 160;
}
unsigned tg2v_hud_plane_pixels, tg2v_hud_marker_pixels, tg2v_hud_sprite_pixels;
int tg2v_window_at(const GVDP *v, int line, int x);
void tg2v_hud_row(const GVDP *v, int line, int ha, int hb, int va, int vb,
                    unsigned ba, unsigned bb, const uint32_t *pal, int nw,
                    uint32_t *out, int w) {
    if (!tg2v_tg2_video_get_hud_mode() || nw != 256 || w <= nw)
        return;
    int origin = (w - nw) / 2, right = w - nw - origin;
    /* One row at a time, single-threaded: keep the scratch off the stack and
     * zero only what this row uses. */
    static unsigned char removed[256], sprites[256], shifted[4096];
    static unsigned short spr_attr[256], spr_front[256];
    memset(removed, 0, sizeof removed);
    memset(sprites, 0, sizeof sprites);
    memset(shifted, 0, sizeof shifted);
    memset(spr_attr, 0, sizeof spr_attr);
    memset(spr_front, 0, sizeof spr_front);
    int dirty = 0;
    /* Only relocate plane-A texels the display actually shows. The stock top
     * window band hides plane A, and there a nonnegative plane-A V-scroll
     * points at HUD cells that are not displayed instruments, so the window
     * decides per pixel instead of the scroll phase. The HUD raster otherwise
     * alternates between a signed-negative phase (-14 on this ROM) and a
     * nonnegative one (+92..+102) that pins the same cells to the same rows:
     * both display the same instruments and both must move. */
    for (int x = 0; x < nw; ++x) {
        if (tg2v_window_at(v, line, x))
            continue;
        unsigned attr, c = tg2v_pixel(v, ba, x - ha, line + va, &attr);
        int side = tg2v_hud_tile(attr);
        if (side && !tg2v_hud_region(x, side))
            side = 0;
        if (side && c) {
            removed[x] = 1;
            shifted[origin + x + (side < 0 ? -origin : right)] = c;
            if (!tg2v_reference_pass) ++tg2v_hud_plane_pixels;
            dirty = 1;
        }
    }
    /* The map's 1P/leader markers bypass the scenery mapper. ROM $00FE8A
     * positions two 2x2 sprites from $FF8B76/$FF8B7E; $00F468 copies them
     * into the SAT. Read the displayed SAT, never the next CPU picture. */
    unsigned sat = (v->reg[5] & 127) << 9;
    int link = 0, on_line = 0, budget = nw;
    static unsigned char occupied[4096];
    memset(occupied, 0, sizeof occupied);
    for (int n = 0; n < 64; ++n) {
        unsigned e = sat + link * 8;
        int y = (tg2_word(v->vram, e) & 1023) - 128;
        unsigned size = v->vram[(e + 2) & 65535], attr = tg2_word(v->vram, e + 4);
        int sw = (((size >> 2) & 3) + 1) * 8, sh = ((size & 3) + 1) * 8;
        int next = v->vram[(e + 3) & 65535] & 127;
        if (line >= y && line < y + sh) {
            if (++on_line > 16)
                break;
            int xword = tg2_word(v->vram, e + 6) & 1023;
            if (!xword && on_line > 1)
                break;
            int x = xword - 128, sy = line - y;
            int skip_actor = tg2v_actor_free && tg2v_promoted_sat(link);
            int marker = size == 5 && (attr & 0x8000) &&
                         ((attr & 2047) == 0x106 || (attr & 2047) == 0x10E);
            /* The game also draws the whole instrument cluster as sprites,
             * with the same pattern IDs the plane-A cells use, on frames where
             * it takes the HUD off plane A (measured at baseline frames
             * 3409..3585: patterns $04..$7D in eight 32-pixel sprites plus the
             * two markers). They belong to the same left/right clusters and
             * must move with them, or the map separates from its markers. */
            int side = marker ? 1 : tg2v_hud_tile(attr);
            if (!marker && side && !tg2v_hud_region(x, side))
                side = 0;
            int hud = marker || side != 0;
            if (attr & 0x1000)
                sy = sh - 1 - sy;
            for (int dx = 0; dx < sw; ++dx) {
                int nx = x + dx, ox = origin + nx + (hud ? (side < 0 ? -origin : right) : 0);
                int sx = attr & 0x800 ? sw - 1 - dx : dx;
                unsigned tile = ((attr & 2047) + (sx / 8) * (sh / 8) + sy / 8) & 2047;
                unsigned data = v->vram[(tile * 32 + (sy & 7) * 4 + (sx & 7) / 2) & 65535];
                unsigned c = sx & 1 ? data & 15 : data >> 4;
                if (!c || skip_actor)
                    continue;
                c |= (attr >> 9) & 48;
                if (tg2v_window_at(v, line, nx < 0 ? 0 : nx > nw - 1 ? nw - 1 : nx))
                    continue;   /* the window hides plane A *and* sprites */
                if (hud && nx >= 0 && nx < nw) {
                    removed[nx] = 1;
                    dirty = 1;
                }
                if (ox < 0 || ox >= w || occupied[ox])
                    continue;
                occupied[ox] = 1;
                if (hud) {
                    shifted[ox] = c;
                    if (!tg2v_reference_pass) {
                        if (marker) ++tg2v_hud_marker_pixels;
                        else ++tg2v_hud_sprite_pixels;
                    }
                } else if (nx >= 0 && nx < nw) {
                    sprites[nx] = c;
                    spr_attr[nx] = attr;
                    int piece=tg2v_shown && link<64?tg2v_shown->sat_piece[link]:-1;
                    spr_front[nx]=piece<0?65535:piece+1;
                }
            }
            budget -= sw;
            if (budget <= 0)
                break;
        }
        if (!next)
            break;
        link = next;
    }
    if (!dirty)
        return;
    /* Restore only vacated opaque HUD pixels. Retain the actual plane B,
     * any non-HUD plane A, and ordinary SAT sprites underneath, with the
     * native priority order. Transparent HUD pixels never copy sky over an
     * actor, and unrelated native pixels remain the original framebuffer. */
    for (int x = 0; x < nw; ++x) {
        if (!removed[x])
            continue;
        unsigned a, b, ap = tg2v_pixel(v, ba, x - ha, line + va, &a);
        unsigned bp = tg2v_pixel(v, bb, x - hb, line + vb, &b), sp = sprites[x];
        if (tg2v_hud_tile(a))
            ap = 0;
        unsigned c = sp && (spr_attr[x] & 0x8000) ? sp :
                     ap && (a & 0x8000) ? ap : bp && (b & 0x8000) ? bp :
                     sp ? sp : ap ? ap : bp ? bp : v->reg[7] & 63;
        out[origin + x] = pal[c];
        if (tg2v_actor_front) tg2v_actor_front[origin+x] = sp ? spr_front[x] : 0;
        if (tg2v_actor_occluder) tg2v_actor_occluder[origin+x] = (ap && (a&0x8000)) || (bp && (b&0x8000));
        if (tg2v_filter_foreground)
            tg2v_filter_foreground[origin + x] = (sp && (spr_attr[x] & 0x8000)) ||
                (ap && (a & 0x8000)) || (!(bp && (b & 0x8000)) && (sp || ap));
    }
    for (int x = 0; x < w; ++x)
        if (shifted[x]) {
            out[x] = pal[shifted[x]];
            if (tg2v_actor_front) tg2v_actor_front[x] = 65535;
            if (tg2v_filter_foreground) tg2v_filter_foreground[x] = 1;
        }
}
/* Window coordinates are unscrolled, with a 32-cell stride in H32. Only
 * extend an opaque, solid native edge: transparent window texels can expose
 * authored panorama detail that must keep its ordinary continuation. */
int tg2v_window_at(const GVDP *v, int line, int x) {
    unsigned wx = v->reg[17], wy = v->reg[18];
    return ((wy & 128) ? line >= (wy & 31) * 8 : line < (wy & 31) * 8) ||
           ((wx & 128) ? x >= (wx & 31) * 16 : x < (wx & 31) * 16);
}
static int edge_solid(const uint32_t *native, int nw, int side) {
    int edge = side ? nw - 1 : 0, step = side ? -1 : 1;
    for (int i = 1; i < 8; ++i)
        if (native[edge + step * i] != native[edge]) return 0;
    return 1;
}
static int window_band_edge(const GVDP *v, int line, const uint32_t *native,
                            int nw, int side) {
    int edge = side ? nw - 1 : 0, step = side ? -1 : 1;
    if (!tg2v_window_at(v, line, edge) || !edge_solid(native, nw, side)) return 0;
    unsigned base = (v->reg[3] & 63) << 10;
    for (int i = 0; i < 8; ++i) {
        int x = edge + step * i;
        if (!tg2v_window_at(v, line, x)) return 0;
        unsigned attr = tg2_word(v->vram, base + ((line / 8) * 32 + x / 8) * 2);
        if (!(attr & 0x8000)) return 0;
        unsigned px = x & 7, py = line & 7;
        if (attr & 0x800) px ^= 7;
        if (attr & 0x1000) py ^= 7;
        unsigned data = v->vram[((attr & 2047) * 32 + py * 4 + px / 2) & 65535];
        unsigned c = px & 1 ? data & 15 : data >> 4;
        if (!c || genesis_dac_cram_to_argb(v->cram[((attr >> 9) & 48) | c], 0) != native[edge])
            return 0;
    }
    return 1;
}
unsigned tg2v_window_margins(const GVDP *v, int line, const uint32_t *native,
                           int nw, uint32_t *out, int w) {
    int origin = (w - nw) / 2;
    unsigned mask = window_band_edge(v, line, native, nw, 0) |
                    (window_band_edge(v, line, native, nw, 1) << 1);
    if (mask & 1)
        for (int x = 0; x < origin; ++x) {
            out[x] = native[0];
            if (tg2v_filter_foreground) tg2v_filter_foreground[x] = 1;
        }
    if (mask & 2)
        for (int x = origin + nw; x < w; ++x) {
            out[x] = native[nw - 1];
            if (tg2v_filter_foreground) tg2v_filter_foreground[x] = 1;
        }
    return mask;
}
/* A surface that owns the native edge covers several adjacent plane-A
 * texels. The weather overlay (rain/snow) is the opposite: one or two
 * high-priority texels on an otherwise transparent plane, moving with the
 * raster scroll. Continuing a weather texel's colour painted a full-width
 * one-line streak into both margins (task 22 finding), while the tunnel wall
 * must still continue. The opaque run length separates the two. */
static int plane_a_edge_run(const GVDP *v, int line, int ha, int va,
                            unsigned ba, int nw, int side) {
    int edge = side ? nw - 1 : 0, step = side ? -1 : 1, run = 0;
    for (int i = 0; i < 8; ++i) {
        unsigned attr, ap = tg2v_pixel(v, ba, edge + step * i - ha, line + va, &attr);
        if (!ap || !(attr & 0x8000)) break;
        ++run;
    }
    return run;
}
/* Plane A also carries raster-positioned full-screen effects, such as the
 * Auckland tunnel wall and its opening. When an opaque high-priority plane-A
 * texel is the visible native edge pixel, the margin continues that native
 * edge colour to the screen edge, so a wall never turns into the plane-B
 * scenery it hides. Sampling plane A farther out is not equivalent: the
 * overlay's silhouette can end exactly at the native edge, and continuing a
 * neighbouring texel would leave a seam. The native centre is untouched, and
 * an ordinary plane-B edge (or a sprite over it) never qualifies. */
unsigned tg2v_pa_extend_mask;
void tg2v_plane_a_margins(const GVDP *v, int line, const uint32_t *native,
                            int nw, const uint32_t *pal, uint32_t *out, int w,
                            int ha, int va, unsigned ba) {
    int origin = (w - nw) / 2;
    for (int side = 0; side < 2; ++side) {
        int edge = side ? nw - 1 : 0;
        unsigned attr, ap = tg2v_pixel(v, ba, edge - ha, line + va, &attr);
        if (!ap || !(attr & 0x8000) || pal[ap] != native[edge]) continue;
        if (plane_a_edge_run(v, line, ha, va, ba, nw, side) < 8) continue;
        tg2v_pa_extend_mask |= 1u << side;
        if (side)
            for (int x = origin + nw; x < w; ++x) {
                out[x] = native[edge];
                if (tg2v_filter_foreground) tg2v_filter_foreground[x] = 1;
            }
        else
            for (int x = 0; x < origin; ++x) {
                out[x] = native[edge];
                if (tg2v_filter_foreground) tg2v_filter_foreground[x] = 1;
            }
    }
}
/* $2B20..$2BEC installs the weather map at C800/C840 (atlas rows
 * 128..383, both 256-pixel halves). $87EA..$887A animates it through
 * plane A's per-line H/V scroll. Continue those coordinates, not an edge
 * colour; the rest of A contains HUD/car/tunnel art and must not repeat. */
unsigned tg2v_weather_pixel(const GVDP *v, int line, int nx,
                              int ha, int va, unsigned ba) {
    int y = (line + va) & 511;
    if (y < 128 || y >= 384) return 0;
    unsigned attr, ap = tg2v_pixel(v, ba, nx - ha, y, &attr);
    return (attr & 0x8000) ? ap : 0;
}
#ifdef GEN_ENABLE_TRACE
/* Private per-line margin evidence, before sprites and HUD relocation.
 * Audits every presented picture, synthesized included. */
static FILE *margin_audit;
static int margin_audit_checked;

void tg2v_audit_margins(const GVDP *v, int line, const uint32_t *native,
                          int nw, const uint32_t *out, int w) {
    if (tg2v_reference_pass) return; /* evidence pass is not another presented row */
    if (!margin_audit_checked) {
        margin_audit_checked = 1;
        const char *path = getenv("TG2_MARGIN_AUDIT");
        if (path && *path) {
            margin_audit = fopen(path, "w");
            if (!margin_audit) { perror(path); exit(1); }
            fprintf(margin_audit, "frame,line,side,native,margin,ap,attr_a,bp,attr_b,backdrop,atlas_y,slope,margin_bp,native_b,edge_solid,window_band,backdrop_band,pa_run,pa_extend,margin_weather\n");
        }
    }
    if (!margin_audit || w <= nw) return;
    unsigned ba = (v->reg[2] & 56) << 10, bb = (v->reg[4] & 7) << 13;
    unsigned hbase = (v->reg[13] & 63) << 10;
    int hm = v->reg[11] & 3, hi = hm == 0 ? 0 : hm == 2 ? line & ~7 : line;
    int ha = tg2_word(v->vram, hbase + hi * 4) & 1023, hb = tg2_word(v->vram, hbase + hi * 4 + 2) & 1023;
    int va = v->vsram[0] & 1023, vb = v->vsram[1] & 1023;
    int origin = (w - nw) / 2;
    for (int side = 0; side < 2; ++side) {
        int edge = side ? nw - 1 : 0;
        unsigned aa, ab;
        unsigned ap = tg2v_pixel(v, ba, edge - ha, line + va, &aa);
        unsigned bp = tg2v_pixel(v, bb, edge - hb, line + vb, &ab);
        unsigned mb_attr;
        unsigned mb = tg2v_pixel(v, bb, tg2v_road_x(side ? nw : -1, hb, line + vb), line + vb, &mb_attr);
        int solid = edge_solid(native, nw, side);
        int backdrop = solid && native[edge] == genesis_dac_cram_to_argb(v->cram[v->reg[7] & 63], 0);
        for (int i = 0; backdrop && i < 8; ++i) {
            int x = edge + (side ? -i : i);
            unsigned attr;
            if ((v->reg[1] & 64) &&
                (tg2v_pixel(v, ba, x - ha, line + va, &attr) ||
                 tg2v_pixel(v, bb, x - hb, line + vb, &attr))) backdrop = 0;
        }
        fprintf(margin_audit, "%llu,%d,%d,%u,%u,%u,%u,%u,%u,%u,%d,%d,%u,%u,%d,%d,%d,%d,%d,%u\n",
                (unsigned long long)tg2v_present_frame, line, side, native[edge],
                out[origin + (side ? nw : -1)], ap, aa, bp, ab,
                v->reg[7] & 63, (line + vb) & 511, (int16_t)tg2_word(g_ram, 0x18E0), mb,
                genesis_dac_cram_to_argb(v->cram[bp ? bp : v->reg[7] & 63], 0),
                solid, window_band_edge(v, line, native, nw, side), backdrop,
                plane_a_edge_run(v, line, ha, va, ba, nw, side),
                (tg2v_pa_extend_mask >> side) & 1,
                /* A rain/snow particle the margin continuation drew there. */
                tg2v_weather_pixel(v, line, side ? nw : -1, ha, va, ba));
    }
    if (line == 223) fflush(margin_audit);
}
#endif
