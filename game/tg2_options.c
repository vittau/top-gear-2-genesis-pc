/*
 * tg2_options.c — player-facing port options.
 *
 * The engine owns widescreen (settings.ini [mods.widescreen]). This file owns
 * the options that are specific to Top Gear 2. They live in settings.ini as
 * [mods.<id>] sections, are offered by the launcher's Mods page through the
 * shared mod-provider ABI, and appear as rows in the in-game recomp-ui
 * overlay. Adding another option is one row in s_options[].
 */
#include "tg2_options.h"
#include "tg2_video.h"
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

typedef enum Tg2OptionKind {
    TG2_OPT_BOOL,       /* feature checkbox / BOOL row                 */
    TG2_OPT_CHOICE,     /* enumerated feature option / CHOICE row      */
} Tg2OptionKind;

typedef struct Tg2Option {
    const char *id;           /* stable id: package/feature/overlay key */
    const char *section;      /* settings.ini section it is saved under */
    const char *key;          /* key inside that section */
    const char *name;         /* player-facing label (overlay row) */
    const char *mod_name;     /* launcher feature label */
    const char *group;        /* launcher feature group / overlay section */
    const char *description;  /* one paragraph, shared by both UIs */
    const char *status_on;    /* boolean status text */
    const char *status_off;
    int         default_value;
    int        *value;
    Tg2OptionKind kind;
    const char *const *choices;   /* serialized choice values */
    const char *const *labels;    /* player-facing choice labels */
    int         choice_count;
    void      (*apply)(int value); /* live renderer/config update, optional */
} Tg2Option;

static int s_race60 = 1;        /* task default: 60 fps races On */
static int s_hud_edges = 0;     /* task default: HUD Centered */
static int s_hide_overscan = 1; /* task default: Hide overscan On */
static int s_racesound = 0;     /* 0 = SOUND EFFECTS (stock), 1 = MUSIC, 2 = BOTH */

static const char *const s_hud_choices[] = { "centered", "edges" };
static const char *const s_hud_labels[]  = { "Centered", "Edges" };

static const char *const s_sound_choices[] = { "sfx", "music", "both" };
static const char *const s_sound_labels[]  = { "Sound effects", "Music", "Both" };

extern int  tg2_audio_race_sound(void);
extern void tg2_audio_set_race_sound(int mode);

static void apply_race_sound(int value)
{
    tg2_audio_set_race_sound(value);
}

/* The in-game RACE SOUND page owns the choice while playing; keep the
 * option in step so it is what settings.ini receives. */
void tg2_options_race_sound_changed(int mode)
{
    if (mode >= 0 && mode <= 2) s_racesound = mode;
}

static const Tg2Option s_options[] = {
    /* Another option is one more row here. */
    { "race60", "mods.race60", "enabled",
      "60 fps races", "60 fps races", "Presentation",
      "Interpolate race pictures at 60 fps with 50 ms of added display delay. "
      "Physics and sound keep stock timing. Off restores the stock rate. "
      "Changes take effect from the next race.",
      "Enabled (60 pictures/s)", "Disabled (stock rate)",
      1, &s_race60, TG2_OPT_BOOL, NULL, NULL, 0, NULL },
    { "hud", "mods.hud", "placement",
      "HUD", "HUD at edges", "Presentation",
      "Centered keeps the widescreen HUD with the car and effects. Edges "
      "anchors the instruments and track map to the left and right margins. "
      "Only meaningful while widescreen is on.",
      "Edges", "Centered",
      0, &s_hud_edges, TG2_OPT_CHOICE, s_hud_choices, s_hud_labels, 2,
      tg2_video_set_hud_mode },
    { "overscan", "mods.overscan", "hidden",
      "Hide overscan", "Hide overscan", "Presentation",
      "Crops the empty bands a CRT hid in overscan: the eight-row window band at "
      "the top of the race screen and the sixteen blank bottom lines, so the "
      "picture fills the window. Menus, split-screen and any picture that draws "
      "into those lines keep their full height. Presentation only; the "
      "simulation is unchanged. Off shows the stock bands.",
      "Cropped", "Shown",
      1, &s_hide_overscan, TG2_OPT_BOOL, NULL, NULL, 0,
      tg2_video_set_hide_overscan },
    { "racesound", "mods.racesound", "mode",
      "RACE SOUND", "RACE SOUND", "Sound",
      "Stock Top Gear 2 races play either music or sound effects. Both runs "
      "both: the cartridge's music driver stays resident while the race SFX "
      "engine also runs. The in-game SOUND menu offers the same choice.",
      "Both", "Sound effects",
      0, &s_racesound, TG2_OPT_CHOICE, s_sound_choices, s_sound_labels, 3,
      apply_race_sound },
};
#define TG2_OPTION_COUNT ((int)(sizeof s_options / sizeof s_options[0]))

