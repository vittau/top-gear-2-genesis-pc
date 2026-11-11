/*
 * tg2_controls.c — the port's controls, implemented as native replacements of
 * the cartridge routines that define them.
 *
 * The recomp runs the game's own code natively, so the carousel and the
 * control mapping are changed where they live instead of being painted over:
 *
 *   $021A62  setup-carousel input handler. Replaced: the cursor has four rows
 *            (RACE, PLAYER, GEARS, SPEED) wrapping 0..3. Stock wraps 0..4 and
 *            its fifth row is CONTROL (the cartridge's TYPE 1..4 selector,
 *            which the port replaces with the launcher/runtime-menu remap).
 *   $021F54  setup-carousel row/page draw. Replaced: for the row list it emits
 *            the first four rows of the page's row-list block and then the
 *            selected row's highlight, exactly as stock does for its five
 *            rows. Every other state (PLAYER, GEARS, SPEED pages) keeps the
 *            stock emission, including the same blocks and offsets, so the
 *            pages are untouched.
 *
 * Analog pedals are additive through the engine's GameSpec.pad_trigger_bits
 * hook: RT presses Genesis B (accelerate) and LT presses Genesis A (brake),
 * on top of every existing binding.
 *
 * Raw-ROM evidence (addresses verified against the stock ROM):
 *   $007942  four 7-word control-type presets; row 0 is TYPE 1
 *            [LEFT RIGHT UP DOWN A B C], the only type the port uses because
 *            the CONTROL page is no longer reachable.
 *   $FF1BC6 / $FF201E  applied type words (0 = TYPE 1); initialized at boot
 *            ($002116/$00212C) and never written elsewhere except by the
 *            setup screen's copy at $021860.
 *   $FF19AE / $FF1E06  applied raw-pad tables; TYPE 1 = 5,6,0,1,3,2,4.
 *   $21F2C   state -> draw routine table (0,2,3,4 -> $21F54; 1 -> $21F96).
 *   $21F40   state -> record {block, value adjust, d6 adjust, d7 adjust}.
 *   $21E6E   carousel per-player SAT linker: draws the player number, emits
 *            both players' blocks ($21EEA dispatcher) and DMAs the SAT.
 *   $FF48BA  descriptor stack (count, free list, 8-byte pieces at +$56).
 *   $FF53A0  page table used by the drawer: 6-byte directory {count, offset}
 *            at +8, payload = count 8-byte pieces {y, size, tile, x}.
 *            Row-list block 0 = 12 pieces: 0..7 = RACE+PLAYER, GEARS+SPEED,
 *            8..11 = CONTROL. Blocks 1..5 = the row highlight.
 *   $001CE0  append one descriptor to the stack (called natively).
 */
#include "tg2_controls.h"

#include "genesis_runtime.h"
#include "genesis_bus.h"     /* GPAD_A / GPAD_B */
#include "glue.h"

#include <stdio.h>

/* ---- Analog pedals ------------------------------------------------------ */
uint16_t tg2_pad_trigger_bits(int player, int lt_held, int rt_held)
{
    (void)player;
    /* RT = accelerate = Genesis B, LT = brake = Genesis A. TYPE 1 maps B to
     * the ACCEL output bit and A to BRAKE ($00D80A..00D872). */
    return (uint16_t)((rt_held ? GPAD_B : 0) | (lt_held ? GPAD_A : 0));
}

/* ---- Setup carousel: four rows ($021A62 replacement) --------------------
 * Stock handler (verified against raw ROM and the generated C):
 *   d0 = newly pressed buttons (bit0 up, bit1 down, bit7 start)
 *   no press            -> return
 *   up                  -> row 0 wraps to 4, else row-1
 *   down                -> row 4 wraps to 0, else row+1
 *   start on row 0      -> begin the race (1P state 3, 2P state 2)
 *   start on other rows -> open that page (sub-state 5)
 * This copy keeps every rule with four rows, so the list wraps 0..3 without a
 * dead stop. */
#define SETUP_STATE_P1 0xFF2556u
#define SETUP_STATE_P2 0xFF25C4u
#define MENU_ROW_LAST  3u

