/* Top Gear 2 (USA) game adapter.
 *
 * IRQ vectors point to installed RAM code; the engine resolves RAM execution
 * through recomp_call_addr. The stock build is byte-identical to the original
 * 4:3 port. The optional "60 fps race" mode is described below and in
 * docs/FRAMERATE.md; its preference is latched at each race start. */
#include "game_spec.h"
#include "tg2_icon.h"
#include "genesis_runtime.h"
#include "tg2_video.h"
#include "tg2_options.h"
extern int tg2_audio_hook(uint32_t pc);
extern void tg2_audio_reset(void);
extern void tg2_frame_post(uint64_t frame_count);
extern void tg2_audio_frame_pre(void);
struct RecompLauncherCModProvider;
const struct RecompLauncherCModProvider *tg2_mods(const struct RecompLauncherCModProvider *base);
static void tg2_password_trace_command(int id, const char *json);
static const GameDebugCommand commands[] = {
    {"tg2_password_trace", tg2_password_trace_command},
    {"tg2_video", tg2_video_command},
    {"tg2_highres", tg2_video_highres_command},
    {"tg2_ui", tg2_options_ui_command},
};

#include <stdio.h>
#include <string.h>
#include "cmd_server.h"

/* Last original-ROM validator return; passive, never changes guest state. */
static struct { unsigned serial, pc, address, result, field_sum; unsigned char work[0x56]; } pw_trace;
static void tg2_password_trace_command(int id, const char *json)
{
    (void)json;
    char hex[sizeof pw_trace.work * 2 + 1], out[512];
    for (unsigned i = 0; i < sizeof pw_trace.work; ++i)
        snprintf(hex + i * 2, 3, "%02x", pw_trace.work[i]);
    snprintf(out, sizeof out, "{\"id\":%d,\"ok\":true,\"serial\":%u,\"pc\":%u,\"address\":%u,\"result\":%u,\"field_sum\":%u,\"work\":\"%s\"}",
        id, pw_trace.serial, pw_trace.pc, pw_trace.address, pw_trace.result, pw_trace.field_sum, hex);
    cmd_send_response(out);
}

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
    tg2_audio_frame_pre();          /* BOTH: writer-routed second sound chip */
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
    /* Frame boundary offered for a host snapshot (F-keys / overlay). */
    glue_state_boundary(pc);
    if (pc == 0x0235C0u || pc == 0x0235C4u) {
        unsigned address = g_cpu.A[0] & 0xFFFFFFu;
        if (address >= 0xFF0000u && address <= 0x1000000u - sizeof pw_trace.work) {
            ++pw_trace.serial; pw_trace.pc = pc; pw_trace.address = address;
            pw_trace.result = g_cpu.D[0] & 65535;
            pw_trace.field_sum = g_cpu.D[7] & 65535;
            memcpy(pw_trace.work, g_ram + (address & 65535u), sizeof pw_trace.work);
        }
    }
    if (tg2_audio_hook(pc)) return 1;
    return tg2_video_hook(pc);
}
static void tg2_post_reset(void)
{
    memset(&pw_trace, 0, sizeof pw_trace);
    tg2_audio_reset();
    tg2_video_reset();
}

/* ── Host snapshots ────────────────────────────────────────────────────────
 * The guest half of a quickstate (CPU, WRAM, VDP/bus, Z80 cores, chips) is
 * the engine's machine payload. What the machine cannot carry is where in
 * the frame loop the snapshot was taken: TG2 has no single game-mode word and
 * no shared WaitForVint routine, it spins on hardware flags inside each
 * screen's own loop. The adapter declares those loop tops as snapshot
 * boundaries (a game hook calls glue_state_boundary there), stores the one
 * the snapshot used, and on load resumes the game fiber at that same
 * instruction (the seeded in-function entry), so the restored CPU continues
 * the exact loop instead of the boot chain that happened to be running. */
#define TG2_STATE_MAGIC   0x54473253u  /* "TG2S" */
#define TG2_STATE_VERSION 1u
typedef struct Tg2HostState {
    uint32_t magic;
    uint32_t version;
    uint32_t poll_site;      /* loop instruction to re-enter */
    uint32_t reserved;
} Tg2HostState;
static uint32_t s_state_poll_site;    /* boundary captured for the save */
static uint32_t s_state_resume_site;  /* loop to re-enter after a load */

/* Frame-loop tops whose re-entry continues the current screen in place. Each
 * is a branch target seeded as an in-function entry in game.toml, so the
 * recompiler emits a callable entry that continues the same host body. */
static const uint32_t tg2_resume_sites[] = {
    0x0065F2u,   /* race: picture-ready wait between frame builds */
    0x001E18u,   /* top-level loop: title/attract screens */
    0x001E9D8u,  /* title: "press START" input spin */
    0x001EBF6u,  /* main menu: per-frame page draw/input loop */
};

