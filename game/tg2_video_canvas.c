/* TG2 video: canvas (pure extraction from tg2_video.c). */
#include "tg2_video_internal.h"

int tg2v_mode;
int tg2v_race60;
uint64_t tg2v_present_frame;
/* Explicit native layer winner for the optional S3 art filter. The raster
 * seam evaluates hardware sprites once and exposes the same priority inputs
 * that produced the native RGB row. Custom margin/HUD writes update its mask. */
const GVDPRasterRow *tg2v_filter_layers;
unsigned char *tg2v_filter_foreground;
unsigned char *tg2v_actor_occluder;
unsigned short *tg2v_actor_front;
int tg2v_actor_free;
#ifdef GEN_ENABLE_TRACE
int tg2v_reference_pass;
#endif
unsigned short tg2v_owners[256];
#ifdef GEN_ENABLE_TRACE
unsigned long long tg2v_actor_rows, tg2v_actor_row_mismatches;
int tg2v_actor_audit = -1;
#endif
int tg2v_foreground_at(const GVDPRasterRow *r, int x) {
    unsigned a = r->plane_a[x], b = r->plane_b[x];
    int sp = r->opaque[x] != 0;
    return (sp && r->high[x]) || ((a & 0xC0) == 0xC0) ||
           ((b & 0xC0) != 0xC0 && (sp || (a & 0x40)));
}
void tg2v_presentation_clear(void);
/* Stock CRT overscan hid the eight-row window band at the top of the race
 * screen. Hiding it is presentation-only: four of the eight rows carry the
 * window-plane colour artefacts documented in docs/WIDESCREEN.md. */
int tg2v_hide_overscan = 1;
void tg2_video_set_hide_overscan(int on) { tg2v_hide_overscan = on != 0; }
int tg2v_tg2_video_get_hide_overscan(void) { return tg2v_hide_overscan; }
int tg2v_hud_edges;
void tg2_video_set_hud_mode(int edges) { tg2v_hud_edges = edges != 0; }
int tg2v_tg2_video_get_hud_mode(void) { return tg2v_hud_edges; }
/* The race picture only uses native lines 8..207. Rows 0..7 are the window
 * band a CRT hid in overscan and rows 208..223 are the bare backdrop, so with
 * Hide overscan on those bands are cropped from the presented picture instead
 * of being left as black bars. A frame is cropped only when its own presented
 * rows justify it (see note_crop_row): a picture that draws into either band
 * keeps its full height, so visible content is never removed. */

int tg2v_crop_race_ok;      /* presented picture is a single-player race */
int tg2v_crop_top_rows;     /* rows 0..CROP_TOP-1 covered by window blanking */
int tg2v_crop_bottom_ok;    /* rows h-CROP_BOTTOM..h-1 all empty            */
int tg2v_presented_cropped; /* the last completed picture was cropped      */
unsigned tg2v_crop_frames, tg2v_crop_withheld;
static double ratio = 16.0 / 9.0;
int tg2v_configure(const char *s) {
    if (!s)
        return 0;
    if (!strcmp(s, "off")) {
        tg2_video_reset();
        tg2v_mode = 0;
        return 1;
    }
    if (!strcmp(s, "fit") || !strcmp(s, "adaptive")) {
        tg2_video_reset();
        tg2v_mode = 1;
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
    tg2v_mode = 2;
    return 1;
}
int tg2v_enabled(void) { return tg2v_mode != 0; }
/* Ownership is independent of the viewport: Hide overscan must also reach a
 * stock 4:3 frame, whose width stays native. */
int tg2v_renderer_enabled(void) {
    return tg2v_mode != 0 || tg2v_race60 || tg2v_tg2_video_get_hide_overscan();
}
static int cropped_height(int nh) {
    return tg2v_presented_cropped && nh > CROP_BANDS ? nh - CROP_BANDS : nh;
}
/* The Nth picture is presented only for qualified race pictures (see
 * compose_presented), and the runner asks for the canvas before the picture
 * exists. Like the overscan crop, the canvas follows the previous completed
 * picture: a race raises it to N x, any other screen keeps the stock canvas so
 * menus stay exactly as they are at 1x. A provider that declines the paint
 * (for example on the first race frame, before the wider canvas exists) still
 * raises the flag, so the transition costs one frame, not a squashed picture. */
int tg2v_highres_wanted;
int tg2v_canvas_scale(void) {
    return tg2v_highres_wanted ? tg2_highres_scale() : 1;
}
int tg2v_width(int dw, int dh, int nw, int nh) {
    /* The canvas follows the presented height: with the empty race bands
     * cropped, 16:9 at 200 lines is 356 pixels wide instead of 398 at 224.
     * A render scale above 1 multiplies the whole 1x canvas by N, so the
     * presented picture keeps the exact N:1 relationship in both axes. */
    int scale = tg2v_canvas_scale();
    if (tg2v_mode == 0) {
        /* Planning runs before the raster IRQ switches to H32, so `nw` can
         * still be the nominal H40 width (320). A qualified 1P race is H32
         * (256); keep Off exactly N times that actual native picture. */
        return (tg2v_highres_wanted ? 256 : nw) * scale;
    }
    int h = cropped_height(nh);
    double w = h * (tg2v_mode == 2 ? ratio : dw > 0 && dh > 0 ? (double)dw / dh : 4.0 / 3.0);
    int result = w > 4096 ? 4096 : (int)(w + 0.5);
    result *= scale;
    /* The capped canvas must still contain whole N-pixel columns. At 3x,
     * 4096 is not divisible by N and would bypass the high-res builder. */
    if (result > 4096) result = (4096 / scale) * scale;
    return result < nw * scale ? nw * scale : result;
}
