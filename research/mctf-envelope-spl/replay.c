/* Fixed-state compensation/fusion replay, independent of encoder evolution.
 * Capture, file I/O, correctness checks and output hashing are outside timing.
 * Planning and every compensation/fusion operation are inside timing. */
#include <assert.h>
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "mctf_interpolation.h"
#include "mctf_support.h"
#include "mctf_uniform8.h"
#include "mctf_envelope.h"

typedef struct {
    int id,w,h,n,cw,ch,mbstride,mbheight,qp,range;
    int32_t weights[3][256],small_weights[3][256],offsets[10];
    uint8_t *anchor,*expected,*planes[10];int16_t *mv[10];
} Snapshot;

static const int32_t phase[4][8]={
    {0,0,0,64,0,0,0,0},{0,2,-9,57,19,-7,2,0},
    {0,1,-7,38,38,-7,1,0},{0,2,-7,19,57,-9,2,0}};
static const char *names[]={"full","moment","joint","support","window_fixed","window_real","window_checked","envelope","full4"};

static void read_exact(FILE *f,void *p,size_t n){if(fread(p,1,n,f)!=n){fprintf(stderr,"short snapshot\n");abort();}}
static void *allocate(size_t n){void *p=malloc(n);if(!p)abort();return p;}
static Snapshot load(const char *path)
{
    Snapshot s={0};FILE *f=fopen(path,"rb");if(!f){perror(path);exit(2);}
    int32_t h[12];read_exact(f,h,sizeof(h));assert(h[0]==0x4d435246 && h[1]==1);
    s.id=h[2];s.w=h[3];s.h=h[4];s.n=h[5];s.cw=h[6];s.ch=h[7];s.mbstride=h[8];s.mbheight=h[9];s.qp=h[10];s.range=h[11];
    assert(s.w>0&&s.h>0&&s.n>0&&s.n<=10&&s.cw>=s.w&&s.ch>=s.h&&s.range<=3);
    read_exact(f,s.weights,sizeof(s.weights));read_exact(f,s.small_weights,sizeof(s.small_weights));
    read_exact(f,s.offsets,s.n*sizeof(int32_t));
    size_t pixels=(size_t)s.w*s.h;
    s.anchor=allocate(pixels);s.expected=allocate(pixels);
    read_exact(f,s.anchor,pixels);read_exact(f,s.expected,pixels);
    for(int j=0;j<s.n;j++)
    {
        int32_t refid;read_exact(f,&refid,sizeof(refid));
        size_t m=(size_t)s.mbstride*s.mbheight*2*sizeof(int16_t);
        s.mv[j]=allocate(m);read_exact(f,s.mv[j],m);
        size_t bytes=(size_t)(s.cw+64)*(s.ch+64);
        s.planes[j]=allocate(bytes);read_exact(f,s.planes[j],bytes);
    }
    assert(fgetc(f)==EOF);fclose(f);return s;
}
static void release(Snapshot *s)
{free(s->anchor);free(s->expected);for(int j=0;j<s->n;j++){free(s->planes[j]);free(s->mv[j]);}}

static unsigned old_plan(int count,const int32_t *const tables[10],int tau)
{
    int order[10];int64_t moment[10],maximum[10],m=0,w=0,p=0;
    for(int j=0;j<count;j++)
    {
        moment[j]=maximum[j]=0;
        for(int x=0;x<256;x++)
        {if((int64_t)tables[j][x]*x>moment[j])moment[j]=(int64_t)tables[j][x]*x;if(tables[j][x]>maximum[j])maximum[j]=tables[j][x];}
        int pos=j;while(pos>0&&moment[order[pos-1]]<moment[j]){order[pos]=order[pos-1];pos--;}order[pos]=j;
        m+=moment[j];w+=maximum[j];
    }
    unsigned mask=0;
    for(int k=0;k<count;k++)
    {
        int64_t a=p>tau*65536LL?p-tau*65536LL:0;
        if(65536*m+a*w<=tau*65536LL*65536)return mask;
        int j=order[k];mask|=1U<<j;p+=moment[j];m-=moment[j];w-=maximum[j];
    }
    return mask;
}

static void compensate(const Snapshot *s,int ref,int x,int y,int width,int height,uint8_t prediction[256])
{
    int mb=(y/16)*s->mbstride+x/16;
    int dx=s->mv[ref][2*mb]*8,dy=s->mv[ref][2*mb+1]*8;
    int ix=dx>>4,iy=dy>>4,xf=(dx&15)>>2,yf=(dy&15)>>2;
    /* Six-tap fractional support is [-2,+3] relative to each sample.
     * The eight-lane implementation uses the same support for full tiles. */
    assert(x+ix-(xf?2:0)>=-32 && y+iy-(yf?2:0)>=-32);
    assert(x+ix+width+(xf?3:0)<=s->cw+32 && y+iy+height+(yf?3:0)<=s->ch+32);
    const uint8_t *p=s->planes[ref]+(y+iy+32)*(s->cw+64)+x+ix+32;
    x264_mctf_interpolate_tile(prediction,16,p,s->cw+64,width,height,phase[xf],phase[yf],!xf,!yf);
}

