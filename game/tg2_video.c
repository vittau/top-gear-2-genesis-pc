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
 * followed by the skyline. The road's center is the atlas seam (X=0),
 * with exterior ground at X=256. Extend that exterior, never another road.
 * The skyline is an authored repeating panorama and retains its wrap. */
static int road_x(int nx, int scroll, int py) {
    if ((py & 511) >= 432)
        return nx - scroll;
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
static int synthesizing;
static void draw_scanline(const GVDP *v, int line, const uint32_t *native, int nw, uint32_t *out,
                     int w) {
    int origin = (w - nw) / 2;
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
typedef struct {
    GVDP row[PRESENT_ROWS];
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
static void presentation_clear(void) {
    if (pictures)
        for (int i = 0; i < PRESENT_HISTORY; ++i) pictures[i].valid = 0;
    capture_picture = 0;
    from_picture = to_picture = NULL;
    picture_key = 0;
}
void tg2_video_frame(uint64_t frame, int on) {
    if (on != race60 || frame < present_frame) presentation_clear();
    race60 = on;
    present_frame = frame;
}
static int mix(int a, int b) {
    return a + (int)lround((double)(b - a) * phase_num / phase_den);
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
    mix_pieces(&from_picture->scene, &to_picture->scene);
}
static void scanline(const GVDP *v, int line, const uint32_t *native, int nw,
                     uint32_t *out, int w) {
    if (!race60 || line >= PRESENT_ROWS || nw != 256 || !race(v)) {
        draw_scanline(v, line, native, nw, out, w);
        return;
    }
    if (!line) presentation_begin(v);
    if (capture_picture && pictures) pictures[picture_index].row[line] = *v;
    if (!from_picture) {
        draw_scanline(v, line, native, nw, out, w);
        return;
    }
    mixed_vdp = from_picture->row[line];
    const GVDP *b = &to_picture->row[line];
    /* Raster vertical offsets encode road perspective, horizontal offsets
     * encode road centre/skyline. Wrap interpolation follows the short arc. */
    for (int i = 0; i < 2; ++i)
        mixed_vdp.vsram[i] = mix_wrap(mixed_vdp.vsram[i], b->vsram[i], 1023);
    unsigned ha = (mixed_vdp.reg[13] & 63) << 10, hb = (b->reg[13] & 63) << 10;
    int ma = mixed_vdp.reg[11] & 3, mb = b->reg[11] & 3;
    int ya = ma == 0 ? 0 : ma == 2 ? line & ~7 : line;
    int yb = mb == 0 ? 0 : mb == 2 ? line & ~7 : line;
    for (int i = 0; i < 2; ++i) {
        unsigned a = ha + ya * 4 + i * 2, q = hb + yb * 4 + i * 2;
        put_word(mixed_vdp.vram, a, mix_wrap(word(mixed_vdp.vram, a), word(b->vram, q), 1023));
    }
    mix_sprites(&mixed_vdp, b);
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
