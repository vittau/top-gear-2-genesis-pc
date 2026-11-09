/* Top Gear 2 (USA): simultaneous race music + sound effects.
 *
 * The cartridge has two independent sound systems and one policy word,
 * $FF240E (A3-$5FFA):
 *   0 = "RACE SOUND: SOUND EFFECTS" - upload the race SFX Z80 image,
 *       tick the 68k FM/PSG SFX engine, do not start music.
 *   1 = "RACE SOUND: MUSIC"         - keep the boot music driver, start a
 *       race track, do not tick or start the SFX engine.
 *
 * This adapter adds a third menu state, "BOTH".  The choice lives in host
 * state (`s_mode`) so it survives every path a player can take: the value
 * page, the menu teardown, a race start, a second race and a guest reset.
 * The cartridge's own word is only ever written in its stock range
 * (0 = SOUND EFFECTS, 1 = MUSIC); BOTH presents 1 to the music-side reads
 * and 0 to the SFX-side reads, at the instruction, for the duration of that
 * instruction only.  Present/restore is therefore re-entrant-safe: the word
 * always ends the instruction with the value the cartridge itself stored.
 *
 * The race-time SFX Z80 image upload is skipped while BOTH is live; that
 * image is never commanded after upload and would overwrite the music
 * driver in Z80 RAM.
 *
 * The SOUND menu text is rendered from dynamic 8x16 glyph tiles.  While the
 * player is on the RACE SOUND page with BOTH selected, the value row's glyph
 * tiles are repainted as "BOTH" in the menu font (see paint_row()).  Nothing
 * in the ROM or in generated C is modified.
 */
#include "genesis_runtime.h"
#include "game_spec.h"
#include "genesis_machine.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* game/tg2_options.c: the RACE SOUND choice is a player option. */
extern void tg2_options_race_sound_changed(int mode);

/* engine/runner/audio/event_queue.h: writer-routed second virtual chip. On in
 * BOTH only, so stock MUSIC/SFX keep the single chip and stay byte-identical. */
void audio_set_chip_routing(int dual);
/* Second Z80 core for the race SFX PCM image, and the 68K-access routing
 * predicate that keeps its upload off the resident music driver. */
void audio_second_z80_set_enabled(int on);
/* Mirrors the engine's audio/event_queue.h contract (the game file does not
 * include engine-internal headers). */
enum {
    AUDIO_Z80_ACCESS_RAM = 0,
    AUDIO_Z80_ACCESS_BUSREQ = 1,
    AUDIO_Z80_ACCESS_RESET = 2
};
typedef int (*AudioZ80RouteFn)(int access, uint16_t off, uint8_t value);
void audio_set_z80_route_fn(AudioZ80RouteFn fn);
/* Which program the first Z80 core runs, for the Music/SFX volume split
 * (engine/runner/audio/event_queue.h). */
void audio_set_first_z80_is_sfx(int is_sfx);

/* Work-RAM addresses (see docs/RAM_MAP.md / docs/AUDIO.md). */
#define RAM_SOUND_MODE   0x240Eu   /* word: 0 = SFX, 1 = MUSIC            */
#define RAM_MENU_PAGE    0x2554u   /* word: menu controller (page index)  */
#define RAM_MENU_VALUE   0x2560u   /* word: RACE SOUND page value (A4+$0C)*/
#define RAM_MENU_DIRTY   0x2556u   /* word: A4+$02 redraw request         */
#define RAM_MENU_STATE   0x256Cu   /* word: A4+$18 page state             */
#define RACE_SOUND_PAGE  4         /* $FF2554 while the value page is open*/

/* RACE SOUND choices.  SFX and MUSIC are the cartridge's own 0/1; BOTH is
 * host-only and never reaches guest RAM as a number. */
enum { TG2_SOUND_SFX = 0, TG2_SOUND_MUSIC = 1, TG2_SOUND_BOTH = 2 };

static int s_mode = TG2_SOUND_SFX;  /* player's choice; stock default */
/* The mode whose routing is LIVE. A RACE SOUND change made while a race is
 * running is remembered (s_mode, the option and the page show it) but its
 * routing/policy layer is adopted at the next race: re-routing mid-race would
 * hand the running music's voices to a chip that was never fed them, which is
 * exactly how a live BOTH/SFX switch used to kill the music. */
