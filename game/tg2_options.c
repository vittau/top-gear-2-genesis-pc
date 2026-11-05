/* Keep shared aspect/settings persistence and describe this game's scope. */
#include <stdio.h>
#include <string.h>
#if RECOMP_LAUNCHER
#include "recomp_launcher.h"
static const RecompLauncherCModProvider *shared;
static int package_get(void *ctx, int i, RecompLauncherCModPackage *out) {
    (void)ctx;
    int ok = shared->package_get(shared->ctx, i, out);
    if (ok && !strcmp(out->id, "custom-widescreen"))
        snprintf(out->description, sizeof out->description,
                 "Widen single-player races. Menus and split-screen keep their original view; the "
                 "HUD stays centered.");
    return ok;
}
static int feature_get(void *ctx, int i, RecompLauncherCModFeature *out) {
    (void)ctx;
    int ok = shared->feature_get(shared->ctx, i, out);
    if (ok && !strcmp(out->package_id, "custom-widescreen"))
        snprintf(out->description, sizeof out->description,
                 "Adaptive follows the window. Fixed ratios include 16:9 and 21:9. Disable for "
                 "stock rendering.");
    return ok;
}
const RecompLauncherCModProvider *tg2_mods(const RecompLauncherCModProvider *base) {
    static RecompLauncherCModProvider result;
    if (!base)
        return NULL;
    shared = base;
    result = *base;
    result.package_get = package_get;
    result.feature_get = feature_get;
    return &result;
}
#else
struct RecompLauncherCModProvider;
const struct RecompLauncherCModProvider *tg2_mods(const struct RecompLauncherCModProvider *base) {
    return base;
}
#endif
