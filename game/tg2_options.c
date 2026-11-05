/*
 * tg2_options.c — player-facing port options.
 *
 * The engine owns widescreen (settings.ini [mods.widescreen]). This file owns
 * the options that are specific to Top Gear 2. They live in settings.ini as
 * [mods.<id>] sections, are offered by the launcher's Mods page through the
 * shared mod-provider ABI, and appear as rows in the in-game recomp-ui
 * overlay. Adding another boolean option is one row in s_options[].
 */
#include "tg2_options.h"
#include "cmd_server.h"

#include <SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#if RECOMP_LAUNCHER
#include "recomp_launcher.h"
#include "recomp_runtime_ui.h"
#endif

/* ── Option registry ─────────────────────────────────────────────────────── */

typedef struct Tg2Option {
    const char *id;           /* stable id: package/feature/overlay key */
    const char *section;      /* settings.ini section it is saved under */
    const char *key;          /* key inside that section */
    const char *name;         /* player-facing label */
    const char *group;        /* launcher feature group / overlay section */
    const char *description;  /* one paragraph, shared by both UIs */
    const char *status_on;
    const char *status_off;
    int         default_value;
    int        *value;
} Tg2Option;

static int s_race60 = 1;      /* task default: 60 fps races On */

static const Tg2Option s_options[] = {
    /* A third option is one more row here. */
    { "race60", "mods.race60", "enabled",
      "60 fps races", "Presentation",
      "Present races at 60 pictures per second while the game clock, lap "
      "counter and AI cadence stay native. Off restores the stock rate. "
      "Changes take effect from the next race.",
      "Enabled (60 pictures/s)", "Disabled (stock rate)",
      1, &s_race60 },
};
#define TG2_OPTION_COUNT ((int)(sizeof s_options / sizeof s_options[0]))

int tg2_race60_requested(void) { return s_race60 != 0; }

/* ── settings.ini ─────────────────────────────────────────────────────────── */

static char *trim(char *s)
{
    while (*s == ' ' || *s == '\t') ++s;
    char *e = s + strlen(s);
    while (e > s && (e[-1] == ' ' || e[-1] == '\t' || e[-1] == '\r' || e[-1] == '\n'))
        *--e = '\0';
    return s;
}

static int parse_bool(const char *v)
{
    while (*v == ' ' || *v == '\t') ++v;
    return strtol(v, NULL, 0) != 0;
}

/* One-time migration for the pre-settings.ini surface: tg2.ini next to the
 * executable used to hold race_60fps. Read only when settings.ini has no
 * [mods.race60] section yet. */
static int legacy_ini_bool(const char *settings_path, const char *key, int *out)
{
    if (!settings_path || !*settings_path) return 0;
    char path[1200];
    snprintf(path, sizeof path, "%s", settings_path);
    char *a = strrchr(path, '/'), *b = strrchr(path, '\\');
    char *sep = !a ? b : !b ? a : a > b ? a : b;
    size_t off = sep ? (size_t)(sep + 1 - path) : 0;
    snprintf(path + off, sizeof path - off, "tg2.ini");
    FILE *f = fopen(path, "rb");
    if (!f) return 0;
    char line[256];
    size_t klen = strlen(key);
    int found = 0;
    while (fgets(line, sizeof line, f)) {
        char *p = line;
        while (*p == ' ' || *p == '\t') ++p;
        if (*p == '#' || *p == ';' || *p == '[' || *p == '\0') continue;
        if (strncmp(p, key, klen)) continue;
        p += klen;
        while (*p == ' ' || *p == '\t') ++p;
        if (*p != '=' && *p != ':') continue;
        ++p;
        *out = parse_bool(p);
        found = 1;
    }
    fclose(f);
    return found;
}

void tg2_options_load(const char *settings_path)
{
    for (int i = 0; i < TG2_OPTION_COUNT; ++i)
        *s_options[i].value = s_options[i].default_value;
    int seen[TG2_OPTION_COUNT] = {0};
    FILE *f = settings_path ? fopen(settings_path, "rb") : NULL;
    char line[512];
    const Tg2Option *current = NULL;
    int current_index = -1;
    while (f && fgets(line, sizeof line, f)) {
        char *s = trim(line);
        if (!*s || *s == ';' || *s == '#') continue;
        if (*s == '[') {
            char *end = strchr(s, ']');
            if (end) *end = '\0';
            current = NULL;
            current_index = -1;
            for (int i = 0; i < TG2_OPTION_COUNT; ++i)
                if (!strcmp(s + 1, s_options[i].section)) {
                    current = &s_options[i];
                    current_index = i;
                }
            continue;
        }
        if (!current) continue;
        char *eq = strchr(s, '=');
        if (!eq) continue;
        *eq = '\0';
        char *key = trim(s);
        if (strcmp(key, current->key)) continue;
        *current->value = parse_bool(trim(eq + 1));
        seen[current_index] = 1;
    }
    if (f) fclose(f);
    for (int i = 0; i < TG2_OPTION_COUNT; ++i)
        if (!seen[i] && !strcmp(s_options[i].id, "race60"))
            (void)legacy_ini_bool(settings_path, "race_60fps", &s_race60);
}

