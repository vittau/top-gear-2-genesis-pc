/* TG2 video: raster (pure extraction from tg2_video.c). */
#include "tg2_video_internal.h"

int tg2v_synthesizing, tg2v_audit_race_frame;
/* The last picture was a qualified single-player race (set on its first row).
 * The presented-height builder and the test provider use it, not a re-check
 * of live RAM at frame end, so 2P split-screen frames stay native. */
int tg2v_last_frame_race;
/* Only remove a band that is visibly empty in this exact presented picture:
 * the top rows when the stock window band was blanked, the bottom rows when
 * every one of their rendered pixels is the empty backdrop. */
void tg2v_note_crop_row(int line, const uint32_t *out, int w);
static void render_scanline(const GVDP *v, int line, const uint32_t *native, int nw,
                            uint32_t *out, int w);
static void render_scanline_1x(const GVDP *v, int line, const uint32_t *native, int nw,
                               uint32_t *out, int w);
#ifdef GEN_ENABLE_TRACE
/* ---- Evidence capture for the carousel CONTROL row (dev only) -----------
 * TG2_CONTROL_CAPTURE=<path> writes one line per presented picture with the
 * non-backdrop pixel count of the three rectangles where the removed CONTROL
 * button can appear: the one-player row list, and player 1's and player 2's
 * lists in the stacked two-player layout. It also records whether the game's
 * own carousel state says the row list is up and how many SAT sprites overlap
 * those rectangles. It never alters a pixel. */
static const struct { int x0, y0, x1, y1; } k_control_rects[3] = {
    { 100, 136, 211, 151 },   /* one-player: the removed fifth row */
    { 100,  80, 211,  95 },   /* two-player: player 1's fifth row     */
    { 100, 192, 211, 207 }    /* two-player: player 2's fifth row     */
};
static FILE *control_capture;
static int control_capture_open_checked;
static int control_counts[3], control_pieces, control_rowlist, control_twop;
static unsigned long long control_capture_frames;

/* The CONTROL row's four pieces are the 32x16 sprites whose SAT tiles are
 * exactly 0x157, 0x15F, 0x167 and 0x16F (the 0x2000 in the attribute tg2_word is
 * the priority bit). The row highlight's tiles start at 0x173, so match the
 * exact set. Count them in the live display list, so a run can prove the
 * pieces never reach the SAT. */
static const unsigned k_control_tiles[4] = { 0x157u, 0x15Fu, 0x167u, 0x16Fu };
static int control_sprites_in_sat(const GVDP *v) {
    unsigned sat = (unsigned)((v->reg[5] & 0x7F) << 9);
    int link = 0, count = 0;
    for (int n = 0; n < 80; ++n) {
        unsigned e = sat + (unsigned)link * 8;
        unsigned tile = tg2_word(v->vram, e + 4) & 0x7FFu;
        for (int t = 0; t < 4; ++t)
            if (tile == k_control_tiles[t]) { ++count; break; }
        int next = v->vram[(e + 3) & 0xFFFF] & 0x7F;
        if (!next || next <= link) break;
        link = next;
    }
    return count;
}
static void control_capture_row(const GVDP *v, int line, int nw, int w,
                                const uint32_t *out) {
    if (!control_capture_open_checked) {
        const char *path = getenv("TG2_CONTROL_CAPTURE");
        control_capture_open_checked = 1;
        if (path && *path) control_capture = fopen(path, "w");
        if (control_capture)
            fputs("# frame rowlist twop pieces r1 r2 r3\n", control_capture);
    }
    if (!control_capture) return;
    if (line == 0) {
        memset(control_counts, 0, sizeof control_counts);
        control_pieces = nw == 256 ? control_sprites_in_sat(v) : 0;
        control_rowlist = tg2_word(g_ram, 0x2554) == 0x00B4u &&
                          tg2_word(g_ram, 0x2556) == 0;
        control_twop = tg2_word(g_ram, 0x189E) != 0;
    }
    if (nw == 256) {
        int origin = (w - nw) / 2;
        for (int r = 0; r < 3; ++r) {
            if (line < k_control_rects[r].y0 || line > k_control_rects[r].y1)
                continue;
            for (int x = k_control_rects[r].x0; x <= k_control_rects[r].x1; ++x) {
                int ox = origin + x;
                if (ox >= 0 && ox < w && (out[ox] & 0xFFFFFFu))
                    ++control_counts[r];
            }
        }
    }
    if (line == 223) {
        fprintf(control_capture, "%llu %d %d %d %d %d %d\n",
                (unsigned long long)tg2v_present_frame, control_rowlist, control_twop,
                control_pieces, control_counts[0], control_counts[1],
                control_counts[2]);
        fflush(control_capture);
        ++control_capture_frames;
    }
}
#endif
void tg2v_draw_scanline(const GVDP *v, int line, const uint32_t *native, int nw, uint32_t *out,
                     int w) {
    render_scanline(v, line, native, nw, out, w);
    tg2v_note_crop_row(line, out, w);
#ifdef GEN_ENABLE_TRACE
    control_capture_row(v, line, nw, w, out);
#endif
}
/* S3: a render scale above 1 presents an N x canvas whose content is the 1x
 * picture scaled by nearest in both axes. The road rows are then repainted at
 * output resolution by tg2_highres_build() once the frame is complete; every
 * other row keeps native detail. Linear On later interpolates this art with
 * explicit native-layer coverage; it does not change LOD, size or positions. */
