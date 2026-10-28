#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "mctf_support.h"

static uint32_t rng=0x51a7e3d9;
static uint32_t random_word(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return rng;}
static int rounded(int y,int count,unsigned mask,const int32_t *const t[10],const int v[10])
{
    int64_t n=65536LL*y,d=65536;
    for(int j=0;j<count;j++)if(mask&(1U<<j))
    {int w=t[j][abs(v[j]-y)];n+=(int64_t)w*v[j];d+=w;}
    return (n+d/2)/d;
}
static int old_feasible(int count,unsigned mask,const int32_t *const t[10],int tau)
{
    int64_t p=0,m=0,w=0;
    for(int j=0;j<count;j++)
    {
        int64_t a=0,b=0;
        for(int x=0;x<256;x++){if((int64_t)t[j][x]*x>a)a=(int64_t)t[j][x]*x;if(t[j][x]>b)b=t[j][x];}
        if(mask&(1U<<j))p+=a;else{m+=a;w+=b;}
    }
    int64_t a=p>tau*65536LL?p-tau*65536LL:0;
    return 65536*m+a*w<=tau*65536LL*65536;
}

int main(void)
{
    uint64_t exhaustive=0,random_checks=0,dominance=0,radius_checks=0;
    int32_t data[10][256];const int32_t *tables[10];
    for(int j=0;j<10;j++)tables[j]=data[j];
    const int ys[]={0,1,32,127,223,254,255};
    for(int family=0;family<20;family++)
    {
        for(int j=0;j<2;j++)for(int x=0;x<256;x++)
            data[j][x]=family<10 ? (int)(65536*(0.01+0.025*family)*(j?0.35:1.0)*exp(-x*x/(2.0*(8+family)*(8+family)))+0.5)
                                : (int)(random_word()%4097);
        for(unsigned mask=0;mask<4;mask++)
        {
            int64_t rn,rd;mctf_support_radius(2,mask,tables,&rn,&rd);
            int64_t bn=0,bd=65536;
            for(int a=0;a<256;a++)for(int b=0;b<256;b++)
            {
                int64_t n=0,d=65536;
                if(mask&1){n+=(int64_t)data[0][a]*a;d+=data[0][a];}
                if(mask&2){n+=(int64_t)data[1][b]*b;d+=data[1][b];}
                if(n*bd>bn*d){bn=n;bd=d;}
            }
            assert(rn*bd==bn*rd);radius_checks++;
            for(int tau=0;tau<=4;tau++)for(int level=0;level<=1;level++)
            {
                int safe=mctf_support_feasible(2,mask,tables,tau,level);
                if(old_feasible(2,mask,tables,tau)){assert(safe);dominance++;}
                if(!safe)continue;
                for(unsigned yi=0;yi<sizeof(ys)/sizeof(*ys);yi++)
                    for(int a=0;a<256;a++)for(int b=0;b<256;b++)
                    {
                        int v[10]={a,b};
                        assert(abs(rounded(ys[yi],2,3,tables,v)-rounded(ys[yi],2,mask,tables,v))<=tau);
                        exhaustive++;
                    }
            }
        }
    }
    for(int trial=0;trial<2000;trial++)
    {
        int count=1+random_word()%10,tau=random_word()%8;
        for(int j=0;j<count;j++)
        {
            int confidence=random_word()%256;
            for(int x=0;x<256;x++)
            {
                int64_t w=trial%2 ? (random_word()%2049) : (int)(10000*exp(-x*x/200.0));
                data[j][x]=(w*confidence+127)/255;
            }
        }
        unsigned all=(1U<<count)-1;
        unsigned mask=mctf_support_plan(count,tables,tau,1);
        for(int sample=0;sample<1000;sample++)
        {
            int y=random_word()%256,v[10];
            for(int j=0;j<count;j++)v[j]=random_word()%256;
            assert(abs(rounded(y,count,all,tables,v)-rounded(y,count,mask,tables,v))<=tau);
            random_checks++;
        }
        unsigned arbitrary=random_word()&all;
        if(old_feasible(count,arbitrary,tables,tau))
        {assert(mctf_support_feasible(count,arbitrary,tables,tau,1));dominance++;}
    }
    /* Exact upper half-up edge: y=127, v=128, w=W0 gives a +0.5 tie.
     * An empty tau=0 plan must reject it. Just below that tie it may accept. */
    for(int x=0;x<256;x++)data[0][x]=0;
    data[0][1]=65536;assert(!mctf_support_empty(1,tables,0));
    data[0][1]=65535;assert(mctf_support_empty(1,tables,0));
    assert(mctf_support_empty(1,tables,255));
    printf("{\"passed\":true,\"exhaustive_scalar_comparisons\":%llu,\"random_scalar_comparisons\":%llu,\"old_condition_dominance_checks\":%llu,\"radius_exhaustive_checks\":%llu,\"half_up_boundary_checks\":3}\n",
        (unsigned long long)exhaustive,(unsigned long long)random_checks,
        (unsigned long long)dominance,(unsigned long long)radius_checks);
    return 0;
}
