/* TG2 video: present (pure extraction from tg2_video.c). */
#include "tg2_video_internal.h"

/* Completed pictures are immutable host snapshots. The guest still executes
 * every instruction, IRQ and DMA with the stock budget. Three V-ints of fixed
 * delay cover the measured 2/3-V-int picture cadence without extrapolation.
 * Full per-row VDP copies also preserve mid-frame raster and palette changes.
 * They are never passed to the bus, scheduler or serialized machine state. */


/* Atlas palette nibbles: 6 = border, 13 = lane marks, 14 = asphalt.
 * Banks 0/1 and the four row ranges encode discrete stripe/ground phases.
 * Measure the authored silhouette instead of interpolating atlas addresses. */
static RoadGeometry road_geometry(const GVDP *v, int line) {
    RoadGeometry result = {256, -257, 0};
    unsigned py = (line + v->vsram[1]) & 511;
    if (py >= 432) return result; /* ground separator/panorama, not a road template */
    unsigned base = (v->reg[4] & 7) << 13;
    for (int x = -256; x < 256; ++x) {
        unsigned attr, nib = tg2v_pixel(v, base, x, py, &attr) & 15;
        if (nib == 6 || nib == 13 || nib == 14) {
            if (x < result.left) result.left = x;
            result.right = x;
            result.valid = 1;
        }
    }
    return result;
}

Picture *tg2v_pictures;
static unsigned picture_index, picture_key;
static int capture_picture;
Picture *tg2v_from_picture, *tg2v_to_picture;
unsigned tg2v_phase_num, tg2v_phase_den;
static Scene mixed_scene;
/* Optional read-only qualification stream. Each row owns three complete
 * plane-B index strips: the two real endpoints and the actual presented row.
 * Export before sprites/HUD so occlusion cannot hide broken road topology. */
#ifdef GEN_ENABLE_TRACE
static FILE *road_audit;
static void audit_u32(unsigned value) {
    unsigned char bytes[4] = {value, value >> 8, value >> 16, value >> 24};
    fwrite(bytes, 1, sizeof bytes, road_audit);
}
static void audit_begin(void) {
    const char *dir = getenv("TG2_ROAD_AUDIT_DIR");
    if (!dir || !*dir || !tg2v_from_picture) return;
    char path[1024];
    snprintf(path, sizeof path, "%s/frame-%06llu.road", dir,
             (unsigned long long)tg2v_present_frame);
    road_audit = fopen(path, "wb");
    if (!road_audit) { perror(path); exit(1); }
    fwrite("TG2ROAD1", 1, 8, road_audit);
    unsigned header[] = {(unsigned)tg2v_present_frame, (unsigned)tg2v_from_picture->frame,
        (unsigned)tg2v_to_picture->frame, tg2v_phase_num, tg2v_phase_den, (unsigned)-384,
        1024, 140, 73};
    for (unsigned i = 0; i < sizeof header / sizeof *header; ++i) audit_u32(header[i]);
}
#endif
unsigned tg2v_hscroll(const GVDP *v, int line, int plane) {
    unsigned base = (v->reg[13] & 63) << 10;
    int tg2v_mode = v->reg[11] & 3;
    int y = tg2v_mode == 0 ? 0 : tg2v_mode == 2 ? line & ~7 : line;
    return tg2_word(v->vram, base + y * 4 + plane * 2) & 1023;
}
#ifdef GEN_ENABLE_TRACE
static void audit_row(int line, const GVDP *a, const GVDP *b, const GVDP *image,
                      int image_hs) {
    if (!road_audit || line < 140 || line > 212) return;
    /* The presented strip keeps the translated H-scroll explicitly: the row's
     * endpoint snapshots are restored before this export, so the image must
     * not be read back from the (now original) snapshot. Sprites never reach
     * this plane-B-only export. */
    const GVDP *sources[] = {a, b, image};
    for (int i = 0; i < 3; ++i) {
        const GVDP *v = sources[i];
        unsigned py = (line + v->vsram[1]) & 511;
        unsigned hs = i == 2 ? (unsigned)image_hs : tg2v_hscroll(v, line, 1);
        unsigned base = (v->reg[4] & 7) << 13;
        audit_u32(py);
        audit_u32(hs);
        unsigned char row[1024];
        for (int x = 0; x < 1024; ++x) {
            unsigned attr;
            row[x] = tg2v_pixel(v, base, tg2v_road_x(x - 384, hs, py), py, &attr);
        }
        if (fwrite(row, 1, sizeof row, road_audit) != sizeof row) {
            perror("road audit write"); exit(1);
        }
    }
}
#endif
void tg2v_presentation_clear(void) {
    if (tg2v_pictures)
        for (int i = 0; i < PRESENT_HISTORY; ++i) tg2v_pictures[i].valid = 0;
    capture_picture = 0;
    tg2v_from_picture = tg2v_to_picture = NULL;
    picture_key = 0;
}
void tg2_video_frame(uint64_t frame, int on) {
#ifdef GEN_ENABLE_TRACE
    if (road_audit) { fclose(road_audit); road_audit = NULL; }
#endif
    if (on != tg2v_race60 || frame < tg2v_present_frame) tg2v_presentation_clear();
    tg2v_race60 = on;
    tg2v_present_frame = frame;
    tg2_actors_frame(frame);
    /* No row producer runs, so no picture will raise the N x canvas. */
    if (!tg2v_renderer_enabled()) tg2v_highres_wanted = 0;
}
static int mix_reverse;
/* Undo log for the per-row VDP edit (see scanline()). The presented row is
 * produced by patching the endpoint's own private snapshot and restoring it,
 * instead of copying the whole 64 KiB GVDP for every presented scanline. */
