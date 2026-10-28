#include <assert.h>
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "mctf_interpolation.h"
#include "mctf_uniform8.h"
static uint32_t rng=0x78b4c237;
static uint32_t next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
int main(void)
{
    uint64_t pixels=0,tiles=0;
    for(int trial=0;trial<12000;trial++)
    {
        uint8_t source[16*41+16],old[sizeof(source)],out[sizeof(source)],exact[sizeof(source)];
        uint8_t pred[10][256];int32_t weights[10][256];const int32_t *tables[10];int confidence[10];
        int refs=trial%11,width=1+(trial/11)%16,height=1+(trial/176)%16;
        int offset=1+trial%7,stride=41;
        for(size_t i=0;i<sizeof(source);i++)source[i]=next();
        for(int j=0;j<10;j++)
        {
            tables[j]=weights[j];
            for(int i=0;i<256;i++)weights[j][i]=next()%750000;
            for(int i=0;i<256;i++)pred[j][i]=next();
            static const int c[]={-1,255,0,1,127,254};
            confidence[j]=trial%3==0?c[(trial+j)%6]:trial%2?-1:255;
        }
        memset(old,0xa7,sizeof(old));memset(out,0xa7,sizeof(out));memset(exact,0xa7,sizeof(exact));
        assert(x264_mctf_neon_weights_safe(tables,refs));
        x264_mctf_filter_tile_neon(old+offset,stride,source+offset,pred,width,height,refs,tables,confidence);
        x264_mctf_filter_tile_uniform8_dispatch(out+offset,stride,source+offset,pred,width,height,refs,tables,confidence);
        for(int y=0;y<height;y++)for(int x=0;x<width;x++)
        {
            int original=source[offset+y*stride+x];uint64_t n=original*65536u,d=65536u;
            for(int j=0;j<refs;j++)
            {
                int v=pred[j][y*16+x],delta=v-original;uint64_t w=weights[j][delta<0?-delta:delta];
                if(confidence[j]>=0)w=(w*confidence[j]+127)/255;
                n+=w*v;d+=w;
            }
            exact[offset+y*stride+x]=(n+d/2)/d;pixels++;
        }
        assert(!memcmp(old,exact,sizeof(old)));assert(!memcmp(out,exact,sizeof(out)));
        /* In-place source/destination is supported for the uniform branch. */
        int uniform=1;for(int j=0;j<refs;j++)uniform&=confidence[j]<0||confidence[j]==255;
        if(uniform)
        {
            memcpy(out,source,sizeof(out));
            x264_mctf_filter_tile_uniform8_dispatch(out+offset,stride,out+offset,pred,width,height,refs,tables,confidence);
            for(int y=0;y<height;y++)for(int x=0;x<width;x++)
                assert(out[offset+y*stride+x]==exact[offset+y*stride+x]);
        }
        tiles++;
    }
    /* Exercise the exact maximum allowed denominator, extreme numerators,
     * vector/tail boundaries and adjacent denominators. Random tables above
     * do not concentrate on these quotient-correction boundaries. */
    uint64_t boundary_pixels=0;
    for(int refs=1;refs<=10;refs++)for(int gap=0;gap<4;gap++)
    for(int original=0;original<=255;original+=255)
    {
        uint8_t source[16*41],old[sizeof(source)],out[sizeof(source)];
        uint8_t pred[10][256];int32_t weights[10][256];const int32_t *tables[10];int confidence[10];
        int total=INT32_MAX/256-65536-gap;
        for(int j=0;j<refs;j++)
        {
            int weight=total/refs+(j<total%refs);tables[j]=weights[j];confidence[j]=j%2?-1:255;
            for(int d=0;d<256;d++)weights[j][d]=weight;
            for(int p=0;p<256;p++)pred[j][p]=p;
        }
        memset(source,original,sizeof(source));assert(x264_mctf_neon_weights_safe(tables,refs));
        for(int width=7;width<=16;width++)
        {
            memset(old,0xa7,sizeof(old));memset(out,0xa7,sizeof(out));
            x264_mctf_filter_tile_neon(old,41,source,pred,width,16,refs,tables,confidence);
            x264_mctf_filter_tile_uniform8_dispatch(out,41,source,pred,width,16,refs,tables,confidence);
            assert(!memcmp(old,out,sizeof(old)));
            for(int y=0;y<16;y++)for(int x=0;x<width;x++)
            {
                uint64_t numerator=(uint64_t)original*65536+(uint64_t)total*(y*16+x);
                uint64_t denominator=65536+total;
                assert(out[y*41+x]==(numerator+denominator/2)/denominator);
                boundary_pixels++;
            }
        }
    }
    printf("{\"passed\":true,\"tiles\":%"PRIu64",\"scalar_pixel_comparisons\":%"PRIu64",\"boundary_pixel_comparisons\":%"PRIu64",\"maximum_safe_denominator\":%d,\"widths\":[1,16],\"heights\":[1,16],\"reference_counts\":[0,10],\"stride\":41,\"unaligned\":true,\"nonuniform_fallback\":true,\"guard_canaries\":true,\"in_place\":true}\n",tiles,pixels,boundary_pixels,INT32_MAX/256);
}