static int s_applied = TG2_SOUND_SFX;
static int s_patched;               /* present/restore nesting depth */
static int s_page_seen;             /* RACE SOUND page handler observed */
/* One saved cartridge value per nesting level, so an SFX-side read nested
 * inside a music-side read (or vice versa) restores exactly. */
#define PATCH_DEPTH 8
static uint16_t s_patch_stack[PATCH_DEPTH];

static uint16_t ram_read16(uint32_t addr)
{
    uint16_t o = (uint16_t)(addr & 0xFFFFu);
    return (uint16_t)((g_ram[o] << 8) | g_ram[(uint16_t)(o + 1)]);
}

static void ram_write16(uint32_t addr, uint16_t v)
{
    uint16_t o = (uint16_t)(addr & 0xFFFFu);
    g_ram[o] = (uint8_t)(v >> 8);
    g_ram[(uint16_t)(o + 1)] = (uint8_t)v;
}

/* What the value page shows: the cartridge has two states, BOTH reuses the
 * MUSIC state so every stock reader stays in range. */
static uint16_t page_value(void)
{
    return (uint16_t)(s_mode == TG2_SOUND_SFX ? 0 : 1);
}

static int both_active(void)
{
    return s_applied == TG2_SOUND_BOTH;
}

/* A race installs its own V-int vector at $FF01EE; while it is live, routing
 * and the BOTH policy layer are frozen at the mode the race started with. */
static int race_running(void)
{
    return ram_read16(0xFF0000u + 0x01EEu) == 0x4714u;
}

/* Push the applied mode into the engine (routing, second core, Z80 routing). */
static int z80_route(int access, uint16_t off, uint8_t value);
static void apply_mode(void)
{
    audio_set_chip_routing(both_active());
    audio_second_z80_set_enabled(both_active());
    audio_set_z80_route_fn(z80_route);
}

/* Adopt the player's choice when nothing is running on the old one. */
static void adopt_mode(void)
{
    if (race_running()) return;
    s_applied = s_mode;
    apply_mode();
}

/* ---- Second Z80 core: the race SFX PCM image -----------------------------
 * In BOTH the 68K uploads the race SFX image (its routine at $0700C8) and its
 * SFX engine later sends PCM sample commands to the image's ports at
 * $A0025E..$A00261. Those 68K accesses to Z80 space must reach the second
 * core's own RAM and reset/busreq lines; letting them hit the resident music
 * driver is exactly what stopped both drivers in the first prototype (the
 * upload overwrites all 8 KB and pulses the Z80 reset). The predicate is the
 * game's, so the engine's stock paths are untouched when BOTH is off. */
static int s_sfx_upload;            /* 68K is inside the SFX image upload   */
static FILE *s_pcm_log;

/* Env-gated command trace: every SFX-engine sample command, in every sound
 * mode, straight from the writer's registers. Used to prove the BOTH command
 * stream is SOUND EFFECTS'. */
static void sfx_cmd_log(uint32_t d0, uint32_t d1, uint32_t d2, uint32_t d3)
{
    extern unsigned long g_snd_frame;
    if (!s_pcm_log) {
        const char *p = getenv("GENESIS_AUDIO_SFXPCM_TRACE");
        if (!p || !*p) return;
        s_pcm_log = fopen(p, "w");
        if (!s_pcm_log) return;
        fprintf(s_pcm_log, "# frame cmd d1 d2 d3\n");
    }
    fprintf(s_pcm_log, "%lu %u %u %u %u\n", g_snd_frame,
            d0 & 0xFFu, d1 & 0xFFu, d2 & 0xFFu, d3 & 0xFFu);
    fflush(s_pcm_log);
}

static int z80_route(int access, uint16_t off, uint8_t value)
{
    (void)value;
    if (!both_active()) return 0;
    if (s_sfx_upload) return 1;             /* image upload: RAM + control  */
    if (access != AUDIO_Z80_ACCESS_RAM) return 0;
    /* The SFX engine's sample-command ports. */
    return off >= 0x25Eu && off <= 0x261u;
}

