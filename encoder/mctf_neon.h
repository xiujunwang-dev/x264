/* Exact 8-bit MCTF arithmetic on AArch64. Explicit experimental controls keep
 * the scalar block-cache implementation available for direct ablations. */
#ifndef X264_MCTF_NEON_H
#define X264_MCTF_NEON_H

#include <stdint.h>
#include <limits.h>
#include <string.h>

#ifndef X264_MCTF_NEON_INTERPOLATION
#define X264_MCTF_NEON_INTERPOLATION 0
#endif
#ifndef X264_MCTF_NEON_NORMALIZE
#define X264_MCTF_NEON_NORMALIZE 0
#endif
#ifndef X264_MCTF_NEON_RECIPROCAL
#define X264_MCTF_NEON_RECIPROCAL 0
#endif
#if X264_MCTF_NEON_RECIPROCAL && !X264_MCTF_NEON_NORMALIZE
#error Reciprocal proposal requires exact NEON normalization
#endif
#ifndef X264_MCTF_STRIPE_COLUMNS
#define X264_MCTF_STRIPE_COLUMNS 0
#endif
#ifndef X264_MCTF_ROW_REUSE
#define X264_MCTF_ROW_REUSE 0
#endif
#ifndef X264_MCTF_REUSE_ACCOUNTING
#define X264_MCTF_REUSE_ACCOUNTING 0
#endif
#if X264_MCTF_ROW_REUSE && (!X264_MCTF_NEON_INTERPOLATION || X264_MCTF_STRIPE_COLUMNS != 4)
#error Row reuse requires the explicit four-column NEON stripe experiment
#endif

#if defined(__aarch64__) && defined(__ARM_NEON)
#include <arm_neon.h>
#define X264_MCTF_HAVE_NEON 1

/* The fixed MCTF phase filters have positive coefficient sum <= 80 and
 * negative coefficient magnitude sum <= 16. Thus every horizontal sum and
 * partial sum is in [-4080,20400], including the identity phase. Preserve this
 * unrounded signed value in int16; the second pass still uses int32. */
static inline int16x8_t x264_mctf_neon_six_tap( const uint8_t *p, int step,
                                               const int32_t filter[8] )
{
    int16x8_t sum = vmulq_n_s16( vreinterpretq_s16_u16( vmovl_u8( vld1_u8( p ) ) ), filter[1] );
    for( int tap = 2; tap <= 6; tap++ )
        sum = vmlaq_n_s16( sum, vreinterpretq_s16_u16( vmovl_u8( vld1_u8( p + (tap-1) * step ) ) ), filter[tap] );
    return sum;
}

static inline void x264_mctf_interpolate_axis_neon( uint8_t *dst, int dst_stride,
                                                   const uint8_t *src, int src_stride,
                                                   int width, int height,
                                                   const int32_t filter[8], int vertical )
{
    int step = vertical ? src_stride : 1;
    for( int y = 0; y < height; y++ )
    {
        int x = 0;
        for( ; x + 8 <= width; x += 8 )
        {
            int16x8_t sum = x264_mctf_neon_six_tap( src + y * src_stride + x - 2 * step, step, filter );
            vst1_u8( dst + y * dst_stride + x, vqrshrun_n_s16( sum, 6 ) );
        }
        for( ; x < width; x++ )
        {
            const uint8_t *p = src + y * src_stride + x - 2 * step;
            int sum = 0;
            for( int tap = 1; tap <= 6; tap++ )
                sum += filter[tap] * p[(tap-1) * step];
            sum = (sum + 32) >> 6;
            dst[y * dst_stride + x] = sum < 0 ? 0 : sum > 255 ? 255 : sum;
        }
    }
}

/* A cache contains only the exact final five horizontal rows of one preceding
 * tile. A hit requires identical displaced source bytes, horizontal phase and
 * width. Reference/column ownership and lifetime are supplied by the caller. */
typedef struct
{
    int16_t tail[5][16];
    const uint8_t *next_source;
    const int32_t *x_filter;
    int width;
    int valid;
} x264_mctf_row_cache_t;

