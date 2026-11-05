#pragma once
#include "game_video.h"
extern const GameVideo tg2_video;
void tg2_video_command(int id, const char *json);
int tg2_video_hook(uint32_t pc);
void tg2_video_reset(void);
/* Presentation preference: 0 = Centered (default), 1 = Edges. */
void tg2_video_set_hud_mode(int edges);
int tg2_video_get_hud_mode(void);