/* ---- Which image is resident on the FIRST Z80 core -----------------------
 * The first core runs the cartridge's music driver in MUSIC and BOTH, but in
 * stock SOUND EFFECTS the race init uploads the small SFX PCM image (ROM
 * $0701F6) over it. That image's writes are sound effects, the driver's are
 * music, so the volume split needs to know which one is resident. Both images
 * have a distinct entry stub at $A00000: the driver starts `DI; LD SP,$1FF0`
 * and the SFX image starts `JP $0410` (docs/AUDIO.md §4), so the resident
 * image is readable straight from the core's RAM. No guest state is written. */
static int first_z80_runs_sfx_image(void)
{
    const uint8_t *ram = g_machine.bus.z80_ram;
    return ram[0] == 0xC3u && ram[1] == 0x10u && ram[2] == 0x04u;
}

static void update_z80_role(void)
{
    audio_set_first_z80_is_sfx(first_z80_runs_sfx_image());
}

/* ---- Value presentation hooks -------------------------------------------
 * Both helpers are no-ops unless BOTH is selected.  A present remembers the
 * cartridge's own value on a small stack so the instruction sees the
 * presented value and the next instruction sees the stock one again, even
 * when an SFX-side read happens inside a music-side one. */
static void present_value(uint16_t want)
{
    if (!both_active()) return;
    uint16_t cur = ram_read16(0xFF0000u + RAM_SOUND_MODE);
    if (s_patched < PATCH_DEPTH) s_patch_stack[s_patched++] = cur;
    if (cur != want) ram_write16(0xFF0000u + RAM_SOUND_MODE, want);
}

static void restore_value(void)
{
    if (s_patched <= 0) return;
    uint16_t prev = s_patch_stack[--s_patched];
    if (ram_read16(0xFF0000u + RAM_SOUND_MODE) != prev)
        ram_write16(0xFF0000u + RAM_SOUND_MODE, prev);
}

static void present_sfx(void)   { present_value(0); }   /* SFX-side read */
static void present_music(void) { present_value(1); }   /* music-side read */

/* Page entry (0x01ED3A) runs in every sound mode, not just BOTH: the page must
 * show the player's choice even when the cartridge word still holds the boot
 * value. BOTH presents MUSIC's 1, so the page's own row and palette are built
 * in stock state and repainted afterwards. */
static void present_session_value(void)
{
    uint16_t want = (uint16_t)(s_mode == TG2_SOUND_SFX ? 0 : 1);
    uint16_t cur = ram_read16(0xFF0000u + RAM_SOUND_MODE);
    if (s_patched < PATCH_DEPTH) s_patch_stack[s_patched++] = cur;
    if (cur != want) ram_write16(0xFF0000u + RAM_SOUND_MODE, want);
}

/* ---- RACE SOUND page value handler ($01F0D4) replacement -----------------
 * d0 = active-low button mask (bit0 up, bit1 down, bits 4-6 A/B/C, bit7
 * start).  The stock handler cycles 0..1; this one adds BOTH above MUSIC.
 * The page value stays in {0,1} so the page's own state machine, the sprite
 * builder and every stock reader keep working. */
