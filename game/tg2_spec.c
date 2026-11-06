/* Top Gear 2 (USA) game adapter.
 *
 * IRQ vectors point to installed RAM code; the engine resolves RAM execution
 * through recomp_call_addr. The stock build is byte-identical to the original
 * 4:3 port. The optional "60 fps race" mode is described below and in
 * docs/FRAMERATE.md; its preference is latched at each race start. */
#include "game_spec.h"
#include "genesis_runtime.h"
#include "tg2_video.h"
#include "tg2_options.h"
extern int tg2_audio_hook(uint32_t pc);
extern void tg2_audio_reset(void);
extern void tg2_frame_post(uint64_t frame_count);
struct RecompLauncherCModProvider;
const struct RecompLauncherCModProvider *tg2_mods(const struct RecompLauncherCModProvider *base);
static const GameDebugCommand commands[] = {
    {"tg2_video", tg2_video_command},
    {"tg2_ui", tg2_options_ui_command},
};

#include <stdio.h>

/* The guest always runs at stock cycle cost. Only the host video adapter
 * uses this race-latched preference; no IRQ hooks or temporary RAM writes. */
static int s_race60, s_race_live;
static int race_live(void)
{
    uint32_t target = glue_peek32(0xFF01ECu);
    return (target == 0x4714u || target == 0x49CCu)
        && glue_peek16(0xFF22FAu) == 0
        && (int16_t)glue_peek16(0xFF1866u) >= 0
        && glue_peek16(0xFF189Eu) == 0;
}
static void tg2_frame_pre(uint64_t frame_count)
{
    int live = race_live();
    if (live && !s_race_live) s_race60 = tg2_race60_requested();
    s_race_live = live;
    tg2_video_frame(frame_count, live && s_race60);
}

/* ── Option surface ────────────────────────────────────────────────────────
 * Player options live in settings.ini ([mods.race60]) and are edited by the
 * launcher Mods page or the in-game overlay. The environment override below
 * exists only for automated captures. */
static void tg2_entry(void)
{
    tg2_options_apply_env();
    s_race60 = tg2_race60_requested();
    if (s_race60)
        fprintf(stderr, "[tg2] race presentation: 60 fps option on\n");
    recomp_call_addr(0x000200u);
}


/* Scene capture hooks only read guest state; the audio hook owns the
 * RACE SOUND menu leaf and the race sound-policy sites. */
static int tg2_instruction_hook(uint32_t pc)
{
    if (tg2_audio_hook(pc)) return 1;
    return tg2_video_hook(pc);
}
static void tg2_post_reset(void)
{
    tg2_audio_reset();
    tg2_video_reset();
}
static void tg2_vblank(void) { recomp_call_addr(0xFF01EAu); }
static void tg2_hblank(void) { recomp_call_addr(0xFFF9FEu); }
const GameSpec g_game_spec = {
    .video = &tg2_video,
    .video_default = "fit",
    .load_settings = tg2_options_load,
    .save_settings = tg2_options_save,
    .runtime_ui_items = tg2_options_runtime_items,
    .runtime_ui_get = tg2_options_runtime_get,
    .runtime_ui_set = tg2_options_runtime_set,
    .mods = tg2_mods,
    .on_post_reset = tg2_post_reset,
    .on_state_loaded = tg2_post_reset,
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
    .on_frame_pre = tg2_frame_pre,
    .on_frame_post = tg2_frame_post,
    .instruction_hook = tg2_instruction_hook,
};