static unsigned sprite_undo_addr[64], sprite_undo_x[64], sprite_undo_y[64];
static unsigned sprite_undo_count;
static int mix(int a, int b) {
    unsigned num = mix_reverse ? tg2v_phase_den - tg2v_phase_num : tg2v_phase_num;
    return a + (int)lround((double)(b - a) * num / tg2v_phase_den);
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
        int ax = (tg2_word(out->vram, a + 6) & 511), ay = tg2_word(out->vram, a) & 1023;
        int ib = 0, best = -1, distance = 4096;
        for (int k = 0; k < 64; ++k) {
            unsigned q = sb + ib * 8;
            if (!used[ib] && tg2_word(out->vram, a + 4) == tg2_word(b->vram, q + 4) &&
                out->vram[(a + 2) & 65535] == b->vram[(q + 2) & 65535]) {
                int d = abs(ax - (int)(tg2_word(b->vram, q + 6) & 511)) +
                        abs(ay - (int)(tg2_word(b->vram, q) & 1023));
                if (d < distance) { best = ib; distance = d; }
            }
            ib = b->vram[(q + 3) & 65535] & 127;
            if (!ib || ib >= 64) break;
        }
        if (best >= 0 && distance < 96) {
            used[best] = 1;
            unsigned q = sb + best * 8;
            if (sprite_undo_count < 64) {
                sprite_undo_addr[sprite_undo_count] = a;
                sprite_undo_y[sprite_undo_count] = tg2_word(out->vram, a);
                sprite_undo_x[sprite_undo_count] = tg2_word(out->vram, a + 6);
                ++sprite_undo_count;
            }
            put_word(out->vram, a, mix_wrap(ay, tg2_word(b->vram, q) & 1023, 1023));
            put_word(out->vram, a + 6, mix_wrap(ax, tg2_word(b->vram, q + 6) & 511, 511));
        }
        ia = out->vram[(a + 3) & 65535] & 127;
        if (!ia || ia >= 64) break;
    }
}
static void mix_pieces(const Scene *a, const Scene *b) {
    mixed_scene = *a;
    unsigned char actor_used[TG2_MAX_ACTORS]={0};
    for(unsigned i=0;i<a->actors.count;++i) {
        const Tg2Actor *p=&a->actors.actors[i]; int best=-1;double distance=96;
        for(unsigned j=0;j<b->actors.count;++j) {
            const Tg2Actor *q=&b->actors.actors[j];
            double d=fabs(p->x-q->x)+fabs(p->y-q->y);
            int same = p->record==q->record && p->kind==q->kind &&
                p->identity==q->identity && (p->car ||
                    (p->kind==0x81 ? p->object==q->object : p->lateral==q->lateral));
            if(!actor_used[j] && same && d<distance){best=j;distance=d;}
        }
        if(best>=0){
            actor_used[best]=1; Tg2Actor *m=&mixed_scene.actors.actors[i];
            float t=(float)tg2v_phase_num/tg2v_phase_den;if(mix_reverse)t=1-t;
            m->x=p->x+(b->actors.actors[best].x-p->x)*t;
            m->y=p->y+(b->actors.actors[best].y-p->y)*t;
            m->continuous=p->continuous+(b->actors.actors[best].continuous-p->continuous)*t;
            m->projection=p->projection+(b->actors.actors[best].projection-p->projection)*t;
            m->depth=p->depth+(b->actors.actors[best].depth-p->depth)*t;
        }
    }
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
    /* The 1x synthesized SAT rounds piece positions. Derive each actor's
     * integer reference from those same pieces, then retain the interpolated
     * fraction inside that integer cell, as on native projection endpoints. */
    for(unsigned i=0;i<a->actors.count;++i) {
        const Tg2Actor *original=&a->actors.actors[i];
        Tg2Actor *actor=&mixed_scene.actors.actors[i];
        int found=0;
        for(unsigned j=0;j<a->count && !found;++j) if(a->pieces[j].actor==(int)i) {
            const Piece *p=&a->pieces[j];
            for(unsigned k=0;k<original->guest_count;++k) {
                const Tg2ModelPiece *q=&a->actors.pieces[original->guest_first+k];
                if(p->attr==q->attr && p->size==q->size &&
                   p->x==original->gx+q->dx && p->y==original->gy+q->dy) {
                    actor->gx=mixed_scene.pieces[j].x-q->dx;
                    actor->gy=mixed_scene.pieces[j].y-q->dy;
                    found=1;break;
                }
            }
        }
        actor->x=fmax(actor->gx,fmin(actor->gx+255.0/256,actor->x));
        actor->y=fmax(actor->gy,fmin(actor->gy+255.0/256,actor->y));
    }

}
static void presentation_begin(const GVDP *v) {
    tg2v_from_picture = tg2v_to_picture = NULL;
    capture_picture = 0;
    if (!tg2v_pictures) tg2v_pictures = calloc(PRESENT_HISTORY, sizeof *tg2v_pictures);
    if (!tg2v_pictures) return;
    unsigned key = tg2_mem32(0xFF231E);
    if (key != picture_key || !tg2v_pictures[picture_index].valid) {
        picture_key = key;
        picture_index = (picture_index + 1) % PRESENT_HISTORY;
        Picture *p = &tg2v_pictures[picture_index];
        p->valid = 1;
        p->frame = tg2v_present_frame;
        tg2v_select_scene(v);
        if (tg2v_shown) p->scene = *tg2v_shown;
        else memset(&p->scene, 0, sizeof p->scene);
        capture_picture = 1;
    }
    if (tg2v_present_frame < PRESENT_DELAY) return;
    uint64_t target = tg2v_present_frame - PRESENT_DELAY;
    for (int i = 0; i < PRESENT_HISTORY; ++i) {
        Picture *p = &tg2v_pictures[i];
        if (!p->valid) continue;
        if (p->frame <= target && (!tg2v_from_picture || p->frame > tg2v_from_picture->frame))
            tg2v_from_picture = p;
        if (p->frame >= target && (!tg2v_to_picture || p->frame < tg2v_to_picture->frame))
            tg2v_to_picture = p;
    }
    if (!tg2v_from_picture) return; /* warm-up: original image until bracketed */
    if (!tg2v_to_picture) tg2v_to_picture = tg2v_from_picture;
    tg2v_phase_den = (unsigned)(tg2v_to_picture->frame - tg2v_from_picture->frame);
    tg2v_phase_num = (unsigned)(target - tg2v_from_picture->frame);
    if (!tg2v_phase_den) { tg2v_phase_den = 1; tg2v_phase_num = 0; }
    mix_reverse = tg2v_phase_num * 2 >= tg2v_phase_den;
    mix_pieces(mix_reverse ? &tg2v_to_picture->scene : &tg2v_from_picture->scene,
               mix_reverse ? &tg2v_from_picture->scene : &tg2v_to_picture->scene);
    mix_reverse = 0;
#ifdef GEN_ENABLE_TRACE
    audit_begin();
#endif
}
void tg2v_scanline(const GVDP *v, int line, const uint32_t *native, int nw,
                     uint32_t *out, int w) {
    if (!line) {
        capture_picture = 0;
        tg2v_from_picture = tg2v_to_picture = NULL;
        /* An overdue frame is not presented: skip the whole synthesis so the
         * guest tick can be repaid sooner. Guest rendering is unaffected. */
        if (tg2v_race60 && !genesis_frame_overdue() && nw == 256 && tg2_race_picture(v)) presentation_begin(v);
    }
    /* Capture every row of an eligible picture, including transient raster
     * bands that use the original row producer below. */
    if (capture_picture && tg2v_pictures && line < PRESENT_ROWS) {
        tg2v_pictures[picture_index].row[line] = *v;
        tg2v_pictures[picture_index].road[line] = road_geometry(v, line);
    }
    if (!tg2v_race60 || line >= PRESENT_ROWS || nw != 256 || !tg2_race_picture(v) || !tg2v_from_picture ||
        genesis_frame_overdue()) {
        tg2v_draw_scanline(v, line, native, nw, out, w);
        return;
    }
    const GVDP *a = &tg2v_from_picture->row[line], *b = &tg2v_to_picture->row[line];
    int nearer_b = tg2v_phase_num * 2 >= tg2v_phase_den;
    const GVDP *source = nearer_b ? b : a;
    /* The snapshot is host-only, immutable between captures and never read by
     * the guest, so the row can be rendered from it directly after applying
     * the two edits below. Copying the complete VDP state per presented
     * scanline cost ~66 KiB x 224 = 14.8 MiB of memory traffic every frame at
     * 60 fps (and evicted the very VRAM the renderer then reads); the undo
     * log is at most 64 sprite entries plus one scroll tg2_word. */
    GVDP *row_vdp = (GVDP *)source;
    /* VSRAM selects a row in one of four authored road atlases, carrying
     * width, stripe phase, palette bank and ground type together. Keep that
     * entire discrete row, VRAM, CRAM and register state from ONE endpoint.
     * Only translate its geometry horizontally; never interpolate atlas Y. */
    unsigned hs = mix_wrap(tg2v_hscroll(a, line, 1), tg2v_hscroll(b, line, 1), 511);
    RoadGeometry ga = tg2v_from_picture->road[line], gb = tg2v_to_picture->road[line];
    /* Ground/separator rows (atlas Y 432..447) have an opaque half and a
     * transparent half. Both endpoints can be non-road there, so the road
     * envelope below does not constrain the interpolated scroll. Translating
     * such a row can move the transparent half onto the native edge and leave
     * a one-line black gap (visible only on synthesized pictures). Keep the
     * row's own discrete scroll instead, exactly like its atlas Y, VRAM and
     * palette. Panorama rows 448..511 remain horizontally interpolated. */
    unsigned source_py = (line + source->vsram[1]) & 511;
    if (!(ga.valid && gb.valid) && !(ga.valid != gb.valid) &&
        source_py >= 432 && source_py < 448)
        hs = tg2v_hscroll(source, line, 1);
    else if (ga.valid && gb.valid) {
        RoadGeometry shape = nearer_b ? gb : ga;
        int ca = 128 + ((tg2v_hscroll(a, line, 1) + 128) & 511) - 256;
        int cb = 128 + ((tg2v_hscroll(b, line, 1) + 128) & 511) - 256;
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
        hs = tg2v_hscroll(source, line, 1); /* horizon/segment boundary: snap row */
    }
    unsigned base = (row_vdp->reg[13] & 63) << 10;
    int hm = row_vdp->reg[11] & 3;
    int hy = hm == 0 ? 0 : hm == 2 ? line & ~7 : line;
    unsigned scroll_slot = base + hy * 4 + 2;
    unsigned scroll_saved = tg2_word(row_vdp->vram, scroll_slot);
    put_word(row_vdp->vram, scroll_slot, hs);
    sprite_undo_count = 0;
    mix_reverse = nearer_b;
    mix_sprites(row_vdp, nearer_b ? a : b);
    mix_reverse = 0;
    uint8_t indices[GVDP_MAX_WIDTH];
    uint32_t pixels[GVDP_MAX_WIDTH];
    static GVDPRasterRow filtered_raster;
    const GVDPRasterRow *saved_layers = tg2v_filter_layers;
    int count;
    if (tg2_highres_scale()>1 && gvdp_capture_presented_scanline(row_vdp, line, &filtered_raster)) {
        count = gvdp_compose_captured(&filtered_raster, indices);
        tg2v_filter_layers = &filtered_raster;
    } else {
        count = gvdp_render_scanline(row_vdp, line, indices);
        tg2v_filter_layers = NULL;
    }
    for (int x = 0; x < count; ++x)
        pixels[x] = indices[x] < 192 ? genesis_dac_cram_to_argb(
            row_vdp->cram[indices[x] & 63], indices[x] >> 6) : 0xFF000000;
    const Scene *saved = tg2v_shown;
    tg2v_shown = &mixed_scene;
    tg2v_synthesizing = 1;
    tg2v_draw_scanline(row_vdp, line, pixels, nw, out, w);
    tg2v_filter_layers = saved_layers;
    tg2v_synthesizing = 0;
    tg2v_shown = saved;
    put_word(row_vdp->vram, scroll_slot, scroll_saved);
    for (unsigned i = 0; i < sprite_undo_count; ++i) {
        put_word(row_vdp->vram, sprite_undo_addr[i], sprite_undo_y[i]);
        put_word(row_vdp->vram, sprite_undo_addr[i] + 6, sprite_undo_x[i]);
    }
    /* Endpoint snapshots must read as real pictures in the audit export. */
#ifdef GEN_ENABLE_TRACE
    audit_row(line, a, b, row_vdp, (int)hs);
#endif
}
/* Engine seam (patch 0033): called once per completed picture, after every
 * native row was produced and before the presented-window crop. Only a
 * qualified single-player race picture with the scale above 1 is composited
 * taller; menus, 2P split-screen and interlaced pictures (native_h 448) keep
 * the machine's own picture and height. */
