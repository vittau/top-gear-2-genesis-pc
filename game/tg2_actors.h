/* tg2_actors.h — read-only actor snapshots for the N x renderer
 * (docs/HIGHRES.md §3, §14). */
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Pre-instruction hook sites (game.toml): $B42E/$B4D6 right after the
 * projection's `swap d1`, $B584 mapper entry, $B5FA per mapping header. */
void tg2_actors_hook(uint32_t pc);
void tg2_actors_frame(uint64_t frame);
void tg2_actors_reset(void);
/* Qualification only: TG2_ACTOR_LOG=path writes the LOD evidence stream. */
int tg2_actors_logging(void);

#ifdef __cplusplus
}
#endif
