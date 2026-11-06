/* gpgx_render.c — minimal headless libretro frontend used as the tempo
 * reference for the TG2 native port.
 *
 * It loads a libretro core (tested with genesis_plus_gx) and a cartridge,
 * drives the pad from an exact-wall-frame input script (the same JSON the
 * port's deterministic route uses), and writes:
 *   - a WAV of the core's own audio callback stream, and
 *   - PPM screenshots at the script's "shot" frames.
 *
 * It never opens a window, never touches the host mixers and does not need a
 * real-time clock: the core is stepped one frame at a time, so the capture is
 * bit-reproducible and the music tempo is the core's own (hardware) tempo.
 *
 * Build:
 *   cc -O2 -o build/gpgx_render tools/gpgx_render.c -ldl -lm
 * Run:
 *   build/gpgx_render --core <core.so> --rom <rom.bin> \
 *       --frames 5400 --script game/baseline-route.json \
 *       --wav out.wav --shots out/dir
 *
 * No ROM, generated C, dump or save state is written by this tool into the
 * repository; it only writes the paths given on the command line.
 */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ---- libretro ABI (only the parts this frontend needs) ------------------ */
#define RETRO_API_VERSION 1
#define RETRO_DEVICE_JOYPAD 1
#define RETRO_DEVICE_ID_JOYPAD_B 0
#define RETRO_DEVICE_ID_JOYPAD_Y 1
#define RETRO_DEVICE_ID_JOYPAD_SELECT 2
#define RETRO_DEVICE_ID_JOYPAD_START 3
#define RETRO_DEVICE_ID_JOYPAD_UP 4
#define RETRO_DEVICE_ID_JOYPAD_DOWN 5
#define RETRO_DEVICE_ID_JOYPAD_LEFT 6
#define RETRO_DEVICE_ID_JOYPAD_RIGHT 7
#define RETRO_DEVICE_ID_JOYPAD_A 8
#define RETRO_DEVICE_ID_JOYPAD_X 9
#define RETRO_DEVICE_ID_JOYPAD_L 10
#define RETRO_DEVICE_ID_JOYPAD_R 11
#define RETRO_DEVICE_MASK_JOYPAD 0xff

enum {
    RETRO_ENVIRONMENT_SET_ROTATION = 1,
    RETRO_ENVIRONMENT_GET_OVERSCAN = 2,
    RETRO_ENVIRONMENT_GET_CAN_DUPE = 3,
    RETRO_ENVIRONMENT_SET_MESSAGE = 6,
    RETRO_ENVIRONMENT_SHUTDOWN = 7,
    RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL = 8,
    RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY = 9,
    RETRO_ENVIRONMENT_SET_PIXEL_FORMAT = 10,
    RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS = 11,
    RETRO_ENVIRONMENT_SET_KEYBOARD_CALLBACK = 12,
    RETRO_ENVIRONMENT_SET_DISK_CONTROL_INTERFACE = 13,
    RETRO_ENVIRONMENT_SET_HW_RENDER = 14,
    RETRO_ENVIRONMENT_GET_VARIABLE = 15,
    RETRO_ENVIRONMENT_SET_VARIABLES = 16,
    RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE = 17,
    RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME = 18,
    RETRO_ENVIRONMENT_GET_LIBRETRO_PATH = 19,
    RETRO_ENVIRONMENT_GET_LOG_INTERFACE = 27,
    RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY = 31,
    RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO = 32,
    RETRO_ENVIRONMENT_SET_SUBSYSTEM_INFO = 34,
    RETRO_ENVIRONMENT_SET_CONTROLLER_INFO = 35,
    RETRO_ENVIRONMENT_SET_MEMORY_MAPS = 36,
    RETRO_ENVIRONMENT_GET_VFS_INTERFACE = 45,
    RETRO_ENVIRONMENT_GET_LANGUAGE = 39,
    RETRO_ENVIRONMENT_GET_AUDIO_VIDEO_ENABLE = 47,
    RETRO_ENVIRONMENT_GET_FASTFORWARDING = 49,
    RETRO_ENVIRONMENT_GET_TARGET_REFRESH_RATE = 50,
    RETRO_ENVIRONMENT_GET_INPUT_BITMASKS = 52,
    RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION = 53,
};

