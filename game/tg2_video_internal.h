/* Private video implementation contract. These names are shared only by the
 * canvas, scene, world/HUD, raster, presentation and diagnostic modules.
 * Public game/runner interfaces remain in tg2_video.h. */
#pragma once
#include "tg2_video.h"
#include "tg2_highres.h"
#include "tg2_actors.h"
#include "cmd_server.h"
#include "genesis_runtime.h"
#include "tg2_race.h"
#include "tg2_memory.h"
#include "video/genesis_dac.h"
#include "video/genesis_vdp.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>


enum { CROP_TOP = 8, CROP_BOTTOM = 16, CROP_BANDS = CROP_TOP + CROP_BOTTOM };
enum { MAX_PIECES = 2048, HISTORY = 4 };
typedef struct {
    int x, y;
    unsigned attr, size;
    int actor;
    unsigned char kind;
} Piece;
typedef struct {
    Piece pieces[MAX_PIECES];
    Tg2ActorSet actors;
    short sat_piece[64];
    unsigned count, serial, sat_size;
    unsigned char sat[512];
} Scene;
enum { PRESENT_HISTORY = 8, PRESENT_ROWS = 224, PRESENT_DELAY = 3 };
typedef struct { int left, right, valid; } RoadGeometry;
typedef struct {
    GVDP row[PRESENT_ROWS];
    RoadGeometry road[PRESENT_ROWS];
    Scene scene;
    uint64_t frame;
    int valid;
} Picture;
typedef struct {
    int ha, hb, va, vb;
    unsigned a, b;
} Tg2VideoScrollRow;
typedef struct {
    unsigned char reg[24];
    unsigned short vsram[2], cram[64];
} Tg2VideoTopRow;

extern int tg2v_actor_audit;
extern int tg2v_actor_free, tg2v_reference_pass;
extern unsigned short *tg2v_actor_front;
void tg2v_actor_native_row(const GVDP *v,int line,int nw,const uint32_t *native,
                              uint32_t *out,GVDPRasterRow *free_row,unsigned short *tg2v_owners);
extern unsigned char *tg2v_actor_occluder;
extern unsigned long long tg2v_actor_rows, tg2v_actor_row_mismatches;
void tg2v_audit_margins(const GVDP *v, int line, const uint32_t *native,
                          int nw, const uint32_t *out, int w);
extern int tg2v_synthesizing, tg2v_audit_race_frame;
int tg2v_canvas_scale(void);
int tg2v_compose_presented(uint32_t *pixels, int stride, int tg2v_width,
                             int native_w, int native_h);
int tg2v_configure(const char *s);
extern int tg2v_crop_bottom_ok;
extern unsigned tg2v_crop_frames, tg2v_crop_withheld;
extern int tg2v_crop_race_ok;
extern int tg2v_crop_top_rows;
void tg2v_draw_scanline(const GVDP *v, int line, const uint32_t *native, int nw, uint32_t *out,
                     int w);
int tg2v_enabled(void);
extern unsigned char *tg2v_filter_foreground;
extern const GVDPRasterRow *tg2v_filter_layers;
int tg2v_foreground_at(const GVDPRasterRow *r, int x);
extern unsigned tg2v_wide_lines, tg2v_native_lines, tg2v_frame_margin_pixels;
extern Picture *tg2v_from_picture, *tg2v_to_picture;
extern int tg2v_hide_overscan;
extern int tg2v_highres_wanted;
unsigned tg2v_hscroll(const GVDP *v, int line, int plane);
extern int tg2v_hud_edges;
extern unsigned tg2v_hud_plane_pixels, tg2v_hud_marker_pixels, tg2v_hud_sprite_pixels;
int tg2v_hud_region(int x, int side);
void tg2v_hud_row(const GVDP *v, int line, int ha, int hb, int va, int vb,
                    unsigned ba, unsigned bb, const uint32_t *pal, int nw,
                    uint32_t *out, int w);
int tg2v_hud_tile(unsigned attr);
extern int tg2v_last_frame_race;
extern unsigned tg2v_serial, tg2v_overflow, tg2v_matched_pieces, tg2v_margin_pieces;
extern int tg2v_mode;
void tg2v_note_crop_row(int line, const uint32_t *out, int w);
extern unsigned short tg2v_owners[256];
extern unsigned tg2v_pa_extend_mask;
extern unsigned tg2v_phase_num, tg2v_phase_den;
extern Picture *tg2v_pictures;
unsigned tg2v_pixel(const GVDP *v, unsigned base, int x, int y, unsigned *attr);
void tg2v_plane_a_margins(const GVDP *v, int line, const uint32_t *native,
                            int nw, const uint32_t *pal, uint32_t *out, int w,
                            int ha, int va, unsigned ba);
void tg2v_prepare_actors(const GVDP *v);
extern uint64_t tg2v_present_frame;
int tg2v_present_window(int native_w, int native_h, int *first, int *last);
void tg2v_presentation_clear(void);
extern int tg2v_presented_cropped;
int tg2v_promoted_sat(int link);
extern int tg2v_race60;
int tg2v_renderer_enabled(void);
int tg2v_road_x(int nx, int scroll, int py);
extern Tg2VideoScrollRow tg2v_rows[240];
void tg2v_scanline(const GVDP *v, int line, const uint32_t *native, int nw,
                     uint32_t *out, int w);
void tg2v_select_scene(const GVDP *v);
extern const Scene *tg2v_shown;
int tg2v_tg2_video_get_hide_overscan(void);
int tg2v_tg2_video_get_hud_mode(void);
int tg2v_tiles(int n);
extern Tg2VideoTopRow tg2v_top_rows[8];
unsigned tg2v_weather_pixel(const GVDP *v, int line, int nx,
                              int ha, int va, unsigned ba);
int tg2v_width(int dw, int dh, int nw, int nh);
int tg2v_window_at(const GVDP *v, int line, int x);
unsigned tg2v_window_margins(const GVDP *v, int line, const uint32_t *native,
                           int nw, uint32_t *out, int w);
