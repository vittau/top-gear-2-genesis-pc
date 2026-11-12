/* TG2 video: adapter (pure extraction from tg2_video.c). */
#include "tg2_video_internal.h"

/* Reuse the framework's immutable presented-row seam; sprite/status work is
 * not repeated on the live VDP. Off uses exactly the legacy row producer. */
static int filter_raster_enabled(const GVDP *v) {
    return tg2_highres_scale()>1 && tg2_race_picture(v);
}
static void scanline_presented(const GVDP *v, int line, int nw, uint32_t *out,
                               int w, GameVideoNativeRow native_row, void *ctx,
                               const GVDPRasterRow *raster) {
    tg2v_filter_layers = tg2_highres_scale()>1 ? raster : NULL;
    tg2v_scanline(v, line, native_row(ctx), nw, out, w);
    tg2v_filter_layers = NULL;
}
/* A render scale above 1 owns the canvas even with widescreen off; enabled()
 * keeps reporting the widescreen option itself. */
static int presented_width(void) { return tg2_highres_scale() > 1; }
const GameVideo tg2_video = {
    .configure = tg2v_configure, .enabled = tg2v_enabled, .width = tg2v_width, .scanline = tg2v_scanline,
    .renderer_enabled = tg2v_renderer_enabled, .present_window = tg2v_present_window,
    .present_frame = tg2v_compose_presented, .presented_width = presented_width,
    .raster_enabled = filter_raster_enabled, .scanline_presented = scanline_presented};
