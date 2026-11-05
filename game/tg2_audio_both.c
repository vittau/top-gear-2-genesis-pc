/* Top Gear 2 (USA): simultaneous race music + sound effects.
 *
 * The cartridge has two independent sound systems and one policy word,
 * $FF240E (A3-$5FFA):
 *   0 = "RACE SOUND: SOUND EFFECTS" - upload the race SFX Z80 image,
 *       tick the 68k FM/PSG SFX engine, do not start music.
 *   1 = "RACE SOUND: MUSIC"         - keep the boot music driver, start a
 *       race track, do not tick or start the SFX engine.
 *
 * This adapter adds a third menu state, "BOTH".  The cartridge's own value
 * word stays 1 (MUSIC) so every stock menu/state-machine read is in range;
 * a host flag records that the player picked BOTH.  In races the SFX-side
 * policy reads are forced to 0 while the music-side reads keep seeing 1,
 * which runs both engines.  The race-time SFX Z80 image upload is skipped:
 * that image is never commanded after upload (verified with a write log),
 * and it would overwrite the music driver in Z80 RAM.
 *
 * The SOUND menu text is rendered from dynamic 8x16 glyph tiles.  While the
 * player is on the RACE SOUND page with BOTH selected, the value row's glyph
 * tiles are repainted as "BOTH " from the host.  Nothing in the ROM or in
 * generated C is modified.
 */
#include "genesis_runtime.h"
#include "game_spec.h"
#include "genesis_machine.h"

/* Work-RAM addresses (see docs/RAM_MAP.md / docs/AUDIO.md). */
#define RAM_SOUND_MODE   0x240Eu   /* word: 0 = SFX, 1 = MUSIC            */
#define RAM_MENU_VALUE   0x2560u   /* RACE SOUND page value word (A4+$0C) */

/* Host selection flag: the player picked BOTH on the RACE SOUND page. */
static int s_both;
/* Set while a sound-mode word patch is outstanding. */
static int s_patched;
/* True while the RACE SOUND page handler has been observed this visit. */
static int s_page_seen;

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

/* BOTH is live only when the cartridge's own word still says MUSIC. */
static int both_active(void)
{
    return s_both && ram_read16(0xFF0000u + RAM_SOUND_MODE) == 1;
}

static void present_sfx(void)
{
    if (both_active() && !s_patched) {
        ram_write16(0xFF0000u + RAM_SOUND_MODE, 0);
        s_patched = 1;
    }
}

static void restore_mode(void)
{
    if (s_patched) {
        ram_write16(0xFF0000u + RAM_SOUND_MODE, 1);
        s_patched = 0;
    }
}

/* ---- RACE SOUND page value handler ($01F0D4) replacement -----------------
 * d0 = active-low button mask (bit0 up, bit1 down, bits 4-6 A/B/C, bit7
 * start).  The stock handler cycles 0..1; this one adds BOTH above MUSIC
 * without ever storing an out-of-range value. */
static int menu_value_handler(void)
{
    uint32_t d0 = g_cpu.D[0] & 0xFFu;
    uint32_t a4 = g_cpu.A[4] & 0xFFFFFFu;

    if (a4 < 0xFF0000u || a4 > 0xFFFFFFu) return 0;  /* run stock handler */

    s_page_seen = 1;

    if (d0 == 0) { g_cpu.D[0] = 0; return 1; }

    ram_write16(a4 + 0x14u, (uint16_t)d0);

    uint16_t val = ram_read16(a4 + 0x0Cu);
    if (val > 1) val = 1;
    int changed = 0;

    if (d0 & 0x01u) {                 /* up */
        if (s_both) {
            s_both = 0;               /* BOTH -> MUSIC */
            changed = 1;              /* redraw state only; text is MUSIC */
        } else if (val == 1) {
            val = 0;                  /* MUSIC -> SOUND EFFECTS */
            changed = 1;
        }
    } else if (d0 & 0x02u) {          /* down */
        if (val == 0) {
            val = 1;                  /* SOUND EFFECTS -> MUSIC */
            changed = 1;
        } else if (!s_both) {
            s_both = 1;               /* MUSIC -> BOTH */
            changed = 1;
        }
    } else if (d0 & 0x70u) {          /* A/B/C: leave the page */
        ram_write16(a4 + 0x02u, 3);
        s_page_seen = 0;
        g_cpu.D[0] = 0;
        return 1;
    }

    if (changed) {
        ram_write16(a4 + 0x0Cu, val);
        ram_write16(a4 + 0x02u, (uint16_t)(ram_read16(a4 + 0x02u) + 1));
        ram_write16(a4 + 0x18u, 2);
    }
    g_cpu.D[0] = 0;
    return 1;
}

/* ---- Instruction hooks --------------------------------------------------- */
int tg2_instruction_hook(uint32_t pc)
{
    switch (pc) {
    case 0x01F0D4u:                    /* RACE SOUND value handler */
        return menu_value_handler();

    case 0x0700C8u:                    /* upload race SFX Z80 image */
        /* Never overwrite the boot music driver while BOTH is selected. */
        return both_active() ? 1 : 0;

    /* --- SFX-side policy sites: present 0 while BOTH is live --- */
    case 0x006530u:                    /* race init: read sound mode */
    case 0x0048E2u:                    /* race V-int: read sound mode */
    case 0x0250E2u:
    case 0x02511Cu:
    case 0x02503Au:
    case 0x02504Au:
    case 0x02529Au:
    case 0x0252CCu:
        present_sfx();
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
        restore_mode();
        return 0;

    default:
        return 0;
    }
}

