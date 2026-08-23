# exp20 — gather-bound-verifier-audit

**Verdict: CONFIRMED** (the I/O-bound premise survives, with one important caveat)

Source SHA (WARP): `7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b` (mfethe1/warp, main)
Platform: Apple M4, 4 P-cores + 6 E-cores, 4 MiB L2. Single-threaded measurement.
Date: 2026-08-22

## What was actually measured

The preregistered spec asked for "the VQ3R 3-bit-index -> dim-8 codeword dequant
inner loop". Reading the pinned source first changed the shape of the experiment:

- `src/vq.c` is the **encoder** only (Lloyd + residual assignment, used by
  `tools/convert.py`). It is not on the decode path at all.
- `src/simd.h` line 8 states the decode hot path is *"a gather (the VQ apply,
  which no SIMD helps — see LEARNED.md §12)"*.
- `src/waste_format.h` line 65 confirms *"the VQ3R gather is scalar."*

So there is no separate "dequantize to a buffer" step to benchmark. VQ3R never
materializes dequantized weights; the codeword lookup is **fused into the
matvec** as a scalar gather-accumulate. The correct object of the audit is
therefore that fused gather, and WARP already ships the exact microbenchmark for
it: `tools/lutbw.c`, whose `kern_A` **is** the shipping VQ3R kernel
(3 stages x 256 entries, fp32 table, scalar gather). Per the "reuse, do not
rewrite" rule it was compiled and run verbatim — zero source modification.

Geometry check: NV=448 = 3584/8 (in-dim / vec_dim), TILE=64, 3 index bytes per
8-dim vector. At M_ROWS=9216 the index stream is 12,386,304 B, within 0.17% of
the established expert record of 12,406,784 B — the benchmark is already sized
to one expert.

## Results [RECOMPUTATION / SYNTHETIC microbenchmark, zero I/O, N=5 per config]

Throughput is measured over **index bytes consumed**, which is the physical byte
stream the 5.919 GiB/s disk figure also denominates — so the two are directly
comparable without conversion.

| index stream | resides in | VQ3R kern_A GiB/s/core | sd | VQ4P kern_D GiB/s/core | sd |
|---|---|---|---|---|---|
| 3.94 MB (M=3072) | L2-resident | 3.925 | 0.978 | 16.813 | 2.779 |
| 11.8 MB (M=9216, ~1 expert) | L2 spill | 5.405 | 0.489 | 22.889 | 2.694 |
| **252 MB (M=196608)** | **DRAM** | **5.065** | **0.085** | 22.705 | 2.427 |

The 252 MB row is the decisive one: it is the only configuration whose working
set cannot sit in cache, which is the regime the engine actually runs in
(~17 GiB of index stream per token). It is also the tightest (sd 0.085, 1.7% rel).
The 3.94 MB row has sd 0.978 — 25% relative — driven entirely by a cold first
rep (2.042 GiB/s); it is reported for completeness but not used for the gate.

### Preregistered gates, quoted

> ACCEPT the I/O-bound premise if rate >= 2.0 GiB/s/core (cores_required <= 3.0
> at 5.919 GiB/s), implying c < 0.10 and exp17's 2.000x eroding by less than 5%.

> REJECT (premise falsified) if rate < 0.75 GiB/s/core, implying cores_required
> > 7.9 and a colibri-scale compute component.

Measured **5.065 GiB/s/core**, sd 0.085, N=5.
- ACCEPT threshold (>= 2.0): **PASS**, by 2.5x margin.
- REJECT threshold (< 0.75): not triggered, by 6.8x margin.
- cores_required @ 5.919 GiB/s = **1.169**  (gate allowed <= 3.0) — PASS
- cores_required @ 11.838 GiB/s = **2.337** (still <= 3.0) — PASS

colibri's 27.6% batch-1 compute component **does not transfer** to WARP's VQ3R
gather at these rates.

## The caveat the gate did not anticipate: one core is not enough

