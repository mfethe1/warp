/* SPDX-License-Identifier: Apache-2.0
 * Copyright 2026 SQLite Cloud, Inc.
 */
/*
 * test_vq_lut.c -- container-free correctness check for the VQ4P
 * (index_bits 6) portable kernel, waste_vq_rows_p6.
 *
 * PR #48 found that comparing a dispatched vq_rows_p6 against
 * WASTE_BACKEND=cpu diverges by 0.4-1.2 on real containers, and that this is
 * not a kernel defect: WASTE_BACKEND=cpu swaps every dispatched kernel in
 * the forward pass, so the float activations feeding that token's
 * vq_quant_range call differ by ordinary ~1e-6 cross-backend noise --
 * and vq_quant_range's scale (max_abs/127) amplifies noise that small into
 * a full LSB flip for any table entry sitting near a k+0.5 boundary. A
 * numeric tolerance on live-container output cannot tell that apart from a
 * genuinely broken kernel.
 *
 * This test removes the confound by holding the int8 LUT and the packed
 * indices FIXED -- hand-built here, never derived from a live forward pass
 * -- so there is no floating-point step left for two computations to
 * disagree on. It checks waste_vq_rows_p6's integer accumulation against an
 * INDEPENDENT reference computed in this file: same format macros (they
 * define the on-disk bit layout, not the algorithm under test) but a
 * separate summation loop, so a real bug in the engine's accumulation
 * cannot hide behind a shared implementation.
 *
 * Only the portable path is checked here (no AVX-512 VBMI or ARM NEON
 * hardware on this box to exercise kda_neon.c:100 or simd_avx512.c:129,
 * the other two dispatch-table slots for the same operation) -- that
 * comparison still needs hardware neither host in this exchange has.
 *
 *   cc -O2 -std=gnu11 -o test_vq_lut tests/test_vq_lut.c
 *   ./test_vq_lut
 */
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../src/simd.h"

/* model.c:1949 -- "must equal the container's index_block". Not in a
 * shared header, so restated here with its source cited rather than
 * pulling in the whole engine to get one constant. */
#define VQ_TILE 64
#define EN 64   /* validated at load; the tbl4 width -- model.c:2131 */
#define STAGES 4

extern void waste_vq_rows_p6(int b, int e, void *p);

/* Independent reference. Same P6_J0..P6_J3 macros (the on-disk format,
 * not the kernel), same addressing arithmetic as vq_rows_p6's own comment
 * describes, but summed in a separate loop that shares no object code with
 * the engine. */
static void reference(const int8_t *lut8, const float *lscale,
                       const uint8_t *idx, const uint16_t *scale, int nv,
                       int M, float *out)
{
    for (int r = 0; r < M; r++) {
        const int tile = r / VQ_TILE, rin = r % VQ_TILE;
        float acc = 0.0f;
        for (int v0 = 0; v0 < nv; v0 += WASTE_VQ_LUT_BLK) {
            int v1 = v0 + WASTE_VQ_LUT_BLK;
            if (v1 > nv) v1 = nv;
            int32_t sum = 0;
            for (int v = v0; v < v1; v++) {
                const int8_t *T = lut8 + (size_t)v * STAGES * EN;
                const uint8_t *ix =
                    idx + ((size_t)tile * nv + v) * VQ_TILE * 3 + rin * 3;
                const unsigned b0 = ix[0], b1 = ix[1], b2 = ix[2];
                sum += T[P6_J0(b0, b1, b2)] + T[EN + P6_J1(b0, b1, b2)] +
                       T[2 * EN + P6_J2(b0, b1, b2)] +
                       T[3 * EN + P6_J3(b0, b1, b2)];
            }
            acc += lscale[v0 / WASTE_VQ_LUT_BLK] * (float)sum;
        }
        out[r] = acc * waste_f16(scale[r]);
    }
}

static int g_fail = 0;

static void run_case(const char *name, const int8_t *lut8,
                      const float *lscale, const uint8_t *idx,
                      const uint16_t *scale, int nv, int M)
{
    float *got = (float *)malloc((size_t)M * sizeof(float));
    float *want = (float *)malloc((size_t)M * sizeof(float));
    vqp_arg a = {got, idx, scale, lut8, lscale, nv};

    waste_vq_rows_p6(0, M, &a);
    reference(lut8, lscale, idx, scale, nv, M, want);

    int bad = 0;
    for (int r = 0; r < M; r++) {
        /* Both sides do identical int32 accumulation, folded to float in
         * the same order per LUT block -- exact equality is the right bar,
         * not a tolerance, because there is no float step left to differ
         * on once the table is fixed. */
        if (got[r] != want[r]) {
            if (bad < 3)
                fprintf(stderr, "  row %d: kernel=%.9g reference=%.9g diff=%.9g\n",
                        r, (double)got[r], (double)want[r],
                        (double)(got[r] - want[r]));
            bad++;
        }
    }
    if (bad) {
        printf("FAIL %-28s %d/%d rows differ\n", name, bad, M);
        g_fail = 1;
    } else {
        printf("PASS %-28s (%d rows, %d vectors)\n", name, M, nv);
    }
    free(got);
    free(want);
}

/* Fills nv*STAGES*EN int8 entries deterministically from a simple LCG, so
 * every stage/entry combination gets exercised without hand-listing them. */
