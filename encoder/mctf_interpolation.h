/* Exact 8-bit single-axis specialization of separable MCTF interpolation. */
#ifndef X264_MCTF_INTERPOLATION_H
#define X264_MCTF_INTERPOLATION_H

#include <stdint.h>
#include <string.h>
#include "mctf_neon.h"

#ifndef X264_MCTF_PRIOR_CONTROL
#define X264_MCTF_PRIOR_CONTROL 0
#endif
#if X264_MCTF_PRIOR_CONTROL
#if !X264_MCTF_HAVE_NEON || !X264_MCTF_NEON_INTERPOLATION || X264_MCTF_ROW_REUSE
#error Prior rolling control requires NEON interpolation without cross-block reuse
#endif
#include "mctf_prior_control.h"
#endif

#ifndef X264_MCTF_AXIS_SPECIALIZATION
#define X264_MCTF_AXIS_SPECIALIZATION 1
#endif

static inline void x264_mctf_interpolate_axis_strides( uint8_t *dst, int dst_stride,
                                                      const uint8_t *src, int src_stride,
                                                      int width, int height,
                                                      const int32_t filter[8], int vertical )
{
#if X264_MCTF_HAVE_NEON && X264_MCTF_NEON_INTERPOLATION
    x264_mctf_interpolate_axis_neon( dst, dst_stride, src, src_stride, width, height, filter, vertical );
    return;
#endif
    const int step = vertical ? src_stride : 1;
    for( int y = 0; y < height; y++ )
        for( int x = 0; x < width; x++ )
        {
            const uint8_t *p = src + y * src_stride + x - 2 * step;
            int sum = filter[1] * p[0]
                    + filter[2] * p[step]
                    + filter[3] * p[2 * step]
                    + filter[4] * p[3 * step]
                    + filter[5] * p[4 * step]
                    + filter[6] * p[5 * step];
            /* The omitted identity pass contributes exactly a factor of 64:
             * (64*sum + 2048) >> 12 == (sum + 32) >> 6, including negatives.
             * No intermediate clipping or rounding is introduced. */
            sum = (sum + 32) >> 6;
            dst[y * dst_stride + x] = sum < 0 ? 0 : sum > 255 ? 255 : sum;
        }
}

static inline void x264_mctf_interpolate_axis( uint8_t *dst, const uint8_t *src,
                                              int stride, int width, int height,
                                              const int32_t filter[8], int vertical )
{
    x264_mctf_interpolate_axis_strides( dst, stride, src, stride, width, height, filter, vertical );
}

/* src points to the integer motion-displaced origin in the padded reference;
 * dst may be a compact tile. Both passes retain the original unrounded sums. */
static inline void x264_mctf_interpolate_tile( uint8_t *dst, int dst_stride,
                                              const uint8_t *src, int src_stride,
                                              int width, int height,
                                              const int32_t x_filter[8], const int32_t y_filter[8],
                                              int x_integer, int y_integer )
{
    if( x_integer && y_integer )
    {
        for( int y = 0; y < height; y++ )
            memcpy( dst + y * dst_stride, src + y * src_stride, width );
        return;
    }
    if( X264_MCTF_AXIS_SPECIALIZATION && (x_integer || y_integer) )
    {
        x264_mctf_interpolate_axis_strides( dst, dst_stride, src, src_stride, width, height,
                                           x_integer ? y_filter : x_filter, x_integer );
        return;
    }
#if X264_MCTF_HAVE_NEON && X264_MCTF_NEON_INTERPOLATION
#if X264_MCTF_PRIOR_CONTROL
    x264_mctf_interpolate_prior_control( dst, dst_stride, src, src_stride, width, height, x_filter, y_filter );
#else
    x264_mctf_interpolate_both_neon( dst, dst_stride, src, src_stride, width, height, x_filter, y_filter );
#endif
    return;
#endif
    int32_t temp[23][16];
    for( int y = 1; y < height + 7; y++ )
        for( int x = 0; x < width; x++ )
        {
            const uint8_t *p = src + (y - 3) * src_stride + x - 3;
            temp[y][x] = x_filter[1] * p[1] + x_filter[2] * p[2]
                       + x_filter[3] * p[3] + x_filter[4] * p[4]
                       + x_filter[5] * p[5] + x_filter[6] * p[6];
        }
    for( int y = 0; y < height; y++ )
        for( int x = 0; x < width; x++ )
        {
            int sum = y_filter[1] * temp[y + 1][x] + y_filter[2] * temp[y + 2][x]
                    + y_filter[3] * temp[y + 3][x] + y_filter[4] * temp[y + 4][x]
                    + y_filter[5] * temp[y + 5][x] + y_filter[6] * temp[y + 6][x];
            sum = (sum + 2048) >> 12;
            dst[y * dst_stride + x] = sum < 0 ? 0 : sum > 255 ? 255 : sum;
        }
}

#endif
