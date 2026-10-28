#include <assert.h>
#include <inttypes.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include "mctf_envelope.h"
static uint32_t state=0x341fedc7;
static uint32_t random_word(void){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
static int rounded(int y,int count,unsigned mask,const int32_t *const t[10],const int *v)
{
    int64_t n=65536LL*y,d=65536;
    for(int j=0;j<count;j++)if(mask&(1U<<j))
    {int w=t[j][abs(v[j]-y)];n+=(int64_t)w*v[j];d+=w;}
    return (n+d/2)/d;
}
int main(void)
{
    int32_t data[10][256]={0};const int32_t *t[10];
    for(int j=0;j<10;j++)t[j]=data[j];
    data[0][2]=65536;data[1][6]=32112;
    assert(!mctf_support_feasible(2,1,t,2,1));
    assert(mctf_envelope_feasible(2,1,t,2));
    uint64_t exhaustive=0,random_checks=0,dominance=0,strict=0;
    for(int trial=0;trial<64;trial++)
    {
        if(trial)for(int j=0;j<2;j++)for(int x=0;x<256;x++)
            data[j][x]=trial%3==0?random_word()%3001:
                (int)(60000.*exp(-x*x/(2.*(2+trial%16)*(2+trial%16))) *(j?.31:1.)+.5);
        for(unsigned mask=0;mask<4;mask++)for(int tau=0;tau<5;tau++)
        {
            int base=mctf_support_feasible(2,mask,t,tau,1);
            int safe=mctf_envelope_feasible(2,mask,t,tau);
            if(base){assert(safe);dominance++;}
            if(!safe)continue;
            strict+=!base;
            /* Independent signed differences; anchor 255 keeps sums positive.
             * Values above 255 deliberately test the larger relaxed domain. */
            for(int a=-255;a<=255;a++)for(int b=-255;b<=255;b++)
            {
                int v[10]={255+a,255+b};
                assert(abs(rounded(255,2,3,t,v)-rounded(255,2,mask,t,v))<=tau);
                exhaustive++;
            }
        }
    }
    for(int trial=0;trial<2000;trial++)
    {
        int count=1+random_word()%10,tau=random_word()%8;
        for(int j=0;j<count;j++)for(int x=0;x<256;x++)
            data[j][x]=trial%2?random_word()%2049:(int)(32000.*exp(-x*x/100.)+.5);
        unsigned mask=mctf_envelope_plan(count,t,tau),all=(1U<<count)-1;
        unsigned base=mctf_support_plan(count,t,tau,1);
        assert(__builtin_popcount(mask)<=__builtin_popcount(base));
        for(int sample=0;sample<1000;sample++)
        {
            int v[10],y=random_word()%256;
            for(int j=0;j<count;j++)v[j]=random_word()%256;
            assert(abs(rounded(y,count,all,t,v)-rounded(y,count,mask,t,v))<=tau);
            random_checks++;
        }
    }
    /* Maximum safe fusion denominator and all original boundary cases. */
    for(int j=0;j<10;j++)for(int x=0;x<256;x++)data[j][x]=832307;
    for(int tau=0;tau<=255;tau+=17)
        assert(mctf_envelope_feasible(10,1023,t,tau));
    printf("{\"passed\":true,\"exhaustive_relaxed_comparisons\":%"PRIu64",\"random_pixel_comparisons\":%"PRIu64",\"support_dominance_checks\":%"PRIu64",\"strict_improvement_cases\":%"PRIu64",\"bins\":16,\"slopes\":[2,4,8,16,32,64,128,255]}\n",exhaustive,random_checks,dominance,strict);
    return 0;
}