int tg2_race60_requested(void) { return s_race60 != 0; }

static void apply_option(const Tg2Option *o)
{
    if (o->apply) o->apply(*o->value);
}

static const char *option_text(const Tg2Option *o)
{
    if (o->kind == TG2_OPT_CHOICE && o->choices &&
        *o->value >= 0 && *o->value < o->choice_count)
        return o->choices[*o->value];
    return *o->value ? "1" : "0";
}

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

static int parse_option(const Tg2Option *o, const char *v)
{
    while (*v == ' ' || *v == '\t') ++v;
    if (o->kind == TG2_OPT_CHOICE) {
        for (int i = 0; i < o->choice_count; ++i)
            if (!strcmp(v, o->choices[i])) return i;
    }
    return parse_bool(v) ? 1 : 0;
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
        *current->value = parse_option(current, trim(eq + 1));
        seen[current_index] = 1;
    }
    if (f) fclose(f);
    for (int i = 0; i < TG2_OPTION_COUNT; ++i)
        if (!seen[i] && !strcmp(s_options[i].id, "race60"))
            (void)legacy_ini_bool(settings_path, "race_60fps", &s_race60);
    for (int i = 0; i < TG2_OPTION_COUNT; ++i)
        apply_option(&s_options[i]);
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
        fprintf(out, "[%s]\n%s = %s\n\n", s_options[i].section,
                s_options[i].key, option_text(&s_options[i]));

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
    const char *hud = getenv("TG2_HUD_MODE");
    if (hud) {
        if (!strcmp(hud, "edges") || !strcmp(hud, "1"))
            s_hud_edges = 1;
        else if (!strcmp(hud, "centered") || !strcmp(hud, "0"))
            s_hud_edges = 0;
        tg2_video_set_hud_mode(s_hud_edges);
    }
    const char *overscan = getenv("TG2_HIDE_OVERSCAN");
    if (overscan)
        s_hide_overscan = !(overscan[0] == '0' || overscan[0] == 'n' ||
                            overscan[0] == 'N' || overscan[0] == 'f' ||
                            overscan[0] == 'F');
    tg2_video_set_hide_overscan(s_hide_overscan);
    const char *sound = getenv("TG2_RACE_SOUND");
    if (sound) {
        int mode = 0;
        if (!strcmp(sound, "both") || !strcmp(sound, "2")) mode = 2;
        else if (!strcmp(sound, "music") || !strcmp(sound, "1")) mode = 1;
        s_racesound = mode;
        tg2_audio_set_race_sound(mode);
    }
}

/* ── In-game overlay rows ─────────────────────────────────────────────────── */

#if RECOMP_LAUNCHER
static const RecompRuntimeUiItem s_runtime_items[] = {
    { "mods.race60.enabled", "Mods", "60 fps races",
      "Interpolate race pictures at 60 fps with 50 ms of added display delay. "
      "Physics and sound keep stock timing. Off restores the stock rate. "
      "Changes take effect from the next race.",
      RECOMP_RUNTIME_UI_BOOL, 0, 1, 1, NULL, 0, NULL },
    { "mods.hud.placement", "Mods", "HUD",
      "Centered keeps the widescreen HUD with the car and effects. Edges "
      "anchors the instruments and track map to the left and right margins. "
      "Only meaningful while widescreen is on.",
      RECOMP_RUNTIME_UI_CHOICE, 0, 1, 1, s_hud_labels, 2, NULL },
    { "mods.overscan.hidden", "Mods", "Hide overscan",
      "Crops the empty bands a CRT hid in overscan: the eight-row window band at "
      "the top of the race screen and the sixteen blank bottom lines, so the "
      "picture fills the window. Menus, split-screen and any picture that draws "
      "into those lines keep their full height. Presentation only; the "
      "simulation is unchanged. Off shows the stock bands.",
      RECOMP_RUNTIME_UI_BOOL, 0, 1, 1, NULL, 0, NULL },
    { "mods.racesound.mode", "Sound", "RACE SOUND",
      "Stock Top Gear 2 races play either music or sound effects. Both runs "
      "both: the cartridge's music driver stays resident while the race SFX "
      "engine also runs. The in-game SOUND menu offers the same choice.",
      RECOMP_RUNTIME_UI_CHOICE, 0, 2, 1, s_sound_labels, 3, NULL },
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
            *out = *s_options[i].value;
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
            if (s_options[i].kind == TG2_OPT_CHOICE && value >= s_options[i].choice_count)
                return 0;
            *s_options[i].value = value;
            apply_option(&s_options[i]);
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
             "{\"id\":%d,\"ok\":%s,\"action\":\"%s\",\"race60\":%d,"
             "\"hud_edges\":%d,\"hide_overscan\":%d,\"race_sound\":%d,"
             "\"menu_open\":%d}",
             id, key != SDLK_UNKNOWN ? "true" : "false", action, s_race60,
             s_hud_edges, s_hide_overscan, tg2_audio_race_sound(),
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
                     "HUD placement is a separate option. Off restores stock 4:3.");
        return ok;
    }
    if (!out) return 0;
    memset(out, 0, sizeof *out);
    snprintf(out->id, sizeof out->id, "tg2-%s", o->id);
    snprintf(out->name, sizeof out->name, "%s", o->mod_name);
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
    snprintf(out->name, sizeof out->name, "%s", o->mod_name);
    snprintf(out->group, sizeof out->group, "%s", o->group);
    snprintf(out->author, sizeof out->author, "Top Gear 2 Recomp contributors");
    snprintf(out->description, sizeof out->description, "%s", o->description);
    if (o->kind == TG2_OPT_CHOICE)
        snprintf(out->status, sizeof out->status, "%s", o->labels[*o->value]);
    else
        snprintf(out->status, sizeof out->status, "%s",
                 *o->value ? o->status_on : o->status_off);
    out->enabled = *o->value != 0;
    out->option_count = o->kind == TG2_OPT_CHOICE ? 1 : 0;
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

