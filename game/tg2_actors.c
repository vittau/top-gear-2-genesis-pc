/* tg2_actors.c — read-only actor (scenery/vehicle) snapshots for the N x
 * renderer (docs/HIGHRES.md §3, §14). Every hook here only reads registers,
 * work RAM and ROM at audited instruction boundaries; nothing is written back
 * to the guest. */
#include "tg2_actors.h"
#include "genesis_runtime.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned ram16(unsigned a) {
    return (g_ram[a & 65535] << 8) | g_ram[(a + 1) & 65535];
}
static unsigned mem16(unsigned a) {
    a &= 0xFFFFFF;
    if (a + 1 < 0x100000)
        return (g_rom[a] << 8) | g_rom[a + 1];
    if (a >= 0xFF0000)
        return ram16(a);
    return 0;
}
static unsigned mem32(unsigned a) { return (mem16(a) << 16) | mem16(a + 2); }
static int valid_pointer(unsigned a) {
    a &= 0xFFFFFF;
    return a && !(a & 1) && (a < 0x100000 || a >= 0xFF0000);
}

/* Projection state latched right after the game's own `swap d1`
 * ($B42C interpolated path, $B4D4 depth-table path). The swap leaves the
 * discarded 16-bit fraction of the projected X in the register's upper word;
 * the interpolated path also leaves the Y fraction in D2's upper word. */
typedef struct {
    int path;                 /* 0 none, 1 interpolated, 2 depth table */
    unsigned d1, d2, d3, d4, depth2, type_in, record;
} Projection;
static Projection pending;

/* ---- LOD evidence log (TG2_ACTOR_LOG=path), qualification only ---------- */
static FILE *log_file;
static int log_checked;
static uint64_t log_frame;
enum { DEFS = 96 };
static struct { unsigned record, art, map; } defs[DEFS];
static unsigned def_count;
static unsigned table_sum[2], table_ptr[2];
static FILE *evidence(void) {
    if (!log_checked) {
        const char *path = getenv("TG2_ACTOR_LOG");
        log_checked = 1;
        if (path && *path)
            log_file = fopen(path, "w");
    }
    return log_file;
}
int tg2_actors_logging(void) { return evidence() != NULL; }
static void log_tables(FILE *f) {
    static const unsigned slots[2] = {0x2222, 0x2226};
    for (int t = 0; t < 2; ++t) {
        unsigned ptr = (ram16(slots[t]) << 16) | ram16(slots[t] + 2), sum = 0;
        if (!valid_pointer(ptr))
            continue;
        for (unsigned i = 0; i < 96; ++i)
            sum = sum * 31 + mem16(ptr + i * 2);
        if (ptr == table_ptr[t] && sum == table_sum[t])
            continue;
        table_ptr[t] = ptr;
        table_sum[t] = sum;
        fprintf(f, "T,%llu,%d,%06X", (unsigned long long)log_frame, t, ptr & 0xFFFFFF);
        for (unsigned i = 0; i < 96; ++i)
            fprintf(f, ",%d", (int16_t)mem16(ptr + i * 2));
        fputc('\n', f);
    }
}
static void log_definition(FILE *f, unsigned record) {
    unsigned art = mem32(record), map = mem32(record + 4);
    for (unsigned i = 0; i < def_count; ++i)
        if (defs[i].record == record && defs[i].art == art && defs[i].map == map)
            return;
    if (def_count == DEFS)
        return;
    defs[def_count].record = record;
    defs[def_count].art = art;
    defs[def_count++].map = map;
    fprintf(f, "D,%llu,%06X,%06X,%06X,%04X\n", (unsigned long long)log_frame,
            record & 0xFFFFFF, art & 0xFFFFFF, map & 0xFFFFFF, mem16(record + 8));
    if (!valid_pointer(art) || !valid_pointer(map))
        return;
    for (unsigned m = 0; m < 40; ++m) {
        unsigned h = mem32(map + m * 4);
        if (!valid_pointer(h))
            continue;
        fprintf(f, "M,%06X,%u,%06X", record & 0xFFFFFF, m, h & 0xFFFFFF);
        for (int n = 0; n < 12; ++n, h += 10) {
            unsigned set = mem16(h), list = art + 8 + set;
            unsigned count = mem16(list), p = (mem32(list + 2) + art) & 0xFFFFFF;
            int minx = 9999, miny = 9999, maxx = -9999, maxy = -9999;
            unsigned lo = 0xFFFF, hi = 0;
            if (count > 128) {
                fprintf(f, ",bad");
                break;
            }
            for (unsigned i = 0; i < count; ++i, p += 8) {
                unsigned sz = mem16(p + 2) >> 8, tile = mem16(p + 4) & 2047;
                int pw = (((sz >> 2) & 3) + 1) * 8, ph = ((sz & 3) + 1) * 8;
                int px = (int16_t)mem16(p + 6), py = (int16_t)mem16(p);
                if (px < minx) minx = px;
                if (py < miny) miny = py;
                if (px + pw > maxx) maxx = px + pw;
                if (py + ph > maxy) maxy = py + ph;
                if (tile < lo) lo = tile;
                if (tile + (unsigned)(pw * ph / 64) - 1 > hi) hi = tile + (unsigned)(pw * ph / 64) - 1;
            }
            fprintf(f, ",%u:%d:%d:%04X:%u:%d:%d:%d:%d:%u:%u", set, (int16_t)mem16(h + 2),
                    (int16_t)mem16(h + 4), mem16(h + 6), count, minx, miny, maxx, maxy, lo, hi);
            if (mem16(h + 8) == 0x8888)
                break;
        }
        fputc('\n', f);
    }
}