/* Copy the file to a temporary path, dropping any section this game owns,
 * then append the current values. Rewriting (rather than blind append) keeps
 * the file unique when several save paths run in one launch. */
int tg2_options_save(const char *settings_path)
{
    if (!settings_path || !*settings_path) return 0;
    char tmp[1200];
    if (snprintf(tmp, sizeof tmp, "%s.tg2tmp", settings_path) >= (int)sizeof tmp)
        return 0;

    FILE *in = fopen(settings_path, "rb");
    FILE *out = fopen(tmp, "wb");
    if (!out) {
        if (in) fclose(in);
        return 0;
    }
    char line[1024];
    int skip = 0;
    while (in && fgets(line, sizeof line, in)) {
        char probe[1024];
        snprintf(probe, sizeof probe, "%s", line);
        char *s = trim(probe);
        if (*s == '[') {
            char *end = strchr(s, ']');
            if (end) *end = '\0';
            skip = 0;
            for (int i = 0; i < TG2_OPTION_COUNT; ++i)
                if (!strcmp(s + 1, s_options[i].section)) skip = 1;
        }
        if (!skip) fputs(line, out);
    }
    if (in) fclose(in);
    for (int i = 0; i < TG2_OPTION_COUNT; ++i)
        fprintf(out, "[%s]\n%s = %d\n\n", s_options[i].section,
                s_options[i].key, *s_options[i].value != 0);

    int ok = !ferror(out);
    if (fclose(out) != 0) ok = 0;
    if (!ok) {
        remove(tmp);
        return 0;
    }
    if (rename(tmp, settings_path) != 0) {
        fprintf(stderr, "[tg2] could not replace %s\n", settings_path);
        remove(tmp);
        return 0;
    }
    return 1;
}

/* Probe overrides: the settings file is the player surface; these exist so
 * automated captures can force a value without editing a user's file. */
void tg2_options_apply_env(void)
{
    const char *env = getenv("TG2_RACE_60FPS");
    if (env)
        s_race60 = env[0] == '1' || env[0] == 'o' || env[0] == 'O'
                || env[0] == 'y' || env[0] == 'Y' || env[0] == 't'
                || env[0] == 'T';
}

/* ── In-game overlay rows ─────────────────────────────────────────────────── */

#if RECOMP_LAUNCHER
static const RecompRuntimeUiItem s_runtime_items[] = {
    { "mods.race60.enabled", "Mods", "60 fps races",
      "Present races at 60 pictures per second while the game clock, lap "
      "counter and AI cadence stay native. Off restores the stock rate. "
      "Changes take effect from the next race.",
      RECOMP_RUNTIME_UI_BOOL, 0, 1, 1, NULL, 0, NULL },
};
#endif

const struct RecompRuntimeUiItem *tg2_options_runtime_items(size_t *count)
{
#if RECOMP_LAUNCHER
    if (count) *count = sizeof s_runtime_items / sizeof s_runtime_items[0];
    return s_runtime_items;
#else
    if (count) *count = 0;
    return NULL;
#endif
}

int tg2_options_runtime_get(const char *key, int *out)
{
    if (!key || !out) return 0;
    for (int i = 0; i < TG2_OPTION_COUNT; ++i) {
        char k[96];
        snprintf(k, sizeof k, "%s.%s", s_options[i].section, s_options[i].key);
        if (!strcmp(key, k)) {
            *out = *s_options[i].value != 0;
            return 1;
        }
    }
    return 0;
}

int tg2_options_runtime_set(const char *key, int value)
{
    if (!key) return 0;
    for (int i = 0; i < TG2_OPTION_COUNT; ++i) {
        char k[96];
        snprintf(k, sizeof k, "%s.%s", s_options[i].section, s_options[i].key);
        if (!strcmp(key, k)) {
            *s_options[i].value = value != 0;
            return 1;
        }
    }
    return 0;
}

