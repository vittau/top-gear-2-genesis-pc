/*
 * tg2_options.h — player-facing Top Gear 2 port options.
 *
 * Widescreen is the engine's built-in "Widescreen" mod (settings.ini
 * [mods.widescreen]); this file owns the game-specific options that are not
 * part of the shared video provider. Every option below is offered in the
 * recomp-ui launcher, in the in-game overlay and persisted in settings.ini.
 */
#pragma once

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

struct RecompRuntimeUiItem;

/* Load every registered option from settings.ini. Called once at startup via
 * GameSpec.load_settings. Missing keys keep their defaults. */
void tg2_options_load(const char *settings_path);

/* Rewrite settings.ini with the game-owned [mods.*] sections. The engine
 * truncates the file first, so this only adds the sections it owns. Called
 * through GameSpec.save_settings after every engine settings save. */
int tg2_options_save(const char *settings_path);

/* Research/probe overrides (never persisted): TG2_RACE_60FPS. */
void tg2_options_apply_env(void);

/* Keep the registry synchronized with the native RACE SOUND page. */
void tg2_options_race_sound_changed(int mode);

struct RecompLauncherCModProvider;
const struct RecompLauncherCModProvider *tg2_mods(const struct RecompLauncherCModProvider *base);

/* Live value of the 60 fps race option (0/1). */
int tg2_race60_requested(void);

/* In-game overlay rows appended to the shared recomp-ui menu. */
extern const struct RecompRuntimeUiLayout tg2_runtime_layout;
const struct RecompRuntimeUiItem *tg2_options_runtime_items(size_t *count);
int tg2_options_runtime_get(const char *key, int *out);
int tg2_options_runtime_set(const char *key, int value);

/* Debug TCP command that drives the in-game overlay headlessly. */
void tg2_options_ui_command(int id, const char *json_line);

#ifdef __cplusplus
}
#endif
