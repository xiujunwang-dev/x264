/* -----------------------------------------------------------------------------
The copyright in this software is being made available under the Clear BSD
License, included below. No patent rights, trademark rights and/or
other Intellectual Property Rights other than the copyrights concerning
the Software are granted under this license.

The Clear BSD License

Copyright (c) 2019-2026, Fraunhofer-Gesellschaft zur Förderung der angewandten Forschung e.V. & The VVenC Authors.
All rights reserved.

Redistribution and use in source and binary forms, with or without modification,
are permitted (subject to the limitations in the disclaimer below) provided that
the following conditions are met:

     * Redistributions of source code must retain the above copyright notice,
     this list of conditions and the following disclaimer.

     * Redistributions in binary form must reproduce the above copyright
     notice, this list of conditions and the following disclaimer in the
     documentation and/or other materials provided with the distribution.

     * Neither the name of the copyright holder nor the names of its
     contributors may be used to endorse or promote products derived from this
     software without specific prior written permission.

NO EXPRESS OR IMPLIED LICENSES TO ANY PARTY'S PATENT RIGHTS ARE GRANTED BY
THIS LICENSE. THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND
CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A
PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.


------------------------------------------------------------------------------------------- */
/* Controlled adaptation of the pinned VVenC six-tap rolling-row design.
 * Copyright (c) 2026 x264 research contributors.
 *
 * Source: fraunhoferhhi/vvenc, de2443e4cef10330e62e64c7f9acbc7380509abc,
 * source/Lib/CommonLib/arm/neon/MCTF_neon.cpp, applyFrac6Tap_8x_filter{1,2}D.
 * The original notice is retained above. This is NOT a VVenC reproduction:
 * inputs are uint8_t; horizontal sums remain unrounded; the vertical pass
 * widens before pairwise additions and rounds only at the final 12-bit shift.
 * The four-row loop and coefficient symmetry are prior implementation ideas.
 * Do not use this control to claim new rolling rows or generic NEON arithmetic.
 */
#ifndef X264_MCTF_PRIOR_CONTROL_H
#define X264_MCTF_PRIOR_CONTROL_H

#include <stdint.h>
#include <string.h>
#include <arm_neon.h>

static inline int x264_mctf_prior_symmetric( const int32_t f[8] )
{
    return f[1] == f[6] && f[2] == f[5] && f[3] == f[4];
}

static inline int16x8_t x264_mctf_prior_horizontal( const uint8_t *p,
                                                 const int32_t f[8], int symmetric )
{
    int16x8_t v[6];
    for( int tap = 0; tap < 6; tap++ )
        v[tap] = vreinterpretq_s16_u16( vmovl_u8( vld1_u8( p + tap ) ) );
    int16x8_t sum;
    if( symmetric )
    {
        sum = vmulq_n_s16( vaddq_s16( v[0], v[5] ), f[1] );
        sum = vmlaq_n_s16( sum, vaddq_s16( v[1], v[4] ), f[2] );
        return vmlaq_n_s16( sum, vaddq_s16( v[2], v[3] ), f[3] );
    }
    if( f[1] == f[6] )
        sum = vmulq_n_s16( vaddq_s16( v[0], v[5] ), f[1] );
    else
    {
        sum = vmulq_n_s16( v[0], f[1] );
        sum = vmlaq_n_s16( sum, v[5], f[6] );
    }
    sum = vmlaq_n_s16( sum, v[1], f[2] );
    sum = vmlaq_n_s16( sum, v[4], f[5] );
    sum = vmlaq_n_s16( sum, v[2], f[3] );
    return vmlaq_n_s16( sum, v[3], f[4] );
}

/* Horizontal rows can be as large as 20400; summing two in int16 is unsafe.
 * Widen before folding symmetric pairs. Every sum/product fits int32 under
 * the same fixed 8-bit filter bounds as the selected implementation. */
