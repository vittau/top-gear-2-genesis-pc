/* tg2_actors.c — read-only actor (scenery/vehicle) snapshots for the N x
 * renderer (docs/HIGHRES.md §3, §14). Every hook here only reads registers,
 * work RAM and ROM at audited instruction boundaries; nothing is written back
 * to the guest. */
#include "tg2_actors.h"
#include "genesis_runtime.h"
#include "tg2_highres.h"
#include "video/genesis_vdp.h"
#include "video/genesis_dac.h"
#include <math.h>
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
    unsigned fraction;
    int lateral;
} Projection;
static Projection pending;
static struct {
    uint64_t actors, native, fallbacks, positions, palettes, priorities;
    uint64_t kinds[256], reasons[8];
    double floor_error, anchor_error;
} totals;

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
    memset(&totals,0,sizeof totals);
    tg2_actors_prepare(NULL,NULL);
    def_count = 0;
    table_ptr[0] = table_ptr[1] = 0;
}
static void evidence_hook(uint32_t pc) {
    if (ram16(0x189E))
        return; /* 2P split-screen stays native */
    if (pc == 0xB314) {
        pending.path = 0;
        pending.fraction = g_cpu.D[2] & 65535;
        pending.lateral = (int16_t)g_cpu.D[1];
    } else if (pc == 0xB42E || pc == 0xB4D6) {
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

/* ---- Immutable model capture ----------------------------------------- */
int tg2_actors_active(void) {
    static int allowed = -1;
    if (allowed < 0) { const char *s = getenv("TG2_ACTORS"); allowed = !s || *s != '0'; }
    return allowed && tg2_highres_present_scale() > 1;
}
void tg2_actors_latch(uint32_t pc) { evidence_hook(pc); }
void tg2_actors_log_header(void) { evidence_hook(0xB5FA); }
void tg2_actors_begin(Tg2ActorSet *set) { memset(set, 0, sizeof *set); pending.path = 0; }

/* All addresses/attributes are resolved while the mapper owns this record.
 * Presentation subsequently reads only these pieces and the displayed VRAM. */
static int capture_model(Tg2ActorSet *set, unsigned record, unsigned model,
                         unsigned *key, unsigned short *first, unsigned short *count) {
    unsigned art = mem32(record), table = mem32(record + 4);
    if (!valid_pointer(art) || !valid_pointer(table) || model >= 40) return 0;
    unsigned h = mem32(table + model * 4), start = set->piece_count;
    *key = h; *first = start; *count = 0;
    if (!valid_pointer(h)) return 0;
    for (unsigned n = 0; n < 16; ++n, h += 10) {
        unsigned list = art + 8 + mem16(h), pieces = mem16(list);
        unsigned p = (mem32(list + 2) + art) & 0xFFFFFF;
        unsigned attr = mem16(h + 6) | mem16(record + 8);
        if (!valid_pointer(p) || pieces > 128 || start + *count + pieces > TG2_MAX_MODEL_PIECES) break;
        int half = (int16_t)mem16(h + 2), height = (int16_t)mem16(h + 4);
        for (unsigned i = 0; i < pieces; ++i, p += 8) {
            Tg2ModelPiece *q = &set->pieces[start + (*count)++];
            unsigned sz = mem16(p + 2) >> 8, pa = mem16(p + 4);
            int pw = (((sz >> 2) & 3) + 1) * 8, xoff = (int16_t)mem16(p + 6);
            q->dx = attr & 0x800 ? half - xoff - pw : -half + xoff;
            q->dy = -height + (int16_t)mem16(p);
            q->size = sz & 15; q->pad = 0;
            q->attr = (((attr ^ (pa & 0x1800)) + (pa & 2047)) | ram16(0x234E));
            if (g_ram[0x22E8]) q->attr |= 0x8000;
        }
        if (mem16(h + 8) == 0x8888) { set->piece_count = start + *count; return *count != 0; }
    }
    *count = 0; return 0;
}
static int tabulated(unsigned kind) {
    return kind == 0x80 || kind == 0xF0 || kind == 0x94 || kind == 0x85 ||
           kind == 0x99 || kind == 0x9A || kind == 0x86;
}
static unsigned car_model(unsigned guest, unsigned *level) {
    for (unsigned row = 0; row < 24; ++row) {
        int best = -1, runs = 0; unsigned previous = 256;
        for (int col = 0; col < 9; ++col) {
            unsigned m = g_rom[0x57C8 + row * 9 + col];
            if (m != previous) ++runs;
            previous = m;
            if (m == guest && (best < 0 || abs(col - 4) < abs(best - 4))) best = col;
        }
        if (best >= 0) { *level = row; return row == 0 ? guest : g_rom[0x57C8 + (runs == 1 ? 4 : best)]; }
    }
    return guest;
}
/* Model 0's authored reference is the geometric centre of its own ROM
 * depth interval. All audited scenery kinds share that interval [0,2),
 * cars use [0,1). Resolve by kind's table, never by the CURRENT art band.
 * Reference scales on the three captured tracks: scenery 2270.0837, cars
 * 2499.1775. This reference never follows the selected hand-drawn band. */
static double projection_reference(int car) {
    unsigned table = mem32(car ? 0xFF2226 : 0xFF2222), scales = mem32(0xFF221E);
    int first = -1, last = -1;
    if (!valid_pointer(table) || !valid_pointer(scales)) return 0;
    for (int d = 0; d < 127; ++d) {
        if (mem16(table + 2*d) == 0) {
            if (first < 0) first = d;
            last = d;
        } else if (first >= 0) break;
    }
    return first < 0 ? 0 : sqrt((double)mem16(scales + first*2) * mem16(scales + (last+1)*2));
}
int tg2_actors_object(Tg2ActorSet *set, unsigned piece_index) {
    evidence_hook(0xB584);
    unsigned record = g_cpu.A[1] & 0xFFFFFF, kind = ram16(0x187C) & 255;
    int path = pending.path;
    pending.path = 0;
    if (!set) return -1;
    if (!path || pending.record != record || ((pending.d1 ^ g_cpu.D[1]) & 65535) ||
        ram16(0x189E) || ram16(0x1878) == 0xFFFE || ram16(0x1878) == 0xFD66 ||
        kind == 0x82 || kind == 0x83 || kind == 0x84 || kind == 0xBD ||
        kind == 0x8A || kind == 0xF8 || kind == 0xF9 || kind == 0xFC || kind == 0xFD ||
        !valid_pointer(record) ||
        (record >= 0xFF8E94 && ram16(0x1878) == ram16(0x17D6))) { ++set->native_objects; return -1; }
    if (set->count == TG2_MAX_ACTORS) { ++set->dropped; return -1; }
    Tg2Actor a = {0};
    a.record = record; a.art = mem32(record); a.kind = kind; a.path = path;
    a.car = record >= 0xFF8E94; a.guest_model = g_cpu.D[7] & 255;
    unsigned level = a.guest_model;
    a.model = a.car ? car_model(a.guest_model, &level) : tabulated(kind) ? 0 : a.guest_model;
    a.fallback = !a.car && !tabulated(kind) ? 1 : 0;
    a.level = level; a.rattr = mem16(record + 8); a.scale = ram16(0x17E0);
    a.scale4 = pending.d4 & 65535;
    a.object = ram16(0x1878);
    a.lateral = pending.lateral;
    /* $B3A2 halves D2 before signed multiplication, then $B422 doubles
     * that product. Preserve the full original unsigned fraction; the far
     * path has the same input but discards it. D0 at both endpoints = 2*row.
     * Read the same table the ROM uses at $B40C/$B4C4, without integer
     * truncation or dependence on the selected art band. */
    unsigned scales = mem32(0xFF221E), row = pending.depth2 / 2;
    a.depth = row + pending.fraction / 65536.0;
    /* $A094..$A0AA forms scenery's shared fractional depth from camera
     * position, multiplied by 16; subsequent rows are 4 units apart ($A312).
     * $B058 copies the active camera ($FF193E for 1P) into $FF17F4.
     * Adding that coordinate gives a stable world identity,
     * even when equal kinds/laterals overlap at different depths. */
    a.identity = a.car ? a.object :
        (mem32(0xFF17F4) << 4) + (row << 16) + pending.fraction;
    a.projection = valid_pointer(scales) && row < 127 ?
        mem16(scales + 2*row) + (mem16(scales + 2*row + 2) - (double)mem16(scales + 2*row)) *
        pending.fraction / 65536.0 : a.scale;
    a.gx = (int16_t)g_cpu.D[1] + 128;
    a.gy = (int16_t)g_cpu.D[2] + (int16_t)ram16(0x2452) - 128;
    a.x = a.gx + (pending.d1 >> 16) / 65536.0;
    double y = (int16_t)pending.d2 + (path == 1 ? (pending.d2 >> 16) / 65536.0 : 0);
    int limit = (int16_t)ram16(0x17BC) - 2;
    if (y >= limit) y = limit;
    unsigned shift = ram16(0x242A);
    y -= ldexp((int16_t)ram16(0x17DC) * a.scale / 65536.0, -(int)(shift & 63));
    y += (int16_t)ram16(0x2452) - 128;
    a.y = fmax(a.gy, fmin(a.gy + 255.0/256, y));
    a.clip = (int16_t)ram16(0x1836) + (int16_t)ram16(0x2452) - 128;
    a.first_piece = piece_index;
    double reference = projection_reference(a.car);
    a.continuous = reference > 0 ? a.projection / reference : 0;
    unsigned start = set->piece_count;
    if (!capture_model(set, record, a.guest_model, &a.guest_key, &a.guest_first, &a.guest_count)) {
        ++set->dropped; return -1;
    }
    if (!capture_model(set, record, a.model, &a.model_key, &a.model_first, &a.model_count)) {
        a.model = a.guest_model; a.model_key = a.guest_key; a.model_first = a.guest_first;
        a.model_count = a.guest_count; a.fallback = 2;
    }
    if (set->piece_count < start) return -1;
    a.high = !!(set->pieces[a.guest_first].attr & 0x8000);
    set->actors[set->count] = a;
    return set->count++;
}

/* ---- Per-picture indexed art, deduplicated by the captured pieces ------ */
typedef struct {
    unsigned first, count;
    int x0, y0, w, h;
    unsigned char *texels;
} Art;
typedef struct {
    Tg2Actor actor;
    int art, promoted;
    float size, stepped_size;
    int continuous_size;
    unsigned native_blocked, pole_blocked, pole_overpaint;
    unsigned pixels, pieces, inside, matched, position_mismatches, palettes, priorities, guest_palettes, guest_priorities;
    double drawn_x, drawn_y;
    int draw_origin, draw_scale;
    int box[4], guest_box[4];
} Prepared;
static Art art_cache[TG2_MAX_ACTORS * 2];
static Prepared prepared[TG2_MAX_ACTORS];
static unsigned art_count, prepared_count;
static unsigned char native_kind[2048];
void tg2_actors_note_native(unsigned piece, unsigned kind) {
    if(piece<2048) native_kind[piece]=kind;
}
static const Tg2ActorSet *prepared_set;
static int raster_model(const GVDP *v, unsigned first, unsigned count) {
    const Tg2ModelPiece *pieces = prepared_set->pieces + first;
    for (unsigned i = 0; i < art_count; ++i) {
        Art *a = &art_cache[i];
        if (count == a->count && !memcmp(pieces, prepared_set->pieces + a->first, count * sizeof *pieces)) return i;
    }
    if (!count || art_count == TG2_MAX_ACTORS * 2) return -1;
    int x0 = 32767, y0 = 32767, x1 = -32768, y1 = -32768;
    for (unsigned i = 0; i < count; ++i) {
        const Tg2ModelPiece *p = &pieces[i];
        int w = (((p->size >> 2) & 3) + 1)*8, h = ((p->size & 3) + 1)*8;
        if (p->dx < x0) x0 = p->dx;
        if (p->dy < y0) y0 = p->dy;
        if (p->dx+w > x1) x1 = p->dx+w;
        if (p->dy+h > y1) y1 = p->dy+h;
    }
    int w = x1-x0, h = y1-y0;
    if (w <= 0 || h <= 0 || w > 256 || h > 256) return -1;
    unsigned char *texels = calloc((size_t)w, h);
    if (!texels) return -1;
    int lx = w, ly = h, rx = 0, ry = 0;
    for (unsigned i = 0; i < count; ++i) {
        const Tg2ModelPiece *p = &pieces[i];
        int pw = (((p->size >> 2) & 3) + 1)*8, ph = ((p->size & 3) + 1)*8;
        for (int dy = 0; dy < ph; ++dy) for (int dx = 0; dx < pw; ++dx) {
            int sx = p->attr & 0x800 ? pw-1-dx : dx, sy = p->attr & 0x1000 ? ph-1-dy : dy;
            unsigned tile = ((p->attr & 2047) + (sx/8)*(ph/8) + sy/8) & 2047;
            unsigned b = v->vram[(tile*32+(sy&7)*4+(sx&7)/2)&65535];
            unsigned c = sx&1 ? b&15 : b>>4;
            if (!c) continue;
            int x = p->dx-x0+dx, y = p->dy-y0+dy;
            texels[y*w+x] = c | ((p->attr >> 9)&48) | ((p->attr >> 8)&128);
            if (x < lx) lx=x; if (y < ly) ly=y;
            if (x+1 > rx) rx=x+1; if (y+1 > ry) ry=y+1;
        }
    }
    if (rx <= lx || ry <= ly) { free(texels); return -1; }
    /* Crop to opaque extent; transparent texels still have zero coverage. */
    int cw=rx-lx, ch=ry-ly;
    for (int y=0;y<ch;++y) memmove(texels+y*cw,texels+(y+ly)*w+lx,cw);
    Art *a = &art_cache[art_count];
    *a = (Art){first,count,x0+lx,y0+ly,cw,ch,texels};
    return art_count++;
}
/* The sole size policy switch. Stepped is the authored size by default;
 * continuous awaits owner motion review before becoming the default. */
static float actor_size_policy(float stepped, double projected, int *selected) {
    static int continuous=-1;
    if (continuous<0) {
        const char *s=getenv("TG2_ACTOR_SIZE");
        continuous=s && !strcmp(s,"continuous");
    }
    *selected = continuous && projected > 0;
    return *selected ? projected : stepped;
}
void tg2_actors_prepare(const GVDP *v, const Tg2ActorSet *set) {
    for (unsigned i=0;i<art_count;++i) free(art_cache[i].texels);
    art_count=prepared_count=0; prepared_set=set;
    memset(native_kind,0,sizeof native_kind);
    if (!v || !set || !tg2_actors_active()) return;
    prepared_count=set->count;
    for (unsigned i=0;i<set->count;++i) {
        Prepared *p=&prepared[i]; memset(p,0,sizeof *p); p->actor=set->actors[i];
        Tg2Actor *a=&p->actor;
        int guest=raster_model(v,a->guest_first,a->guest_count), model=raster_model(v,a->model_first,a->model_count);
        if (guest<0) continue;
        if (model<0) { model=guest; a->fallback=3; }
        Art *g=&art_cache[guest], *m=&art_cache[model];
        p->guest_box[0]=a->gx+g->x0; p->guest_box[1]=a->gy+g->y0;
        p->guest_box[2]=p->guest_box[0]+g->w; p->guest_box[3]=p->guest_box[1]+g->h;
        p->size=m->w>=m->h ? (float)g->w/m->w : (float)g->h/m->h;
        if (p->size>1) { model=guest; p->size=1; a->fallback=4; }
        if (model==guest) a->model=a->guest_model;
        p->stepped_size=p->size;
        p->size=actor_size_policy(p->size,a->fallback?0:a->continuous,&p->continuous_size);
        p->art=model; p->promoted=1;
        for(int n=0;n<g->w*g->h;++n) if(g->texels[n]) {
            p->guest_palettes|=1u<<((g->texels[n]>>4)&3);
            p->guest_priorities|=1u<<(g->texels[n]>>7);
        }
        m=&art_cache[model];
        for (int n=0;n<m->w*m->h;++n) if (m->texels[n]) {
            p->palettes |= 1u<<((m->texels[n]>>4)&3);
            p->priorities |= 1u<<(m->texels[n]>>7);
        }
    }
}
unsigned tg2_actors_dropped(void) { return prepared_set?prepared_set->dropped:0; }
unsigned tg2_actors_native_objects(void) { return prepared_set?prepared_set->native_objects:0; }
int tg2_actors_promoted(int index) {
    return index>=0 && (unsigned)index<prepared_count && prepared[index].promoted;
}
void tg2_actors_note_sat(int index, unsigned pieces, unsigned inside, unsigned matched, unsigned position_mismatches) {
    if (index<0 || (unsigned)index>=prepared_count) return;
    prepared[index].position_mismatches=position_mismatches;
    prepared[index].pieces=pieces; prepared[index].inside=inside; prepared[index].matched=matched;
    if (!pieces || position_mismatches || inside != matched) {
        /* Respect the guest emitter's final culling/SAT allocation. A piece
         * captured before that decision is insufficient to replace an actor. */
        prepared[index].promoted=0;
        prepared[index].actor.fallback=!pieces?6:position_mismatches?7:5;
    }
}
void tg2_actors_paint(const Tg2ActorCanvas *c) {
    static int trace_checked;
    static FILE *trace;
    if (!trace_checked) {
        const char *path=getenv("TG2_ACTOR_TRACE"); trace_checked=1;
        if(path && *path) {
            trace=fopen(path,"w");
            if(trace) fprintf(trace,"frame,index,record,kind,car,level,model,path,x,y,lateral,depth,guest_scale,scale4,projection,size,promoted,fallback,pixels,identity\n");
        }
    }
    for (unsigned i=0;i<prepared_count;++i) {
        Prepared *p=&prepared[i]; p->pixels=p->native_blocked=p->pole_blocked=p->pole_overpaint=0;
        const Tg2Actor *a=&p->actor;
        if(a->fallback) {++totals.fallbacks;if(a->fallback<8)++totals.reasons[a->fallback];}
        if (!p->promoted) {++totals.native;goto traced;}
        ++totals.actors;++totals.kinds[a->kind];
        totals.positions+=p->position_mismatches;
        totals.palettes+=p->palettes!=p->guest_palettes;
        totals.priorities+=p->priorities!=p->guest_priorities;
        double error=fmax(fabs(floor(a->x)-a->gx),fabs(floor(a->y)-a->gy));
        if(error>totals.floor_error)totals.floor_error=error;
        const Art *m=&art_cache[p->art];
        double k=p->size*c->scale, ax=(a->x+c->origin)*c->scale, ay=a->y*c->scale;
        p->drawn_x=ax;p->drawn_y=ay;p->draw_origin=c->origin;p->draw_scale=c->scale;
        error=fmax(fabs(p->drawn_x-(a->x+c->origin)*c->scale),fabs(p->drawn_y-a->y*c->scale));
        if(error>totals.anchor_error)totals.anchor_error=error;
        double radius=fmax(1,1/k)*0.5;
        int x0=(int)floor(ax+(m->x0-radius)*k), x1=(int)ceil(ax+(m->x0+m->w+radius)*k);
        int y0=(int)floor(ay+(m->y0-radius)*k), y1=(int)ceil(ay+(m->y0+m->h+radius)*k);
        p->box[0]=x0;p->box[1]=y0;p->box[2]=x1;p->box[3]=y1;
        if (x0<0)x0=0; if (x1>c->width)x1=c->width;
        if (y0<0)y0=0; if (y1>c->rows*c->scale)y1=c->rows*c->scale;
        for (int y=y0;y<y1;++y) {
            int row=y/c->scale;
            if (!c->row_ok[row] || y+0.5>=a->clip*c->scale) continue;
            uint32_t pal[64];
            for (int n=0;n<64;++n) pal[n]=genesis_dac_cram_to_argb(c->state[row].cram[n],0);
            double ty=(y+0.5-ay)/k-m->y0, top=ty-radius, bottom=ty+radius;
            int sy0=(int)floor(top), sy1=(int)ceil(bottom);
            if(sy0<0)sy0=0;if(sy1>m->h)sy1=m->h;
            for (int x=x0;x<x1;++x) {
                int col=x/c->scale; unsigned front=c->front[row][col];
                int blocked=front==65535 || (front && front-1>=a->first_piece);
                unsigned kind=front && front<=2048?native_kind[front-1]:0;
                int pole=kind==0xBD || kind==0x83 || kind==0x84;
                double tx=(x+0.5-ax)/k-m->x0, left=tx-radius,right=tx+radius;
                int sx0=(int)floor(left),sx1=(int)ceil(right);
                if(sx0<0)sx0=0;if(sx1>m->w)sx1=m->w;
                double rgb[3]={0}, alpha=0, area=4*radius*radius;
                for(int sy=sy0;sy<sy1;++sy) for(int sx=sx0;sx<sx1;++sx) {
                    unsigned t=m->texels[sy*m->w+sx];
                    if (!t || (c->occluder[row][col] && !(t&128))) continue;
                    double weight=(fmin(right,sx+1)-fmax(left,sx))*(fmin(bottom,sy+1)-fmax(top,sy));
                    uint32_t color=pal[t&63]; alpha+=weight;
                    for(int ch=0;ch<3;++ch) rgb[ch]+=((color>>(ch*8))&255)*weight;
                }
                if (alpha<=0)continue;
                if(blocked) {++p->native_blocked;if(pole)++p->pole_blocked;continue;}
                if(pole)++p->pole_overpaint;
                uint32_t *out=&c->pixels[(size_t)y*c->stride+x], under=*out,color=0xFF000000;
                for(int ch=0;ch<3;++ch) color|=(unsigned)fmin(255,floor((rgb[ch]+((under>>(ch*8))&255)*(area-alpha))/area+0.5))<<(ch*8);
                *out=color;++p->pixels;
            }
        }
traced:
        if(trace) fprintf(trace,"%llu,%u,%u,%u,%u,%u,%u,%u,%.8f,%.8f,%d,%.8f,%u,%u,%.8f,%.8f,%d,%u,%u,%u\n",
            (unsigned long long)log_frame,i,a->record,a->kind,a->car,a->level,a->model,a->path,
            a->x,a->y,a->lateral,a->depth,a->scale,a->scale4,a->projection,p->size,p->promoted,a->fallback,p->pixels,a->identity);
    }
}
int tg2_actors_json(char *out,int cap) {
    int n=snprintf(out,cap,"[");
    for(unsigned i=0;i<prepared_count && n>0 && n<cap;++i) {
        Prepared *p=&prepared[i]; Tg2Actor *a=&p->actor;
        n+=snprintf(out+n,cap-n,"%s{\"kind\":%u,\"record\":%u,\"guest_model\":%u,\"model\":%u,\"fallback\":%u,\"promoted\":%d,\"guest\":[%d,%d],\"anchor\":[%.8f,%.8f],\"size\":%.8f,\"clip\":%d,\"first_piece\":%u,\"palette_mask\":%u,\"priority_mask\":%u,\"high\":%u,\"box\":[%d,%d,%d,%d],\"pixels\":%u,\"pieces\":%u,\"inside\":%u,\"matched\":%u,\"position_mismatches\":%u,\"guest_palette_mask\":%u,\"guest_priority_mask\":%u,\"drawn_anchor\":[%.8f,%.8f],\"draw_origin\":%d,\"draw_scale\":%d,\"native_blocked\":%u,\"pole_blocked\":%u,\"pole_overpaint\":%u,\"guest_box\":[%d,%d,%d,%d],\"projection\":%.8f,\"depth\":%.8f,\"car\":%u,\"object\":%u,\"continuous_size\":%d,\"stepped_size\":%.8f}",
            i?",":"",a->kind,a->record,a->guest_model,a->model,a->fallback,p->promoted,a->gx,a->gy,a->x,a->y,p->size,a->clip,a->first_piece,p->palettes,p->priorities,a->high,p->box[0],p->box[1],p->box[2],p->box[3],p->pixels,p->pieces,p->inside,p->matched,p->position_mismatches,p->guest_palettes,p->guest_priorities,p->drawn_x,p->drawn_y,p->draw_origin,p->draw_scale,p->native_blocked,p->pole_blocked,p->pole_overpaint,p->guest_box[0],p->guest_box[1],p->guest_box[2],p->guest_box[3],a->projection,a->depth,a->car,a->object,p->continuous_size,p->stepped_size);
    }
    if(n>0 && n<cap)n+=snprintf(out+n,cap-n,"]");
    return n;
}

int tg2_actors_stats_json(char *out,int cap) {
    int n=snprintf(out,cap,"{\"actors\":%llu,\"native\":%llu,\"fallbacks\":%llu,\"position_mismatches\":%llu,\"palette_mismatches\":%llu,\"priority_mismatches\":%llu,\"max_floor_error\":%.8f,\"max_drawn_anchor_error\":%.8f,\"fallback_reasons\":[",
        (unsigned long long)totals.actors,(unsigned long long)totals.native,(unsigned long long)totals.fallbacks,
        (unsigned long long)totals.positions,(unsigned long long)totals.palettes,(unsigned long long)totals.priorities,totals.floor_error,totals.anchor_error);
    for(int i=0;i<8 && n>0 && n<cap;++i) n+=snprintf(out+n,cap-n,"%s%llu",i?",":"",(unsigned long long)totals.reasons[i]);
    if(n>0 && n<cap)n+=snprintf(out+n,cap-n,"],\"kinds\":{");
    int comma=0;
    for(int i=0;i<256 && n>0 && n<cap;++i) if(totals.kinds[i]) n+=snprintf(out+n,cap-n,"%s\"%02X\":%llu",comma++?",":"",i,(unsigned long long)totals.kinds[i]);
    if(n>0 && n<cap)n+=snprintf(out+n,cap-n,"}}");
    return n;
}
