/* TG2 USA presentation. Guest raster state is authoritative on every row. */
#include "tg2_video.h"
#include "cmd_server.h"
#include "genesis_runtime.h"
#include "video/genesis_dac.h"
#include "video/genesis_vdp.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int mode;
static int race60;
static uint64_t present_frame;
static void presentation_clear(void);
static int hud_edges, hud_configured;
void tg2_video_set_hud_mode(int edges) {
    hud_edges = edges != 0;
    hud_configured = 1;
}
int tg2_video_get_hud_mode(void) {
    if (!hud_configured) {
        const char *s = getenv("TG2_HUD_MODE");
        tg2_video_set_hud_mode(s && (!strcmp(s, "edges") || !strcmp(s, "1")));
    }
    return hud_edges;
}
static double ratio = 16.0 / 9.0;
static unsigned word(const unsigned char *p, unsigned a) {
    return (p[a & 65535] << 8) | p[(a + 1) & 65535];
}
static int configure(const char *s) {
    if (!s)
        return 0;
    if (!strcmp(s, "off")) {
        tg2_video_reset();
        mode = 0;
        return 1;
    }
    if (!strcmp(s, "fit") || !strcmp(s, "adaptive")) {
        tg2_video_reset();
        mode = 1;
        return 1;
    }
    char *end;
    double w = strtod(s, &end);
    if (end == s || *end != ':')
        return 0;
    const char *hstart = end + 1;
    double h = strtod(hstart, &end);
    if (end == hstart || *end || !isfinite(w) || !isfinite(h) || w <= 0 || h <= 0 || w / h > 32)
        return 0;
    tg2_video_reset();
    ratio = w / h;
    mode = 2;
    return 1;
}
static int enabled(void) { return mode != 0; }
static int renderer_enabled(void) { return mode != 0 || race60; }
static int width(int dw, int dh, int nw, int nh) {
    double w = nh * (mode == 2 ? ratio : dw > 0 && dh > 0 ? (double)dw / dh : 4.0 / 3.0);
    int result = w > 4096 ? 4096 : (int)(w + 0.5);
    return result < nw ? nw : result;
}
/* Snapshots match the SAT actually displayed, rather than the CPU's next
 * scene. These hooks only read registers, RAM and ROM. */
