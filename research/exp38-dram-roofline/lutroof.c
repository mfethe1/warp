/* SPDX-License-Identifier: Apache-2.0
 * exp38 STAGE 1: is the VQ4P gather (kern_D) on the DRAM roof?
 *
 * kern_D body is BYTE-IDENTICAL to lutbw.c @ WARP 7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b
 * (same bytes as exp35 evidence lutmt2.c, sha256 768e690d...).
 *
 * Arms, all at the SAME thread count T, all QOS_CLASS_USER_INTERACTIVE
 * (P-core preference on Apple silicon), all per-thread INDEPENDENT buffers:
 *
 *   D     : VQ4P gather over a per-thread index stream of nidx bytes  (reads nidx)
 *   CPY   : memcpy(dst,src,nidx)                                      (reads nidx, writes nidx)
 *   RDSUM : pure streaming vector read-reduce over nidx bytes         (reads nidx)
 *
 * Reported bandwidth is INDEX-STREAM (source-read) GiB/s for all three so that
 * the ratio D/control is dimensionally the same quantity. CPY total DRAM
 * traffic is >= 2x its reported number; RDSUM is the honest read-only roof.
 *
 *   cc -O3 -mcpu=native -DM_ROWS=196608 -o lutroof lutroof.c -lm -lpthread
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include <pthread.h>
#include <pthread/qos.h>
#include <stdatomic.h>
#include <math.h>
#include <arm_neon.h>

#ifndef M_ROWS
#define M_ROWS 196608
#endif
#define NV   448
#define TILE 64
#define MAXT 16
#define NREP 5

static double now(void)
{ struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec+t.tv_nsec/1e9; }

/* ---- BEGIN byte-identical kernel from lutbw.c ---- */
/* D: VQ4P — 4 stages x 64 entries, int8 table, one vqtbl4q per stage */
static void kern_D(float *y, const uint8_t *idx, const int8_t *lut8,
                   const float *sc, const float *ls)
{
    int32_t acc[TILE];
    const uint8x16_t m3f=vdupq_n_u8(0x3f), m0f=vdupq_n_u8(0x0f), m03=vdupq_n_u8(0x03);
    for (int r0=0; r0<M_ROWS; r0+=TILE) {
        int32x4_t A[16];
        for (int i=0;i<16;i++) A[i]=vdupq_n_s32(0);
        for (int v0=0; v0<NV; v0+=32) {
            const int ve = v0+32>NV?NV:v0+32;
            int16x8_t s[8];
            for (int i=0;i<8;i++) s[i]=vdupq_n_s16(0);
            for (int v=v0; v<ve; v++) {
                const int8_t *blk = lut8 + (size_t)v*4*64;
                int8x16x4_t T0,T1,T2,T3;
                for (int k=0;k<4;k++){
                    T0.val[k]=vld1q_s8(blk+   0+k*16); T1.val[k]=vld1q_s8(blk+ 64+k*16);
                    T2.val[k]=vld1q_s8(blk+128+k*16);  T3.val[k]=vld1q_s8(blk+192+k*16);
                }
                const uint8_t *ix = idx + ((size_t)(r0/TILE)*NV + v)*TILE*3;
                for (int g=0; g<4; g++) {
                    const uint8x16x3_t I = vld3q_u8(ix+g*48);
                    const uint8x16_t j0=vandq_u8(I.val[0],m3f);
                    const uint8x16_t j1=vorrq_u8(vshrq_n_u8(I.val[0],6),vshlq_n_u8(vandq_u8(I.val[1],m0f),2));
                    const uint8x16_t j2=vorrq_u8(vshrq_n_u8(I.val[1],4),vshlq_n_u8(vandq_u8(I.val[2],m03),4));
                    const uint8x16_t j3=vshrq_n_u8(I.val[2],2);
                    int8x16_t r =vaddq_s8(vqtbl4q_s8(T0,j0),vqtbl4q_s8(T1,j1));
                    int8x16_t r2=vaddq_s8(vqtbl4q_s8(T2,j2),vqtbl4q_s8(T3,j3));
                    s[g*2]  =vaddw_s8(s[g*2],  vget_low_s8(r));
                    s[g*2+1]=vaddw_s8(s[g*2+1],vget_high_s8(r));
                    s[g*2]  =vaddw_s8(s[g*2],  vget_low_s8(r2));
                    s[g*2+1]=vaddw_s8(s[g*2+1],vget_high_s8(r2));
                }
            }
            for (int i=0;i<8;i++){
                A[i*2]  =vaddw_s16(A[i*2],  vget_low_s16(s[i]));
                A[i*2+1]=vaddw_s16(A[i*2+1],vget_high_s16(s[i]));
            }
        }
        for (int i=0;i<16;i++) vst1q_s32(acc+i*4,A[i]);
        for (int r=0;r<TILE;r++) y[r0+r]=(float)acc[r]*ls[0]*sc[r0+r];
    }
}
/* ---- END byte-identical kernel ---- */

