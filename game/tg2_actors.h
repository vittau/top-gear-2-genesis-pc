/* tg2_actors.h — read-only actor snapshots and the N x actor painter
 * (docs/HIGHRES.md §3, §14, S4). */
#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

struct GVDP;
struct Tg2RowState;

enum { TG2_MAX_ACTORS = 160, TG2_MAX_MODEL_PIECES = 1280 };

/* One sprite piece of a model, relative to the object's anchor (X centre,
 * Y base line): the same fields the mapper would put in the SAT. */
typedef struct Tg2ModelPiece {
    short dx, dy;
    unsigned short attr;
    unsigned char size, pad;
} Tg2ModelPiece;

/* One promoted object, latched at the mapper entry ($B584). Everything the
 * painter needs is copied here; nothing is looked up in live guest memory at
 * presentation time. */
typedef struct Tg2Actor {
    double x, y;                 /* sub-pixel anchor, screen coordinates      */
    double continuous;         /* projection / fixed model-0 reference      */
    double projection, depth;   /* unrounded scale and depth + fraction      */
    short lateral;              /* projection input, for temporal matching   */
    unsigned short object;      /* car number or moving-scenery slot         */
    unsigned identity;          /* scenery world depth (16.16), or car slot  */
    unsigned record;
    short gx, gy, clip;         /* guest integer anchor, first hidden row    */
    unsigned short first_piece; /* scene piece index when it started (depth) */
    unsigned short scale, scale4;
    unsigned short guest_first, guest_count, model_first, model_count;
    unsigned char kind, guest_model, model, level, path, high, fallback, car;
} Tg2Actor;

typedef struct Tg2ActorSet {
    unsigned count, piece_count, dropped, native_objects;
    Tg2Actor actors[TG2_MAX_ACTORS];
    Tg2ModelPiece pieces[TG2_MAX_MODEL_PIECES];
} Tg2ActorSet;

/* S4 is on: render scale above 1 (TG2_ACTORS=0 keeps the S3 picture, for
 * qualification A/B runs only). */
int tg2_actors_active(void);
/* Qualification only: TG2_ACTOR_LOG=path writes the LOD evidence stream. */
int tg2_actors_logging(void);

/* Pre-instruction hook sites (game.toml): $B314 projection input,
 * $B42E/$B4D6 right after `swap d1`, $B584 mapper, $B5FA mapping header. */
void tg2_actors_latch(uint32_t pc);
void tg2_actors_begin(Tg2ActorSet *set);
/* Returns the new actor's index, or -1 when the object stays native. `set`
 * may be NULL (evidence log only). */
int tg2_actors_object(Tg2ActorSet *set, unsigned piece_index);
void tg2_actors_log_header(void);
void tg2_actors_frame(uint64_t frame);
void tg2_actors_reset(void);

/* Once per presented picture, before its rows: rasterise the models of the
 * displayed set from the displayed VRAM and fix each actor's size. A NULL set
 * clears the prepared picture. */
void tg2_actors_prepare(const struct GVDP *v, const Tg2ActorSet *set);
/* Whether actor `index` of the prepared set will be painted (its native
 * sprites may then be removed from the row). */
int tg2_actors_promoted(int index);
unsigned tg2_actors_dropped(void);
unsigned tg2_actors_native_objects(void);
/* Qualification: how many scene pieces the actor has, how many intersect the
 * native picture and how many of those the displayed SAT contains. */
void tg2_actors_note_sat(int index, unsigned pieces, unsigned inside, unsigned matched, unsigned position_mismatches);

void tg2_actors_note_native(unsigned piece, unsigned kind);

typedef struct Tg2ActorCanvas {
    uint32_t *pixels;
    int stride, width, scale, w1, origin, rows;
    const unsigned char *const *occluder;   /* per native row, w1 entries   */
    const unsigned short *const *front;     /* per native row, w1 entries   */
    const unsigned char *row_ok;            /* row was rendered actor-free  */
    const struct Tg2RowState *state;        /* per native row (palette)     */
} Tg2ActorCanvas;
/* Paint the prepared actors far to near into the finished N x picture. */
void tg2_actors_paint(const Tg2ActorCanvas *canvas);
/* JSON array of the prepared actors and the last paint's results. */
int tg2_actors_json(char *out, int capacity);
int tg2_actors_stats_json(char *out, int capacity);

#ifdef __cplusplus
}
#endif
