#pragma once
#include <stdint.h>
/* SPIKE (task 29): sprite LOD / projection capture. See tg2_lod_probe.c. */
void tg2_lod_probe_frame(uint64_t frame);
int tg2_lod_probe_hook(uint32_t pc);
void tg2_lod_command(int id, const char *json);
