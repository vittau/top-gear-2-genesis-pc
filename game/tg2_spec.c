/* Top Gear 2 (USA) game adapter.
 *
 * IRQ vectors point to installed RAM code; the engine resolves RAM execution
 * through recomp_call_addr. The stock build is byte-identical to the original
 * 4:3 port. The optional "60 fps race" mode is described below and in
 * docs/FRAMERATE.md; it is off unless the player enables it. */
#include "game_spec.h"
#include "genesis_runtime.h"
#include "tg2_video.h"
#include "tg2_options.h"
struct RecompLauncherCModProvider;
const struct RecompLauncherCModProvider *tg2_mods(const struct RecompLauncherCModProvider *base);
static const GameDebugCommand commands[] = {
    {"tg2_video", tg2_video_command},
    {"tg2_ui", tg2_options_ui_command},
};

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ── Guest addresses used by the race presentation-rate option ──────────────
 * All addresses are verified against the raw ROM and runtime snapshots in
 * docs/FRAMERATE.md and docs/RAM_MAP.md. */
#define TG2_VINT_TARGET   0x00FF01ECu  /* live V-int ROM target */
#define TG2_FADE_PHASE    0x00FF22FAu  /* 1 fade in, 0 done, 2 fade out */
#define TG2_RACE_PHASE    0x00FF1866u  /* countdown negative, then race time */
#define TG2_RACE_VINT     0x00FF238Cu  /* race V-int counter (1 per V-int) */
#define TG2_VINT_RACE     0x00004714u  /* race V-int handler */
#define TG2_VINT_REENT    0x000049CCu  /* target installed inside that handler */
#define TG2_PLAYER_REC    0x00FF18CAu  /* player 1 record */
#define TG2_PLAYER_POS    0x00FF18CAu  /* record +0: track position */
#define TG2_PLAYER_VIEW   0x00FF18D2u  /* record +8: view/track sample position */
#define TG2_SECOND_PLAYER 0x00FF189Eu  /* non-zero in a two-player race */
#define TG2_UPDATE_PLAYER 0x0000CD84u  /* per-player update chain (IRQ, 60 Hz) */
#define TG2_SAMPLE_VIEW_A 0x0000CE18u  /* reads record +8 */
#define TG2_SAMPLE_VIEW_B 0x0000D644u  /* reads record +8 -> +$12/+$14/+$16 */
#define TG2_SAMPLE_VIEW_C 0x0000DA82u  /* reads record +8 */
#define TG2_SUBMIT_READY  0x0000476Cu  /* V-int: picture submitted, ready cleared */
#define TG2_QUEUED_UPLOAD 0x000052C2u  /* pending VRAM block upload ($FF23C4) */
#define TG2_DEFERRED_WORK 0x0000E4A0u  /* deferred VRAM block/object work */
#define TG2_UPLOAD_PENDING 0x00FF23C4u /* a queued VRAM upload is waiting */

/* Main-program cycle-cost divisor applied only while a race picture is being
 * built; IRQ, DMA, raster and sound-driver clocks stay native. One stock build
 * costs ~2.9 frames of emulated 68K time, so 8 leaves a wide margin for
 * heavier scenes. TG2_RACE60_DIVISOR exists only for A/B investigation; the
 * validated range is 8..64 (identical measured output). */
static unsigned s_divisor = 8u;

/* The stock main program refreshes the view position once per completed
 * picture, which measures as one V-int in three. See docs/FRAMERATE.md. */
#define TG2_VIEW_PERIOD 3u

static int      s_race60;          /* option latched for the current race */
static int      s_race_live;       /* last observed "race is running" state */
static int      s_race60_hook;     /* re-entrancy guard for the hooks */
static uint32_t s_phys_view;       /* view position handed to IRQ physics */
static int      s_phys_view_valid;

static int tg2_race_live(void)
{
    uint32_t target = glue_peek32(TG2_VINT_TARGET);
    /* $004714 installs $0049CC on entry and restores it on exit, so both
     * values mean "the live V-int handler is the race handler". */
    return (target == TG2_VINT_RACE || target == TG2_VINT_REENT)
        && glue_peek16(TG2_FADE_PHASE) == 0        /* palette fade finished */
        && (int16_t)glue_peek16(TG2_RACE_PHASE) >= 0 /* countdown finished */
        && glue_peek16(TG2_SECOND_PLAYER) == 0;    /* single-player races only */
}

static int tg2_race_active(void)
{
    return s_race60 && tg2_race_live();
}

static unsigned tg2_main_cpu_divisor(void)
{
    return tg2_race_active() ? s_divisor : 1u;
}

/* Refresh the physics view position on the stock schedule. The main program
 * writes record +8 from the physical position at the start of a picture build;
 * with one build per V-int that becomes one V-int in TG2_VIEW_PERIOD, which is
 * the measured stock cadence. */