static uint64_t run_mask(const Snapshot *s,unsigned mask,int small,uint8_t *output,int kernel)
{
    const int32_t *tables[10];int confidence[10];int refs[10],n=0;
    for(int j=0;j<s->n;j++)if(mask&(1U<<j))
    {refs[n]=j;tables[n]=small?s->small_weights[abs(s->offsets[j])-1]:s->weights[abs(s->offsets[j])-1];confidence[n++]=-1;}
    for(int y=0;y<s->h;y+=16)for(int x=0;x<s->w;x+=16)
    {
        int width=s->w-x<16?s->w-x:16,height=s->h-y<16?s->h-y:16;
        uint8_t prediction[10][256];
        for(int j=0;j<n;j++)compensate(s,refs[j],x,y,width,height,prediction[j]);
        if(kernel==8)
            x264_mctf_filter_tile_uniform8_dispatch(output+y*s->w+x,s->w,s->anchor+y*s->w+x,
                                  prediction,width,height,n,tables,confidence);
        else x264_mctf_filter_tile_neon(output+y*s->w+x,s->w,s->anchor+y*s->w+x,
                                  prediction,width,height,n,tables,confidence);
    }
    return (uint64_t)((s->w+15)/16)*((s->h+15)/16)*n;
}

static uint64_t run(const Snapshot *s,int variant,int tau,uint8_t *out,uint8_t *scratch,unsigned *selected)
{
    const int32_t *tables[10];
    int64_t summax=65536;
    for(int j=0;j<s->n;j++)
    {
        tables[j]=s->weights[abs(s->offsets[j])-1];int max=0;
        for(int x=0;x<256;x++){assert(tables[j][x]>=0);if(tables[j][x]>max)max=tables[j][x];}
        summax+=max;
    }
    assert(summax<=INT32_MAX/256);
    unsigned all=(1U<<s->n)-1,mask=all;
    if(variant==1)mask=old_plan(s->n,tables,tau);
    if(variant==2)mask=mctf_support_plan(s->n,tables,tau,0);
    if(variant==3)mask=mctf_support_plan(s->n,tables,tau,1);
    if(variant==7)mask=mctf_envelope_plan(s->n,tables,tau);
    if(variant>=4&&variant<=6)
    {mask=0;for(int j=0;j<s->n;j++)if(abs(s->offsets[j])<=(s->range>1?s->range-1:1))mask|=1U<<j;}
    *selected=mask;
    if(variant!=6)return run_mask(s,mask,variant==5,out,variant==8?4:8);
    uint64_t work=run_mask(s,all,0,scratch,8)+run_mask(s,mask,1,out,8);
    size_t pixels=(size_t)s->w*s->h;
    for(size_t i=0;i<pixels;i++)if(abs(out[i]-scratch[i])>tau)
    {memcpy(out,scratch,pixels);break;}
    return work;
}

static double now(void){struct timespec t;assert(!clock_gettime(CLOCK_MONOTONIC,&t));return t.tv_sec+t.tv_nsec*1e-9;}
static uint64_t hash(const uint8_t *p,size_t n)
{uint64_t h=1469598103934665603ULL;for(size_t i=0;i<n;i++){h^=p[i];h*=1099511628211ULL;}return h;}

int main(int argc,char **argv)
{
    if(argc<4){fprintf(stderr,"usage: replay TAU REPEATS SNAPSHOT...\n");return 2;}
    int tau=atoi(argv[1]),repeats=atoi(argv[2]);assert(tau>=0&&tau<=255&&repeats>=1);
    for(int file=3;file<argc;file++)
    {
        Snapshot s=load(argv[file]);size_t pixels=(size_t)s.w*s.h;
        uint8_t *out=allocate(pixels),*scratch=allocate(pixels);
        uint64_t hashes[9]={0};
        for(int repeat=-1;repeat<repeats;repeat++)for(int position=0;position<9;position++)
        {
            int method=(position+repeat+1+file-3)%9;unsigned mask;
            double start=now();uint64_t work=run(&s,method,tau,out,scratch,&mask);double seconds=now()-start;
            uint64_t output_hash=hash(out,pixels);
            if(repeat==-1)hashes[method]=output_hash;else assert(hashes[method]==output_hash);
            uint64_t sse=0,violations=0;int maximum=0;
            if(repeat==0)
            {
                for(size_t i=0;i<pixels;i++){int e=abs(out[i]-s.expected[i]);sse+=(uint64_t)e*e;violations+=e>tau;if(e>maximum)maximum=e;}
                if(method==0||method==8)assert(!memcmp(out,s.expected,pixels));
                if((method>=1&&method<=3)||method==6||method==7)assert(maximum<=tau);
            }
            printf("{\"snapshot\":\"%s\",\"frame\":%d,\"method\":\"%s\",\"tau\":%d,\"repeat\":%d,\"seconds\":%.12g,\"work\":%"PRIu64",\"selected_mask\":%u,\"output_fnv64\":\"%016"PRIx64"\",\"audit\":%s,\"pixels\":%zu,\"sse\":%"PRIu64",\"max_error\":%d,\"violations\":%"PRIu64"}\n",
                argv[file],s.id,names[method],tau,repeat,seconds,work,mask,output_hash,repeat==0?"true":"false",pixels,sse,maximum,violations);
        }
        free(out);free(scratch);release(&s);
    }
    return 0;
}
