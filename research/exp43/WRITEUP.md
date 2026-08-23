# exp43 — objective routing for exp26's 66.06% prefill byte reduction (audit candidate #10)

**Verdict: CONFIRMED (routing claim).** All three preregistered deliverables quantified;
decode non-credit stated; reject gate not tripped.

**Evidence class: RECOMPUTATION over frozen PROXY/SYNTHETIC inputs. Zero hardware.
Deterministic, N=1 per arm (exact replay; variance reported across 3 split points, not
sampling noise). NO REAL-K3 MEASUREMENT.**

Inputs (all pinned):
- exp26 artifacts (sweep.out / variance.out, sha256 in exp26/SHA256SUMS)
- exp30 B_eff ladder (exp30_fixed_point.json; published dup4 points 19.634 / 16.569 /
  11.542 / 8.377 / 7.017 GiB/s — NOTE: spec parenthetical "19.634/9/12/18" matched no
  published table; the published table was used verbatim)
- exp40 miss mass: 18,786/62,400 = 30.106% LRU @ cap=1490 [PROXY]
- trace tests/trace_kimi_300.jsonl, sha256
  06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965
  (byte-identical to ~/e3-policy copy modulo trailing line; 300 tok x 26L x top-8)

Reproduction anchor: recomputed C=1→C=32 reduction = 66.06% exactly matches exp26's
published number (721.014 → 244.683 GiB per 300-tok prompt, 2.947x dedup).

## Deliverable 1 — TTFT saving per 300-tok prefill (476.332 GiB saved [PROXY])

At exp30's published dup-4x B_eff points [SYNTHETIC bandwidth x PROXY bytes]:

| B_eff GiB/s | bytes/tok | TTFT saved |
|---|---|---|
| 19.634 | 7.7190 | 24.26 s |
| 16.569 | 3.6704 | 28.75 s |
| 11.542 | 1.7453 | 41.27 s |
| 8.377 | 0.8299 | 56.86 s |
| 7.017 | 0.3946 | 67.88 s |

Caveat (correctness): exp30's B_eff(miss) is a DECODE barrier model; prefill has ~81
concurrent distinct experts per (chunk,layer) cell, not 0.37. Prefill-correct dup4 B_eff
= B_dev · E[k]/E[ceil(k/4)] = 5.919 · 81.45/20.75 = **23.230 GiB/s** → **TTFT saved
≈ 20.51 s per 300-tok prompt** [SYNTHETIC barrier model x PROXY cell stats]. The
decode-ladder rows bracket it. K3 prompt-bytes must be re-measured (shape caveat below).

## Deliverable 2 — measurement-loop multiplier [RECOMPUTATION over upstream fraction]

Upstream fraction frozen in spec: ~50 s per K3 measurement, ~48 s load+prefill,
bandwidth-bound. Dedup shrinks the 48 s:
- PROXY (trace 2.947x): 48 s → 16.29 s → **exp/hr ×2.734**
- REAL-K3 anchor (colibri measured 2.7x @ C=32, sha 33e67a9): 48 s → 17.78 s → **exp/hr ×2.528**

Real-K3 lane throughput roughly **doubles-to-triples**. This is the cheapest capacity
lever in the program: it multiplies every future Winnie experiment hour.

## Deliverable 3 — residency side-effect on decode E[k] [PROXY, deterministic]

LRU cap=1490, key=(layer,expert). Warm state = naive C=1 prefill vs dedup C=32 prefill
of tokens [0,split); decode-phase misses only (both arms replay the identical decode
sequence; phase-only counts, warm-phase excluded):

| split | naive warm decode misses | dedup warm decode misses | dE[k] |
|---|---|---|---|
| 150 | 9,476/31,200 (30.372%) | 9,396/31,200 (30.115%) | −0.844% |
| 200 | 6,351/20,800 (30.534%) | 6,284/20,800 (30.212%) | −1.055% |
| 250 | 3,074/10,400 (29.558%) | 2,997/10,400 (28.817%) | −2.505% |

Bound: **|dE[k]| ≤ 2.505% < 5%** at all splits; direction is slightly FAVORABLE (dedup
warm state marginally lowers decode misses). REJECT GATE NOT TRIPPED — prefill dedup is
NOT re-queued as a decode lever.

## Decode non-credit [RECOMPUTATION]

exp26's 66.06% is a prefill-phase reduction. At batch-1 decode C=1 dedup is exactly
1.000x on this trace (2.4034 GiB/tok == raw logical demand): decode bytes/token
unchanged by the mechanism. **Credit toward the 19.562x decode gap = 0.00x. The 66.06%
is NOT credited toward the decode objective.** It moves TTFT (D1) and lab throughput (D2).

## Shape caveat (inherited from exp26)

Trace is Kimi-Linear-shaped (26L x 256E x top-8), NOT K3 (92L x 896E x top-16).
Byte counts and dedup factors are PROXY; the colibri 2.7x REAL-K3 anchor bounds the K3
multiplier. TTFT seconds on real K3 prompts require a real K3 routing dump.

## Objective check

Optimized: correct attribution of a byte saving across the two algebraic terms of
`tok/s = B_eff / (physical bytes per accepted token)`. TTFT: prefill bytes ÷ B_eff —
algebraically direct (same bytes, same bandwidth). Loop cost: prefills ÷ hour — a
capacity term, not a decode-term credit. Decode: shown EXACTLY ZERO on the bytes
denominator (C=1 dedup = 1.000x), with the only indirect path (residency) bounded at
−2.5%..−0.8% miss rate. The routing claim is therefore algebraically complete: no term
of the decode objective is moved, two adjacent objectives are moved by 20.5 s TTFT and
×2.5–2.7 experiments/hour.
