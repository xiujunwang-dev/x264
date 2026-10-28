/* Research MCTF extension for the pinned, otherwise upstream x264 encoder.
 * Author: Xiujun Wang. GPL-2.0-or-later, like the surrounding x264 source.
 * Luma-only; original low-resolution lookahead samples remain unchanged. */
#ifndef MCTF_X264_H
#define MCTF_X264_H
#define X264_MCTF_NEON_INTERPOLATION 1
#define X264_MCTF_NEON_NORMALIZE 1
#define X264_MCTF_PRIOR_CONTROL 1
#include "mctf_interpolation.h"
#include "mctf_uniform8.h"
#include "mctf_envelope.h"

static const int32_t mctf_phase[4][8]={
    {0,0,0,64,0,0,0,0}, {0,2,-9,57,19,-7,2,0},
    {0,1,-7,38,38,-7,1,0}, {0,2,-7,19,57,-9,2,0}};

static void build_mctf_weight_table(int32_t weights[3][1024], double strength,
        int count, int range, int qp, const int32_t offsets[10], int chroma)
{
    static const double relative[3][3]={{.85,.57,.41},{1.13,.97,.81},{.30,.30,.30}};
    int present[3]={0}, pos=0, neg=0;
    memset(weights,0,3*1024*sizeof(int32_t));
    for (int j=0;j<count;j++)
    { pos|=offsets[j]>0;neg|=offsets[j]<0;present[abs(offsets[j])-1]++; }
    int directions=pos&&neg?2:1;
    int row=directions==2&&count>=2*range?0:count>=range?1:2;
    int sigma=(qp-10)*(qp-10)*9;
    assert(!chroma && sigma>0);
    for (int k=0;k<range;k++)
    {
        double available=X264_MIN(1.,(double)present[k]/directions);
        double amplitude=strength*.4*relative[row][k]*available*65536.;
        for (int x=0;x<256;x++)
            weights[k][x]=(int32_t)(exp(-(double)x*x*16/(2.*sigma))*amplitude+.5);
    }
}

static unsigned mctf_extrema_plan(int count,const int32_t *const tables[10],int tau)
{
    int order[10];int64_t moment[10],maximum[10],m=0,w=0,p=0;
    for(int j=0;j<count;j++)
    {
        moment[j]=maximum[j]=0;
        for(int x=0;x<256;x++)
        { if((int64_t)tables[j][x]*x>moment[j])moment[j]=(int64_t)tables[j][x]*x;
          if(tables[j][x]>maximum[j])maximum[j]=tables[j][x]; }
        int pos=j;
        while(pos>0&&moment[order[pos-1]]<moment[j]){order[pos]=order[pos-1];pos--;}
        order[pos]=j;m+=moment[j];w+=maximum[j];
    }
    unsigned mask=0;
    for(int k=0;k<count;k++)
    {
        int64_t a=X264_MAX(p-tau*65536LL,0);
        if(65536*m+a*w<=tau*65536LL*65536)return mask;
        int j=order[k];mask|=1U<<j;p+=moment[j];m-=moment[j];w-=maximum[j];
    }
    return mask;
}

#ifdef X264_MCTF_CAPTURE
#include "capture.h"
#endif

/* Dedicated lowres fields keep temporal filtering independent of the
 * encoder's bidirectional lookahead caches. In particular, stock lookahead
 * cost evaluation does not support a future-only I-frame search. */