static inline uint8x8_t x264_mctf_prior_vertical( const int16x8_t rows[6],
                                               const int32_t f[8], int symmetric )
{
    int32x4_t lo, hi;
    if( symmetric )
    {
        lo = vmulq_n_s32( vaddl_s16( vget_low_s16( rows[0] ), vget_low_s16( rows[5] ) ), f[1] );
        hi = vmulq_n_s32( vaddl_s16( vget_high_s16( rows[0] ), vget_high_s16( rows[5] ) ), f[1] );
        lo = vmlaq_n_s32( lo, vaddl_s16( vget_low_s16( rows[1] ), vget_low_s16( rows[4] ) ), f[2] );
        hi = vmlaq_n_s32( hi, vaddl_s16( vget_high_s16( rows[1] ), vget_high_s16( rows[4] ) ), f[2] );
        lo = vmlaq_n_s32( lo, vaddl_s16( vget_low_s16( rows[2] ), vget_low_s16( rows[3] ) ), f[3] );
        hi = vmlaq_n_s32( hi, vaddl_s16( vget_high_s16( rows[2] ), vget_high_s16( rows[3] ) ), f[3] );
    }
    else
    {
        lo = vmull_n_s16( vget_low_s16( rows[0] ), f[1] );
        hi = vmull_n_s16( vget_high_s16( rows[0] ), f[1] );
        for( int tap = 1; tap < 6; tap++ )
        {
            lo = vmlal_n_s16( lo, vget_low_s16( rows[tap] ), f[tap+1] );
            hi = vmlal_n_s16( hi, vget_high_s16( rows[tap] ), f[tap+1] );
        }
    }
    return vqmovn_u16( vcombine_u16( vqrshrun_n_s32( lo, 12 ), vqrshrun_n_s32( hi, 12 ) ) );
}

static inline void x264_mctf_interpolate_prior_control( uint8_t *dst, int ds,
                                                       const uint8_t *src, int ss,
                                                       int width, int height,
                                                       const int32_t xf[8], const int32_t yf[8] )
{
    int x_symmetric = x264_mctf_prior_symmetric( xf );
    int y_symmetric = x264_mctf_prior_symmetric( yf );
    int x = 0;
    for( ; x + 8 <= width; x += 8 )
    {
        int16x8_t rows[9];
        for( int row = 0; row < 5; row++ )
            rows[row] = x264_mctf_prior_horizontal( src + (row - 2) * ss + x - 2, xf, x_symmetric );
        int y = 0;
        for( ; y + 4 <= height; y += 4 )
        {
            for( int row = 0; row < 4; row++ )
                rows[5 + row] = x264_mctf_prior_horizontal( src + (y + 3 + row) * ss + x - 2, xf, x_symmetric );
            for( int row = 0; row < 4; row++ )
                vst1_u8( dst + (y + row) * ds + x, x264_mctf_prior_vertical( rows + row, yf, y_symmetric ) );
            for( int row = 0; row < 5; row++ )
                rows[row] = rows[4 + row];
        }
        for( ; y < height; y++ )
        {
            rows[5] = x264_mctf_prior_horizontal( src + (y + 3) * ss + x - 2, xf, x_symmetric );
            vst1_u8( dst + y * ds + x, x264_mctf_prior_vertical( rows, yf, y_symmetric ) );
            for( int row = 0; row < 5; row++ )
                rows[row] = rows[row + 1];
        }
    }
    /* Exact scalar tail for non-eight-lane borders. Both public 720p sources
     * and the 352-wide CIF timing sources use full 16-pixel tiles. */
    for( ; x < width; x++ )
        for( int y = 0; y < height; y++ )
        {
            int64_t value = 0;
            for( int ty = 1; ty <= 6; ty++ )
                for( int tx = 1; tx <= 6; tx++ )
                    value += (int64_t)yf[ty] * xf[tx] * src[(y - 3 + ty) * ss + x - 3 + tx];
            value = (value + 2048) >> 12;
            dst[y * ds + x] = value < 0 ? 0 : value > 255 ? 255 : value;
        }
}

#endif