enum retro_pixel_format { RETRO_PIXEL_FORMAT_0RGB1555 = 0,
                          RETRO_PIXEL_FORMAT_XRGB8888 = 1,
                          RETRO_PIXEL_FORMAT_RGB565 = 2 };

struct retro_game_info {
    const char *path;
    const void *data;
    size_t size;
    const char *meta;
};

struct retro_system_info {
    const char *library_name, *library_version, *valid_extensions;
    int need_fullpath, block_extract;
};

struct retro_system_av_info {
    struct { unsigned base_width, base_height, max_width, max_height; float aspect_ratio; } geometry;
    struct { double fps, sample_rate; } timing;
};

struct retro_game_geometry {
    unsigned base_width, base_height, max_width, max_height;
    float aspect_ratio;
};
struct retro_system_timing { double fps, sample_rate; };

struct retro_variable { const char *key, *value; };
typedef void (*retro_log_printf_t)(int level, const char *fmt, ...);
struct retro_log_callback { retro_log_printf_t log; };
struct retro_message { const char *msg; unsigned frames; };
struct retro_input_descriptor {
    unsigned port, device, index, id;
    const char *description;
};

/* ---- loaded API -------------------------------------------------------- */
static void (*r_init)(void);
static void (*r_deinit)(void);
static unsigned (*r_api_version)(void);
static void (*r_get_system_info)(struct retro_system_info *);
static void (*r_get_system_av_info)(struct retro_system_av_info *);
static void (*r_set_environment)(bool (*)(unsigned, void *));
static void (*r_set_video_refresh)(void (*)(const void *, unsigned, unsigned, size_t));
static void (*r_set_audio_sample)(void (*)(int16_t, int16_t));
static void (*r_set_audio_sample_batch)(size_t (*)(const int16_t *, size_t));
static void (*r_set_input_poll)(void (*)(void));
static void (*r_set_input_state)(int16_t (*)(unsigned, unsigned, unsigned, unsigned));
static int (*r_load_game)(const struct retro_game_info *);
static void (*r_unload_game)(void);
static void (*r_run)(void);

/* ---- capture state ----------------------------------------------------- */
static FILE *s_wav;
static unsigned long s_audio_frames;
static int s_sample_rate = 44100;
static const char *s_shots;

/* Script state: one entry per input change. */
typedef struct { long frame; unsigned mask; int shot; } ScriptRow;
static ScriptRow s_script[512];
static int s_script_n;
static long s_frame;

/* Pad masks use the port's baseline-route bit order:
 * bit0 UP, bit1 DOWN, bit2 LEFT, bit3 RIGHT, bit4 B, bit5 C, bit6 A, bit7 START. */
static int16_t input_state(unsigned port, unsigned device, unsigned index, unsigned id)
{
    if (port != 0 || (device & RETRO_DEVICE_MASK_JOYPAD) != RETRO_DEVICE_JOYPAD || index != 0)
        return 0;
    unsigned mask = 0;
    for (int i = 0; i < s_script_n; i++)
        if (s_script[i].frame <= s_frame) mask = s_script[i].mask;
        else break;
    unsigned rp = 0;
    if (mask & 0x01) rp |= 1u << RETRO_DEVICE_ID_JOYPAD_UP;
    if (mask & 0x02) rp |= 1u << RETRO_DEVICE_ID_JOYPAD_DOWN;
    if (mask & 0x04) rp |= 1u << RETRO_DEVICE_ID_JOYPAD_LEFT;
    if (mask & 0x08) rp |= 1u << RETRO_DEVICE_ID_JOYPAD_RIGHT;
    if (mask & 0x10) rp |= 1u << RETRO_DEVICE_ID_JOYPAD_B;   /* MD B */
    if (mask & 0x20) rp |= 1u << RETRO_DEVICE_ID_JOYPAD_A;   /* MD C */
    if (mask & 0x40) rp |= 1u << RETRO_DEVICE_ID_JOYPAD_Y;   /* MD A */
    if (mask & 0x80) rp |= 1u << RETRO_DEVICE_ID_JOYPAD_START;
    if (id == 256)   /* RETRO_DEVICE_ID_JOYPAD_MASK: the whole pad bitmask */
        return (int16_t)rp;
    return (int16_t)((rp >> id) & 1u);
}

