/* Standalone TG2 FM model probe (task 30 measurement, not part of the game).
 *
 * Renders through the game's own ym2612_ymfm.cpp so the numbers describe the
 * exact TU the runtime uses:
 *   dac  a 440 Hz tone fed to the DAC at 6.6 kHz, as the race image does;
 *   fm   a single FM note at full and low level through both FM cores.
 * Writes one raw stereo s16 stream per run (name.raw) plus a text report.
 */
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include <vector>
extern "C" {
#include "ym2612.h"
}

static void w8(int port, int v) { ym2612_write_chip(0, (uint8_t)port, (uint8_t)v); }
static void reg(int addr, int v)
{
    if (addr >= 0x100) { w8(2, addr & 0xFF); w8(3, v); }
    else { w8(0, addr); w8(1, v); }
}

static void run(const char *name, std::vector<int16_t> &out, int dac_mode, int variant, int resample, int quiet)
{
    ym2612_init_chip(0);
    ym2612_set_variant(0, variant);
    ym2612_set_dac_resample(0, resample);

    /* Silence every channel, then either stream the DAC or key a note. */
    for (int ch = 0; ch < 6; ++ch) reg(0x28, ch | 0x00);
    if (dac_mode) {
        reg(0x2B, 0x80);              /* DAC enable, ch6 */
        reg(0x1B6, 0xC0);             /* ch6 pan both */
    } else {
        /* Algorithm 7, all operators as carriers; op1 at full level. */
        reg(0xB0, 0x07);
        for (int op = 0; op < 4; ++op) {
            int slot = 0x30 + op * 4;
            reg(slot + 0, 0x01);      /* DT/MUL */
            reg(slot + 4, quiet ? 0x7F : 0x00);   /* TL */
            reg(slot + 8, 0x00);      /* RS/AR */
            reg(slot + 12, 0x00);     /* AM/D1R */
            reg(slot + 16, 0x00);     /* D2R */
            reg(slot + 20, 0x0F);     /* SL/RR */
        }
        reg(0xA4, 0x22);              /* F-NUM block */
        reg(0xA0, 0x69);
        reg(0xB4, 0xC0);              /* pan/AMS/PMS */
        reg(0x28, 0xF0);              /* key on ch1, all ops */
    }

    const int samples = 53267 * 2;
    out.resize((size_t)samples * 2);
    long last_dac = -1;
    for (int i = 0; i < samples; ++i) {
        if (dac_mode) {
            /* 440 Hz sampled at exactly 6.6 kHz on the output grid. */
            long d = (long)((double)i * 6600.0 / 53267.0);
            if (d != last_dac) {
                last_dac = d;
                double t = (double)d / 6600.0;
                double v = 0.45 * sin(2.0 * 3.14159265358979 * 440.0 * t);
                int b = (int)lround(v * 127.0) + 128;
                if (b < 0) b = 0; else if (b > 255) b = 255;
                reg(0x2A, b);
            }
        }
        int16_t buf[2] = {0, 0};
        /* Advance exactly one output sample (1008 master cycles). */
        ym2612_advance_chip(0, 1008);
        size_t got = ym2612_render_chip(0, buf, 1);
        if (got != 1) { fprintf(stderr, "%s: short render\n", name); exit(1); }
        out[(size_t)i * 2 + 0] = buf[0];
        out[(size_t)i * 2 + 1] = buf[1];
    }

    FILE *f = fopen(name, "wb");
    fwrite(out.data(), 2 * sizeof(int16_t), out.size() / 2, f);
    fclose(f);
}

int main(int argc, char **argv)
{
    const char *mode = argc > 1 ? argv[1] : "dac";
    char path[512];
    std::vector<int16_t> v;
    if (!strcmp(mode, "dac")) {
        snprintf(path, sizeof path, "build/t/dac-off.raw");  run(path, v, 1, 0, 0, 0);
        snprintf(path, sizeof path, "build/t/dac-on.raw");   run(path, v, 1, 0, 1, 0);
        snprintf(path, sizeof path, "build/t/dac-on3438.raw"); run(path, v, 1, 1, 1, 0);
    } else {
        snprintf(path, sizeof path, "build/t/fm-2612.raw");  run(path, v, 0, 0, 0, 0);
        snprintf(path, sizeof path, "build/t/fm-3438.raw");  run(path, v, 0, 1, 0, 0);
        snprintf(path, sizeof path, "build/t/fmq-2612.raw"); run(path, v, 0, 0, 0, 1);
        snprintf(path, sizeof path, "build/t/fmq-3438.raw"); run(path, v, 0, 1, 0, 1);
    }
    printf("ok\n");
    return 0;
}