static const Tg2Option *option_by_identity(const char *package,
                                           const char *feature)
{
    for (int n = 0; n < TG2_OPTION_COUNT; ++n)
        if (tg2_option_identity(package, feature, &s_options[n]))
            return &s_options[n];
    return NULL;
}

static int tg2_option_get(void *ctx, const char *package, const char *feature,
                          int i, RecompLauncherCModOption *out)
{
    const Tg2Option *o = option_by_identity(package, feature);
    if (o) {
        if (!out || i != 0 || o->kind != TG2_OPT_CHOICE) return 0;
        memset(out, 0, sizeof *out);
        out->type = RECOMP_MOD_OPTION_CHOICE;
        out->step = 1;
        out->choice_count = o->choice_count;
        snprintf(out->id, sizeof out->id, "%s", o->key);
        snprintf(out->label, sizeof out->label, "Placement");
        snprintf(out->description, sizeof out->description,
                 "Centered keeps the HUD with the car; Edges anchors it to the "
                 "widescreen margins.");
        snprintf(out->value, sizeof out->value, "%s", o->choices[*o->value]);
        snprintf(out->default_value, sizeof out->default_value, "%s",
                 o->choices[o->default_value]);
        return 1;
    }
    return s_base->feature_option_get
        ? s_base->feature_option_get(s_base->ctx, package, feature, i, out) : 0;
}

static int tg2_option_choice(void *ctx, const char *package, const char *feature,
                             const char *option, int i, RecompLauncherCModChoice *out)
{
    (void)ctx;
    const Tg2Option *o = option_by_identity(package, feature);
    if (o && o->kind == TG2_OPT_CHOICE && option && !strcmp(option, o->key)) {
        if (!out || i < 0 || i >= o->choice_count) return 0;
        memset(out, 0, sizeof *out);
        snprintf(out->value, sizeof out->value, "%s", o->choices[i]);
        snprintf(out->label, sizeof out->label, "%s", o->labels[i]);
        return 1;
    }
    return s_base->feature_choice_get
        ? s_base->feature_choice_get(s_base->ctx, package, feature, option, i, out) : 0;
}

static int tg2_feature_enable(void *ctx, const char *package, const char *feature,
                              int on)
{
    (void)ctx;
    const Tg2Option *o = option_by_identity(package, feature);
    if (o) {
        if (o->kind == TG2_OPT_CHOICE) {
            /* A choice is "enabled" while it sits off its first value (the
             * shared mod model ties a feature's enabled flag to value != 0).
             * Turning the feature on must keep the recorded choice: replay
             * capture writes the option value first and the enable line
             * second, so collapsing it to 1 here turned a recorded BOTH into
             * MUSIC and the feedback replay diverged on its first frame.
             * Turning it off returns the feature's off value. */
            if (!on) *o->value = 0;
        } else {
            *o->value = on != 0;
        }
        apply_option(o);
        return 1;
    }
    return s_base->feature_enable(s_base->ctx, package, feature, on);
}

static int tg2_feature_set(void *ctx, const char *package, const char *feature,
                           const char *option, const char *value)
{
    (void)ctx;
    const Tg2Option *o = option_by_identity(package, feature);
    if (o && o->kind == TG2_OPT_CHOICE && option && value &&
        !strcmp(option, o->key)) {
        for (int i = 0; i < o->choice_count; ++i)
            if (!strcmp(value, o->choices[i])) {
                *o->value = i;
                apply_option(o);
                return 1;
            }
        return 0;
    }
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