static inline int x264_mctf_interpolate_both_neon_cached( uint8_t *dst, int dst_stride,
                                                   const uint8_t *src, int src_stride,
                                                   int width, int height,
                                                   const int32_t x_filter[8], const int32_t y_filter[8],
                                                   x264_mctf_row_cache_t *cache )
{
    /* Output rows 0..height-1 use exactly height+5 horizontal rows. Unlike the
     * scalar historical buffer, no unused halo rows are evaluated. */
    int16_t temp[21][16];
    int reused_rows = cache && cache->valid && cache->next_source == src
                   && cache->x_filter == x_filter && cache->width == width ? 5 : 0;
    if( reused_rows )
        memcpy( temp, cache->tail, sizeof(cache->tail) );
    for( int y = reused_rows; y < height + 5; y++ )
    {
        const uint8_t *p = src + (y - 2) * src_stride - 2;
        int x = 0;
        for( ; x + 8 <= width; x += 8 )
            vst1q_s16( temp[y] + x, x264_mctf_neon_six_tap( p + x, 1, x_filter ) );
        for( ; x < width; x++ )
        {
            int sum = 0;
            for( int tap = 1; tap <= 6; tap++ )
                sum += x_filter[tap] * p[x + tap - 1];
            temp[y][x] = sum;
        }
    }
    if( cache )
    {
        /* Initialize partial-row padding so copying all 16 lanes never carries
         * indeterminate bytes, even though only width lanes are evaluated. */
        for( int y = 0; y < 5; y++ )
        {
            memcpy( cache->tail[y], temp[height + y], width * sizeof(int16_t) );
            memset( cache->tail[y] + width, 0, (16 - width) * sizeof(int16_t) );
        }
        cache->next_source = src + height * src_stride;
        cache->x_filter = x_filter;
        cache->width = width;
        cache->valid = 1;
    }
    for( int y = 0; y < height; y++ )
    {
        int x = 0;
        for( ; x + 8 <= width; x += 8 )
        {
            int16x8_t row = vld1q_s16( temp[y] + x );
            int32x4_t lo = vmull_n_s16( vget_low_s16( row ), y_filter[1] );
            int32x4_t hi = vmull_n_s16( vget_high_s16( row ), y_filter[1] );
            for( int tap = 2; tap <= 6; tap++ )
            {
                row = vld1q_s16( temp[y + tap - 1] + x );
                lo = vmlal_n_s16( lo, vget_low_s16( row ), y_filter[tap] );
                hi = vmlal_n_s16( hi, vget_high_s16( row ), y_filter[tap] );
            }
            uint16x8_t rounded = vcombine_u16( vqrshrun_n_s32( lo, 12 ), vqrshrun_n_s32( hi, 12 ) );
            vst1_u8( dst + y * dst_stride + x, vqmovn_u16( rounded ) );
        }
        for( ; x < width; x++ )
        {
            int sum = 0;
            for( int tap = 1; tap <= 6; tap++ )
                sum += y_filter[tap] * temp[y + tap - 1][x];
            sum = (sum + 2048) >> 12;
            dst[y * dst_stride + x] = sum < 0 ? 0 : sum > 255 ? 255 : sum;
        }
    }
    return reused_rows;
}

static inline void x264_mctf_interpolate_both_neon( uint8_t *dst, int dst_stride,
                                                   const uint8_t *src, int src_stride,
                                                   int width, int height,
                                                   const int32_t x_filter[8], const int32_t y_filter[8] )
{
    x264_mctf_interpolate_both_neon_cached( dst, dst_stride, src, src_stride, width, height,
                                          x_filter, y_filter, NULL );
}

/* Check the actual weight tables once per frame. Nonnegative weights and
 * Dmax <= INT32_MAX/256 bound N+D/2, q*D, and all legacy signed accumulations.
 * Confidence in [0,255] cannot increase a nonnegative integer weight. */
static inline int x264_mctf_neon_weights_safe( const int32_t *const tables[10], int refs )
{
    int64_t maximum_denominator = 65536;
    for( int ref = 0; ref < refs; ref++ )
    {
        int32_t maximum = 0;
        for( int delta = 0; delta < 256; delta++ )
        {
            int32_t weight = tables[ref][delta];
            if( weight < 0 )
                return 0;
            if( weight > maximum )
                maximum = weight;
        }
        maximum_denominator += maximum;
    }
    return maximum_denominator <= INT32_MAX / 256;
}

/* A/D is in [0,255.5]. Two binary32 conversions and correctly rounded FDIV
 * have absolute quotient error < 0.0001, so truncation differs by at most one.
 * Integer comparisons correct either direction. The returned quotient is
 * EXACT; floating arithmetic only proposes a candidate. The caller establishes
 * 1 <= D <= INT32_MAX/256 and 0 <= A <= 255.5*D. */
#if X264_MCTF_NEON_RECIPROCAL
/* This contract does not depend on a reciprocal instruction's error bound.
 * Clamp any proposed quotient before multiplication: 255*D fits int32 under
 * the caller's guard. Try one correction in either direction, then accept
 * ONLY if q*D <= A and A-q*D < D. Otherwise divide the failing lanes exactly.
 * The validated quotient/remainder inequalities prove the returned floor. */