static int menu_value_handler(void)
{
    uint32_t d0 = g_cpu.D[0] & 0xFFu;
    /* Accept both the zero-extended 24-bit form and a sign-extended address. */
    uint32_t a4 = g_cpu.A[4] & 0xFFFFFFu;

    if (a4 < 0xFF0000u) return 0;  /* not work RAM: run the stock handler */

    s_page_seen = 1;

    /* The page must show the session's choice even when the cartridge word is
     * stale: a fresh boot with BOTH persisted, or a guest reset, leaves the
     * word at the boot value 0 while the host mode is BOTH. */
    uint16_t page = ram_read16(a4 + 0x0Cu);
    if (page > 1) page = 1;            /* never trust an out-of-range value */
    if (both_active() && page != 1u) {
        page = 1;
        ram_write16(a4 + 0x0Cu, page);
        ram_write16(a4 + 0x02u, (uint16_t)(ram_read16(a4 + 0x02u) + 1));
        ram_write16(a4 + 0x18u, 2);
    }

    if (d0 == 0) {
        g_cpu.D[0] = 0;
        g_cpu.SR = (uint16_t)((g_cpu.SR & ~(SR_N|SR_Z|SR_V|SR_C)) | SR_Z);
        return 1;
    }

    ram_write16(a4 + 0x14u, (uint16_t)d0);

    int mode = s_mode;
    int changed = 0;

    if (d0 & 0x01u) {                  /* up */
        if (mode == TG2_SOUND_BOTH) {
            mode = TG2_SOUND_MUSIC;    /* BOTH -> MUSIC (page value unchanged) */
            changed = 1;
        } else if (page == 1) {
            mode = TG2_SOUND_SFX;      /* MUSIC -> SOUND EFFECTS */
            changed = 1;
        }
    } else if (d0 & 0x02u) {           /* down */
        if (page == 0) {
            mode = TG2_SOUND_MUSIC;    /* SOUND EFFECTS -> MUSIC */
            changed = 1;
        } else if (mode != TG2_SOUND_BOTH) {
            mode = TG2_SOUND_BOTH;     /* MUSIC -> BOTH */
            changed = 1;
        }
    } else if (d0 & 0x70u) {           /* A/B/C: leave the page */
        ram_write16(a4 + 0x02u, 3);
        s_page_seen = 0;
        g_cpu.D[0] = 0;
        g_cpu.SR = (uint16_t)((g_cpu.SR & ~(SR_N|SR_Z|SR_V|SR_C)) | SR_Z);
        return 1;
    }

    if (changed) {
        s_mode = mode;
        tg2_options_race_sound_changed(mode);
        ram_write16(a4 + 0x0Cu, page_value());
        ram_write16(a4 + 0x02u, (uint16_t)(ram_read16(a4 + 0x02u) + 1));
        ram_write16(a4 + 0x18u, 2);
    }
    g_cpu.D[0] = 0;
    g_cpu.SR = (uint16_t)((g_cpu.SR & ~(SR_N|SR_Z|SR_V|SR_C)) | SR_Z);
    return 1;
}

/* ---- Instruction hooks --------------------------------------------------- */
int tg2_audio_hook(uint32_t pc)
{
    switch (pc) {
    case 0x01F0D4u:                    /* RACE SOUND value handler */
        return menu_value_handler();

    case 0x0700C8u:                    /* upload race SFX Z80 image */
        /* In BOTH the upload really runs, but every Z80-space access it makes
         * is routed to the second core (z80_route above), so the resident
         * music driver keeps its RAM and its reset line. */
        if (!both_active()) return 0;
        s_sfx_upload = 1;
        return 0;

    case 0x070188u:                    /* upload routine's RTS */
        s_sfx_upload = 0;
        update_z80_role();
        return 0;

    case 0x0701DAu:                    /* SFX engine writes command $025E */
        sfx_cmd_log(g_cpu.D[0], g_cpu.D[1], g_cpu.D[2], g_cpu.D[3]);
        return 0;

    /* --- RACE SOUND page entry: load the value word from $FF240E ----------
     * The page profile loader copies the cartridge word into the page's value
     * (A4+$0C) at entry. That word is only written by the menu teardown, so on
     * a fresh boot (or after a state load) it still holds SOUND EFFECTS while
     * the player's choice may be MUSIC or BOTH. Present the session choice for
     * this instruction only: the page then builds its own row and palette from
     * a stock state, and the frame hook repaints that row as "BOTH".
     *
     * Writing the page value after the page was already building (the old
     * approach) skipped the profile's own palette upload: the first open of
     * the RACE SOUND page was entirely black and the next one drew mismatched
     * glyphs, because the tiles were recovered from a half-built row. */
    case 0x01ED3Au:
        present_session_value();
        return 0;
    case 0x01ED40u:
        restore_value();
        return 0;

    /* --- SFX-side policy sites: present 0 while BOTH is live --- */
    case 0x006530u:                    /* race init: read sound mode */
    case 0x0048E2u:                    /* race V-int: read sound mode */
    case 0x0250E2u:
    case 0x02511Cu:
    case 0x02504Au:
    case 0x02529Au:
    case 0x0252CCu:
        present_sfx();
        return 0;

    /* --- music-side policy sites: present 1 while BOTH is live ---
     * The stock code only reaches these with word == 1; forcing it keeps
     * music running even if the cartridge word is stale (0) at the moment
     * a race starts or a guest reset reloads the boot value. */
    case 0x025088u:                    /* music start/refresh gate */
    case 0x025200u:                    /* race track start */
    case 0x02523Au:
    /* $02503A stops the music ($FF) before the race track is started. That is
     * a MUSIC-side action: stock SOUND EFFECTS skips it because no music is
     * playing, but BOTH has the menu music running, so it must see MUSIC's
     * value or the stop is skipped and the new track is layered on the old. */
    case 0x02503Au:
        present_music();
        return 0;

    /* --- restore before the dependent branch executes (flags already set) */
    case 0x006538u:
    case 0x0048EAu:
    case 0x0250E6u:
    case 0x025120u:
    case 0x02503Eu:
    case 0x02504Eu:
    case 0x02529Eu:
    case 0x0252D0u:
    case 0x02508Cu:
    case 0x025204u:
    case 0x02523Eu:
        restore_value();
        return 0;

    default:
        return 0;
    }
}

