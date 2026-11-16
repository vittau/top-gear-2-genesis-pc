/* Approved Task 42 OKLCH rule. Classify the ROM base once per descriptor;
 * transform the presented row's live CRAM, including delayed 60-fps rows.
 * Coverage is layer ownership, never a framebuffer colour-key replacement. */
#include "tg2_video_internal.h"
#include "tg2_sky.h"

typedef struct { double L, a, b; } Lab;
typedef struct { double top, kt, horizon, kh; const char *name; } Rule;
static const Rule rules[] = {
    {-.07,.90,.10,.70,"night"}, {-.06,.90,.06,.70,"nightrain"},
    {-.035,1,0,1,"fog"}, {-.07,.90,.06,.60,"snow"},
    {-.09,.85,.05,.70,"rain"}, {-.07,1,.05,.80,"overcast"},
    {-.10,1.25,.07,.60,"day"}
};
static int enabled, kind, active, split, frame_width;
static unsigned descriptor, base_sky;
static unsigned char masks[224][4096];
unsigned char *tg2_sky_mask;
static unsigned short live[224], atlas[224];
static unsigned char valid[224];
static int band_top[2], band_bottom[2];
static unsigned painted;
static double linear(double c) { return c <= .04045 ? c/12.92 : pow((c+.055)/1.055,2.4); }
static Lab to_lab(uint32_t rgb) {
    double r=linear(((rgb>>16)&255)/255.),g=linear(((rgb>>8)&255)/255.),b=linear((rgb&255)/255.);
    double l=cbrt(.4122214708*r+.5363325363*g+.0514459929*b);
    double m=cbrt(.2119034982*r+.6806995451*g+.1073969566*b);
    double s=cbrt(.0883024619*r+.2817188376*g+.6299787005*b);
    return (Lab){.2104542553*l+.7936177850*m-.0040720468*s,
        1.9779984951*l-2.4285922050*m+.4505937099*s,
        .0259040371*l+.7827717662*m-.8086757660*s};
}
static void lab_rgb(Lab c, double rgb[3]) {
    double l=c.L+.3963377774*c.a+.2158037573*c.b;
    double m=c.L-.1055613458*c.a-.0638541728*c.b;
    double s=c.L-.0894841775*c.a-1.2914855480*c.b;
    l=l*l*l;m=m*m*m;s=s*s*s;
    rgb[0]=4.0767416621*l-3.3077115913*m+.2309699292*s;
    rgb[1]=-1.2684380046*l+2.6097574011*m-.3413193965*s;
    rgb[2]=-.0041960863*l-.7034186147*m+1.7076147010*s;
}
/* Match the approved references with a 1e-4 linear-sRGB numerical tolerance.
 * It matters near black: strict zero changes the night top by four codes. */
static int in_gamut(const double rgb[3]) {
    return rgb[0]>=-1e-4 && rgb[1]>=-1e-4 && rgb[2]>=-1e-4 &&
           rgb[0]<=1.0001 && rgb[1]<=1.0001 && rgb[2]<=1.0001;
}
static Lab stop(Lab c, double dl, double k) {
    c.L=fmax(0,fmin(.97,c.L+dl));c.a*=k;c.b*=k;
    double rgb[3];lab_rgb(c,rgb);
    for(int n=0;!in_gamut(rgb) && n<1024;++n) {c.a*=.97;c.b*=.97;lab_rgb(c,rgb);}
    return c;
}
static double srgb(double c) { c=fmax(0,fmin(1,c));return c<=.0031308?12.92*c:1.055*pow(c,1/2.4)-.055; }
static uint32_t colour(Lab c) {
    double rgb[3];lab_rgb(c,rgb);uint32_t out=0xFF000000;
    for(int k=0;k<3;++k) out|=(uint32_t)lround(srgb(rgb[k])*255)<<(16-8*k);
    return out;
}
static uint32_t ramp(unsigned cram, double t) {
    Lab base=to_lab(genesis_dac_cram_to_argb(cram,0));
    const Rule *r=&rules[kind];Lab a,b;
    if(t<=.6) {a=stop(base,r->top,r->kt);b=base;t=fmax(0,t)/.6;}
    else {a=base;b=stop(base,r->horizon,r->kh);t=fmin(1,(t-.6)/.4);}
    return colour((Lab){a.L+(b.L-a.L)*t,a.a+(b.a-a.a)*t,a.b+(b.b-a.b)*t});
}
void tg2_video_set_gradient_skies(int on) { enabled=on!=0;tg2_sky_mask=NULL; }
int tg2_sky_enabled(void) { return enabled; }
static int race(const GVDP *v) {
    unsigned op=tg2_ram16(0xF9FE);
    return !(v->reg[12]&15) && v->reg[16]==0x11 &&
        ((v->reg[2]&56)<<10)==0xC000 && ((v->reg[4]&7)<<13)==0xE000 &&
        (op==0x2C9D || op==0x601E || op==0x6042);
}
void tg2_sky_begin_row(const GVDP *v,int line,int width) {
    tg2_sky_mask=NULL;
    if(!enabled || tg2v_reference_pass || line<0 || line>=224 || width>4096)return;
    if(!line) {
        memset(valid,0,sizeof valid);painted=0;active=race(v);split=tg2_ram16(0x189E)!=0;
        frame_width=width;
        unsigned d=tg2_ram32(0x241C);
        if(active && d && d<0xFFF80 && d!=descriptor) {
            descriptor=d;
            unsigned flags=g_rom[d+3],p=tg2_mem32(d+0x6C);
            unsigned base=p<0xFFFE0?tg2_mem16(p+30):0;
            base_sky=base;
            Lab c=to_lab(genesis_dac_cram_to_argb(base,0));
            int night=(base&0xEEE)==0x200;
            kind=night?((flags&32)?1:0):(flags&8)?2:
                 (flags&32)?((flags&64)?3:4):hypot(c.a,c.b)<.03?5:6;
        }
    }
    if(!active || !race(v) || !(v->reg[1]&64))return;
    /* A completed fade hides the whole picture. Do not lift its black with
     * a positive horizon offset; intermediate palette states use the rule. */
    if (!(v->cram[63]&0xEEE)) {
        unsigned visible=0;
        for (int i=0;i<64;++i) visible|=v->cram[i]&0xEEE;
        if (!visible) return;
    }
    tg2_sky_mask=masks[line];memset(tg2_sky_mask,0,width);
    valid[line]=1;live[line]=v->cram[63];atlas[line]=(line+v->vsram[1])&511;
}
int tg2_sky_source(unsigned index,int py,unsigned backdrop) {
    return py>=448 && (index?index==63:backdrop==63);
}
/* The engine captured the exact priority inputs already; no second sprite
 * evaluation and no equality-based removal of weather, cars or silhouettes. */