static void tg2_view_gate(void)
{
    if (!s_phys_view_valid) {
        s_phys_view = glue_peek32(TG2_PLAYER_VIEW);
        s_phys_view_valid = 1;
    }
    if ((glue_peek16(TG2_RACE_VINT) % TG2_VIEW_PERIOD) == 0)
        s_phys_view = glue_peek32(TG2_PLAYER_POS);
}

static void tg2_frame_pre(uint64_t frame_count)
{
    (void)frame_count;
    int live = tg2_race_live();
    if (live && !s_race_live) {
        /* A race just started: adopt the player's current choice and begin
         * with a fresh stock-schedule view position. A mid-race toggle is
         * deliberately deferred to the next race so physics never changes
         * inside one. */
        s_race60 = tg2_race60_requested();
        s_phys_view_valid = 0;
    }
    s_race_live = live;
    if (tg2_race_active()) tg2_view_gate();
}

/* Run one game routine with the stock-schedule view position in place, so the
 * IRQ physics sees exactly the terrain input it sees on the stock build while
 * the picture keeps the fresh position. A replacing hook owns the routine's
 * register/stack contract; these routines are plain leaf call chains. */
static void tg2_call_with_stock_view(uint32_t addr)
{
    uint32_t fresh = glue_peek32(TG2_PLAYER_VIEW);
    s_race60_hook = 1;
    glue_poke32(TG2_PLAYER_VIEW, s_phys_view);
    recomp_call_addr(addr);
    glue_poke32(TG2_PLAYER_VIEW, fresh);
    s_race60_hook = 0;
}

/* The stock race V-int handler splits its work by a "picture ready" handshake:
 * with a new picture it submits it ($004768) and skips the deferred block at
 * $004774..$0047C0; without one it runs that block instead. With a picture
 * ready every V-int the block would never run, which starves the game's
 * queued VRAM uploads ($00E4A0, $0052C2) and the deferred object timer work.
 * Run it on the two V-ints in three that the stock build leaves free. */
static void tg2_deferred_work(void)
{
    M68KState saved = g_cpu;
    if (glue_peek16(TG2_FADE_PHASE) & 0x8000) return;
    g_cpu.D[4] &= 0xFFFFFF00u;                  /* sf.b d4 */
    if (glue_peek8(TG2_UPLOAD_PENDING) != 0) {
        recomp_call_addr(TG2_QUEUED_UPLOAD);
    }
    if ((g_cpu.D[4] & 0xFFu) == 0) recomp_call_addr(TG2_DEFERRED_WORK);
    g_cpu = saved;
}

static int tg2_race60_hook(uint32_t pc)
{
    if (!tg2_race_active() || s_race60_hook) return 0;
    /* A pending guest split-stack adjustment means this entry came from a
     * computed tail dispatch; let the generated body own that bookkeeping. */
    if (g_split_sp_popped != 0) return 0;
    switch (pc) {
    case TG2_UPDATE_PLAYER:  /* the whole per-player IRQ chain, A4 set inside */
        tg2_call_with_stock_view(pc);
        return 1;
    case TG2_SAMPLE_VIEW_A:
    case TG2_SAMPLE_VIEW_B:
    case TG2_SAMPLE_VIEW_C:
        /* Same routines reached from other IRQ paths with the player record. */
        if (g_cpu.A[4] != TG2_PLAYER_REC) return 0;
        tg2_call_with_stock_view(pc);
        return 1;
    case TG2_SUBMIT_READY:
        if (glue_peek16(TG2_RACE_VINT) % TG2_VIEW_PERIOD) tg2_deferred_work();
        return 0;   /* continue with the picture submission */
    default:
        return 0;
    }
}

/* ── Option surface ────────────────────────────────────────────────────────
 * Player options live in settings.ini ([mods.race60]) and are edited by the
 * launcher Mods page or the in-game overlay. The environment override below
 * exists only for automated captures. */
static void tg2_entry(void)
{
    const char *div = getenv("TG2_RACE60_DIVISOR");
    if (div) {
        unsigned long v = strtoul(div, NULL, 10);
        if (v >= 1 && v <= 1024) s_divisor = (unsigned)v;
    }
    tg2_options_apply_env();
    s_race60 = tg2_race60_requested();
    if (s_race60)
        fprintf(stderr, "[tg2] race presentation: 60 fps option on\n");
    recomp_call_addr(0x000200u);
}


/* Both presentation options hook distinct guest PCs. The 60 fps hook may
 * replace a routine (returns 1); the widescreen hook only captures. */
static int tg2_instruction_hook(uint32_t pc)
{
    if (tg2_race60_hook(pc)) return 1;
    return tg2_video_hook(pc);
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
    .on_frame_pre = tg2_frame_pre,
    .instruction_hook = tg2_instruction_hook,
    .main_cpu_divisor = tg2_main_cpu_divisor,
};