/* ── Headless overlay driver (debug command) ──────────────────────────────── */

#if RECOMP_LAUNCHER
int runner_runtime_ui_open(void);   /* runner/main.c */
#else
static int runner_runtime_ui_open(void) { return 0; }
#endif

static void push_key(SDL_Keycode key)
{
    SDL_Event ev;
    SDL_zero(ev);
    ev.type = SDL_KEYDOWN;
    ev.key.type = SDL_KEYDOWN;
    ev.key.state = SDL_PRESSED;
    ev.key.keysym.sym = key;
    SDL_PushEvent(&ev);
    ev.type = SDL_KEYUP;
    ev.key.type = SDL_KEYUP;
    ev.key.state = SDL_RELEASED;
    SDL_PushEvent(&ev);
}

/* tg2_ui {"action":"open|close|up|down|left|right|accept|back|toggle"}.
 * Pushes the same SDL key events a player's keyboard produces, so automated
 * captures exercise the real menu path. The controller path shares the same
 * recomp-ui model and is covered by the runner's gamepad mapping. */
void tg2_options_ui_command(int id, const char *json)
{
    char action[24] = "";
    const char *p = json ? strstr(json, "\"action\"") : NULL;
    if (p && (p = strchr(p, ':')) != NULL) {
        ++p;
        while (*p == ' ' || *p == '\t' || *p == '"') ++p;
        size_t n = 0;
        while (*p && *p != '"' && n + 1 < sizeof action) action[n++] = *p++;
        action[n] = '\0';
    }
    SDL_Keycode key = SDLK_UNKNOWN;
    if      (!strcmp(action, "open") || !strcmp(action, "close") || !strcmp(action, "back"))
        key = SDLK_ESCAPE;
    else if (!strcmp(action, "up"))     key = SDLK_UP;
    else if (!strcmp(action, "down"))   key = SDLK_DOWN;
    else if (!strcmp(action, "left"))   key = SDLK_LEFT;
    else if (!strcmp(action, "right"))  key = SDLK_RIGHT;
    else if (!strcmp(action, "accept") || !strcmp(action, "toggle"))
        key = SDLK_RETURN;
    if (key != SDLK_UNKNOWN) push_key(key);
    char out[192];
    snprintf(out, sizeof out,
             "{\"id\":%d,\"ok\":%s,\"action\":\"%s\",\"race60\":%d,\"menu_open\":%d}",
             id, key != SDLK_UNKNOWN ? "true" : "false", action, s_race60,
             runner_runtime_ui_open());
    cmd_send_response(out);
}

/* ── Launcher mod provider ────────────────────────────────────────────────── */

#if RECOMP_LAUNCHER
static const RecompLauncherCModProvider *s_base;
static char s_error[160];

static int base_count(int (*fn)(void *))
{
    return fn ? fn(s_base->ctx) : 0;
}

static int tg2_package_count(void *ctx)
{
    (void)ctx;
    return base_count(s_base->package_count) + TG2_OPTION_COUNT;
}

static int tg2_feature_count(void *ctx)
{
    (void)ctx;
    return base_count(s_base->feature_count) + TG2_OPTION_COUNT;
}

static const Tg2Option *option_at(int index, int base)
{
    if (index < base || index >= base + TG2_OPTION_COUNT) return NULL;
    return &s_options[index - base];
}

static int tg2_package_get(void *ctx, int i, RecompLauncherCModPackage *out)
{
    (void)ctx;
    int base = base_count(s_base->package_count);
    const Tg2Option *o = option_at(i, base);
    if (!o) {
        int ok = s_base->package_get(s_base->ctx, i, out);
        if (ok && !strcmp(out->id, "custom-widescreen"))
            snprintf(out->description, sizeof out->description,
                     "Widen single-player races. Menus and split-screen keep their original view; the "
                     "HUD stays centered. Off restores stock 4:3.");
        return ok;
    }
    if (!out) return 0;
    memset(out, 0, sizeof *out);
    snprintf(out->id, sizeof out->id, "tg2-%s", o->id);
    snprintf(out->name, sizeof out->name, "%s", o->name);
    snprintf(out->version, sizeof out->version, "1");
    snprintf(out->author, sizeof out->author, "Top Gear 2 Recomp contributors");
    snprintf(out->description, sizeof out->description, "%s", o->description);
    out->enabled = *o->value != 0;
    return 1;
}

