/* Engineering follow-up: exact eight-pixel uniform-weight fusion.
 * Include after mctf_interpolation.h. Caller retains the existing weight-sum
 * safety guard; no approximate quotient or changed LUT is introduced. */
#ifndef MCTF_UNIFORM8_H
#define MCTF_UNIFORM8_H
#if X264_MCTF_HAVE_NEON && X264_MCTF_NEON_NORMALIZE
static inline void x264_mctf_filter_tile_uniform8_neon(
        uint8_t *destination,int stride,const uint8_t *source,
        const uint8_t prediction[][256],int width,int height,int refs,
        const int32_t *const tables[10])
{
    if(!refs)
    {
        if(destination!=source)
            for(int y=0;y<height;y++)memcpy(destination+y*stride,source+y*stride,width);
        return;
    }
    for(int y=0;y<height;y++)
    {
        int x=0;
        for(;x+8<=width;x+=8)
        {
            uint8x8_t original8=vld1_u8(source+y*stride+x);
            uint16x8_t original16=vmovl_u8(original8);
            uint32x4_t original0=vmovl_u16(vget_low_u16(original16));
            uint32x4_t original1=vmovl_u16(vget_high_u16(original16));
            uint32x4_t n0=vshlq_n_u32(original0,16),n1=vshlq_n_u32(original1,16);
            uint32x4_t d0=vdupq_n_u32(65536),d1=d0;
            for(int ref=0;ref<refs;ref++)
            {
                uint8x8_t value8=vld1_u8(prediction[ref]+y*16+x);
                uint8x8_t delta=vabd_u8(value8,original8);
                const int32_t *table=tables[ref];
                uint32_t weights[8]={
                    table[vget_lane_u8(delta,0)],table[vget_lane_u8(delta,1)],
                    table[vget_lane_u8(delta,2)],table[vget_lane_u8(delta,3)],
                    table[vget_lane_u8(delta,4)],table[vget_lane_u8(delta,5)],
                    table[vget_lane_u8(delta,6)],table[vget_lane_u8(delta,7)]};
                uint32x4_t w0=vld1q_u32(weights),w1=vld1q_u32(weights+4);
                uint16x8_t value16=vmovl_u8(value8);
                n0=vmlaq_u32(n0,w0,vmovl_u16(vget_low_u16(value16)));
                n1=vmlaq_u32(n1,w1,vmovl_u16(vget_high_u16(value16)));
                d0=vaddq_u32(d0,w0);d1=vaddq_u32(d1,w1);
            }
            uint32x4_t q0=x264_mctf_neon_divide_exact(vaddq_u32(n0,vshrq_n_u32(d0,1)),d0);
            uint32x4_t q1=x264_mctf_neon_divide_exact(vaddq_u32(n1,vshrq_n_u32(d1,1)),d1);
            uint16x8_t result16=vcombine_u16(vmovn_u32(q0),vmovn_u32(q1));
            vst1_u8(destination+y*stride+x,vmovn_u16(result16));
        }
        for(;x<width;x++)
        {
            uint32_t original=source[y*stride+x],n=original*65536u,d=65536u;
            for(int ref=0;ref<refs;ref++)
            {
                int value=prediction[ref][y*16+x],delta=value-(int)original;
                uint32_t w=tables[ref][delta<0?-delta:delta];n+=w*value;d+=w;
            }
            destination[y*stride+x]=(n+d/2)/d;
        }
    }
}

static inline void x264_mctf_filter_tile_uniform8_dispatch(
        uint8_t *destination,int stride,const uint8_t *source,
        const uint8_t prediction[][256],int width,int height,int refs,
        const int32_t *const tables[10],const int confidence[10])
{
    for(int ref=0;ref<refs;ref++)
        if(confidence[ref]>=0 && confidence[ref]!=255)
        {
            x264_mctf_filter_tile_neon(destination,stride,source,prediction,
                width,height,refs,tables,confidence);return;
        }
    x264_mctf_filter_tile_uniform8_neon(destination,stride,source,prediction,
        width,height,refs,tables);
}
#endif
#endif
