/* Side-effect-free, big-endian guest storage reads. Addresses wrap exactly
 * as the old game readers did; unmapped addresses are not bus accesses. */
#pragma once
#include "genesis_runtime.h"

static inline unsigned tg2_word(const unsigned char *bytes, unsigned address) {
    return (bytes[address & 65535u] << 8) | bytes[(address + 1u) & 65535u];
}
static inline unsigned tg2_ram16(unsigned address) { return tg2_word(g_ram, address); }
static inline unsigned tg2_ram32(unsigned address) {
    return (tg2_ram16(address) << 16) | tg2_ram16(address + 2u);
}
static inline unsigned tg2_mem16(unsigned address) {
    address &= 0xFFFFFFu;
    if (address < 0xFFFFFu) return (g_rom[address] << 8) | g_rom[address + 1u];
    if (address >= 0xFF0000u) return tg2_ram16(address);
    return 0;
}
static inline unsigned tg2_mem32(unsigned address) {
    return (tg2_mem16(address) << 16) | tg2_mem16(address + 2u);
}
