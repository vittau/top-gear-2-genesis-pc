/*
 * tg2_controls.h — fixed TYPE 1 controls and analog pedals for the recomp.
 *
 * The port owns controller remapping (the launcher's binding table and the
 * in-game runtime menu), so the cartridge's own CONTROL TYPE choice is not
 * offered any more: the carousel row that leads to it is skipped and the
 * mapping table is held at TYPE 1 for both players. The game's defaults
 * (B = accelerate, A = brake, C = nitro) are what the launcher's face-button
 * bindings already describe, so nothing about remapping moves into the port.
 *
 * Analog triggers are additive: RT presses Genesis B and LT presses Genesis A
 * (above the player's analog deadzone), while every existing face-button
 * binding keeps working, including in menus.
 */
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* GameSpec.pad_trigger_bits: adds B for RT and A for LT. player is unused
 * beyond symmetry with the per-player binding table. */
uint16_t tg2_pad_trigger_bits(int player, int lt_held, int rt_held);

/* game.toml game_hook sites: the carousel input handler ($021A62), the
 * carousel draw ($021E14, records that the row list is on screen this frame)
 * and the control-mapping applier ($00797A). Returns 1 when it replaced the
 * instruction's routine. */
int tg2_controls_hook(uint32_t pc);

/* Per-frame safety net: both players' applied control type is held at 0
 * (TYPE 1), which is also what the applier at $00797A reads. Clears the
 * row-list presentation flag. Called from on_frame_pre. */
void tg2_controls_frame(void);

/* After a quickstate load: the restored RAM may carry another type, including
 * a mapping table built from it. Force TYPE 1 for both players and log when
 * the restored state needed correcting. */
void tg2_controls_state_loaded(void);

/* True while the setup carousel drew its row list in the current frame; the
 * presenter uses it to leave the removed CONTROL row out of the picture. */
int tg2_controls_row_list_active(void);

/* Row-list pixel rectangles in the native 256x224 picture (inclusive bounds)
 * covered when the CONTROL row is removed. One-player setup centres a single
 * five-row list; two-player setup stacks both players' lists, so both
 * CONTROL buttons move (player 1's to the top half, player 2's lower). */
typedef struct Tg2ControlsRowRect {
    int x0, y0, x1, y1;
} Tg2ControlsRowRect;
int tg2_controls_row_rects(Tg2ControlsRowRect *out, int max);

#ifdef __cplusplus
}
#endif
