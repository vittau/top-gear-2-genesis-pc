/* Top Gear 2 (USA): stock 4:3 adapter. IRQ vectors point to installed RAM
 * code; the engine resolves RAM execution through recomp_call_addr. */
#include "game_spec.h"
#include "genesis_runtime.h"
#include "tg2_video.h"
struct RecompLauncherCModProvider;
const struct RecompLauncherCModProvider *tg2_mods(const struct RecompLauncherCModProvider *base);
static const GameDebugCommand commands[] = {{"tg2_video", tg2_video_command}};
static void tg2_entry(void) { recomp_call_addr(0x000200u); }
static void tg2_vblank(void) { recomp_call_addr(0xFF01EAu); }
static void tg2_hblank(void) { recomp_call_addr(0xFFF9FEu); }
const GameSpec g_game_spec = {
    .video = &tg2_video,
    .video_default = "fit",
    .mods = tg2_mods,
    .instruction_hook = tg2_video_hook,
    .on_post_reset = tg2_video_reset,
    .on_state_loaded = tg2_video_reset,
    .commands = commands,
    .command_count = sizeof commands / sizeof commands[0],
    .display_name = "Top Gear 2",
    .short_name = "TG2",
    .expected_rom_crc32 = 0xBD3074D2u,
    .expected_rom_size = 0x100000u,
    .tier3_floor_default = 1,
    .call_entry_point = tg2_entry,
    .call_vblank = tg2_vblank,
    .call_hblank = tg2_hblank,
};
