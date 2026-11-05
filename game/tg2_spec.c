/* Top Gear 2 (USA): stock 4:3 adapter. IRQ vectors point to installed RAM
 * code; the engine resolves RAM execution through recomp_call_addr. */
#include "game_spec.h"
#include "genesis_runtime.h"
#if TG2_TIMING_EXPERIMENT
#include <string.h>
#include <stdlib.h>
/* RESEARCH ONLY: IRQ cadence stays native, but faster main-loop view sampling
 * changes terrain/collision inputs to IRQ physics. See docs/FRAMERATE.md.
 * This is intentionally absent from normal builds and the player's options. */
static int race_headroom;
static void tg2_timing_init(void)
{
    const char *value = getenv("TG2_RACE_HEADROOM");
    race_headroom = value && !strcmp(value, "1");
}
static unsigned tg2_main_cpu_divisor(void)
{
    return race_headroom && glue_peek32(0xFF01ECu) == 0x004714u
        && glue_peek16(0xFF22FAu) == 0 /* palette fade has finished */
        && (int16_t)glue_peek16(0xFF1866u) >= 0 /* countdown has ended */
        ? 64 : 1;
}
static void tg2_entry(void) { tg2_timing_init(); recomp_call_addr(0x000200u); }
#else
static void tg2_entry(void) { recomp_call_addr(0x000200u); }
#endif
static void tg2_vblank(void) { recomp_call_addr(0xFF01EAu); }
static void tg2_hblank(void) { recomp_call_addr(0xFFF9FEu); }
const GameSpec g_game_spec = {
    .display_name = "Top Gear 2",
    .short_name = "TG2",
    .expected_rom_crc32 = 0xBD3074D2u,
    .expected_rom_size = 0x100000u,
    .tier3_floor_default = 1,
    .call_entry_point = tg2_entry,
    .call_vblank = tg2_vblank,
    .call_hblank = tg2_hblank,
#if TG2_TIMING_EXPERIMENT
    .main_cpu_divisor = tg2_main_cpu_divisor,
#endif
};