static void fill_lut(int8_t *lut8, size_t n, uint32_t seed)
{
    for (size_t i = 0; i < n; i++) {
        seed = seed * 1103515245u + 12345u;
        lut8[i] = (int8_t)((seed >> 16) % 255 - 127); /* -127..127, per the
            engine's own "-127 rather than -128" symmetry rule, model.c */
    }
}

int main(void)
{
    const int nv = 4, M = VQ_TILE; /* one full tile */

    /* Case 1: generic table, generic indices. */
    {
        int8_t lut8[4 * STAGES * EN];
        fill_lut(lut8, sizeof lut8, 0xC0FFEEu);
        float lscale[1] = {0.03125f}; /* nv=4 <= WASTE_VQ_LUT_BLK=32, one block */
        uint8_t idx[4 * VQ_TILE * 3];
        uint32_t seed = 0xBEEFu;
        for (size_t i = 0; i < sizeof idx; i++) {
            seed = seed * 1103515245u + 12345u;
            idx[i] = (uint8_t)(seed >> 16);
        }
        uint16_t scale[VQ_TILE];
        for (int r = 0; r < VQ_TILE; r++) scale[r] = 0x3C00; /* fp16 1.0 */
        run_case("generic-table-generic-idx", lut8, lscale, idx, scale, nv, M);
    }

    /* Case 2: every 6-bit index value 0..63 appears at least once across
     * j0..j3, all rows -- exercises the full table width, not just
     * whatever a random draw happened to touch. */
    {
        int8_t lut8[4 * STAGES * EN];
        fill_lut(lut8, sizeof lut8, 0x1234ABCDu);
        float lscale[1] = {1.0f};
        uint8_t idx[4 * VQ_TILE * 3];
        /* Pack (j0=r%64, j1=(r+7)%64, j2=(r+23)%64, j3=(r+41)%64) into the
         * 3-byte/4x6-bit layout by inverting P6_J0..P6_J3 by hand. */
        for (int v = 0; v < 4; v++) {
            for (int r = 0; r < VQ_TILE; r++) {
                unsigned j0 = (r + v) % 64, j1 = (r + v + 7) % 64;
                unsigned j2 = (r + v + 23) % 64, j3 = (r + v + 41) % 64;
                unsigned b0 = (j0 & 0x3f) | ((j1 & 0x03) << 6);
                unsigned b1 = ((j1 >> 2) & 0x0f) | ((j2 & 0x0f) << 4);
                unsigned b2 = ((j2 >> 4) & 0x03) | ((j3 & 0x3f) << 2);
                uint8_t *ix = idx + ((size_t)v * VQ_TILE + r) * 3;
                ix[0] = (uint8_t)b0; ix[1] = (uint8_t)b1; ix[2] = (uint8_t)b2;
                /* verify the hand-packing round-trips through the real
                 * macros before trusting this case at all */
                if (P6_J0(b0,b1,b2)!=j0 || P6_J1(b0,b1,b2)!=j1 ||
                    P6_J2(b0,b1,b2)!=j2 || P6_J3(b0,b1,b2)!=j3) {
                    fprintf(stderr, "SELF-CHECK FAILED packing v=%d r=%d\n", v, r);
                    g_fail = 1;
                }
            }
        }
        uint16_t scale[VQ_TILE];
        for (int r = 0; r < VQ_TILE; r++) scale[r] = 0x3C00;
        run_case("full-index-range", lut8, lscale, idx, scale, nv, M);
    }

    /* Case 3: extremes -127/+127 in the table, to catch any accumulator
     * width issue (int16 sum, per the engine's own comment: 4 stages x 32
     * positions x 127 = 16256, well under INT16_MAX). */
    {
        int8_t lut8[4 * STAGES * EN];
        for (size_t i = 0; i < sizeof lut8; i++)
            lut8[i] = (i % 2) ? 127 : -127;
        float lscale[1] = {1.0f};
        uint8_t idx[4 * VQ_TILE * 3];
        memset(idx, 0, sizeof idx); /* j0=j1=j2=j3=0 for every vector/row */
        uint16_t scale[VQ_TILE];
        for (int r = 0; r < VQ_TILE; r++) scale[r] = 0x3C00;
        run_case("extreme-values", lut8, lscale, idx, scale, nv, M);
    }

    /* Case 4: non-unit, non-power-of-two output scale, to make sure the
     * final f16 fold isn't accidentally hidden by a scale of exactly 1.0
     * in the earlier cases. */
    {
        int8_t lut8[4 * STAGES * EN];
        fill_lut(lut8, sizeof lut8, 0x9E3779B9u);
        float lscale[1] = {0.017f};
        uint8_t idx[4 * VQ_TILE * 3];
        uint32_t seed = 0xABCDEF01u;
        for (size_t i = 0; i < sizeof idx; i++) {
            seed = seed * 1103515245u + 12345u;
            idx[i] = (uint8_t)(seed >> 16);
        }
        uint16_t scale[VQ_TILE];
        for (int r = 0; r < VQ_TILE; r++)
            scale[r] = (uint16_t)(0x3800 + r); /* varies per row, near 0.5 */
        run_case("nonunit-output-scale", lut8, lscale, idx, scale, nv, M);
    }

    return g_fail;
}