Per token, physical demand is 7.719 GiB. At 5.065 GiB/s/core a single core needs
**1524.0 ms** to gather it, versus 1304.1 ms of disk time. So on ONE core the
verifier is *compute* bound, not I/O bound:

| cores | 1xSSD (5.919) | 2xSSD (11.838) |
|---|---|---|
| 1 | io 1304.1 / cp 1524.0 -> **1524.0 COMPUTE** | io 652.1 / cp 1524.0 -> **1524.0 COMPUTE** |
| 2 | io 1304.1 / cp 762.0 -> 1304.1 I/O | io 652.1 / cp 762.0 -> **762.0 COMPUTE** |
| 3 | io 1304.1 / cp 508.0 -> 1304.1 I/O | io 652.1 / cp 508.0 -> **652.1 I/O** |
| 4 | io 1304.1 / cp 381.0 -> 1304.1 I/O | io 652.1 / cp 381.0 -> **652.1 I/O** |

**exp17's dual-SSD 2.000x is safe from 3 cores upward** and fully realized there;
at 2 cores it degrades to 1.71x; at 1 core it vanishes entirely (1.00x). Since
the target machine has 4 P-cores and 10 total, the lever holds. But "100% I/O
bound" is only true given >= 3 cores dedicated to the gather — it is a
*parallel* claim, not a scalar property of the kernel, and any future design that
spends cores elsewhere (or runs on a 2-core budget device) re-enters the
compute-bound regime.

Note on the spec's own `c` formula: it defines
`c = min(1, cores_required/available_cores)`, which at 4 cores yields c=0.2922 and
predicts 1.548x. That formula treats compute as a *serial fraction added to* I/O
time, but the engine overlaps gather with O_DIRECT reads, so the correct model is
`t = max(io, compute)`, not a weighted sum. Under the overlap model the answer is
a clean 2.000x at >= 3 cores. Both numbers are reported; the max() model is the
physically correct one and the sum model is preserved only because it was
preregistered. This does not move the gate — the gate was on **rate**, and rate
passed by 2.5x under either interpretation.

## Free finding: VQ4P is 4.48x faster than VQ3R at identical bit rate

kern_D (VQ4P: 4 stages x 64 entries, int8 table, `vqtbl4q` NEON table lookup)
sustains 22.705 GiB/s/core vs VQ3R's 5.065 — a **4.48x** speedup at *exactly the
same 3.00 bits/weight and the same three index bytes per vector*
(`waste_format.h` line 57-65). This costs zero bytes/token: same denominator,
same physical read volume. It is not on the critical path today (I/O bound at
>= 3 cores), so it buys nothing right now — but it is what makes the 1-2 core
regime and any >= 3x bandwidth increase safe. If a future experiment doubles
bandwidth again beyond dual-SSD, VQ3R becomes the binding constraint at 5.065
GiB/s/core and VQ4P is the ready answer.

## Objective check

Objective: `tok/s ~= aggregate_effective_bandwidth / physical_bytes_per_accepted_token`.

This experiment optimized **neither** term. It is an audit that tests whether the
denominator-side arithmetic (the "1% bytes = 44.7 ms" budget) and the
numerator-side lever (exp17 dual-SSD 2.000x) rest on a sound premise. The
algebraic connection is that both established results silently assume
`t_token = physical_bytes / bandwidth` with no additive compute term, i.e. that
`max(io, compute) == io`. The measurement confirms this holds at >= 3 cores
(compute 508.0 ms < io 652.1 ms even in the dual-SSD regime) and fails at 1 core.
So: the existing byte-accounting budget is **validated, conditionally on core
count >= 3**, and no established number needs re-denominating.

## Reproduction

```
gh api repos/mfethe1/warp/contents/tools/lutbw.c?ref=7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b
cc -O3 -mcpu=native -DM_ROWS=196608 -o lutbw_196608 lutbw.c -lm
for i in 1 2 3 4 5; do ./lutbw_196608; done
python3 analyze.py
```
