/* Experimental joint weight/influence bounds for a fixed integer operator.
 * Fractional programming is established; this is its discrete use in a
 * temporal-reference omission certificate, not a priority claim.
 * Assumptions: 0<=weights, <=10 references, W0+sum(max weight)<=INT32_MAX/256.
 * Every result compares one common input state. */
#ifndef MCTF_SUPPORT_H
#define MCTF_SUPPORT_H
#include <stdint.h>
#include <limits.h>
#define MCTF_SUPPORT_W0 65536LL

/* Exact maximum normalized positive displacement over independent relaxed
 * differences d_j in {0,...,255}. This relaxed set contains all actual signed
 * displacements after taking absolute values. Dinkelbach updates use integers.
 * On a defensive iteration limit, P/W0 is a valid conservative fallback. */
static inline int mctf_support_radius(int count, unsigned mask,
        const int32_t *const tables[10], int64_t *numerator, int64_t *denominator)
{
    int64_t n=0, d=MCTF_SUPPORT_W0, p=0;
    for (int j=0; j<count; j++) if (mask & (1U<<j))
    {
        int64_t best=0;
        for (int x=0; x<256; x++)
            if ((int64_t)tables[j][x]*x > best) best=(int64_t)tables[j][x]*x;
        p+=best;
    }
    for (int iteration=0; iteration<64; iteration++)
    {
        int64_t next_n=0, next_d=MCTF_SUPPORT_W0;
        for (int j=0; j<count; j++) if (mask & (1U<<j))
        {
            int arg=0;
            int64_t best=INT64_MIN;
            for (int x=0; x<256; x++)
            {
                int64_t value=(int64_t)tables[j][x]*(x*d-n);
                if (value>best) {best=value;arg=x;}
            }
            next_n+=(int64_t)tables[j][arg]*arg;
            next_d+=tables[j][arg];
        }
        if (next_n*d==n*next_d)
        {
            *numerator=next_n;*denominator=next_d;return 1;
        }
        n=next_n;d=next_d;
    }
    *numerator=p;*denominator=MCTF_SUPPORT_W0;return 0;
}

/* With K empty, q_K=y. Exact support of each reference in the relaxed signed
 * difference domain gives q_F-y <= tau iff sum max_d w(d)(2d-2tau-1)
 * < (2tau+1)W0. Symmetry implies the lower condition; the strict upper edge
 * is essential for half-up rounding. Actual finite sample bounds only reduce
 * this domain. */
static inline int mctf_support_empty(int count,
        const int32_t *const tables[10], int tau)
{
    int64_t sum=0, threshold=2LL*tau+1;
    for (int j=0; j<count; j++)
    {
        int64_t best=INT64_MIN;
        for (int x=0; x<256; x++)
        {
            int64_t value=(int64_t)tables[j][x]*(2LL*x-threshold);
            if(value>best)best=value;
        }
        sum+=best;
    }
    return sum < threshold*MCTF_SUPPORT_W0;
}

/* If r_K=N/D bounds |u_K-y|, then the omitted positive residual is at most
 * sum_O max_d w_j(d)(d+r_K-tau). Bounding it by tau*W0 <= tau*D_K
 * proves |u_F-u_K|<=tau. Integer half-up rounding preserves integer tau.
 * Unlike separate moment/max bounds, this preserves the coupling between
 * a difference, its weight, and the tolerance. */
static inline int mctf_support_feasible(int count, unsigned retained,
        const int32_t *const tables[10], int tau, int tight_radius)
{
    if (!retained) return mctf_support_empty(count,tables,tau);
    int64_t n=0,d=MCTF_SUPPORT_W0;
    if (tight_radius) mctf_support_radius(count,retained,tables,&n,&d);
    else for (int j=0; j<count; j++) if (retained & (1U<<j))
    {
        int64_t best=0;
        for(int x=0;x<256;x++)
            if((int64_t)tables[j][x]*x>best)best=(int64_t)tables[j][x]*x;
        n+=best;
    }
    int64_t sum=0;
    for (int j=0; j<count; j++) if (!(retained & (1U<<j)))
    {
        int64_t best=INT64_MIN;
        for (int x=0; x<256; x++)
        {
            int64_t value=(int64_t)tables[j][x]*(x*d+n-tau*d);
            if(value>best)best=value;
        }
        sum+=best;
    }
    return sum <= tau*MCTF_SUPPORT_W0*d;
}

static inline unsigned mctf_support_plan(int count,
        const int32_t *const tables[10], int tau, int tight_radius)
{
    int order[10];int64_t moment[10];
    for(int j=0;j<count;j++)
    {
        moment[j]=0;
        for(int x=0;x<256;x++)
            if((int64_t)tables[j][x]*x>moment[j])moment[j]=(int64_t)tables[j][x]*x;
        int pos=j;
        while(pos>0 && moment[order[pos-1]]<moment[j]){order[pos]=order[pos-1];pos--;}
        order[pos]=j;
    }
    unsigned mask=0;
    for(int k=0;k<count;k++)
    {
        if(mctf_support_feasible(count,mask,tables,tau,tight_radius))return mask;
        mask|=1U<<order[k];
    }
    return mask;
}
#endif
