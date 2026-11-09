#pragma once
#include "game_video.h"
extern const GameVideo tg2_video;
void tg2_video_command(int id, const char *json);
/* Compact row-state dump for S1 evidence (see docs/HIGHRES.md §8). */
void tg2_video_highres_command(int id, const char *json);
int tg2_video_hook(uint32_t pc);
void tg2_video_reset(void);
/* Presentation preference: 0 = Centered (default), 1 = Edges. */
void tg2_video_set_hud_mode(int edges);
int tg2_video_get_hud_mode(void);
/* Presentation preference: 1 = Hide overscan (default), 0 = show it. */
void tg2_video_set_hide_overscan(int on);
int tg2_video_get_hide_overscan(void);

/* Called once per stock simulation V-int; enables host presentation only. */
void tg2_video_frame(uint64_t frame, int race60);