/* ---- "BOTH" text overlay -------------------------------------------------
 * The menu draws text as 8x16 glyphs split over two 8x8 VRAM tiles.  We
 * repaint the value row's tiles in place, so sprite positions, palette and
 * priority remain the game's own.  Only presentation memory is touched.
 *
 * Glyph construction matches the menu font exactly: 8x16 cell, 2-pixel
 * strokes on an 8-pixel grid, a one-pixel outline in palette entry 1 around
 * every stroke, and the stroke body split into palette entry 3 on the top
 * half and 2 on the bottom half.  O and T are the menu font's own glyph
 * shapes (from the RACE SOUND page's "SOUND EFFECTS" value, tiles 457 and
 * 475); B is that font's D bowl plus the E middle bar and H is that font's
 * two stems plus the M crossbar - the parts the font itself uses for those
 * letters on other pages.  docs/AUDIO.md records the derivation.
 *
 * The row is painted as one continuous pixel band, not per glyph, so the
 * four letters can sit centred on x = 160 even though the game's column grid
 * is 5 pixels off that centre. */
static const uint8_t s_glyph_b[16] = {
    0x00, 0x7C, 0x7E, 0x66, 0x66, 0x66, 0x7E, 0x7E,
    0x66, 0x66, 0x66, 0x66, 0x7E, 0x7C, 0x00, 0x00,
};
static const uint8_t s_glyph_o[16] = {
    0x00, 0x3C, 0x7E, 0x66, 0x66, 0x66, 0x66, 0x66,
    0x66, 0x66, 0x66, 0x66, 0x7E, 0x3C, 0x00, 0x00,
};
static const uint8_t s_glyph_t[16] = {
    0x00, 0x7E, 0x7E, 0x18, 0x18, 0x18, 0x18, 0x18,
    0x18, 0x18, 0x18, 0x18, 0x18, 0x18, 0x00, 0x00,
};
static const uint8_t s_glyph_h[16] = {
    0x00, 0x66, 0x66, 0x66, 0x66, 0x66, 0x7E, 0x7E,
    0x66, 0x66, 0x66, 0x66, 0x66, 0x66, 0x00, 0x00,
};

#define BOTH_COLS   4
#define ROW_COLS   16

static const uint8_t *const s_both_glyphs[BOTH_COLS] = {
    s_glyph_b, s_glyph_o, s_glyph_t, s_glyph_h,
};

struct col {
    int x;              /* screen x of the column */
    unsigned top;       /* top VRAM tile of the 8x16 glyph */
};