static int tg2_feature_get(void *ctx, int i, RecompLauncherCModFeature *out)
{
    (void)ctx;
    int base = base_count(s_base->feature_count);
    const Tg2Option *o = option_at(i, base);
    if (!o) {
        int ok = s_base->feature_get(s_base->ctx, i, out);
        if (ok && !strcmp(out->package_id, "custom-widescreen"))
            snprintf(out->description, sizeof out->description,
                     "Adaptive follows the window. Fixed ratios include 16:9 and 21:9. "
                     "Disable for stock 4:3 rendering.");
        return ok;
    }
    if (!out) return 0;
    memset(out, 0, sizeof *out);
    snprintf(out->id, sizeof out->id, "%s", o->id);
    snprintf(out->package_id, sizeof out->package_id, "tg2-%s", o->id);
    snprintf(out->package_name, sizeof out->package_name, "%s", o->name);
    snprintf(out->package_version, sizeof out->package_version, "1");
    snprintf(out->name, sizeof out->name, "%s", o->name);
    snprintf(out->group, sizeof out->group, "%s", o->group);
    snprintf(out->author, sizeof out->author, "Top Gear 2 Recomp contributors");
    snprintf(out->description, sizeof out->description, "%s", o->description);
    snprintf(out->status, sizeof out->status, "%s",
             *o->value ? o->status_on : o->status_off);
    out->enabled = *o->value != 0;
    return 1;
}

static int tg2_option_identity(const char *package, const char *feature,
                               const Tg2Option *o)
{
    char pid[64];
    snprintf(pid, sizeof pid, "tg2-%s", o->id);
    return package && feature && !strcmp(package, pid) &&
           !strcmp(feature, o->id);
}

static int tg2_option_get(void *ctx, const char *package, const char *feature,
                          int i, RecompLauncherCModOption *out)
{
    for (int n = 0; n < TG2_OPTION_COUNT; ++n)
        if (tg2_option_identity(package, feature, &s_options[n])) {
            (void)i;
            (void)out;
            return 0;   /* booleans use the list checkbox */
        }
    return s_base->feature_option_get
        ? s_base->feature_option_get(s_base->ctx, package, feature, i, out) : 0;
}

static int tg2_option_choice(void *ctx, const char *package, const char *feature,
                             const char *option, int i, RecompLauncherCModChoice *out)
{
    (void)ctx;
    return s_base->feature_choice_get
        ? s_base->feature_choice_get(s_base->ctx, package, feature, option, i, out) : 0;
}

static int tg2_feature_enable(void *ctx, const char *package, const char *feature,
                              int on)
{
    (void)ctx;
    for (int n = 0; n < TG2_OPTION_COUNT; ++n)
        if (tg2_option_identity(package, feature, &s_options[n])) {
            *s_options[n].value = on != 0;
            return 1;
        }
    return s_base->feature_enable(s_base->ctx, package, feature, on);
}

static int tg2_feature_set(void *ctx, const char *package, const char *feature,
                           const char *option, const char *value)
{
    (void)ctx; (void)package; (void)feature; (void)option; (void)value;
    return s_base->feature_set_option
        ? s_base->feature_set_option(s_base->ctx, package, feature, option, value) : 0;
}

static int tg2_commit(void *ctx, const char *image)
{
    (void)ctx;
    s_error[0] = '\0';
    if (!s_base->commit || !s_base->commit(s_base->ctx, image)) {
        snprintf(s_error, sizeof s_error, "Unable to save Top Gear 2 options");
        return 0;
    }
    return 1;
}

static const char *tg2_last_error(void *ctx)
{
    (void)ctx;
    return s_error[0] ? s_error
                      : (s_base->last_error ? s_base->last_error(s_base->ctx) : "");
}

const RecompLauncherCModProvider *tg2_mods(const RecompLauncherCModProvider *base)
{
    static RecompLauncherCModProvider result;
    if (!base) return NULL;
    s_base = base;
    result = *base;
    result.package_count = tg2_package_count;
    result.package_get = tg2_package_get;
    result.feature_count = tg2_feature_count;
    result.feature_get = tg2_feature_get;
    result.feature_option_get = tg2_option_get;
    result.feature_choice_get = tg2_option_choice;
    result.feature_enable = tg2_feature_enable;
    result.feature_set_option = tg2_feature_set;
    result.commit = tg2_commit;
    result.last_error = tg2_last_error;
    return &result;
}
#else
struct RecompLauncherCModProvider;
const struct RecompLauncherCModProvider *tg2_mods(
    const struct RecompLauncherCModProvider *base)
{
    return base;
}
#endif