static int row_list_handler(void)
{
    uint32_t a4 = g_cpu.A[4] & 0xFFFFFFu;
    /* Only the setup carousel uses this address; anything else runs stock. */
    if (a4 != SETUP_STATE_P1 && a4 != SETUP_STATE_P2) return 0;

    uint16_t d0 = (uint16_t)(g_cpu.D[0] & 0xFFu);
    g_cpu.D[0] = (g_cpu.D[0] & 0xFFFF0000u) | d0;
    g_cpu.SR = (g_cpu.SR & ~0x0Fu) | (d0 ? 0u : (1u << 2));
    if (!d0) return 1;                       /* no new press: stock returns */

    glue_poke16(a4 + 0x1Cu, d0);

    uint16_t row = glue_peek16(a4 + 4u);
    if (row > MENU_ROW_LAST) row = MENU_ROW_LAST;

    if (d0 & 0x1u) {                         /* UP */
        row = row == 0 ? MENU_ROW_LAST : (uint16_t)(row - 1);
    } else if (d0 & 0x2u) {                  /* DOWN */
        row = row == MENU_ROW_LAST ? 0 : (uint16_t)(row + 1);
    } else if (d0 & 0x80u) {                 /* START */
        if (row == 0) {
            glue_poke16(a4 + 2u, glue_peek16(0xFF189Eu) ? 2u : 3u);
        } else {
            glue_poke16(a4 + 0x24u, row);
            glue_poke16(a4 + 2u, 5u);
        }
        g_cpu.D[0] &= 0xFFFF0000u;
        g_cpu.SR = (g_cpu.SR & ~0x0Fu) | (1u << 2);
        return 1;
    } else {
        return 0;                            /* other buttons: stock */
    }

    glue_poke16(a4 + 2u, (uint16_t)(glue_peek16(a4 + 2u) + 1u));
    glue_poke16(a4 + 0x26u, 2u);
    glue_poke16(a4 + 4u, row);
    g_cpu.D[0] &= 0xFFFF0000u;
    g_cpu.SR = (g_cpu.SR & ~0x0Fu) | (1u << 2);
    return 1;
}

/* ---- Setup carousel: draw four rows ($021F54 replacement) ---------------- */
#define SETUP_BASE      0xFF2554u
#define SETUP_DESC      0x2366u   /* descriptor stack, relative to the base */
#define SETUP_PAGES     0x2E4Cu   /* page table, relative to the base       */
#define SETUP_RECORDS   0x21F40u  /* state -> record table                  */
#define APPEND_DESC     0x0001CE0u

/* Stock append routine ($001CE0): pushes one 8-byte piece onto the stack. */
static void carousel_append(uint32_t a2, uint16_t y, uint16_t size,
                            uint16_t tile, uint16_t x)
{
    g_cpu.A[2] = a2;
    g_cpu.D[1] = y;
    g_cpu.D[2] = size;
    g_cpu.D[3] = tile;
    g_cpu.D[4] = x;
    recomp_call_addr(APPEND_DESC);
}

/* Stock emitter ($0206AE): emit one page block with the caller's offsets.
 * `keep` > 0 limits the number of pieces (the four-row row list). */
static void carousel_emit(uint32_t a2, uint32_t table, uint16_t block,
                          uint16_t d5, uint16_t d6, uint16_t d7, uint16_t keep)
{
    uint32_t record = table + 8u + 6u * block;
    uint16_t count = glue_peek16(record);
    uint32_t payload = table + glue_peek32(record + 2u);
    if (keep && count > keep) count = keep;
    for (uint16_t i = 0; i < count; ++i) {
        uint32_t piece = payload + 8u * i;
        carousel_append(a2,
                        (uint16_t)(glue_peek16(piece) + d7),
                        (uint16_t)(glue_peek16(piece + 2u) & 0xFF00u),
                        (uint16_t)(glue_peek16(piece + 4u) + d5),
                        (uint16_t)(glue_peek16(piece + 6u) + d6));
    }
}

static int carousel_draw(void)
{
    uint32_t a4 = g_cpu.A[4] & 0xFFFFFFu;
    uint32_t a1 = g_cpu.A[1] & 0xFFFFFFu;
    if (a4 != SETUP_BASE || (a1 != SETUP_STATE_P1 && a1 != SETUP_STATE_P2))
        return 0;                            /* not the carousel: stock */

    uint16_t state = glue_peek16(a1);
    if (state > 4u) return 0;                /* unknown state: stock */

    uint16_t value = glue_peek16(a1 + 4u + 2u * state);
    uint32_t record = glue_peek32(SETUP_RECORDS + 4u * state);
    uint16_t block = glue_peek16(record);
    value = (uint16_t)(value + glue_peek16(record + 2u));
    uint16_t d5 = (uint16_t)(g_cpu.D[5] + 0x2000u);
    uint16_t d6 = (uint16_t)(g_cpu.D[6] + glue_peek16(record + 4u));
    uint16_t d7 = (uint16_t)(g_cpu.D[7] + glue_peek16(record + 6u));
    uint32_t a2 = (a4 + SETUP_DESC) & 0xFFFFFFu;
    uint32_t table = (a4 + SETUP_PAGES) & 0xFFFFFFu;

    /* Row list: four rows are entries 0..7 of block 0 (RACE+PLAYER and
     * GEARS+SPEED); entries 8..11 are the removed CONTROL row. The highlight
     * block index is row+1, so clamp it to the last kept row in case a
     * snapshot restored the old fifth selection. */
    if (state == 0u && value > 4u) value = 4u;
    carousel_emit(a2, table, block, d5, d6, d7, state == 0u ? 8u : 0u);
    carousel_emit(a2, table, value, d5, d6, d7, 0u);

    g_cpu.A[2] = a2;                          /* the SAT linker reads it */
    return 1;
}

int tg2_controls_hook(uint32_t pc)
{
    switch (pc) {
        case 0x021A62u:                       /* carousel input handler */
            return row_list_handler();
        case 0x021F54u:                       /* carousel row/page draw */
            return carousel_draw();
        default:
            return 0;
    }
}