/* Locate the value row of the RACE SOUND page from the sprite table. */
static int value_cols(struct col *cols)
{
    uint8_t *vram = g_machine.vdp.vram;
    unsigned sat = (unsigned)((g_machine.vdp.reg[5] & 0x7Fu) << 9);
    int header = 0;
    int ncols = 0;

    for (int i = 0; i < 80; i++) {
        unsigned e = sat + (unsigned)i * 8u;
        if (e + 7u >= 0x10000u) break;
        uint16_t w0 = (uint16_t)((vram[e] << 8) | vram[e + 1]);
        uint8_t  sz = vram[e + 2];
        uint16_t w2 = (uint16_t)((vram[e + 4] << 8) | vram[e + 5]);
        uint16_t w3 = (uint16_t)((vram[e + 6] << 8) | vram[e + 7]);
        unsigned y = w0 & 0x3FFu;
        unsigned x = w3 & 0x1FFu;
        unsigned tile = w2 & 0x7FFu;

        if (y == 0x00D4u && x == 0x0130u && tile == 439u)
            header = 1;

        if (y == 0x0104u && ((w2 >> 13) & 3u) == 3u && ncols < ROW_COLS) {
            unsigned hsz = ((sz >> 2) & 3u) + 1u;
            unsigned vsz = (sz & 3u) + 1u;
            if (vsz < 2) vsz = 2;
            for (unsigned c = 0; c < hsz && ncols < ROW_COLS; c++) {
                cols[ncols].x = (int)(x - 128u) + (int)c * 8;
                cols[ncols].top = tile + c * vsz;
                ncols++;
            }
        }
    }

    if (!header || ncols < BOTH_COLS) return 0;
    /* sort by screen x (the sprite list is not ordered) */
    for (int i = 1; i < ncols; i++)
        for (int j = i; j > 0 && cols[j - 1].x > cols[j].x; j--) {
            struct col t = cols[j]; cols[j] = cols[j - 1]; cols[j - 1] = t;
        }
    return ncols;
}

/* Original value-row tiles, saved the first frame BOTH is painted so that
 * cycling BOTH -> MUSIC (page value unchanged, no game redraw) can put the
 * game's own glyphs back.  The row is re-captured whenever the game rebuilds
 * it, which changes its column count or its tile numbers. */
static uint8_t s_saved_tiles[ROW_COLS][2][32];
static unsigned s_saved_top[ROW_COLS];
static int s_saved_n;
static unsigned s_sig;          /* row signature: columns + first tile */

/* Paint the four letters across the row and blank the columns after them. */
static void paint_row(uint8_t *vram, const struct col *cols, int ncols)
{
    enum { MAXW = ROW_COLS * 8 };
    static uint8_t shape[16][MAXW];
    static uint8_t px[16][MAXW];
    const int width = ncols * 8;
    const int gx = (160 - (BOTH_COLS * 8) / 2) - cols[0].x;

    for (int r = 0; r < 16; r++)
        for (int x = 0; x < width; x++) shape[r][x] = 0;

    for (int g = 0; g < BOTH_COLS; g++) {
        for (int r = 0; r < 16; r++) {
            for (int c = 0; c < 8; c++) {
                if (!((s_both_glyphs[g][r] >> (7 - c)) & 1)) continue;
                int x = gx + g * 8 + c;
                if (x >= 0 && x < width) shape[r][x] = 1;
            }
        }
    }

    for (int r = 0; r < 16; r++) {
        for (int x = 0; x < width; x++) {
            if (shape[r][x]) { px[r][x] = (uint8_t)(r < 8 ? 3 : 2); continue; }
            int adj = 0;
            for (int dr = -1; dr <= 1 && !adj; dr++) {
                int rr = r + dr;
                if (rr < 0 || rr >= 16) continue;
                for (int dc = -1; dc <= 1; dc++) {
                    int xx = x + dc;
                    if (xx < 0 || xx >= width) continue;
                    if (shape[rr][xx]) { adj = 1; break; }
                }
            }
            px[r][x] = (uint8_t)(adj ? 1 : 0);
        }
    }

    for (int i = 0; i < ncols; i++) {
        unsigned top = cols[i].top & 0x7FFu;
        unsigned bot = (top + 1u) & 0x7FFu;
        for (int r = 0; r < 16; r++) {
            unsigned tile = (r < 8 ? top : bot);
            uint8_t *dst = vram + (size_t)tile * 32u + (size_t)(r & 7) * 4u;
            const uint8_t *src = &px[r][i * 8];
            dst[0] = (uint8_t)((src[0] << 4) | src[1]);
            dst[1] = (uint8_t)((src[2] << 4) | src[3]);
            dst[2] = (uint8_t)((src[4] << 4) | src[5]);
            dst[3] = (uint8_t)((src[6] << 4) | src[7]);
        }
    }
}