static void input_poll(void) {}

static size_t audio_batch(const int16_t *data, size_t frames)
{
    if (s_wav && frames) {
        fwrite(data, sizeof(int16_t) * 2, frames, s_wav);
        s_audio_frames += frames;
    }
    return frames;
}
static void audio_sample(int16_t l, int16_t r) { audio_batch((int16_t[]){l, r}, 1); }

/* Reference framebuffer (for spot-check PPMs only). */
static const uint8_t *s_fb;
static unsigned s_fb_w, s_fb_h;
static size_t s_fb_pitch;
static void video_refresh(const void *data, unsigned w, unsigned h, size_t pitch)
{
    if (data && w && h) { s_fb = data; s_fb_w = w; s_fb_h = h; s_fb_pitch = pitch; }
}

static void write_ppm(const char *dir, const char *tag)
{
    if (!s_shots || !s_fb) return;
    char path[1024];
    snprintf(path, sizeof path, "%s/%s.ppm", dir, tag);
    FILE *f = fopen(path, "wb");
    if (!f) return;
    unsigned w = s_fb_w ? s_fb_w : 320, h = s_fb_h ? s_fb_h : 224;
    fprintf(f, "P6\n%u %u\n255\n", w, h);
    for (unsigned y = 0; y < h; y++) {
        const uint16_t *row = (const uint16_t *)(s_fb + (size_t)y * s_fb_pitch);
        for (unsigned x = 0; x < w; x++) {
            uint16_t p = row[x];
            unsigned char rgb[3] = {
                (unsigned char)(((p >> 10) & 0x1f) * 255 / 31),
                (unsigned char)(((p >> 5) & 0x1f) * 255 / 31),
                (unsigned char)((p & 0x1f) * 255 / 31)};
            fwrite(rgb, 1, 3, f);
        }
    }
    fclose(f);
}

static void log_cb(int level, const char *fmt, ...)
{
    if (level > 1) return;   /* 0=debug 1=info; drop warnings+ */
    va_list ap;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fputc('\n', stderr);
}

static bool env_cb(unsigned cmd, void *data_)
{
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_CAN_DUPE: *(bool *)data_ = true; return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT: return *(int *)data_ == RETRO_PIXEL_FORMAT_RGB565;
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY: *(const char **)data_ = "/tmp/opencode/gpgx"; return true;
    case RETRO_ENVIRONMENT_GET_LOG_INTERFACE: ((struct retro_log_callback *)data_)->log = log_cb; return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE: {
        struct retro_variable *v = data_;
        /* Region auto (=NTSC for this ROM), stereo output, no filters. */
        if (!strcmp(v->key, "genesis_plus_gx_region_detect")) { v->value = "0"; return true; }
        if (!strcmp(v->key, "genesis_plus_gx_sound_output")) { v->value = "1"; return true; }
        if (!strcmp(v->key, "genesis_plus_gx_ym2413")) { v->value = "0"; return true; }
        v->value = NULL;
        return false;
    }
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE: *(bool *)data_ = false; return true;
    case RETRO_ENVIRONMENT_GET_INPUT_BITMASKS: return true;
    case RETRO_ENVIRONMENT_GET_CORE_OPTIONS_VERSION: *(unsigned *)data_ = 0; return true;
    case RETRO_ENVIRONMENT_SET_VARIABLES:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME:
    case RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL:
    case RETRO_ENVIRONMENT_SET_CONTROLLER_INFO:
    case RETRO_ENVIRONMENT_SET_MEMORY_MAPS:
    case RETRO_ENVIRONMENT_SET_KEYBOARD_CALLBACK:
    case RETRO_ENVIRONMENT_SET_DISK_CONTROL_INTERFACE:
    case RETRO_ENVIRONMENT_SET_SYSTEM_AV_INFO:
        return true;
    default:
        return false;
    }
}