static int tg2_state_at_boundary_site(uint32_t site)
{
    for (unsigned i = 0; i < sizeof tg2_resume_sites / sizeof tg2_resume_sites[0]; i++)
        if (tg2_resume_sites[i] == site) { s_state_poll_site = site; return 1; }
    return 0;
}
static size_t tg2_state_size(void) { return sizeof(Tg2HostState); }
static int tg2_state_save(void *data, size_t size)
{
    if (!data || size != sizeof(Tg2HostState) || !s_state_poll_site) return 0;
    Tg2HostState st = { TG2_STATE_MAGIC, TG2_STATE_VERSION, s_state_poll_site, 0 };
    memcpy(data, &st, sizeof st);
    return 1;
}
static int tg2_state_load(const void *data, size_t size, int apply)
{
    if (!data || size != sizeof(Tg2HostState)) return 0;
    Tg2HostState st;
    memcpy(&st, data, sizeof st);
    if (st.magic != TG2_STATE_MAGIC || st.version != TG2_STATE_VERSION) return 0;
    if (apply) s_state_resume_site = st.poll_site;
    return 1;
}
static uint32_t tg2_state_resume_pc(void) { return s_state_resume_site; }
/* Experimental render scale (owner decisions 4, 5 and 6). `values` are the
 * settings.ini internal_scale numbers tg2_highres_scale() understands, in row
 * order; 1 keeps the stock picture. S7 extends this surface (NTSC exclusion,
 * live switching, launcher text); S3 only needs the row to exist and drive the
 * scale. */
static const int tg2_internal_scales[] = {1, 2, 3, 4};
static const char *const tg2_internal_scale_labels[] = {
    "1x (off)", "2x", "3x", "4x"};
static const GameInternalScale tg2_internal_scale = {
    tg2_internal_scales, tg2_internal_scale_labels, 4,
    "Experimental: redraws the road at N times the internal resolution from "
    "the game's own per-line road data. Sprites, HUD and sky keep native "
    "detail. Applies next launch. 1x (off) restores the stock picture.",
    "Experimental: the road is redrawn at 2x-4x from the game's per-line road "
    "data. Applies next launch."};

static void tg2_vblank(void) { recomp_call_addr(0xFF01EAu); }
static void tg2_hblank(void) { recomp_call_addr(0xFFF9FEu); }
const GameSpec g_game_spec = {
    .video = &tg2_video,
    .video_default = "fit",
    /* Top Gear 2 has a two-player mode; player 2's default bindings (IJKL,
     * M/N/comma, right Shift = Start, second gamepad) are live from a fresh
     * install. A saved settings.ini keeps whatever device it recorded. */
    .default_players = 2,
    .load_settings = tg2_options_load,
    .save_settings = tg2_options_save,
    .runtime_ui_items = tg2_options_runtime_items,
    .runtime_ui_layout = &tg2_runtime_layout,
    .runtime_ui_get = tg2_options_runtime_get,
    .runtime_ui_set = tg2_options_runtime_set,
    .mods = tg2_mods,
    .on_post_reset = tg2_post_reset,
    .on_state_loaded = tg2_post_reset,
    .state_build_id = "tg2-0.1.0-bd3074d2-state1",
    .state_size = tg2_state_size,
    .state_save = tg2_state_save,
    .state_load = tg2_state_load,
    .state_at_boundary_site = tg2_state_at_boundary_site,
    .state_resume_pc = tg2_state_resume_pc,
    /* When a resumed screen finishes (race over, menu left) the engine
     * continues the guest callers saved on the stack ($001E82 after a race,
     * $001E1E after the title/menu; patch 0021). The top-level loop is only
     * the fallback once that chain ends. */
    .dispatch_main_loop_pc = 0x001E18u,
    .commands = commands,
    .command_count = sizeof commands / sizeof commands[0],
    .display_name = "Top Gear 2",
    .short_name = "TG2",
    .app_id = "tg2recomp",
    .icon_rgba = tg2_icon_rgba,
    .icon_width = 32,
    .icon_height = 32,
    .expected_rom_crc32 = 0xBD3074D2u,
    .expected_rom_size = 0x100000u,
    .tier3_floor_default = 1,
    /* tg2_video draws every frame itself. The engine's "Internal resolution"
     * row is the owner's control for the experimental high-resolution road
     * rendering (decision 4): same settings.ini value (internal_scale), the
     * port's own 1x-4x vocabulary. */
    .internal_scale = &tg2_internal_scale,
    .call_entry_point = tg2_entry,
    .call_vblank = tg2_vblank,
    .call_hblank = tg2_hblank,
    .on_frame_pre = tg2_frame_pre,
    .on_frame_post = tg2_frame_post,
    .instruction_hook = tg2_instruction_hook,
};
