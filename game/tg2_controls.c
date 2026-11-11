/*
 * tg2_controls.c — TYPE 1 lock, CONTROL row removal and analog pedals.
 *
 * Raw-ROM evidence (see docs/RAM_MAP.md and docs/CONTROLS.md):
 *   $007942  four 7-word control-mapping presets; row 0 is TYPE 1. The row is
 *            read as [LEFT, RIGHT, UP, DOWN, A, B, C] -> output bit index.
 *   $00797A  applier: reads the per-player type word and copies that row into
 *            the player's raw-pad table.
 *   $FF1BC6  player 1 type word ($FF201E for player 2), copied from the setup
 *            screen's menu controller by $021860.
 *   $FF19AE  player 1 applied table: UP,DOWN,LEFT,RIGHT,B,A,C
 *            ($FF1E06 for player 2). TYPE 1 = 5,6,0,1,3,2,4.
 *   $021A62  setup carousel input handler: rows 0..4 = RACE, PLAYER, GEARS,
 *            SPEED, CONTROL, wrapping 0..4.
 *   $021E14  setup carousel row-list draw leaf (also does the palette fade).
 *   $021CB2  CONTROL page value handler: edits the type word at menu+$C.
 *
 * Everything here is game-specific guest logic; the engine only gained the
 * generic GameSpec.pad_trigger_bits hook.
 */
#include "tg2_controls.h"

#include "genesis_runtime.h"
#include "genesis_bus.h"     /* GPAD_A / GPAD_B */
#include "glue.h"

#include <stdio.h>

/* ---- Type words and the TYPE 1 table ------------------------------------ */
#define P1_TYPE_ADDR   0xFF1BC6u
#define P2_TYPE_ADDR   0xFF201Eu
#define P1_TABLE_ADDR  0xFF19AEu   /* UP DOWN LEFT RIGHT B A C */
#define P2_TABLE_ADDR  0xFF1E06u
#define SETUP_BASE     0xFF2554u   /* shared menu controller struct */
#define SETUP_ROW_LIST 0xFF2556u   /* menu state word inside it */

/* TYPE 1, in the applied table's memory order. */
static const uint16_t s_type1_table[7] = { 5, 6, 0, 1, 3, 2, 4 };

static unsigned s_frame;         /* advanced once per VBlank */
static unsigned s_row_list_seen; /* frame the carousel row list last ran */
static int s_row_list_drawn;     /* row list counted as on screen this frame */
static int s_logged_type;      /* non-zero type words corrected */
static int s_logged_table;     /* non-zero table words corrected at load */

/* ---- Analog pedals ------------------------------------------------------ */
uint16_t tg2_pad_trigger_bits(int player, int lt_held, int rt_held)
{
    (void)player;
    /* RT = accelerate = Genesis B, LT = brake = Genesis A. TYPE 1 maps B to
     * the ACCEL output bit and A to BRAKE ($00D80A..$00D872). */
    return (uint16_t)((rt_held ? GPAD_B : 0) | (lt_held ? GPAD_A : 0));
}

/* ---- TYPE 1 enforcement ------------------------------------------------- */
static void hold_type(uint32_t addr)
{
    uint16_t v = glue_peek16(addr);
    if (v == 0) return;
    if (!s_logged_type) {
        s_logged_type = 1;
        fprintf(stderr, "[tg2] control type at $%06X was %u; holding TYPE 1\n",
                (unsigned)addr, (unsigned)v);
    }
    glue_poke16(addr, 0);
}

static void hold_tables(void)
{
    for (unsigned p = 0; p < 2; ++p) {
        uint32_t base = p ? P2_TABLE_ADDR : P1_TABLE_ADDR;
        for (unsigned i = 0; i < 7; ++i) {
            uint32_t addr = base + i * 2u;
            uint16_t v = glue_peek16(addr);
            if (v != s_type1_table[i]) {
                if (!s_logged_table) {
                    s_logged_table = 1;
                    fprintf(stderr,
                            "[tg2] control table at $%06X was %u, expected %u; "
                            "restoring TYPE 1\n",
                            (unsigned)addr, (unsigned)v,
                            (unsigned)s_type1_table[i]);
                }
                glue_poke16(addr, s_type1_table[i]);
            }
        }
    }
}

void tg2_controls_state_loaded(void)
{
    hold_type(P1_TYPE_ADDR);
    hold_type(P2_TYPE_ADDR);
    hold_tables();
}

/* ---- Setup carousel: drop the CONTROL row ($021A62 replacement) ---------
 * Stock handler (verified against raw ROM and generated C):
 *   d0 = newly pressed buttons (bit0 up, bit1 down, bit7 start)
 *   no press            -> return
 *   up                  -> row 0 wraps to 4, else row-1
 *   down                -> row 4 wraps to 0, else row+1
 *   start on row 0      -> begin the race (1P state 3, 2P state 2)
 *   start on other rows -> open that page (sub-state 5)
 * This copy keeps every rule except that row 4 no longer exists, so the row
 * list is RACE, PLAYER, GEARS, SPEED and wraps 0..3 with no dead stop. */
#define MENU_STATE_ROW_LIST 0u
#define MENU_ROW_LAST       3u

static int row_list_handler(void)
{
    uint32_t a4 = g_cpu.A[4] & 0xFFFFFFu;
    /* Only the setup carousel uses this address; anything else runs stock. */
    if (a4 != SETUP_ROW_LIST && a4 != SETUP_ROW_LIST + 0x6Eu) return 0;
    s_row_list_seen = s_frame;

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

int tg2_controls_hook(uint32_t pc)
{
    switch (pc) {
        case 0x021A62u:                       /* carousel input handler */
            return row_list_handler();
        case 0x021E14u:                       /* carousel row-list draw */
            s_row_list_seen = s_frame;
            return 0;
        case 0x00797Au:                       /* mapping applier: force TYPE 1 */
            hold_type(P1_TYPE_ADDR);
            hold_type(P2_TYPE_ADDR);
            return 0;
        default:
            return 0;
    }
}

void tg2_controls_frame(void)
{
    /* Both players' applied type, before the applier consumes it. */
    hold_type(P1_TYPE_ADDR);
    hold_type(P2_TYPE_ADDR);

    /* The carousel's own state word and live-struct marker say the row list is
     * up; the freshness window covers the 2-frame input delay substates, and
     * ends within a few frames once START leaves the screen. */
    ++s_frame;
    s_row_list_drawn = glue_peek16(SETUP_BASE) == 0x00B4u &&
                       glue_peek16(SETUP_ROW_LIST) == 0u &&
                       s_frame - s_row_list_seen <= 4u;
}

int tg2_controls_row_list_active(void)
{
    return s_row_list_drawn;
}