static void mctf_motion(x264_t *h,x264_mb_analysis_t *a,x264_frame_t *anchor,
        x264_frame_t *reference,int16_t (*motion)[2])
{
    int w=h->mb.i_mb_width,ht=h->mb.i_mb_height,stride=anchor->i_stride_lowres;
    for(int y=ht-1;y>=0;y--)for(int x=w-1;x>=0;x--)
    {
        int mb=y*w+x,offset=8*(x+y*stride),limit=2*h->param.analyse.i_mv_range;
        h->mb.i_mb_x=x;h->mb.i_mb_y=y;
        h->mb.mv_min_spel[0]=X264_MAX(4*(-8*x-12),-limit);
        h->mb.mv_max_spel[0]=X264_MIN(4*(8*(w-x-1)+12),limit-1);
        h->mb.mv_min_spel[1]=X264_MAX(4*(-8*y-12),-limit);
        h->mb.mv_max_spel[1]=X264_MIN(4*(8*(ht-y-1)+12),limit-1);
        for(int k=0;k<2;k++)
        {h->mb.mv_limit_fpel[0][k]=h->mb.mv_min_spel[k]>>2;
         h->mb.mv_limit_fpel[1][k]=h->mb.mv_max_spel[k]>>2;}
        x264_me_t m={0};
        m.i_pixel=PIXEL_8x8;m.p_cost_mv=a->p_cost_mv;m.i_stride[0]=stride;
        m.weight=x264_weight_none;m.p_fenc[0]=h->mb.pic.fenc_buf;
        h->mc.copy[PIXEL_8x8](m.p_fenc[0],FENC_STRIDE,anchor->lowres[0]+offset,stride,8);
        for(int k=0;k<4;k++)m.p_fref[k]=reference->lowres[k]+offset;
        m.p_fref_w=m.p_fref[0];
        ALIGNED_ARRAY_8(int16_t,mvc,[4],[2]);memset(mvc,0,sizeof(mvc));
        int n=0;
        if(x+1<w){mvc[n][0]=motion[mb+1][0];mvc[n++][1]=motion[mb+1][1];}
        if(y+1<ht)
        {
            mvc[n][0]=motion[mb+w][0];mvc[n++][1]=motion[mb+w][1];
            if(x>0){mvc[n][0]=motion[mb+w-1][0];mvc[n++][1]=motion[mb+w-1][1];}
            if(x+1<w){mvc[n][0]=motion[mb+w+1][0];mvc[n++][1]=motion[mb+w+1][1];}
        }
        if(n<=1){m.mvp[0]=mvc[0][0];m.mvp[1]=mvc[0][1];}
        else x264_median_mv(m.mvp,mvc[0],mvc[1],mvc[2]);
        if(m.mvp[0]||m.mvp[1]||h->pixf.mbcmp[PIXEL_8x8](m.p_fenc[0],FENC_STRIDE,m.p_fref[0],stride)>=64)
            x264_me_search(h,&m,mvc,n);
        motion[mb][0]=m.mv[0];motion[mb][1]=m.mv[1];
    }
}