static void render_scanline(const GVDP *v, int line, const uint32_t *native, int nw,
                            uint32_t *out, int w) {
    int scale = tg2_highres_scale();
    /* A wide native menu/2P canvas can also be divisible by N and wider
     * than nw*N. Dimensions alone do not make it an N x race picture. */
    if (scale > 1 && (nw != 256 || !tg2_race_picture(v))) scale = 1;
    if (scale <= 1 || w % scale || w / scale < nw) {
        render_scanline_1x(v, line, native, nw, out, w);
        return;
    }
    static uint32_t row1[4096];
    int w1 = w / scale;
    static unsigned char foreground[4096], occluder[4096];
    static unsigned short front[4096];
    static uint32_t stripped[256], reference[4096];
    static GVDPRasterRow free_row;
    const GVDPRasterRow *original=tg2v_filter_layers;
    int layers = tg2v_filter_layers && tg2v_filter_layers->width >= (unsigned)nw;
    if (!line) {
        if (!tg2v_synthesizing) tg2v_select_scene(v);
        tg2v_prepare_actors(v);
    }
    tg2v_actor_free=0;
    /* Keep the actual native+margin picture for same-frame downscale evidence. */
    if(tg2_highres_native_dump_active()) {
        tg2v_reference_pass=1;
        render_scanline_1x(v,line,native,nw,reference,w1);
        tg2v_reference_pass=0;
    }
    if(layers && tg2_actors_active()) {
        tg2v_actor_native_row(v,line,nw,native,stripped,&free_row,tg2v_owners);
        tg2v_filter_layers=&free_row; native=stripped; tg2v_actor_free=1;
    }
    memset(occluder,0,w1);memset(front,0,w1*sizeof *front);
    tg2v_actor_occluder=layers?occluder:NULL;tg2v_actor_front=layers?front:NULL;
    tg2v_filter_foreground=layers?foreground:NULL;
    render_scanline_1x(v, line, native, nw, row1, w1);
    if (layers) {
        tg2_highres_capture_native(line, row1, foreground, w1);
        tg2_highres_capture_actors(line,foreground,occluder,front,reference,w1,tg2v_actor_free);
    }
    tg2v_filter_foreground=NULL;tg2v_actor_occluder=NULL;tg2v_actor_front=NULL;tg2v_actor_free=0;
    tg2v_filter_layers=original;
    for (int x = 0; x < w; ++x)
        out[x] = row1[x / scale];
}
void tg2v_note_crop_row(int line, const uint32_t *out, int w) {
    if (line < CROP_TOP) return;              /* counted when the band is blanked */
    if (line < 224 - CROP_BOTTOM) return;
    if (!tg2v_crop_race_ok || !tg2v_crop_bottom_ok) return;
    for (int x = 0; x < w; ++x)
        if (out[x] & 0xFFFFFF) { tg2v_crop_bottom_ok = 0; return; }
}
/* The 1x canvas picture. At a render scale above 1 this draws into a scratch
 * row of the 1x canvas width and render_scanline() expands it by N; every
 * placement rule (origin, margins, HUD, crop note, margin audit) stays the
 * stock 1x logic. */
