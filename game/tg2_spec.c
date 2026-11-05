/* Top Gear 2 (USA): stock 4:3 adapter. IRQ vectors point to installed RAM
 * code; the engine resolves RAM execution through recomp_call_addr. */
#include "game_spec.h"
#include "genesis_runtime.h"
static void tg2_entry(void) { recomp_call_addr(0x000200u); }
static void tg2_vblank(void) { recomp_call_addr(0xFF01EAu); }
static void tg2_hblank(void) { recomp_call_addr(0xFFF9FEu); }
extern int tg2_instruction_hook(uint32_t pc);
extern void tg2_frame_post(uint64_t frame_count);
const GameSpec g_game_spec = {
    .display_name = "Top Gear 2",
    .short_name = "TG2",
    .expected_rom_crc32 = 0xBD3074D2u,
    .expected_rom_size = 0x100000u,
    .tier3_floor_default = 1,
    .call_entry_point = tg2_entry,
    .call_vblank = tg2_vblank,
    .call_hblank = tg2_hblank,
    .instruction_hook = tg2_instruction_hook,
    .on_frame_post = tg2_frame_post,
};