static void mctf_filter_frame(x264_t *h,x264_mb_analysis_t *a,
        x264_frame_t **frames,int b,int last)
{
    x264_frame_t *frame=frames[b],*refs[10];
    int range=x264_clip3(h->param.mctf.range+(IS_X264_TYPE_I(frame->i_type)?1:0),1,3);
    int count=0;int32_t offsets[10];int16_t (*mv[10])[2];
    for(int j=X264_MAX(0,b-range);j<=X264_MIN(last,b+range);j++)
    {
        if(j==b||!frames[j]||frames[j]->i_frame!=frame->i_frame+j-b)continue;
        refs[count]=frames[j];offsets[count++]=j-b;
    }
    if(!count)return;
    int qp=h->param.mctf.qp;
    double strength=IS_X264_TYPE_I(frame->i_type)?1.05:.63;
    int32_t weights[3][1024];const int32_t *tables[10];
    build_mctf_weight_table(weights,strength,count,range,qp,offsets,0);
    int64_t summax=65536;
    for(int j=0;j<count;j++)
    {
        tables[j]=weights[abs(offsets[j])-1];int max=0;
        for(int x=0;x<256;x++){assert(tables[j][x]>=0);if(tables[j][x]>max)max=tables[j][x];}
        summax+=max;
    }
    assert(summax<=INT32_MAX/256);
    unsigned mask=(1U<<count)-1;
    int method=h->param.mctf.method,tau=h->param.mctf.tau;
    if(method==2)mask=mctf_extrema_plan(count,tables,tau);
    if(method==3)mask=mctf_support_plan(count,tables,tau,1);
    if(method==4)mask=mctf_envelope_plan(count,tables,tau);
    int16_t (*motion)[2]=x264_malloc(count*h->mb.i_mb_count*2*sizeof(int16_t));
    if(!motion){x264_log(h,X264_LOG_WARNING,"MCTF motion allocation failed; retaining source\n");return;}
    for(int j=0;j<count;j++)
    {
        mv[j]=motion+j*h->mb.i_mb_count;
        if(!(mask&(1U<<j)))continue;
        mctf_motion(h,a,frame,refs[j],mv[j]);
    }
    const int stride=frame->i_stride[0];
    /* Copy coding padding and retain stock x264's valid input border. */
    for(int y=-PADV;y<frame->i_lines[0]+PADV;y++)
        memcpy(frame->plane_dnr[0]+y*stride-PADH_ALIGN,
               frame->orig_plane[0]+y*stride-PADH_ALIGN,stride);
    for(int y=0;y<h->param.i_height;y+=16)for(int x=0;x<h->param.i_width;x+=16)
    {
        int width=X264_MIN(16,h->param.i_width-x),height=X264_MIN(16,h->param.i_height-y);
        int mb=(y/16)*h->mb.i_mb_stride+x/16,n=0;
        uint8_t prediction[10][256];const int32_t *selected[10];int confidence[10];
        for(int j=0;j<count;j++)if(mask&(1U<<j))
        {
            int dx=mv[j][mb][0]*8,dy=mv[j][mb][1]*8;
            int ix=dx>>4,iy=dy>>4,xf=(dx&15)>>2,yf=(dy&15)>>2;
            assert(x+ix-(xf?2:0)>=-32&&y+iy-(yf?2:0)>=-32);
            assert(x+ix+width+(xf?3:0)<=refs[j]->i_width[0]+32);
            assert(y+iy+height+(yf?3:0)<=refs[j]->i_lines[0]+32);
            const uint8_t *src=(uint8_t *)refs[j]->orig_plane[0]+(y+iy)*refs[j]->i_stride[0]+x+ix;
            x264_mctf_interpolate_tile(prediction[n],16,src,refs[j]->i_stride[0],width,height,
                                      mctf_phase[xf],mctf_phase[yf],!xf,!yf);
            selected[n]=tables[j];confidence[n++]=-1;
        }
        uint8_t *dst=(uint8_t *)frame->plane_dnr[0]+y*stride+x;
        const uint8_t *src=(uint8_t *)frame->orig_plane[0]+y*stride+x;
        if(h->param.mctf.kernel==8)
            x264_mctf_filter_tile_uniform8_dispatch(dst,stride,src,prediction,width,height,n,selected,confidence);
        else x264_mctf_filter_tile_neon(dst,stride,src,prediction,width,height,n,selected,confidence);
    }
#ifdef X264_MCTF_CAPTURE
    assert(method==1);
    capture_mctf_state(h,frame,refs,mv,count,offsets,range,qp,strength,NULL,weights);
#endif
    frame->plane[0]=frame->plane_dnr[0];
    x264_frame_expand_border_mod16(h,frame);
    x264_free(motion);
}

static void mctf_minigop(x264_t *h,int bframes)
{
    if(!h->param.mctf.method)return;
    x264_frame_t *frames[X264_LOOKAHEAD_MAX+2]={0};
    int last=X264_MIN(h->lookahead->next.i_size,X264_LOOKAHEAD_MAX);
    frames[0]=h->lookahead->last_nonb;
    memcpy(frames+1,h->lookahead->next.list,last*sizeof(*frames));
    x264_mb_analysis_t a;lowres_context_init(h,&a);
    for(int b=1;b<=bframes+1;b++)
        if(IS_X264_TYPE_I(frames[b]->i_type)||frames[b]->i_type==X264_TYPE_P)
            mctf_filter_frame(h,&a,frames,b,last);
}
#endif
