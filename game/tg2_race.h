/* TG2 has distinct simulation, audio-policy and raster ownership states.
 * Do not infer one from another: pause, menus and raster transitions differ. */
#pragma once
#include "tg2_memory.h"
#include "video/genesis_vdp.h"

enum {
    TG2_RACE_VINT_VECTOR = 0xFF01ECu,
    TG2_RACE_VINT = 0x4714u,
    TG2_RACE_VINT_BUSY = 0x49CCu
};

/* Freeze the sound policy adopted at race start, including paused/2P phases.
 * ROM $471C installs BUSY and $49AC restores RACE before RTE. The default
 * engine delivers V-int atomically, so frame-pre cannot see BUSY (801 base
 * boundaries sampled, zero hits). Only opt-in GENESIS_INTERLEAVE_IRQ could
 * expose it there; preserve the existing low-word-only policy in that case. */
static inline int tg2_race_audio_policy_frozen(void) {
    return tg2_ram16(TG2_RACE_VINT_VECTOR + 2u) == TG2_RACE_VINT;
}

/* Simulation eligibility for 60-fps interpolation, not sound ownership. */
static inline int tg2_race_tick_active(void) {
    unsigned target = tg2_ram32(TG2_RACE_VINT_VECTOR);
    return (target == TG2_RACE_VINT || target == TG2_RACE_VINT_BUSY)
        && tg2_ram16(0xFF22FAu) == 0
        && (int16_t)tg2_ram16(0xFF1866u) >= 0
        && tg2_ram16(0xFF189Eu) == 0;
}

/* This row is a 1P race picture: use its own VDP/raster state, which can
 * differ from the CPU's next scene or simulation eligibility. */
static inline int tg2_race_picture(const GVDP *v) {
    unsigned op = tg2_ram16(0xF9FEu);
    return !(v->reg[12] & 15) && v->reg[16] == 0x11 && ((v->reg[2] & 56) << 10) == 0xC000 &&
           ((v->reg[4] & 7) << 13) == 0xE000 && !tg2_ram16(0x189Eu) &&
           (op == 0x2C9D || op == 0x601E || op == 0x6042);
}