static void render_scanline_1x(const GVDP *v, int line, const uint32_t *native, int nw,
                               uint32_t *out, int w) {
    int origin = (w - nw) / 2;
    tg2v_pa_extend_mask = 0;
    if (!line) {
        tg2v_audit_race_frame = nw == 256 && tg2_race_picture(v);
        tg2v_last_frame_race = tg2v_audit_race_frame;
        /* Overscan can return before the first visible race row. Select the
         * displayed SAT now at 1x too, so 60-fps Off retains margin sprites. */
        if (tg2v_last_frame_race && !tg2v_synthesizing && tg2_highres_scale()<=1)
            tg2v_select_scene(v);
        tg2v_highres_wanted = tg2v_last_frame_race && tg2_highres_scale() > 1;
        if (tg2v_last_frame_race && !tg2v_reference_pass)
            tg2_highres_picture_start();
        tg2v_crop_race_ok = tg2v_audit_race_frame;
        tg2v_crop_top_rows = 0;
        tg2v_crop_bottom_ok = 1;
    }
#ifdef GEN_ENABLE_TRACE
    if (line < 8) {
        memcpy(tg2v_top_rows[line].reg, v->reg, sizeof tg2v_top_rows[line].reg);
        memcpy(tg2v_top_rows[line].vsram, v->vsram, sizeof tg2v_top_rows[line].vsram);
        memcpy(tg2v_top_rows[line].cram, v->cram, sizeof tg2v_top_rows[line].cram);
    }
#endif
    if (!line) {
        tg2v_frame_margin_pixels = 0;
        tg2v_hud_plane_pixels = tg2v_hud_marker_pixels = tg2v_hud_sprite_pixels = 0;
    }
    for (int x = 0; x < w; ++x)
        out[x] = 0xFF000000;
    if (tg2v_filter_foreground) memset(tg2v_filter_foreground, 1, (size_t)w);
    /* Presentation-only: the stock top window band carried coloured
     * window-plane artefacts that CRT overscan hid. Blank the whole band in
     * every output mode, while an inactive window keeps menu rows intact. */
    if (tg2v_tg2_video_get_hide_overscan() && line < 8 &&
        tg2v_window_at(v, line, 0) && tg2v_window_at(v, line, nw - 1)) {
        if (!tg2v_reference_pass) ++tg2v_crop_top_rows;

#ifdef GEN_ENABLE_TRACE
        if (tg2v_audit_race_frame) tg2v_audit_margins(v, line, native, nw, out, w);
#endif
        return;
    }
    if (!tg2_race_picture(v) || !(v->reg[1] & 64)) {
        if (!tg2v_reference_pass) ++tg2v_native_lines;
        memcpy(out + origin, native, nw * sizeof *out);
        if (tg2v_audit_race_frame) {
            tg2v_window_margins(v, line, native, nw, out, w);

#ifdef GEN_ENABLE_TRACE
            tg2v_audit_margins(v, line, native, nw, out, w);
#endif
        }
        return;
    }
    if (!tg2v_reference_pass) ++tg2v_wide_lines;
    unsigned ba = (v->reg[2] & 56) << 10, bb = (v->reg[4] & 7) << 13;
    unsigned hbase = (v->reg[13] & 63) << 10;
    int hm = v->reg[11] & 3, hi = hm == 0 ? 0 : hm == 2 ? line & ~7 : line;
    int ha = tg2_word(v->vram, hbase + hi * 4) & 1023, hb = tg2_word(v->vram, hbase + hi * 4 + 2) & 1023;
    int va = v->vsram[0] & 1023, vb = v->vsram[1] & 1023;
    tg2v_rows[line].ha = ha;
    tg2v_rows[line].hb = hb;
    tg2v_rows[line].va = va;
    tg2v_rows[line].vb = vb;
    tg2v_rows[line].a = ba;
    tg2v_rows[line].b = bb;
    /* S1: compact per-row capture, only when the render scale is above 1, so
     * the stock path pays nothing. It records exactly the row state the
     * renderer is about to use. */
    if (!tg2v_reference_pass) tg2_highres_capture_row(v, line, ha, hb);
    uint32_t pal[64];
    for (int i = 0; i < 64; ++i)
        pal[i] = genesis_dac_cram_to_argb(v->cram[i], 0);
    for (int x = 0; x < w; ++x) {
        int nx = x - origin;
        if (nx >= 0 && nx < nw)
            continue;
        unsigned b;
        unsigned bp = tg2v_pixel(v, bb, tg2v_road_x(nx, hb, line + vb), line + vb, &b);
        out[x] = pal[bp ? bp : v->reg[7] & 63];
        unsigned ap = tg2v_weather_pixel(v, line, nx, ha, va, ba);
        if (ap) out[x] = pal[ap];
        if (tg2v_filter_foreground) tg2v_filter_foreground[x] = ap != 0;
        if (tg2v_actor_occluder) tg2v_actor_occluder[x] = (bp && (b&0x8000)) || ap;
    }
    unsigned window_mask = tg2v_window_margins(v, line, native, nw, out, w);
    tg2v_plane_a_margins(v, line, native, nw, pal, out, w, ha, va, ba);
    if (tg2v_actor_occluder) for(int x=0;x<w;++x) if((x<origin && ((window_mask|tg2v_pa_extend_mask)&1)) || (x>=origin+nw && ((window_mask|tg2v_pa_extend_mask)&2))) tg2v_actor_occluder[x]=1;

#ifdef GEN_ENABLE_TRACE
    if (tg2v_audit_race_frame) tg2v_audit_margins(v, line, native, nw, out, w);
#endif
    /* Reverse allocation order matches the native backward SAT builder. */
    static unsigned char covered[4096];
    memset(covered, 0, sizeof covered);
    for (unsigned n = tg2v_shown ? tg2v_shown->count : 0; n > 0; --n) {
        const Piece *s = &tg2v_shown->pieces[n - 1];
        if (tg2v_actor_free && tg2_actors_promoted(s->actor)) continue;
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
            if (tg2v_actor_front) tg2v_actor_front[ox] = n;
            unsigned b;
            unsigned bp = tg2v_pixel(v, bb, tg2v_road_x(nx, hb, line + vb), line + vb, &b);
            if (!(s->attr & 0x8000) &&
                ((window_mask & (nx < 0 ? 1 : 2)) ||
                 tg2v_weather_pixel(v, line, nx, ha, va, ba)))
                continue; /* solid high-priority window, as in the native compositor */
            if ((s->attr & 0x8000) || !(bp && (b & 0x8000))) {
                out[ox] = pal[((s->attr >> 9) & 48) | c];
                if (tg2v_filter_foreground) tg2v_filter_foreground[ox] = 1;
                if (!tg2v_reference_pass) ++tg2v_frame_margin_pixels;
            }
        }
    }
    memcpy(out + origin, native, nw * sizeof *out);
    if (tg2v_actor_front) memcpy(tg2v_actor_front+origin,tg2v_owners,nw*sizeof *tg2v_owners);
    if (tg2v_actor_occluder) for(int x=0;x<nw;++x) {
        int k=x+((int)tg2v_filter_layers->width-nw)/2;
        tg2v_actor_occluder[origin+x] = ((tg2v_filter_layers->plane_a[k]&0xC0)==0xC0) || ((tg2v_filter_layers->plane_b[k]&0xC0)==0xC0);
    }
    if (tg2v_filter_foreground) {
        int offset = ((int)tg2v_filter_layers->width - nw) / 2;
        for (int x = 0; x < nw; ++x)
            tg2v_filter_foreground[origin + x] = tg2v_foreground_at(tg2v_filter_layers, offset + x);
    }
    if (tg2v_actor_front && !tg2v_tg2_video_get_hud_mode()) {
        int offset=((int)tg2v_filter_layers->width-nw)/2;
        for(int x=0;x<nw;++x) {
            int k=x+offset;
            unsigned ap=tg2v_filter_layers->plane_a[k],bp=tg2v_filter_layers->plane_b[k];
            int sprite=tg2v_filter_layers->opaque[k],sprite_high=sprite && tg2v_filter_layers->high[k];
            int a_wins=!sprite_high && ((ap&0xC0)==0xC0 ||
                ((bp&0xC0)!=0xC0 && !sprite && (ap&0x40)));
            if(!a_wins)continue;
            unsigned attr;
            tg2v_pixel(v,ba,x-ha,line+va,&attr);
            int side=tg2v_hud_tile(attr);
            if(side && tg2v_hud_region(x,side)) tg2v_actor_front[origin+x]=65535;
        }
    }
    tg2v_hud_row(v, line, ha, hb, va, vb, ba, bb, pal, nw, out, w);
}