enum { MAX_PIECES = 2048, HISTORY = 4 };
typedef struct {
    int x, y;
    unsigned attr, size;
} Piece;
typedef struct {
    Piece pieces[MAX_PIECES];
    unsigned count, serial, sat_size;
    unsigned char sat[512];
} Scene;
static Scene building, history[HISTORY];
static const Scene *shown;
static unsigned serial, overflow, matched_pieces, margin_pieces;
static unsigned read16(unsigned a) {
    a &= 0xFFFFFF;
    if (a < 0xFFFFF)
        return (g_rom[a] << 8) | g_rom[a + 1];
    if (a >= 0xFF0000)
        return word(g_ram, a);
    return 0;
}
static unsigned read32(unsigned a) { return (read16(a) << 16) | read16(a + 2); }
void tg2_video_reset(void) {
    presentation_clear();
    memset(&building, 0, sizeof building);
    memset(history, 0, sizeof history);
    shown = NULL;
    serial = overflow = matched_pieces = margin_pieces = 0;
}
int tg2_video_hook(uint32_t pc) {
    if (!renderer_enabled())
        return 0;
    if (pc == 0x67EE)
        building.count = 0;
    else if (pc == 0x6982) {
        unsigned index = word(g_ram, 0x22D8);
        if (index > 127)
            return 0;
        building.sat_size = (127 - index) * 8;
        if (building.sat_size > 512)
            building.sat_size = 512;
        unsigned src = read32(0xFF2316) + index * 8;
        for (unsigned i = 0; i < building.sat_size; i++)
            building.sat[i] = g_ram[(src + i) & 65535];
        building.serial = ++serial;
        history[serial % HISTORY] = building;
    } else if (pc == 0xB5FA && !word(g_ram, 0x189E)) {
        unsigned p = g_cpu.A[1] & 0xFFFFFF, header = g_cpu.A[0] & 0xFFFFFF;
        unsigned count = g_cpu.D[7] & 65535;
        if (count > 128)
            return 0;
        int x = (int16_t)g_cpu.D[1], y = (int16_t)g_cpu.D[2] - (int16_t)read16(header);
        unsigned attr = read16(header + 2) | (g_cpu.D[5] & 65535);
        if (word(g_ram, 0x1878) != 0xFD66)
            x += (read16(header + 2) & 0x800) ? (int16_t)g_cpu.D[6] : -(int16_t)g_cpu.D[6];
        for (unsigned i = 0; i < count; i++, p += 8) {
            unsigned sz = read16(p + 2) >> 8, pa = read16(p + 4);
            int pw = (((sz >> 2) & 3) + 1) * 8, ph = ((sz & 3) + 1) * 8;
            int px = x + (attr & 0x800 ? -(int16_t)read16(p + 6) - pw : (int16_t)read16(p + 6));
            int py = y + (int16_t)read16(p);
            /* Original vertical occlusion/culling. X alone is expanded. */
            if (py >= (int16_t)word(g_ram, 0x1836) ||
                py + (int)(read16(p + 2) & 255) >= (int16_t)word(g_ram, 0x1836) ||
                py + ph <= (int16_t)word(g_ram, 0x23E6))
                continue;
            if (building.count == MAX_PIECES) {
                ++overflow;
                break;
            }
            Piece *piece = &building.pieces[building.count++];
            piece->x = px;
            piece->y = py + (int16_t)word(g_ram, 0x2452) - 128;
            piece->size = sz & 15;
            piece->attr = (((attr ^ (pa & 0x1800)) + (pa & 2047)) | word(g_ram, 0x234E)) & 65535;
            if (g_ram[0x22E8])
                piece->attr |= 0x8000;
        }
    }
    return 0;
}
static void select_scene(const GVDP *v) {
    matched_pieces = margin_pieces = 0;
    shown = NULL;
    unsigned base = (v->reg[5] & 127) << 9;
    for (unsigned i = 0; i < HISTORY; ++i) {
        Scene *sc = &history[i];
        if (!sc->serial || (shown && shown->serial > sc->serial))
            continue;
        unsigned k = 0;
        while (k < sc->sat_size && sc->sat[k] == v->vram[(base + k) & 65535])
            ++k;
        if (k == sc->sat_size && k)
            shown = sc;
    }
    if (shown)
        for (unsigned i = 0; i < shown->count; ++i) {
            const Piece *p = &shown->pieces[i];
            if (p->x < 0 || p->x + ((((p->size >> 2) & 3) + 1) * 8) > 256)
                ++margin_pieces;
            for (unsigned k = 0; k < shown->sat_size; k += 8) {
                const unsigned char *q = shown->sat + k;
                if (((word(q, 0) & 511) - 128) == (unsigned)p->y &&
                    ((word(q, 6) & 511) - 128) == (unsigned)p->x && (q[2] & 15) == p->size &&
                    word(q, 4) == p->attr) {
                    ++matched_pieces;
                    break;
                }
            }
        }
}
static int tiles(int n) { return n == 1 ? 64 : n == 3 ? 128 : 32; }
static unsigned pixel(const GVDP *v, unsigned base, int x, int y, unsigned *attr) {
    int wt = tiles(v->reg[16] & 3), ht = tiles((v->reg[16] >> 4) & 3);
    unsigned a = word(v->vram, base + (((y >> 3) & (ht - 1)) * wt + ((x >> 3) & (wt - 1))) * 2);
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
static struct {
    int ha, hb, va, vb;
    unsigned a, b;
} rows[240];
static unsigned wide_lines, native_lines, frame_margin_pixels;
/* Read-only evidence for the race's transitional top raster/window band. */
static struct {
    unsigned char reg[24];
    unsigned short vsram[2], cram[64];
} top_rows[8];
static int race(const GVDP *v) {
    unsigned op = word(g_ram, 0xF9FE);
    return !(v->reg[12] & 15) && v->reg[16] == 0x11 && ((v->reg[2] & 56) << 10) == 0xC000 &&
           ((v->reg[4] & 7) << 13) == 0xE000 && !word(g_ram, 0x189E) &&
           (op == 0x2C9D || op == 0x601E || op == 0x6042);
}
/* The 512x512 B atlas holds four road templates in rows 0..431,
 * followed by ground separators and the skyline. The road's center is the atlas seam (X=0),
 * with exterior ground at X=256. Extend that exterior, never another road.
 * The skyline is an authored repeating panorama and retains its wrap. */
static int road_x(int nx, int scroll, int py) {
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
static int hud_tile(unsigned attr) {
    unsigned tile = attr & 2047;
    return (attr & 0x8000) && tile >= 4 && tile <= 0x84
               ? (tile < 0x3D ? -1 : 1) : 0;
}
static unsigned hud_plane_pixels, hud_marker_pixels;
static void hud_row(const GVDP *v, int line, int ha, int hb, int va, int vb,
                    unsigned ba, unsigned bb, const uint32_t *pal, int nw,
                    uint32_t *out, int w) {
    if (!tg2_video_get_hud_mode() || nw != 256 || w <= nw)
        return;
    int origin = (w - nw) / 2, right = w - nw - origin;
    unsigned char removed[256] = {0}, sprites[256] = {0}, shifted[4096] = {0};
    unsigned short spr_attr[256] = {0};
    int dirty = 0;
    /* The HUD raster phase uses signed-negative 10-bit V-scroll (-14 on
     * this ROM). During the initial window-plane band, nonnegative plane-A
     * scroll can point at HUD cells hidden behind that window. They are
     * not displayed instruments and must not be relocated. */
    for (int x = 0; (va & 512) && x < nw; ++x) {
        unsigned attr, c = pixel(v, ba, x - ha, line + va, &attr);
        int side = hud_tile(attr);
        if (side && c) {
            removed[x] = 1;
            shifted[origin + x + (side < 0 ? -origin : right)] = c;
            ++hud_plane_pixels;
            dirty = 1;
        }
    }
    /* The map's 1P/leader markers bypass the scenery mapper. ROM $00FE8A
     * positions two 2x2 sprites from $FF8B76/$FF8B7E; $00F468 copies them
     * into the SAT. Read the displayed SAT, never the next CPU picture. */
    unsigned sat = (v->reg[5] & 127) << 9;
    int link = 0, on_line = 0, budget = nw;
    unsigned char occupied[4096] = {0};
    for (int n = 0; n < 64; ++n) {
        unsigned e = sat + link * 8;
        int y = (word(v->vram, e) & 1023) - 128;
        unsigned size = v->vram[(e + 2) & 65535], attr = word(v->vram, e + 4);
        int sw = (((size >> 2) & 3) + 1) * 8, sh = ((size & 3) + 1) * 8;
        int next = v->vram[(e + 3) & 65535] & 127;
        if (line >= y && line < y + sh) {
            if (++on_line > 16)
                break;
            int xword = word(v->vram, e + 6) & 1023;
            if (!xword && on_line > 1)
                break;
            int x = xword - 128, sy = line - y;
            int marker = size == 5 && (attr & 0x8000) &&
                         ((attr & 2047) == 0x106 || (attr & 2047) == 0x10E);
            if (attr & 0x1000)
                sy = sh - 1 - sy;
            for (int dx = 0; dx < sw; ++dx) {
                int nx = x + dx, ox = origin + nx + (marker ? right : 0);
                int sx = attr & 0x800 ? sw - 1 - dx : dx;
                unsigned tile = ((attr & 2047) + (sx / 8) * (sh / 8) + sy / 8) & 2047;
                unsigned data = v->vram[(tile * 32 + (sy & 7) * 4 + (sx & 7) / 2) & 65535];
                unsigned c = sx & 1 ? data & 15 : data >> 4;
                if (!c)
                    continue;
                c |= (attr >> 9) & 48;
                if (marker && nx >= 0 && nx < nw) {
                    removed[nx] = 1;
                    dirty = 1;
                }
                if (ox < 0 || ox >= w || occupied[ox])
                    continue;
                occupied[ox] = 1;
                if (marker) {
                    shifted[ox] = c;
                    ++hud_marker_pixels;
                } else if (nx >= 0 && nx < nw) {
                    sprites[nx] = c;
                    spr_attr[nx] = attr;
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
        unsigned a, b, ap = pixel(v, ba, x - ha, line + va, &a);
        unsigned bp = pixel(v, bb, x - hb, line + vb, &b), sp = sprites[x];
        if (hud_tile(a))
            ap = 0;
        unsigned c = sp && (spr_attr[x] & 0x8000) ? sp :
                     ap && (a & 0x8000) ? ap : bp && (b & 0x8000) ? bp :
                     sp ? sp : ap ? ap : bp ? bp : v->reg[7] & 63;
        out[origin + x] = pal[c];
    }
    for (int x = 0; x < w; ++x)
        if (shifted[x])
            out[x] = pal[shifted[x]];
}
/* Window coordinates are unscrolled, with a 32-cell stride in H32. Only
 * extend an opaque, solid native edge: transparent window texels can expose
 * authored panorama detail that must keep its ordinary continuation. */
static int window_at(const GVDP *v, int line, int x) {
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
    if (!window_at(v, line, edge) || !edge_solid(native, nw, side)) return 0;
    unsigned base = (v->reg[3] & 63) << 10;
    for (int i = 0; i < 8; ++i) {
        int x = edge + step * i;
        if (!window_at(v, line, x)) return 0;
        unsigned attr = word(v->vram, base + ((line / 8) * 32 + x / 8) * 2);
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
static unsigned window_margins(const GVDP *v, int line, const uint32_t *native,
                           int nw, uint32_t *out, int w) {
    int origin = (w - nw) / 2;
    unsigned mask = window_band_edge(v, line, native, nw, 0) |
                    (window_band_edge(v, line, native, nw, 1) << 1);
    if (mask & 1)
        for (int x = 0; x < origin; ++x) out[x] = native[0];
    if (mask & 2)
        for (int x = origin + nw; x < w; ++x) out[x] = native[nw - 1];
    return mask;
}
/* Private per-line margin evidence, before sprites and HUD relocation. */
static FILE *margin_audit;
static int margin_audit_checked;
static void audit_margins(const GVDP *v, int line, const uint32_t *native,
                          int nw, const uint32_t *out, int w) {
    if (!margin_audit_checked) {
        margin_audit_checked = 1;
        const char *path = getenv("TG2_MARGIN_AUDIT");
        if (path && *path) {
            margin_audit = fopen(path, "w");
            if (!margin_audit) { perror(path); exit(1); }
            fprintf(margin_audit, "frame,line,side,native,margin,ap,attr_a,bp,attr_b,backdrop,atlas_y,slope,margin_bp,native_b,edge_solid,window_band,backdrop_band\n");
        }
    }
    if (!margin_audit || w <= nw) return;
    unsigned ba = (v->reg[2] & 56) << 10, bb = (v->reg[4] & 7) << 13;
    unsigned hbase = (v->reg[13] & 63) << 10;
    int hm = v->reg[11] & 3, hi = hm == 0 ? 0 : hm == 2 ? line & ~7 : line;
    int ha = word(v->vram, hbase + hi * 4) & 1023, hb = word(v->vram, hbase + hi * 4 + 2) & 1023;
    int va = v->vsram[0] & 1023, vb = v->vsram[1] & 1023;
    int origin = (w - nw) / 2;
    for (int side = 0; side < 2; ++side) {
        int edge = side ? nw - 1 : 0;
        unsigned aa, ab;
        unsigned ap = pixel(v, ba, edge - ha, line + va, &aa);
        unsigned bp = pixel(v, bb, edge - hb, line + vb, &ab);
        unsigned mb_attr;
        unsigned mb = pixel(v, bb, road_x(side ? nw : -1, hb, line + vb), line + vb, &mb_attr);
        int solid = edge_solid(native, nw, side);
        int backdrop = solid && native[edge] == genesis_dac_cram_to_argb(v->cram[v->reg[7] & 63], 0);
        for (int i = 0; backdrop && i < 8; ++i) {
            int x = edge + (side ? -i : i);
            unsigned attr;
            if ((v->reg[1] & 64) &&
                (pixel(v, ba, x - ha, line + va, &attr) ||
                 pixel(v, bb, x - hb, line + vb, &attr))) backdrop = 0;
        }
        fprintf(margin_audit, "%llu,%d,%d,%u,%u,%u,%u,%u,%u,%u,%d,%d,%u,%u,%d,%d,%d\n",
                (unsigned long long)present_frame, line, side, native[edge],
                out[origin + (side ? nw : -1)], ap, aa, bp, ab,
                v->reg[7] & 63, (line + vb) & 511, (int16_t)word(g_ram, 0x18E0), mb,
                genesis_dac_cram_to_argb(v->cram[bp ? bp : v->reg[7] & 63], 0),
                solid, window_band_edge(v, line, native, nw, side), backdrop);
    }
    if (line == 223) fflush(margin_audit);
}
static int synthesizing, audit_race_frame;
static void draw_scanline(const GVDP *v, int line, const uint32_t *native, int nw, uint32_t *out,
                     int w) {
    int origin = (w - nw) / 2;
    if (!line) audit_race_frame = nw == 256 && race(v);
    if (line < 8) {
        memcpy(top_rows[line].reg, v->reg, sizeof top_rows[line].reg);
        memcpy(top_rows[line].vsram, v->vsram, sizeof top_rows[line].vsram);
        memcpy(top_rows[line].cram, v->cram, sizeof top_rows[line].cram);
    }
    if (!line) {
        frame_margin_pixels = 0;
        hud_plane_pixels = hud_marker_pixels = 0;
    }
    for (int x = 0; x < w; ++x)
        out[x] = 0xFF000000;
    if (!race(v) || !(v->reg[1] & 64)) {
        ++native_lines;
        memcpy(out + origin, native, nw * sizeof *out);
        if (audit_race_frame) {
            window_margins(v, line, native, nw, out, w);
            audit_margins(v, line, native, nw, out, w);
        }
        return;
    }
    ++wide_lines;
    if (!line && !synthesizing)
        select_scene(v);
    unsigned ba = (v->reg[2] & 56) << 10, bb = (v->reg[4] & 7) << 13;
    unsigned hbase = (v->reg[13] & 63) << 10;
    int hm = v->reg[11] & 3, hi = hm == 0 ? 0 : hm == 2 ? line & ~7 : line;
    int ha = word(v->vram, hbase + hi * 4) & 1023, hb = word(v->vram, hbase + hi * 4 + 2) & 1023;
    int va = v->vsram[0] & 1023, vb = v->vsram[1] & 1023;
    rows[line].ha = ha;
    rows[line].hb = hb;
    rows[line].va = va;
    rows[line].vb = vb;
    rows[line].a = ba;
    rows[line].b = bb;
    uint32_t pal[64];
    for (int i = 0; i < 64; ++i)
        pal[i] = genesis_dac_cram_to_argb(v->cram[i], 0);
    for (int x = 0; x < w; ++x) {
        int nx = x - origin;
        if (nx >= 0 && nx < nw)
            continue;
        unsigned b;
        unsigned bp = pixel(v, bb, road_x(nx, hb, line + vb), line + vb, &b);
        out[x] = pal[bp ? bp : v->reg[7] & 63];
    }
    unsigned window_mask = window_margins(v, line, native, nw, out, w);
    if (audit_race_frame) audit_margins(v, line, native, nw, out, w);
    /* Reverse allocation order matches the native backward SAT builder. */
    unsigned char covered[4096] = {0};
    for (unsigned n = shown ? shown->count : 0; n > 0; --n) {
        const Piece *s = &shown->pieces[n - 1];
        int sw = (((s->size >> 2) & 3) + 1) * 8, sh = ((s->size & 3) + 1) * 8;
        int sy = line - s->y;
        if (sy < 0 || sy >= sh)
            continue;
        if (s->attr & 0x1000)
            sy = sh - 1 - sy;
        for (int dx = 0; dx < sw; ++dx) {
            int nx = s->x + dx, ox = origin + nx;
            if (ox < 0 || ox >= w || (nx >= 0 && nx < nw) || covered[ox])
                continue;
            int sx = s->attr & 0x800 ? sw - 1 - dx : dx;
            unsigned tile = ((s->attr & 2047) + (sx / 8) * (sh / 8) + sy / 8) & 2047;
            unsigned data = v->vram[(tile * 32 + (sy & 7) * 4 + (sx & 7) / 2) & 65535];
            unsigned c = sx & 1 ? data & 15 : data >> 4;
            if (!c)
                continue;
            covered[ox] = 1;
            unsigned b;
            unsigned bp = pixel(v, bb, road_x(nx, hb, line + vb), line + vb, &b);
            if (!(s->attr & 0x8000) && (window_mask & (nx < 0 ? 1 : 2)))
                continue; /* solid high-priority window, as in the native compositor */
            if ((s->attr & 0x8000) || !(bp && (b & 0x8000))) {
                out[ox] = pal[((s->attr >> 9) & 48) | c];
                ++frame_margin_pixels;
            }
        }
    }
    memcpy(out + origin, native, nw * sizeof *out);
    hud_row(v, line, ha, hb, va, vb, ba, bb, pal, nw, out, w);
}
/* Completed pictures are immutable host snapshots. The guest still executes
 * every instruction, IRQ and DMA with the stock budget. Three V-ints of fixed
 * delay cover the measured 2/3-V-int picture cadence without extrapolation.
 * Full per-row VDP copies also preserve mid-frame raster and palette changes.
 * They are never passed to the bus, scheduler or serialized machine state. */
enum { PRESENT_HISTORY = 8, PRESENT_ROWS = 224, PRESENT_DELAY = 3 };
typedef struct { int left, right, valid; } RoadGeometry;
/* Atlas palette nibbles: 6 = border, 13 = lane marks, 14 = asphalt.
 * Banks 0/1 and the four row ranges encode discrete stripe/ground phases.
 * Measure the authored silhouette instead of interpolating atlas addresses. */
static RoadGeometry road_geometry(const GVDP *v, int line) {
    RoadGeometry result = {256, -257, 0};
    unsigned py = (line + v->vsram[1]) & 511;
    if (py >= 432) return result; /* ground separator/panorama, not a road template */
    unsigned base = (v->reg[4] & 7) << 13;
    for (int x = -256; x < 256; ++x) {
        unsigned attr, nib = pixel(v, base, x, py, &attr) & 15;
        if (nib == 6 || nib == 13 || nib == 14) {
            if (x < result.left) result.left = x;
            result.right = x;
            result.valid = 1;
        }
    }
    return result;
}
typedef struct {
    GVDP row[PRESENT_ROWS];
    RoadGeometry road[PRESENT_ROWS];
    Scene scene;
    uint64_t frame;
    int valid;
} Picture;
static Picture *pictures;
static unsigned picture_index, picture_key;
static int capture_picture;
static Picture *from_picture, *to_picture;
static unsigned phase_num, phase_den;
static Scene mixed_scene;
static GVDP mixed_vdp;
/* Optional read-only qualification stream. Each row owns three complete
 * plane-B index strips: the two real endpoints and the actual presented row.
 * Export before sprites/HUD so occlusion cannot hide broken road topology. */
static FILE *road_audit;
static void audit_u32(unsigned value) {
    unsigned char bytes[4] = {value, value >> 8, value >> 16, value >> 24};
    fwrite(bytes, 1, sizeof bytes, road_audit);
}
static void audit_begin(void) {
    const char *dir = getenv("TG2_ROAD_AUDIT_DIR");
    if (!dir || !*dir || !from_picture) return;
    char path[1024];
    snprintf(path, sizeof path, "%s/frame-%06llu.road", dir,
             (unsigned long long)present_frame);
    road_audit = fopen(path, "wb");
    if (!road_audit) { perror(path); exit(1); }
    fwrite("TG2ROAD1", 1, 8, road_audit);
    unsigned header[] = {(unsigned)present_frame, (unsigned)from_picture->frame,
        (unsigned)to_picture->frame, phase_num, phase_den, (unsigned)-384,
        1024, 140, 73};
    for (unsigned i = 0; i < sizeof header / sizeof *header; ++i) audit_u32(header[i]);
}
static unsigned hscroll(const GVDP *v, int line, int plane) {
    unsigned base = (v->reg[13] & 63) << 10;
    int mode = v->reg[11] & 3;
    int y = mode == 0 ? 0 : mode == 2 ? line & ~7 : line;
    return word(v->vram, base + y * 4 + plane * 2) & 1023;
}
static void audit_row(int line, const GVDP *a, const GVDP *b, const GVDP *image) {
    if (!road_audit || line < 140 || line > 212) return;
    const GVDP *sources[] = {a, b, image};
    for (int i = 0; i < 3; ++i) {
        const GVDP *v = sources[i];
        unsigned py = (line + v->vsram[1]) & 511;
        unsigned hs = hscroll(v, line, 1), base = (v->reg[4] & 7) << 13;
        audit_u32(py);
        audit_u32(hs);
        unsigned char row[1024];
        for (int x = 0; x < 1024; ++x) {
            unsigned attr;
            row[x] = pixel(v, base, road_x(x - 384, hs, py), py, &attr);
        }
        if (fwrite(row, 1, sizeof row, road_audit) != sizeof row) {
            perror("road audit write"); exit(1);
        }
    }
}
static void presentation_clear(void) {
    if (pictures)
        for (int i = 0; i < PRESENT_HISTORY; ++i) pictures[i].valid = 0;
    capture_picture = 0;
    from_picture = to_picture = NULL;
    picture_key = 0;
}
void tg2_video_frame(uint64_t frame, int on) {
    if (road_audit) { fclose(road_audit); road_audit = NULL; }
    if (on != race60 || frame < present_frame) presentation_clear();
    race60 = on;
    present_frame = frame;
}
static int mix_reverse;
static int mix(int a, int b) {
    unsigned num = mix_reverse ? phase_den - phase_num : phase_num;
    return a + (int)lround((double)(b - a) * num / phase_den);
}
static unsigned mix_wrap(unsigned a, unsigned b, unsigned mask) {
    int delta = (int)((b - a + (mask + 1) / 2) & mask) - (int)((mask + 1) / 2);
    return mix((int)a, (int)a + delta) & mask;
}
static void put_word(unsigned char *p, unsigned a, unsigned x) {
    p[a & 65535] = x >> 8;
    p[(a + 1) & 65535] = x;
}
/* Match pieces by tile/size and nearest screen position, never by the SAT
 * allocation index (the game builds that list backwards and culls entries).
 * Appearance/disappearance and animation changes keep the older picture. */
static void mix_sprites(GVDP *out, const GVDP *b) {
    unsigned sa = (out->reg[5] & 127) << 9, sb = (b->reg[5] & 127) << 9;
    unsigned char used[80] = {0};
    int ia = 0;
    for (int n = 0; n < 64; ++n) {
        unsigned a = sa + ia * 8;
        int ax = (word(out->vram, a + 6) & 511), ay = word(out->vram, a) & 1023;
        int ib = 0, best = -1, distance = 4096;
        for (int k = 0; k < 64; ++k) {
            unsigned q = sb + ib * 8;
            if (!used[ib] && word(out->vram, a + 4) == word(b->vram, q + 4) &&
                out->vram[(a + 2) & 65535] == b->vram[(q + 2) & 65535]) {
                int d = abs(ax - (int)(word(b->vram, q + 6) & 511)) +
                        abs(ay - (int)(word(b->vram, q) & 1023));
                if (d < distance) { best = ib; distance = d; }
            }
            ib = b->vram[(q + 3) & 65535] & 127;
            if (!ib || ib >= 64) break;
        }
        if (best >= 0 && distance < 96) {
            used[best] = 1;
            unsigned q = sb + best * 8;
            put_word(out->vram, a, mix_wrap(ay, word(b->vram, q) & 1023, 1023));
            put_word(out->vram, a + 6, mix_wrap(ax, word(b->vram, q + 6) & 511, 511));
        }
        ia = out->vram[(a + 3) & 65535] & 127;
        if (!ia || ia >= 64) break;
    }
}
static void mix_pieces(const Scene *a, const Scene *b) {
    mixed_scene = *a;
    unsigned char used[MAX_PIECES] = {0};
    for (unsigned i = 0; i < a->count; ++i) {
        const Piece *p = &a->pieces[i];
        int best = -1, distance = 96;
        for (unsigned j = 0; j < b->count; ++j) {
            const Piece *q = &b->pieces[j];
            if (used[j] || p->attr != q->attr || p->size != q->size) continue;
            int d = abs(p->x - q->x) + abs(p->y - q->y);
            if (d < distance) { best = (int)j; distance = d; }
        }
        if (best >= 0) {
            used[best] = 1;
            mixed_scene.pieces[i].x = mix(p->x, b->pieces[best].x);
            mixed_scene.pieces[i].y = mix(p->y, b->pieces[best].y);
        }
    }
}
static void presentation_begin(const GVDP *v) {
    from_picture = to_picture = NULL;
    capture_picture = 0;
    if (!pictures) pictures = calloc(PRESENT_HISTORY, sizeof *pictures);
    if (!pictures) return;
    unsigned key = read32(0xFF231E);
    if (key != picture_key || !pictures[picture_index].valid) {
        picture_key = key;
        picture_index = (picture_index + 1) % PRESENT_HISTORY;
        Picture *p = &pictures[picture_index];
        p->valid = 1;
        p->frame = present_frame;
        select_scene(v);
        if (shown) p->scene = *shown;
        else memset(&p->scene, 0, sizeof p->scene);
        capture_picture = 1;
    }
    if (present_frame < PRESENT_DELAY) return;
    uint64_t target = present_frame - PRESENT_DELAY;
    for (int i = 0; i < PRESENT_HISTORY; ++i) {
        Picture *p = &pictures[i];
        if (!p->valid) continue;
        if (p->frame <= target && (!from_picture || p->frame > from_picture->frame))
            from_picture = p;
        if (p->frame >= target && (!to_picture || p->frame < to_picture->frame))
            to_picture = p;
    }
    if (!from_picture) return; /* warm-up: original image until bracketed */
    if (!to_picture) to_picture = from_picture;
    phase_den = (unsigned)(to_picture->frame - from_picture->frame);
    phase_num = (unsigned)(target - from_picture->frame);
    if (!phase_den) { phase_den = 1; phase_num = 0; }
    mix_reverse = phase_num * 2 >= phase_den;
    mix_pieces(mix_reverse ? &to_picture->scene : &from_picture->scene,
               mix_reverse ? &from_picture->scene : &to_picture->scene);
    mix_reverse = 0;
    audit_begin();
}
static void scanline(const GVDP *v, int line, const uint32_t *native, int nw,
                     uint32_t *out, int w) {
    if (!line) {
        capture_picture = 0;
        from_picture = to_picture = NULL;
        if (race60 && nw == 256 && race(v)) presentation_begin(v);
    }
    /* Capture every row of an eligible picture, including transient raster
     * bands that use the original row producer below. */
    if (capture_picture && pictures && line < PRESENT_ROWS) {
        pictures[picture_index].row[line] = *v;
        pictures[picture_index].road[line] = road_geometry(v, line);
    }
    if (!race60 || line >= PRESENT_ROWS || nw != 256 || !race(v) || !from_picture) {
        draw_scanline(v, line, native, nw, out, w);
        return;
    }
    const GVDP *a = &from_picture->row[line], *b = &to_picture->row[line];
    int nearer_b = phase_num * 2 >= phase_den;
    const GVDP *source = nearer_b ? b : a;
    mixed_vdp = *source;
    /* VSRAM selects a row in one of four authored road atlases, carrying
     * width, stripe phase, palette bank and ground type together. Keep that
     * entire discrete row, VRAM, CRAM and register state from ONE endpoint.
     * Only translate its geometry horizontally; never interpolate atlas Y. */
    unsigned hs = mix_wrap(hscroll(a, line, 1), hscroll(b, line, 1), 511);
    RoadGeometry ga = from_picture->road[line], gb = to_picture->road[line];
    if (ga.valid && gb.valid) {
        RoadGeometry shape = nearer_b ? gb : ga;
        int ca = 128 + ((hscroll(a, line, 1) + 128) & 511) - 256;
        int cb = 128 + ((hscroll(b, line, 1) + 128) & 511) - 256;
        int center = 128 + ((hs + 128) & 511) - 256;
        int la = ca + ga.left, lb = cb + gb.left;
        int ra = ca + ga.right, rb = cb + gb.right;
        int lo_l = (la < lb ? la : lb) - shape.left;
        int lo_r = (ra < rb ? ra : rb) - shape.right;
        int hi_l = (la > lb ? la : lb) - shape.left;
        int hi_r = (ra > rb ? ra : rb) - shape.right;
        int lower = lo_l > lo_r ? lo_l : lo_r, upper = hi_l < hi_r ? hi_l : hi_r;
        /* The selected endpoint's centre is always feasible. Clamp only the
         * translation so both edges stay in their neighbours' envelopes;
         * stripe topology and width remain an authored, unmixed road row. */
        if (center < lower) center = lower;
        if (center > upper) center = upper;
        hs = (unsigned)center & 511;
    } else if (ga.valid != gb.valid) {
        hs = hscroll(source, line, 1); /* horizon/segment boundary: snap row */
    }
    unsigned base = (mixed_vdp.reg[13] & 63) << 10;
    int hm = mixed_vdp.reg[11] & 3;
    int hy = hm == 0 ? 0 : hm == 2 ? line & ~7 : line;
    put_word(mixed_vdp.vram, base + hy * 4 + 2, hs);
    mix_reverse = nearer_b;
    mix_sprites(&mixed_vdp, nearer_b ? a : b);
    mix_reverse = 0;
    audit_row(line, a, b, &mixed_vdp);
    uint8_t indices[GVDP_MAX_WIDTH];
    uint32_t pixels[GVDP_MAX_WIDTH];
    int count = gvdp_render_scanline(&mixed_vdp, line, indices);
    for (int x = 0; x < count; ++x)
        pixels[x] = indices[x] < 192 ? genesis_dac_cram_to_argb(
            mixed_vdp.cram[indices[x] & 63], indices[x] >> 6) : 0xFF000000;
    const Scene *saved = shown;
    shown = &mixed_scene;
    synthesizing = 1;
    draw_scanline(&mixed_vdp, line, pixels, nw, out, w);
    synthesizing = 0;
    shown = saved;
}
void tg2_video_command(int id, const char *json) {
    char out[22000];
    int n = snprintf(out, sizeof out,
                     "{\"id\":%d,\"ok\":true,\"enabled\":%d,\"wide_lines\":%u,\"native_lines\":%u,"
                     "\"published\":%u,\"displayed\":%u,\"pieces\":%u,\"overflow\":%u,"
                     "\"sat_matches\":%u,\"margin_pieces\":%u,\"sprite_margin_pixels\":%u,"
                     "\"hud_edges\":%d,\"hud_plane_pixels\":%u,\"hud_marker_pixels\":%u",
                     id, enabled(), wide_lines, native_lines, serial, shown ? shown->serial : 0,
                     shown ? shown->count : 0, overflow, matched_pieces, margin_pieces,
                     frame_margin_pixels, tg2_video_get_hud_mode(), hud_plane_pixels, hud_marker_pixels);
    n += snprintf(out + n, sizeof out - n,
                  ",\"race60\":%d,\"presentation_delay_frames\":%d,\"presentation_frame\":%llu,"
                  "\"from_frame\":%llu,\"to_frame\":%llu,\"phase_num\":%u,\"phase_den\":%u",
                  race60, PRESENT_DELAY, (unsigned long long)present_frame,
                  (unsigned long long)(from_picture ? from_picture->frame : 0),
                  (unsigned long long)(to_picture ? to_picture->frame : 0), phase_num, phase_den);
    if (json && strstr(json, "\"rows\"")) {
        n += snprintf(out + n, sizeof out - n, ",\"rows\":[");
        for (int i = 0; i < 224; ++i)
            n += snprintf(out + n, sizeof out - n, "%s[%d,%d,%d,%d,%u,%u]", i ? "," : "",
                          rows[i].ha, rows[i].hb, rows[i].va, rows[i].vb, rows[i].a, rows[i].b);
        n += snprintf(out + n, sizeof out - n, "]");
    }
    if (json && strstr(json, "\"top\"")) {
        n += snprintf(out + n, sizeof out - n, ",\"top\":[");
        for (int row = 0; row < 8; ++row) {
            n += snprintf(out + n, sizeof out - n, "%s{\"reg\":[", row ? "," : "");
            for (int i = 0; i < 24; ++i)
                n += snprintf(out + n, sizeof out - n, "%s%u", i ? "," : "", top_rows[row].reg[i]);
            n += snprintf(out + n, sizeof out - n, "],\"vsram\":[%u,%u],\"cram\":[",
                          top_rows[row].vsram[0], top_rows[row].vsram[1]);
            for (int i = 0; i < 64; ++i)
                n += snprintf(out + n, sizeof out - n, "%s%u", i ? "," : "", top_rows[row].cram[i]);
            n += snprintf(out + n, sizeof out - n, "]}");
        }
        n += snprintf(out + n, sizeof out - n, "]");
    }
    snprintf(out + n, sizeof out - n, "}");
    cmd_send_response(out);
}
const GameVideo tg2_video = {
    .configure = configure, .enabled = enabled, .width = width, .scanline = scanline,
    .renderer_enabled = renderer_enabled};