/* ---- script (same JSON shape as game/baseline-route.json) -------------- */
static void load_script(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); exit(2); }
    fseek(f, 0, SEEK_END); long n = ftell(f); fseek(f, 0, SEEK_SET);
    char *buf = malloc((size_t)n + 1);
    if (fread(buf, 1, (size_t)n, f) != (size_t)n) exit(2);
    buf[n] = 0; fclose(f);
    /* Minimal scan: each object holds "frame": N and optionally "keys": "HH",
     * "shot": "name". Everything is on one line per object in this file. */
    char *p = buf, *obj; unsigned mask = 0;
    while ((obj = strstr(p, "{")) != NULL) {
        char *end = strchr(obj, '}');
        if (!end) break;
        *end = 0;
        long frame = -1;
        char *k = strstr(obj, "\"frame\"");
        if (k) frame = strtol(strchr(k, ':') + 1, NULL, 10);
        char *ky = strstr(obj, "\"keys\"");
        if (ky) {
            char *v = strchr(ky, ':');
            if (v) { v++; while (*v && *v != '0' && *v != '1' && *v != '2' && *v != '4' &&
                              *v != '8' && *v != 'A' && *v != 'a' && !(*v >= '0' && *v <= '9')) v++;
                     mask = (unsigned)strtoul(v, NULL, 16); }
        }
        if (frame >= 0 && s_script_n < 512) {
            s_script[s_script_n].frame = frame;
            s_script[s_script_n].mask = mask;
            s_script[s_script_n].shot = 0;
            s_script_n++;
        }
        /* record shot frames separately as mask-preserving markers */
        char *sh = strstr(obj, "\"shot\"");
        if (sh) {
            char name[64] = {0};
            char *q = strchr(sh, ':');
            if (q) {
                q = strchr(q, '"'); if (q) { q++; char *e = strchr(q, '"');
                    if (e && (size_t)(e - q) < sizeof name) { memcpy(name, q, (size_t)(e - q)); } }
            }
            if (frame >= 0 && name[0] && s_script_n < 512) {
                s_script[s_script_n].frame = frame;
                s_script[s_script_n].mask = mask;
                s_script[s_script_n].shot = 1;
                s_script_n++;
            }
        }
        p = end + 1;
    }
    free(buf);
    /* stable insertion by frame (the file is already ordered) */
    for (int i = 1; i < s_script_n; i++) {
        ScriptRow r = s_script[i];
        int j = i - 1;
        while (j >= 0 && s_script[j].frame > r.frame) { s_script[j + 1] = s_script[j]; j--; }
        s_script[j + 1] = r;
    }
}

static void wav_header(FILE *f, unsigned long frames, int rate)
{
    uint32_t data = (uint32_t)(frames * 4);
    uint32_t riff = 36 + data;
    uint16_t ch = 2, bits = 16, align = 4, fmt = 1;
    uint32_t byterate = (uint32_t)rate * 4, fmtlen = 16;
    fwrite("RIFF", 1, 4, f); fwrite(&riff, 4, 1, f);
    fwrite("WAVEfmt ", 1, 8, f);
    fwrite(&fmtlen, 4, 1, f); fwrite(&fmt, 2, 1, f); fwrite(&ch, 2, 1, f);
    fwrite(&rate, 4, 1, f); fwrite(&byterate, 4, 1, f);
    fwrite(&align, 2, 1, f); fwrite(&bits, 2, 1, f);
    fwrite("data", 1, 4, f); fwrite(&data, 4, 1, f);
}