static inline uint32x4_t x264_mctf_neon_validate_quotient( uint32x4_t a, uint32x4_t d,
                                                        uint32x4_t proposal )
{
    uint32x4_t q = vminq_u32( proposal, vdupq_n_u32( 255 ) );
    uint32x4_t product = vmulq_u32( q, d );
    q = vsubq_u32( q, vshrq_n_u32( vcgtq_u32( product, a ), 31 ) );
    product = vmulq_u32( q, d );
    q = vaddq_u32( q, vshrq_n_u32( vcgeq_u32( vsubq_u32( a, product ), d ), 31 ) );
    product = vmulq_u32( q, d );
    uint32x4_t invalid = vorrq_u32( vcgtq_u32( product, a ),
                                  vcgeq_u32( vsubq_u32( a, product ), d ) );
    if( vmaxvq_u32( invalid ) )
    {
        uint32_t numerator[4], denominator[4], result[4], failed[4];
        vst1q_u32( numerator, a );
        vst1q_u32( denominator, d );
        vst1q_u32( result, q );
        vst1q_u32( failed, invalid );
        for( int lane = 0; lane < 4; lane++ )
            if( failed[lane] )
                result[lane] = numerator[lane] / denominator[lane];
        q = vld1q_u32( result );
    }
    return q;
}
#endif

static inline uint32x4_t x264_mctf_neon_divide_exact( uint32x4_t a, uint32x4_t d )
{
#if X264_MCTF_NEON_RECIPROCAL
    float32x4_t estimate = vmulq_f32( vcvtq_f32_u32( a ), vrecpeq_f32( vcvtq_f32_u32( d ) ) );
    return x264_mctf_neon_validate_quotient( a, d, vcvtq_u32_f32( estimate ) );
#else
    uint32x4_t q = vcvtq_u32_f32( vdivq_f32( vcvtq_f32_u32( a ), vcvtq_f32_u32( d ) ) );
    uint32x4_t product = vmulq_u32( q, d );
    q = vsubq_u32( q, vshrq_n_u32( vcgtq_u32( product, a ), 31 ) );
    product = vmulq_u32( q, d );
    return vaddq_u32( q, vshrq_n_u32( vcgeq_u32( vsubq_u32( a, product ), d ), 31 ) );
#endif
}

static inline uint32x4_t x264_mctf_neon_load4( const uint8_t *source )
{
    uint32_t packed;
    memcpy( &packed, source, sizeof(packed) );
    return vmovl_u16( vget_low_u16( vmovl_u8( vcreate_u8( packed ) ) ) );
}

static inline void x264_mctf_filter_tile_neon( uint8_t *destination, int stride,
                                               const uint8_t *source, const uint8_t prediction[][256],
                                               int width, int height, int refs,
                                               const int32_t *const tables[10], const int confidence[10] )
{
    for( int y = 0; y < height; y++ )
    {
        int x = 0;
        for( ; x + 4 <= width; x += 4 )
        {
            uint32x4_t original = x264_mctf_neon_load4( source + y * stride + x );
            uint32x4_t n = vshlq_n_u32( original, 16 ), d = vdupq_n_u32( 65536 );
            for( int ref = 0; ref < refs; ref++ )
            {
                uint32x4_t value = x264_mctf_neon_load4( prediction[ref] + y * 16 + x );
                uint32_t delta[4], weight[4];
                vst1q_u32( delta, vabdq_u32( value, original ) );
                for( int lane = 0; lane < 4; lane++ )
                {
                    weight[lane] = tables[ref][delta[lane]];
                    if( confidence[ref] >= 0 && confidence[ref] < 255 )
                        weight[lane] = ((int64_t)weight[lane] * confidence[ref] + 127) / 255;
                }
                uint32x4_t w = vld1q_u32( weight );
                n = vmlaq_u32( n, w, value );
                d = vaddq_u32( d, w );
            }
            uint32_t result[4];
            vst1q_u32( result, x264_mctf_neon_divide_exact( vaddq_u32( n, vshrq_n_u32( d, 1 ) ), d ) );
            for( int lane = 0; lane < 4; lane++ )
                destination[y * stride + x + lane] = result[lane];
        }
        for( ; x < width; x++ )
        {
            int original = source[y * stride + x];
            int32_t n = original * 65536, d = 65536;
            for( int ref = 0; ref < refs; ref++ )
            {
                int value = prediction[ref][y * 16 + x];
                int delta = value - original;
                int32_t w = tables[ref][delta < 0 ? -delta : delta];
                if( confidence[ref] >= 0 )
                    w = ((int64_t)w * confidence[ref] + 127) / 255;
                n += w * value;
                d += w;
            }
            destination[y * stride + x] = (n + d / 2) / d;
        }
    }
}
#else
#define X264_MCTF_HAVE_NEON 0
#endif
#endif
