/* SPIKE (task 29): read-only sprite LOD / projection capture.
 *
 * Two audited instruction boundaries in the scenery mapper:
 *   $B584  entry after the LOD table lookup: D7 = model index the object's
 *          mapping table is asked for, D1/D2 = projected position, A1 = the
 *          object's mapping record.
 *   $B5F0  after the mapping header resolved: A1 = piece list (pattern set),
 *          D7 = piece count, D1/D2 = projected position, D6 = width.
 *
 * Pairs of entries describe "distance -> pattern set" with no guest writes.
 * Remove this file, its hook sites and the `tg2_lod` command after the
 * high-resolution design is settled; it exists only to supply evidence.
 */
#include "tg2_lod_probe.h"
#include "cmd_server.h"
#include "genesis_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { LOD_RING = 8192 };
typedef struct {
    unsigned kind, frame, d0, d1, d2, d3, d5, d6, d7, a0, a1, a2;
} LodEntry;
static LodEntry ring[LOD_RING];
static unsigned head, total;
static uint64_t frame;
static FILE *dump;

void tg2_lod_probe_frame(uint64_t f)
{
    frame = f;
    if (!dump) {
        const char *p = getenv("TG2_LOD_DUMP");
        if (p && *p) dump = fopen(p, "wb");
    }
    if (dump) fflush(dump);
}

int tg2_lod_probe_hook(uint32_t pc)
{
    if (pc != 0xB584 && pc != 0xB5F0)
        return 0;
    LodEntry *e = &ring[head++ % LOD_RING];
    e->kind = pc == 0xB584 ? 0 : 1;
    e->frame = (unsigned)frame;
    e->d0 = g_cpu.D[0]; e->d1 = g_cpu.D[1]; e->d2 = g_cpu.D[2];
    e->d3 = g_cpu.D[3]; e->d5 = g_cpu.D[5]; e->d6 = g_cpu.D[6];
    e->d7 = g_cpu.D[7];
    e->a0 = g_cpu.A[0] & 0xFFFFFF; e->a1 = g_cpu.A[1] & 0xFFFFFF;
    e->a2 = g_cpu.A[2] & 0xFFFFFF;
    if (dump) fwrite(e, sizeof *e, 1, dump);
    ++total;
    return 0;
}

/* Dump the ring newest-last, with the ROM words a piece list starts with so a
 * single query carries the pattern IDs too. */
void tg2_lod_command(int id, const char *json)
{
    static char out[1 << 17];
    unsigned from = 0;
    const char *s = json ? strstr(json, "\"from\"") : NULL;
    if (s) {
        const char *colon = strchr(s, ':');
        if (colon) from = (unsigned)strtoul(colon + 1, NULL, 10);
    }
    unsigned n = total < LOD_RING ? total : LOD_RING;
    if (from > total - n) from = total - n;
    unsigned n_out = total - from;
    if (n_out > 400) n_out = 400;   /* send() may be partial on big replies */
    if (from + n_out < total) from = total - n_out;
    int p = snprintf(out, sizeof out, "{\"id\":%d,\"ok\":true,\"total\":%u,\"from\":%u,\"entries\":[",
                     id, total, from);
    for (unsigned i = 0; i < n_out; ++i) {
        const LodEntry *e = &ring[(from + i) % LOD_RING];
        p += snprintf(out + p, sizeof out - p,
                      "%s{\"k\":%u,\"f\":%u,\"d0\":%u,\"d1\":%u,\"d2\":%u,\"d3\":%u,"
                      "\"d5\":%u,\"d6\":%u,\"d7\":%u,\"a0\":%u,\"a1\":%u,\"a2\":%u,\"w\":[",
                      i ? "," : "", e->kind, e->frame, e->d0, e->d1, e->d2, e->d3,
                      e->d5, e->d6, e->d7, e->a0, e->a1, e->a2);
        for (unsigned k = 0; k < 8; ++k) {
            unsigned a = e->a1 + k * 2, w = 0;
            if (a < 0x400000) w = ((unsigned)g_rom[a] << 8) | g_rom[a + 1];
            else if (a >= 0xFF0000 && a < 0x1000000)
                w = ((unsigned)g_ram[(a - 0xFF0000) & 65535] << 8) |
                    g_ram[(a - 0xFF0000 + 1) & 65535];
            p += snprintf(out + p, sizeof out - p, "%s%u", k ? "," : "", w);
            if (p >= (int)sizeof out - 64) break;
        }
        p += snprintf(out + p, sizeof out - p, "]}");
        if (p >= (int)sizeof out - 128) break;
    }
    snprintf(out + p, sizeof out - p, "]}");
    cmd_send_response(out);
}