int main(int argc, char **argv)
{
    const char *core = NULL, *rom = NULL, *script = NULL, *wav = NULL;
    long frames = 3600, shot_every = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--core") && i + 1 < argc) core = argv[++i];
        else if (!strcmp(argv[i], "--rom") && i + 1 < argc) rom = argv[++i];
        else if (!strcmp(argv[i], "--frames") && i + 1 < argc) frames = atol(argv[++i]);
        else if (!strcmp(argv[i], "--script") && i + 1 < argc) script = argv[++i];
        else if (!strcmp(argv[i], "--wav") && i + 1 < argc) wav = argv[++i];
        else if (!strcmp(argv[i], "--shots") && i + 1 < argc) s_shots = argv[++i];
        else if (!strcmp(argv[i], "--shot-every") && i + 1 < argc) shot_every = atol(argv[++i]);
        else { fprintf(stderr, "unknown argument %s\n", argv[i]); return 2; }
    }
    if (!core || !rom) { fprintf(stderr, "need --core and --rom\n"); return 2; }
    if (script) load_script(script);

    void *h = dlopen(core, RTLD_NOW);
    if (!h) { fprintf(stderr, "dlopen: %s\n", dlerror()); return 2; }
#define SYM(name) do { *(void **)(&r_##name) = dlsym(h, "retro_" #name); \
        if (!r_##name) { fprintf(stderr, "missing retro_" #name "\n"); return 2; } } while (0)
    SYM(init); SYM(deinit); SYM(api_version); SYM(get_system_info);
    SYM(get_system_av_info); SYM(set_environment); SYM(set_video_refresh);
    SYM(set_audio_sample); SYM(set_audio_sample_batch); SYM(set_input_poll);
    SYM(set_input_state); SYM(load_game); SYM(unload_game); SYM(run);
#undef SYM

    r_set_environment(env_cb);
    r_init();
    if (r_api_version() != RETRO_API_VERSION) { fprintf(stderr, "api %u\n", r_api_version()); return 2; }
    r_set_video_refresh(video_refresh);
    r_set_audio_sample(audio_sample);
    r_set_audio_sample_batch(audio_batch);
    r_set_input_poll(input_poll);
    r_set_input_state(input_state);

    struct retro_system_info si;
    memset(&si, 0, sizeof si);
    r_get_system_info(&si);
    struct retro_game_info gi = {rom, NULL, 0, NULL};
    if (!r_load_game(&gi)) { fprintf(stderr, "load_game failed (need_fullpath=%d)\n", si.need_fullpath); return 2; }

    struct retro_system_av_info av;
    memset(&av, 0, sizeof av);
    r_get_system_av_info(&av);
    s_sample_rate = (int)(av.timing.sample_rate + 0.5);
    if (s_sample_rate <= 0) s_sample_rate = 44100;
    fprintf(stderr, "[gpgx_render] fps=%.5f rate=%d\n", av.timing.fps, s_sample_rate);

    if (wav) {
        s_wav = fopen(wav, "wb");
        if (!s_wav) { perror(wav); return 2; }
        wav_header(s_wav, 0, s_sample_rate);
    }

    for (s_frame = 0; s_frame < frames; s_frame++) {
        for (int i = 0; i < s_script_n; i++)
            if (s_script[i].frame == s_frame && s_script[i].shot) {
                /* Shot markers are taken after the frame is rendered. */
            }
        r_run();
        for (int i = 0; i < s_script_n; i++)
            if (s_script[i].frame == s_frame && s_script[i].shot) {
                char tag[32];
                snprintf(tag, sizeof tag, "f%05ld", s_frame);
                write_ppm(s_shots, tag);
            }
        if (shot_every > 0 && s_frame % shot_every == 0) {
            char tag[32];
            snprintf(tag, sizeof tag, "f%05ld", s_frame);
            write_ppm(s_shots, tag);
        }
    }

    if (s_wav) {
        fclose(s_wav);
        s_wav = fopen(wav, "r+b");
        wav_header(s_wav, s_audio_frames, s_sample_rate);
        fclose(s_wav);
    }
    r_unload_game();
    r_deinit();
    fprintf(stderr, "[gpgx_render] frames=%ld audio_frames=%lu rate=%d dur=%.3fs\n",
            frames, s_audio_frames, s_sample_rate,
            (double)s_audio_frames / s_sample_rate);
    return 0;
}
