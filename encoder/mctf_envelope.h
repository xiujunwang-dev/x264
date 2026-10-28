/* Denominator envelopes for the fixed integer reference-omission operator.
 * The existing radius certificate is a fast path. Additional interval tests
 * retain the relationship between anchor displacement and normalization mass.
 * Products use signed 128-bit integers; no approximate division is used. */
#ifndef MCTF_ENVELOPE_H
#define MCTF_ENVELOPE_H
#include "mctf_support.h"

static inline int mctf_envelope_feasible(int count, unsigned retained,
        const int32_t *const tables[10], int tau)
{
    if (mctf_support_feasible(count, retained, tables, tau, 1)) return 1;
    if (!retained || tau == 0) return 0;
    int64_t n, d;
    mctf_support_radius(count, retained, tables, &n, &d);
    if (!n) return 0;
    static const int slopes[8] = {2,4,8,16,32,64,128,255};
    int64_t intercept[8] = {0};
    for (int k=0; k<8; k++)
        for (int j=0; j<count; j++) if (retained & (1U<<j))
        {
            int64_t best=INT64_MIN;
            for (int x=0; x<256; x++)
            {
                int64_t value=(int64_t)tables[j][x]*(x-slopes[k]);
                if (value>best) best=value;
            }
            intercept[k]+=best;
        }
    /* Each [lo,hi] covers possible |u_K-y|, with a common exact denominator. */
    const int bins=16;
    int64_t scale=bins*d;
    for (int bin=0; bin<bins; bin++)
    {
        int64_t lo=bin*n, hi=(bin+1)*n, residual=0;
        for (int j=0; j<count; j++) if (!(retained & (1U<<j)))
        {
            int64_t best=INT64_MIN;
            for (int x=0; x<256; x++)
            {
                int64_t value=(int64_t)tables[j][x]*(x*scale+hi-tau*scale);
                if (value>best) best=value;
            }
            residual+=best;
        }
        if ((__int128)residual <= (__int128)tau*MCTF_SUPPORT_W0*scale) continue;
        int valid=0;
        for (int k=0; k<8; k++)
        {
            int64_t c=slopes[k], numerator=c*MCTF_SUPPORT_W0-intercept[k];
            if (c*scale<=hi || numerator<=0) continue;
            /* D_K >= (c W0 - sum_K H_j(c))/(c-lo).
             * The omitted residual is bounded at hi; D_K is bounded at lo. */
            if ((__int128)residual*(c*scale-lo)
                <= (__int128)tau*numerator*scale*scale)
            { valid=1; break; }
        }
        if (!valid) return 0;
    }
    return 1;
}

static inline unsigned mctf_envelope_plan(int count,
        const int32_t *const tables[10], int tau)
{
    int order[10]; int64_t moment[10];
    for (int j=0; j<count; j++)
    {
        moment[j]=0;
        for (int x=0; x<256; x++)
            if ((int64_t)tables[j][x]*x>moment[j]) moment[j]=(int64_t)tables[j][x]*x;
        int pos=j;
        while (pos>0 && moment[order[pos-1]]<moment[j])
        { order[pos]=order[pos-1]; pos--; }
        order[pos]=j;
    }
    unsigned mask=0;
    for (int k=0; k<count; k++)
    {
        if (mctf_envelope_feasible(count,mask,tables,tau)) return mask;
        mask|=1U<<order[k];
    }
    return mask;
}
#endif