/* pure streaming read-reduce, 8 independent accumulators, NEON */
static uint64_t kern_rdsum(const uint8_t *p, size_t n)
{
    uint64x2_t a0=vdupq_n_u64(0),a1=vdupq_n_u64(0),a2=vdupq_n_u64(0),a3=vdupq_n_u64(0);
    size_t i=0;
    for (; i+256<=n; i+=256) {
        for (int k=0;k<256;k+=64) {
            uint8x16_t v0=vld1q_u8(p+i+k+ 0), v1=vld1q_u8(p+i+k+16);
            uint8x16_t v2=vld1q_u8(p+i+k+32), v3=vld1q_u8(p+i+k+48);
            a0=vaddq_u64(a0,vpaddlq_u32(vpaddlq_u16(vpaddlq_u8(v0))));
            a1=vaddq_u64(a1,vpaddlq_u32(vpaddlq_u16(vpaddlq_u8(v1))));
            a2=vaddq_u64(a2,vpaddlq_u32(vpaddlq_u16(vpaddlq_u8(v2))));
            a3=vaddq_u64(a3,vpaddlq_u32(vpaddlq_u16(vpaddlq_u8(v3))));
        }
    }
    uint64_t s = vgetq_lane_u64(a0,0)+vgetq_lane_u64(a0,1)
               + vgetq_lane_u64(a1,0)+vgetq_lane_u64(a1,1)
               + vgetq_lane_u64(a2,0)+vgetq_lane_u64(a2,1)
               + vgetq_lane_u64(a3,0)+vgetq_lane_u64(a3,1);
    for (; i<n; i++) s += p[i];
    return s;
}

typedef struct {
    uint8_t *idx;
    uint8_t *dst;
    int8_t  *lut8;
    float   *sc;
    float   *y;
    float    ls[1];
    double   t_start, t_end;
    int      tid;
    volatile double sink;
    volatile uint64_t usink;
    char     pad[64];
} tctx_t;

static tctx_t CTX[MAXT];
static atomic_int g_arrive;
static atomic_int g_go;
static int g_T;
static int g_arm;      /* 0 = D, 1 = CPY, 2 = RDSUM */
static size_t g_nidx;

static void barrier(void)
{
    int n = atomic_fetch_add(&g_arrive, 1) + 1;
    if (n == g_T) { atomic_store(&g_arrive, 0); atomic_fetch_add(&g_go, 1); }
    else { int want = atomic_load(&g_go); while (atomic_load(&g_go) == want) { } }
}

static void *worker(void *arg)
{
    tctx_t *c = (tctx_t *)arg;
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
    barrier();
    c->t_start = now();
    if      (g_arm == 0) kern_D(c->y, c->idx, c->lut8, c->sc, c->ls);
    else if (g_arm == 1) memcpy(c->dst, c->idx, g_nidx);
    else                 c->usink = kern_rdsum(c->idx, g_nidx);
    c->t_end = now();
    if (g_arm == 0) { double s2=0; for (int i=0;i<M_ROWS;i++) s2+=c->y[i]; c->sink=s2; }
    else if (g_arm == 1) { c->usink = c->dst[0] + c->dst[g_nidx-1]; }
    return NULL;
}