static void paint_both(void)
{
    uint8_t *vram = g_machine.vdp.vram;
    struct col cols[ROW_COLS];
    int ncols = value_cols(cols);
    if (ncols < BOTH_COLS) return;

    unsigned sig = (unsigned)ncols * 2048u + (cols[0].top & 0x7FFu);
    if (s_saved_n && sig != s_sig) s_saved_n = 0;   /* game rebuilt the row */

    if (!s_saved_n) {
        s_sig = sig;
        s_saved_n = ncols;
        for (int i = 0; i < ncols; i++) {
            unsigned top = cols[i].top & 0x7FFu;
            s_saved_top[i] = top;
            for (int b = 0; b < 32; b++) {
                s_saved_tiles[i][0][b] = vram[top * 32u + (unsigned)b];
                s_saved_tiles[i][1][b] =
                    vram[((top + 1u) & 0x7FFu) * 32u + (unsigned)b];
            }
        }
    }

    paint_row(vram, cols, ncols);
}

/* Put back the stock value-row glyphs when BOTH goes away.  The cached tile
 * numbers are used directly: the row may have been rebuilt in between, so
 * re-deriving it now would miss the tiles we actually overwrote. */
static void restore_row(void)
{
    uint8_t *vram = g_machine.vdp.vram;
    for (int i = 0; i < s_saved_n; i++) {
        unsigned top = s_saved_top[i] & 0x7FFu;
        for (int b = 0; b < 32; b++) {
            vram[top * 32u + (unsigned)b] = s_saved_tiles[i][0][b];
            vram[((top + 1u) & 0x7FFu) * 32u + (unsigned)b] = s_saved_tiles[i][1][b];
        }
    }
    s_saved_n = 0;
}

/* ---- Host selection surface --------------------------------------------- */
int tg2_audio_race_sound(void) { return s_mode; }

void tg2_audio_set_race_sound(int mode)
{
    if (mode < TG2_SOUND_SFX || mode > TG2_SOUND_BOTH) return;
    s_mode = mode;
    /* Two virtual chips and a second Z80 core only while BOTH is the live
     * choice; stock modes keep the single chip and core so their output stays
     * byte-identical. A change made mid-race is adopted at the next race. */
    adopt_mode();
}

/* Per-frame, before the guest runs: keep the engine's chip routing in step
 * with the host choice (the menu, the option row and TG2_RACE_SOUND can all
 * change it, and a guest reset reloads the cartridge's own word). */
void tg2_audio_frame_pre(void)
{
    adopt_mode();
    update_z80_role();
}

/* Guest reset or state load: the cartridge reloads its boot value; the
 * player's choice is a host preference and survives it. */
void tg2_audio_reset(void)
{
    s_patched = 0;
    s_page_seen = 0;
    s_saved_n = 0;
    s_sfx_upload = 0;
    /* A guest reset reboots the cartridge (no race running, so the player's
     * selection applies); a state loaded mid-race keeps the routing that race
     * was running, because the restored chip state belongs to it. */
    if (!race_running()) s_applied = s_mode;
    apply_mode();
    /* A guest reset reboots the cartridge, whose init re-uploads the music
     * driver; a state load restores the Z80 RAM and the per-frame check
     * corrects the role on the next frame either way. */
    audio_set_first_z80_is_sfx(first_z80_runs_sfx_image());
}

static int race_sound_page_open(void)
{
    return ram_read16(0xFF0000u + RAM_MENU_PAGE) == RACE_SOUND_PAGE;
}

void tg2_frame_post(uint64_t frame_count)
{
    (void)frame_count;

    /* The page's entry hook (0x01ED3A) loads the page value from the session
     * choice, so the cartridge always builds its own MUSIC or SOUND EFFECTS
     * row in stock state. While BOTH is the choice that row says "MUSIC", so
     * repaint it as "BOTH" on every frame the page is open (the page can be
     * re-entered from several routes and its tiles are rebuilt per visit). */
    int open = race_sound_page_open();
    s_page_seen = open;

    if (!open) {
        if (s_saved_n) restore_row();
        return;
    }

    if (s_mode == TG2_SOUND_BOTH) {
        paint_both();
        return;
    }
    if (s_saved_n) restore_row();
}
