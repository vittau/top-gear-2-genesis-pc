/* Game-owned audio policy and lifecycle; the engine chip APIs live in
 * audio/event_queue.h and audio/mixer.h. */
#pragma once
#include <stdint.h>
int tg2_audio_hook(uint32_t pc);
void tg2_audio_reset(void);
void tg2_audio_frame_pre(void);
int tg2_audio_race_sound(void);
void tg2_audio_set_race_sound(int mode);