static void alloc_ctx(int tid)
{
    tctx_t *c = &CTX[tid];
    if (c->idx) return;
    c->idx  = aligned_alloc(64, g_nidx);
    c->dst  = aligned_alloc(64, g_nidx);
    c->lut8 = aligned_alloc(64, (size_t)NV*4*64);
    c->sc   = aligned_alloc(64, M_ROWS*sizeof(float));
    c->y    = aligned_alloc(64, M_ROWS*sizeof(float));
    c->ls[0]= 1.0f/127.0f;
    c->tid  = tid;
    if (!c->idx || !c->dst || !c->lut8 || !c->sc || !c->y) {
        fprintf(stderr, "alloc failed tid %d\n", tid); exit(1);
    }
    unsigned seed = 1234u + (unsigned)tid*7919u;
    srandom(seed);
    for (size_t i=0;i<g_nidx;i++) c->idx[i]=(uint8_t)(random()&0xff);
    memset(c->dst, 0, g_nidx);
    for (size_t i=0;i<(size_t)NV*4*64;i++) c->lut8[i]=(int8_t)((random()%127)-63);
    for (int i=0;i<M_ROWS;i++) c->sc[i]=0.01f;
}

/* AGGREGATE source-read GiB/s for one rep */
static double run_rep(int T, int arm)
{
    pthread_t th[MAXT];
    g_T = T; g_arm = arm;
    atomic_store(&g_arrive, 0);
    atomic_store(&g_go, 0);
    for (int i=0;i<T;i++) pthread_create(&th[i], NULL, worker, &CTX[i]);
    for (int i=0;i<T;i++) pthread_join(th[i], NULL);
    double t0 = CTX[0].t_start, t1 = CTX[0].t_end;
    for (int i=1;i<T;i++) {
        if (CTX[i].t_start < t0) t0 = CTX[i].t_start;
        if (CTX[i].t_end   > t1) t1 = CTX[i].t_end;
    }
    double total_gib = (double)g_nidx * (double)T / 1073741824.0;
    return total_gib / (t1 - t0);
}

static int cmpd(const void *a, const void *b)
{ double x=*(const double*)a, y=*(const double*)b; return x<y?-1:(x>y?1:0); }

int main(int argc, char **argv)
{
    int T = (argc>1)? atoi(argv[1]) : 4;
    if (T<1||T>MAXT) T=4;
    g_nidx = (size_t)(M_ROWS/TILE)*NV*TILE*3;

    fprintf(stderr,"M_ROWS=%d  per-thread stream=%.2f MB  T=%d\n",
            M_ROWS,(double)g_nidx/1048576.0,T);
    for (int i=0;i<T;i++) alloc_ctx(i);
    fprintf(stderr,"allocated %d independent stream pairs (%.2f GB)\n",
            T,(double)g_nidx*2.0*T/1073741824.0);

    const char *names[3]={"D","CPY","RDSUM"};
    printf("{\n  \"m_rows\": %d,\n  \"nidx_bytes\": %zu,\n  \"T\": %d,\n  \"nrep\": %d,\n  \"arms\": {\n",
           M_ROWS,g_nidx,T,NREP);
    for (int arm=0; arm<3; arm++) {
        double r[NREP];
        run_rep(T,arm);                    /* warm/discard */
        for (int k=0;k<NREP;k++) r[k]=run_rep(T,arm);
        double mean=0; for(int k=0;k<NREP;k++) mean+=r[k]; mean/=NREP;
        double var=0;  for(int k=0;k<NREP;k++) var+=(r[k]-mean)*(r[k]-mean);
        double sd = NREP>1 ? sqrt(var/(NREP-1)) : 0.0;
        double srt[NREP]; memcpy(srt,r,sizeof r); qsort(srt,NREP,sizeof(double),cmpd);
        printf("    \"%s\": { \"mean_read_GiB_s\": %.4f, \"sd\": %.4f, \"min\": %.4f, \"max\": %.4f, \"median\": %.4f, \"reps\": [",
               names[arm],mean,sd,srt[0],srt[NREP-1],srt[NREP/2]);
        for(int k=0;k<NREP;k++) printf("%s%.4f",k?", ":"",r[k]);
        printf("] }%s\n", arm<2?",":"");
        fflush(stdout);
        fprintf(stderr,"  arm %-5s mean %8.3f GiB/s  sd %6.3f\n",names[arm],mean,sd);
    }
    printf("  }\n}\n");
    return 0;
}
