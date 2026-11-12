/* TG2 video: scene (pure extraction from tg2_video.c). */
#include "tg2_video_internal.h"

/* Snapshots match the SAT actually displayed, rather than the CPU's next
 * scene. These hooks only read registers, RAM and ROM. */



static Scene building, history[HISTORY];
const Scene *tg2v_shown;
static int current_actor = -1;
unsigned tg2v_serial, tg2v_overflow, tg2v_matched_pieces, tg2v_margin_pieces;
void tg2_video_reset(void) {
    tg2v_presentation_clear();
    tg2_highres_reset();
    tg2_actors_reset();
    tg2v_highres_wanted = 0;
#ifdef GEN_ENABLE_TRACE
    tg2v_actor_rows=tg2v_actor_row_mismatches=0;
#endif
    memset(&building, 0, sizeof building);
    memset(history, 0, sizeof history);
    tg2v_shown = NULL; current_actor=-1;
    tg2v_serial = tg2v_overflow = tg2v_matched_pieces = tg2v_margin_pieces = 0;
    tg2v_crop_race_ok = tg2v_crop_top_rows = tg2v_crop_bottom_ok = tg2v_presented_cropped = 0;
    tg2v_crop_frames = tg2v_crop_withheld = 0;
}
int tg2_video_hook(uint32_t pc) {
    int actors = tg2_actors_active();
    if (pc == 0xB314 || pc == 0xB42E || pc == 0xB4D6) {
        if (actors || tg2_actors_logging()) tg2_actors_latch(pc);
    } else if (pc == 0xB584) {
        current_actor = (actors || tg2_actors_logging()) ?
            tg2_actors_object(actors ? &building.actors : NULL, building.count) : -1;
    } else if (pc == 0xB5FA && tg2_actors_logging()) tg2_actors_log_header();
    if (!tg2v_renderer_enabled())
        return 0;
    if (pc == 0x67EE) {
        building.count = 0; current_actor = -1;
        tg2_actors_begin(&building.actors);
    }
    else if (pc == 0x6982) {
        unsigned index = tg2_word(g_ram, 0x22D8);
        if (index > 127)
            return 0;
        building.sat_size = (127 - index) * 8;
        if (building.sat_size > 512)
            building.sat_size = 512;
        unsigned src = tg2_mem32(0xFF2316) + index * 8;
        for (unsigned i = 0; i < building.sat_size; i++)
            building.sat[i] = g_ram[(src + i) & 65535];
        building.serial = ++tg2v_serial;
        history[tg2v_serial % HISTORY] = building;
    } else if (pc == 0xB5FA && !tg2_word(g_ram, 0x189E)) {
        unsigned p = g_cpu.A[1] & 0xFFFFFF, header = g_cpu.A[0] & 0xFFFFFF;
        unsigned count = g_cpu.D[7] & 65535;
        if (count > 128)
            return 0;
        int x = (int16_t)g_cpu.D[1], y = (int16_t)g_cpu.D[2] - (int16_t)tg2_mem16(header);
        unsigned attr = tg2_mem16(header + 2) | (g_cpu.D[5] & 65535);
        if (tg2_word(g_ram, 0x1878) != 0xFD66)
            x += (tg2_mem16(header + 2) & 0x800) ? (int16_t)g_cpu.D[6] : -(int16_t)g_cpu.D[6];
        for (unsigned i = 0; i < count; i++, p += 8) {
            unsigned sz = tg2_mem16(p + 2) >> 8, pa = tg2_mem16(p + 4);
            int pw = (((sz >> 2) & 3) + 1) * 8, ph = ((sz & 3) + 1) * 8;
            int px = x + (attr & 0x800 ? -(int16_t)tg2_mem16(p + 6) - pw : (int16_t)tg2_mem16(p + 6));
            int py = y + (int16_t)tg2_mem16(p);
            /* Original vertical occlusion/culling. X alone is expanded. */
            if (py >= (int16_t)tg2_word(g_ram, 0x1836) ||
                py + (int)(tg2_mem16(p + 2) & 255) >= (int16_t)tg2_word(g_ram, 0x1836) ||
                py + ph <= (int16_t)tg2_word(g_ram, 0x23E6))
                continue;
            if (building.count == MAX_PIECES) {
                ++tg2v_overflow;
                break;
            }
            Piece *piece = &building.pieces[building.count++];
            piece->actor = current_actor;
            piece->kind = tg2_word(g_ram,0x187C)&255;
            piece->x = px;
            piece->y = py + (int16_t)tg2_word(g_ram, 0x2452) - 128;
            piece->size = sz & 15;
            piece->attr = (((attr ^ (pa & 0x1800)) + (pa & 2047)) | tg2_word(g_ram, 0x234E)) & 65535;
            if (g_ram[0x22E8])
                piece->attr |= 0x8000;
        }
    }
    return 0;
}
void tg2v_select_scene(const GVDP *v) {
    tg2v_matched_pieces = tg2v_margin_pieces = 0;
    tg2v_shown = NULL;
    unsigned base = (v->reg[5] & 127) << 9;
    for (unsigned i = 0; i < HISTORY; ++i) {
        Scene *sc = &history[i];
        if (!sc->serial || (tg2v_shown && tg2v_shown->serial > sc->serial))
            continue;
        unsigned k = 0;
        while (k < sc->sat_size && sc->sat[k] == v->vram[(base + k) & 65535])
            ++k;
        if (k == sc->sat_size && k)
            tg2v_shown = sc;
    }
    if (tg2v_shown) memset(((Scene *)tg2v_shown)->sat_piece, 0xFF, sizeof tg2v_shown->sat_piece);
    if (tg2v_shown)
        for (unsigned n = tg2v_shown->count; n > 0; --n) {
            unsigned i=n-1; /* nearest first, like the backward SAT allocator */
            const Piece *p = &tg2v_shown->pieces[i];
            if (p->x < 0 || p->x + ((((p->size >> 2) & 3) + 1) * 8) > 256)
                ++tg2v_margin_pieces;
            for (unsigned k = 0; k < tg2v_shown->sat_size; k += 8) {
                const unsigned char *q = tg2v_shown->sat + k;
                if (tg2v_shown->sat_piece[k/8]<0 && ((tg2_word(q, 0) & 511) - 128) == (unsigned)p->y &&
                    ((tg2_word(q, 6) & 511) - 128) == (unsigned)p->x && (q[2] & 15) == p->size &&
                    tg2_word(q, 4) == p->attr) {
                    ((Scene *)tg2v_shown)->sat_piece[k / 8] = i;
                    ++tg2v_matched_pieces;
                    break;
                }
            }
        }
}
/* Replay just the host sprite ownership from the immutable row. The real
 * evaluator already ran once in the engine seam; this changes no VDP flags. */
