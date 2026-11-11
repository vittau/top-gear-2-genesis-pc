/*
 * tg2_controls.h — the port's controls, as native game code.
 *
 * The setup carousel is a native replacement of the cartridge's row-list
 * input handler and row/page draw routine: four rows (RACE, PLAYER, GEARS,
 * SPEED), cursor wrap 0..3, and no CONTROL row. The cartridge's control type
 * stays TYPE 1 because its only selector (the CONTROL page) no longer exists;
 * remapping belongs to the launcher and the in-game runtime menu.
 *
 * Analog triggers are additive: RT presses Genesis B and LT presses Genesis A
 * (above the player's analog deadzone), while every existing binding keeps
 * working, including in menus.
 */
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* GameSpec.pad_trigger_bits: adds B for RT and A for LT. */
uint16_t tg2_pad_trigger_bits(int player, int lt_held, int rt_held);

/* game.toml game_hook sites: the carousel input handler ($021A62) and the
 * carousel row/page draw ($021F54). Returns 1 when it replaced the routine. */
int tg2_controls_hook(uint32_t pc);

#ifdef __cplusplus
}
#endif