int tg2v_compose_presented(uint32_t *pixels, int stride, int tg2v_width,
                             int native_w, int native_h) {
    if (!pixels || native_h != 224 || !tg2v_last_frame_race)
        return 0;
    int scale = tg2_highres_scale();
    if (scale <= 1)
        return 0;
    /* A wider canvas is asked for one frame late (see canvas_scale); never
     * paint into a canvas that cannot hold the Nth picture. A native-width
     * canvas (widescreen off) is always wide enough. */
    if (tg2v_width > native_w && tg2v_width < native_w * scale)
        return 0;
    int crop = tg2v_tg2_video_get_hide_overscan() && tg2v_crop_race_ok && tg2v_crop_bottom_ok &&
               tg2v_crop_top_rows == CROP_TOP && tg2v_width >= 256;
    return tg2_highres_build(tg2v_present_frame, pixels, stride, tg2v_width, native_w,
                             native_h, crop ? CROP_TOP : 0,
                             crop ? native_h - CROP_BOTTOM : native_h);
}
/* Called by the runner once per completed picture, after every native row was
 * produced. Cropping is presentation-only: the bands are dropped from what is
 * shown, so screenshots, hashes and the logical canvas all use the cropped
 * height, while guest output and the margin audit keep all 224 lines. An N x
 * picture drops the same bands at its own height (8N top, 16N bottom). */
int tg2v_present_window(int native_w, int native_h, int *first, int *last) {
    int factor = native_h > 0 && native_h % 224 == 0 ? native_h / 224 : 0;
    int crop = factor > 0 && tg2v_tg2_video_get_hide_overscan() && tg2v_crop_race_ok &&
               tg2v_crop_bottom_ok && tg2v_crop_top_rows == CROP_TOP && native_w >= 256;
    tg2v_presented_cropped = crop;
    if (crop) {
        *first = CROP_TOP * factor;
        *last = native_h - CROP_BOTTOM * factor;
        ++tg2v_crop_frames;
    } else if (tg2v_tg2_video_get_hide_overscan() && tg2v_crop_race_ok) {
        /* The crop was wanted but this picture draws into a band. */
        ++tg2v_crop_withheld;
    }
    return crop;
}