void tg2_actors_frame(uint64_t frame) { log_frame = frame; }
void tg2_actors_reset(void) {
    pending.path = 0;
    def_count = 0;
    table_ptr[0] = table_ptr[1] = 0;
}
void tg2_actors_hook(uint32_t pc) {
    if (ram16(0x189E))
        return; /* 2P split-screen stays native */
    if (pc == 0xB42E || pc == 0xB4D6) {
        pending.path = pc == 0xB42E ? 1 : 2;
        pending.d1 = g_cpu.D[1];
        pending.d2 = g_cpu.D[2];
        pending.d3 = g_cpu.D[3];
        pending.d4 = g_cpu.D[4];
        pending.depth2 = g_cpu.D[0] & 65535;
        pending.type_in = g_cpu.D[7] & 65535;
        pending.record = g_cpu.A[1] & 0xFFFFFF;
    } else if (pc == 0xB584) {
        FILE *f = evidence();
        unsigned record = g_cpu.A[1] & 0xFFFFFF;
        int path = pending.path;
        if (path && (pending.record != record ||
                     ((pending.d1 ^ g_cpu.D[1]) & 65535)))
            path = 0;
        if (f) {
            log_tables(f);
            if (valid_pointer(record))
                log_definition(f, record);
            fprintf(f, "O,%llu,%02X,%04X,%06X,%d,%u,%u,%u,%u,%d,%u,%d,%d,%u,%u,%u,%d,%u,%d,%d,%d,%u,%u,%d\n",
                    (unsigned long long)log_frame, ram16(0x187C) & 255, ram16(0x1878), record,
                    path, pending.type_in, g_cpu.D[7] & 65535, pending.depth2,
                    pending.d3 & 65535, (int16_t)g_cpu.D[1], pending.d1 >> 16,
                    (int16_t)g_cpu.D[2], (int16_t)pending.d2, pending.d2 >> 16,
                    pending.d4 & 65535, ram16(0x17E0), (int16_t)ram16(0x17DC),
                    ram16(0x242A), (int16_t)ram16(0x1836), (int16_t)ram16(0x17BC),
                    (int16_t)ram16(0x1894), g_ram[0x22E8], ram16(0x22D8),
                    (int16_t)ram16(0x2452));
        }
        pending.path = 0;
    } else if (pc == 0xB5FA) {
        FILE *f = evidence();
        unsigned header = g_cpu.A[0] & 0xFFFFFF;
        if (f)
            fprintf(f, "H,%llu,%d,%d,%04X,%u,%u,%06X,%d,%d\n", (unsigned long long)log_frame,
                    (int16_t)g_cpu.D[6], (int16_t)mem16(header), mem16(header + 2),
                    mem16(header - 4), g_cpu.D[7] & 65535, g_cpu.A[1] & 0xFFFFFF,
                    (int16_t)g_cpu.D[1], (int16_t)g_cpu.D[2]);
    }
}