static unsigned sprite_texel(const GVDP *v, unsigned attr, unsigned size, int dx, int dy) {
    int w=(((size>>2)&3)+1)*8,h=((size&3)+1)*8;
    int sx=attr&0x800?w-1-dx:dx,sy=attr&0x1000?h-1-dy:dy;
    unsigned tile=((attr&2047)+(sx/8)*(h/8)+sy/8)&2047;
    unsigned b=v->vram[(tile*32+(sy&7)*4+(sx&7)/2)&65535];
    return sx&1?b&15:b>>4;
}
int tg2v_promoted_sat(int link) {
    return tg2v_shown && link<64 && tg2v_shown->sat_piece[link]>=0 &&
        tg2_actors_promoted(tg2v_shown->pieces[tg2v_shown->sat_piece[link]].actor);
}
void tg2v_prepare_actors(const GVDP *v) {
    tg2_actors_prepare(v,tg2v_shown?&tg2v_shown->actors:NULL);
    if (!tg2v_shown) return;
    for(unsigned j=0;j<tg2v_shown->count;++j) tg2_actors_note_native(j,tg2v_shown->pieces[j].kind);
    for(unsigned i=0;i<tg2v_shown->actors.count;++i) {
        unsigned count=0,inside=0,matched=0,bad_position=0;
        const Tg2Actor *a=&tg2v_shown->actors.actors[i];
        for(unsigned j=0;j<tg2v_shown->count;++j) if(tg2v_shown->pieces[j].actor==(int)i) {
            const Piece *p=&tg2v_shown->pieces[j];++count;
            int found=0;
            for(unsigned k=0;k<a->guest_count;++k) {
                const Tg2ModelPiece *q=&tg2v_shown->actors.pieces[a->guest_first+k];
                if(p->attr==q->attr && p->size==q->size && p->x==a->gx+q->dx && p->y==a->gy+q->dy) {found=1;break;}
            }
            if(!found)++bad_position;
            int w=(((p->size>>2)&3)+1)*8;
            if(p->x<256 && p->x+w>0) {
                ++inside;
                for(unsigned k=0;k<64;++k) if(tg2v_shown->sat_piece[k]==(int)j) {++matched;break;}
            }
        }
        tg2_actors_note_sat(i,count,inside,matched,bad_position);
    }
}
void tg2v_actor_native_row(const GVDP *v,int line,int nw,const uint32_t *native,
                              uint32_t *out,GVDPRasterRow *free_row,unsigned short *tg2v_owners) {
    *free_row=*tg2v_filter_layers;
    if(!free_row->display) {memset(tg2v_owners,0,nw*sizeof *tg2v_owners);memcpy(out,native,nw*sizeof *out);return;}
    unsigned char all[256]={0},all_hi[256]={0},kept[256]={0},hi[256]={0};
    int owner[256]; for(int x=0;x<nw;++x)owner[x]=-1;
    memset(tg2v_owners,0,nw*sizeof *tg2v_owners);
    unsigned sat=(v->reg[5]&127)<<9;
    int link=0,on_line=0,budget=tg2v_filter_layers->width;
    for(int n=0;n<64;++n) {
        unsigned e=sat+link*8,sz=v->vram[(e+2)&65535],attr=tg2_word(v->vram,e+4);
        int y=(tg2_word(v->vram,e)&1023)-128,h=((sz&3)+1)*8,w=(((sz>>2)&3)+1)*8;
        int next=v->vram[(e+3)&65535]&127;
        if(line>=y && line<y+h) {
            if(++on_line>16)break;
            int xword=tg2_word(v->vram,e+6)&1023;
            if(!xword && on_line>1)break;
            int removed=tg2v_promoted_sat(link);
            for(int dx=0;dx<w;++dx) {
                int x=xword-128+dx;
                if(x<0||x>=nw)continue;
                unsigned c=sprite_texel(v,attr,sz,dx,line-y);
                if(!c)continue;
                c|=(attr>>9)&48;
                if(!all[x]){all[x]=c;all_hi[x]=!!(attr&0x8000);owner[x]=removed;}
                if(!removed && !kept[x]) {
                    kept[x]=c;hi[x]=!!(attr&0x8000);
                    int piece=tg2v_shown && link<64?tg2v_shown->sat_piece[link]:-1;
                    tg2v_owners[x]=piece<0?65535:piece+1;
                }
            }
            budget-=w;if(budget<=0)break;
        }
        if(!next)break;
        link=next;
    }
    int offset=((int)free_row->width-nw)/2;
    /* A full no-removal reconstruction is checked against the engine's own
     * captured sprite channels, independently of colour/palette equality. */
#ifdef GEN_ENABLE_TRACE
    if(tg2v_actor_audit<0)tg2v_actor_audit=getenv("TG2_ACTOR_AUDIT")!=NULL;
    if(tg2v_actor_audit) {
        ++tg2v_actor_rows;
        for(int x=0;x<nw;++x) {
            int k=x+offset;
            if(!!all[x]!=!!tg2v_filter_layers->opaque[k] || (all[x] && (all[x]!=tg2v_filter_layers->sprite[k] || all_hi[x]!=tg2v_filter_layers->high[k]))) ++tg2v_actor_row_mismatches;
        }
    }
#endif
    for(int x=0;x<nw;++x) if(owner[x]==1) {
        int k=x+offset;
        free_row->sprite[k]=kept[x];free_row->opaque[k]=!!kept[x];free_row->high[k]=hi[x];
        free_row->shadow_op[k]=free_row->hilite_op[k]=0;
    }
    uint8_t indices[GVDP_MAX_WIDTH];
    gvdp_compose_captured(free_row,indices);
    for(int x=0;x<nw;++x) {
        int k=x+offset;
        out[x]=owner[x]==1?genesis_dac_cram_to_argb(v->cram[indices[k]&63],indices[k]>>6):native[x];
    }
}