void tg2_sky_native(const GVDP *v,int line,const uint32_t *native,
                    const uint32_t *out,int nw,int width) {
    if(!tg2_sky_mask || !tg2v_filter_layers || nw!=256)return;
    const GVDPRasterRow *r=tg2v_filter_layers;
    int origin=(width-nw)/2,offset=((int)r->width-nw)/2;
    uint32_t sky=genesis_dac_cram_to_argb(v->cram[63],0);
    for(int x=0;x<nw;++x) {
        int k=x+offset;unsigned a=r->plane_a[k],b=r->plane_b[k];
        int sp=r->opaque[k],sh=sp&&r->high[k];
        int bw=!sh && (a&0xC0)!=0xC0 &&
            ((b&0xC0)==0xC0 || (!sp && !(a&0x40)));
        int source=bw && tg2_sky_source((b&0x40)?b&63:0,atlas[line],r->backdrop);
        /* HUD relocation has explicitly reconstructed a vacated pixel. Its
         * coverage is written in tg2v_hud_row, after the native mask below. */
        if(out[origin+x]==native[x]) tg2_sky_mask[origin+x]=source && out[origin+x]==sky &&
            !r->shadow_op[k] && !r->hilite_op[k] && !tg2v_window_at(v,line,x);
    }
}
int tg2_sky_pixel(int line,int x) {
    return enabled && active && line>=0 && line<224 && valid[line] &&
        x>=0 && x<frame_width && masks[line][x];
}
void tg2_sky_paint(uint32_t *pixels,int stride,int width,int scale,int first) {
    if(!enabled || !active || width!=frame_width*scale)return;
    for(int half=0;half<(split?2:1);++half) {
        int lo=split?half*112:first,hi=split?(half+1)*112:208;
        int top=lo,bottom=lo,seen=0;
        if(split && !half && tg2v_hide_overscan && tg2v_crop_top_rows==8) top=8;
        /* Only the leading sky run belongs to this camera. A later 448
         * at the split boundary can be the next camera's raster setup. */
        int scan=lo<CROP_TOP?CROP_TOP:lo;
        for(int y=scan;y<hi;++y) if(valid[y]) {
            if(atlas[y]==448) {seen=1;bottom=y;}
            else break;
        }
        /* The short split-screen camera can start inside the panorama:
         * all remaining sky holes are already at/below the clipped horizon.
         * Apply the horizon stop there rather than inventing extra sky. */
        if(!seen || bottom<top) bottom=top;
        band_top[half]=top;band_bottom[half]=bottom;
        for(int y=lo;y<hi;++y) if(valid[y] && memchr(masks[y],1,(size_t)frame_width)) {
            for(int j=0;j<scale;++j) {
                double position=y+(double)j/scale;
                uint32_t c=ramp(live[y],bottom>top?(position-top)/(bottom-top):1);
                uint32_t *row=pixels+(size_t)(y*scale+j)*stride;
                for(int x=0;x<width;++x) if(masks[y][x/scale]) {row[x]=c;++painted;}
            }
        }
    }
}
int tg2_sky_json(char *out,int size) {
    return snprintf(out,size,"\"sky_base\":%u,\"sky_live\":%u,\"sky_stops\":[%u,%u,%u],\"gradient_skies\":%d,\"sky_class\":\"%s\",\"sky_descriptor\":%u,\"sky_pixels\":%u,\"sky_bands\":[[%d,%d],[%d,%d]]",
        base_sky,live[band_top[0]],ramp(base_sky,0)&0xFFFFFF,ramp(base_sky,.6)&0xFFFFFF,ramp(base_sky,1)&0xFFFFFF,
        enabled,rules[kind].name,descriptor,painted,band_top[0],band_bottom[0],band_top[1],band_bottom[1]);
}

int tg2_sky_rows_json(char *out,int size) {
    int n=snprintf(out,size,",\"sky_rows\":[");
    for(int y=0;y<224 && n<size;++y) {
        unsigned count=0;
        if(enabled && active && valid[y])
            for(int x=0;x<frame_width;++x) count+=masks[y][x]!=0;
        n+=snprintf(out+n,size-n,"%s[%d,%u,%u]",y?",":"",
            enabled && active && valid[y]?atlas[y]:-1,live[y],count);
    }
    if(n<size)n+=snprintf(out+n,size-n,"]");
    return n;
}