/* ---- "BOTH" text overlay -------------------------------------------------
 * The menu draws text as 8x16 glyphs split over two 8x8 VRAM tiles.  We
 * repaint the value-row tiles in place, so sprite positions, palette and
 * priority remain the game's own.  Only presentation memory is touched. */
static const uint8_t s_glyph_b[16][8] = {
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,3,3,3,3,1,1,1}, {1,3,3,3,3,3,1,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,3,3,3,1,1},
    {1,3,3,3,3,1,1,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,3,3,3,1,1}, {1,3,3,3,3,1,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
};
static const uint8_t s_glyph_o[16][8] = {
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,1,3,3,3,3,1,1}, {1,3,3,3,3,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,3,3,3,3,1}, {1,1,3,3,3,3,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
};
static const uint8_t s_glyph_t[16][8] = {
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {3,3,3,3,3,3,3,3}, {3,3,3,3,3,3,3,3},
    {1,1,3,3,3,3,1,1}, {1,1,3,3,3,3,1,1},
    {1,1,3,3,3,3,1,1}, {1,1,3,3,3,3,1,1},
    {1,1,3,3,3,3,1,1}, {1,1,3,3,3,3,1,1},
    {1,1,3,3,3,3,1,1}, {1,1,3,3,3,3,1,1},
    {1,1,3,3,3,3,1,1}, {1,1,3,3,3,3,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
};
static const uint8_t s_glyph_h[16][8] = {
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,3,3,3,3,1},
    {1,3,3,3,3,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,3,3,1,1,3,3,1}, {1,3,3,1,1,3,3,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
};
static const uint8_t s_glyph_blank[16][8] = {
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
    {1,1,1,1,1,1,1,1}, {1,1,1,1,1,1,1,1},
};

/* Paint one half of an 8x16 glyph.  Source pixels are 3 = white glyph and
 * anything else = empty.  The menu font draws a one-pixel palette-1 (blue)
 * outline around white strokes, so synthesize the same outline here. */
static void vram_tile(uint8_t *vram, unsigned tile, const uint8_t px[16][8], int half)
{
    uint8_t t[16][8];
    for (int r = 0; r < 16; r++)
        for (int c = 0; c < 8; c++)
            t[r][c] = px[r][c] == 3 ? 3 : 0;
    for (int r = 0; r < 16; r++) {
        for (int c = 0; c < 8; c++) {
            if (t[r][c]) continue;
            int adj = 0;
            for (int dr = -1; dr <= 1 && !adj; dr++) {
                int rr = r + dr;
                if (rr < 0 || rr >= 16) continue;
                for (int dc = -1; dc <= 1; dc++) {
                    int cc = c + dc;
                    if (cc < 0 || cc >= 8) continue;
                    if (px[rr][cc] == 3) { adj = 1; break; }
                }
            }
            if (adj) t[r][c] = 1;
        }
    }
    uint8_t *dst = vram + (size_t)tile * 32u;
    for (int r = 0; r < 8; r++) {
        const uint8_t *src = t[half * 8 + r];
        dst[r * 4 + 0] = (uint8_t)((src[0] << 4) | src[1]);
        dst[r * 4 + 1] = (uint8_t)((src[2] << 4) | src[3]);
        dst[r * 4 + 2] = (uint8_t)((src[4] << 4) | src[5]);
        dst[r * 4 + 3] = (uint8_t)((src[6] << 4) | src[7]);
    }
}

struct col { int x; unsigned top; };
static void sort_cols(struct col *c, int n)
{
    for (int i = 1; i < n; i++)
        for (int j = i; j > 0 && c[j - 1].x > c[j].x; j--) {
            struct col t = c[j]; c[j] = c[j - 1]; c[j - 1] = t;
        }
}

static void draw_both(void)
{
    uint8_t *vram = g_machine.vdp.vram;
    unsigned sat = (unsigned)((g_machine.vdp.reg[5] & 0x7Fu) << 9);
    int header = 0;
    struct col cols[8];
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

        if (y == 0x0104u && ((w2 >> 13) & 3u) == 3u && ncols < 8) {
            unsigned hsz = ((sz >> 2) & 3u) + 1u;
            unsigned vsz = (sz & 3u) + 1u;
            if (vsz < 2) vsz = 2;
            for (unsigned c = 0; c < hsz && ncols < 8; c++) {
                cols[ncols].x = (int)(x - 128u) + (int)c * 8;
                cols[ncols].top = tile + c * vsz;
                ncols++;
            }
        }
    }

    if (!header || ncols < 4) return;
    sort_cols(cols, ncols);

    static const uint8_t (*const glyphs[])[8] = {
        (const uint8_t (*)[8])s_glyph_b,
        (const uint8_t (*)[8])s_glyph_o,
        (const uint8_t (*)[8])s_glyph_t,
        (const uint8_t (*)[8])s_glyph_h,
        (const uint8_t (*)[8])s_glyph_blank,
    };
    int n = ncols < 5 ? ncols : 5;
    for (int i = 0; i < n; i++) {
        unsigned top = cols[i].top & 0x7FFu;
        unsigned bot = (top + 1u) & 0x7FFu;
        vram_tile(vram, top, glyphs[i], 0);
        vram_tile(vram, bot, glyphs[i], 1);
    }
}

void tg2_frame_post(uint64_t frame_count)
{
    (void)frame_count;
    if (!s_both || !s_page_seen) return;
    draw_both();
}
