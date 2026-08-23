# exp22 — VQ3R INDEX-ENTROPY CENSUS (verdict: FALSIFIED / REJECT)

**Run:** 2026-08-23 ~11:45 EDT. Lane real_k3 (read-only histogram on Winnie).
**Source:** E:\models\k3.waste, format code from E:\Projects\warp (READ-ONLY,
never modified). Convert writer: tools/convert.py `write_expert_record` /
`block_indices`; layout header: src/waste_format.h (WQ_VQ3R=4).

## Preregistered gates (from rq spec, unmodified)
- accept: net page-rounded reduction >= 5%
- reject: net reduction < 5% -> "reproduced but not transferable", close rANS line, NO codec, NO kernel
- stop rule: stop after 3 layers if entropy > 7.6 bits/symbol

## What was measured [REAL-K3, N=32 experts/layer x layers {1, 46, 92}, 44M symbols/cell]

Marginal entropy per (matrix, stage), from exact byte histograms over
48 records x 3 segments x 3 stages. Blocked index layout [nb, nvr, 64, 3]
means stage bytes stay adjacent per vector: stage = offset%3; blocking is a
permutation so marginals are exact.

| layer | matrix | H(stage0) | H(stage1) | H(stage2) | combined |
|---|---|---|---|---|---|
| 1  | gate | 7.9718 | 7.9680 | 7.8902 | 7.9816 |
| 1  | up   | 7.9715 | 7.9707 | 7.8939 | 7.9834 |
| 1  | down | 7.9743 | 7.9723 | 7.9000 | 7.9859 |
| 46 | gate | 7.9766 | 7.9783 | 7.9181 | 7.9863 |
| 46 | up   | 7.9770 | 7.9774 | 7.9150 | 7.9871 |
| 46 | down | 7.9779 | 7.9801 | 7.9172 | 7.9869 |
| 92 | gate | 7.9710 | 7.9615 | 7.8826 | 7.9786 |
| 92 | up   | 7.9735 | 7.9765 | 7.8988 | 7.9858 |
| 92 | down | 7.9771 | 7.9765 | 7.9044 | 7.9845 |

All 27 cells: 7.88–7.99 bits/symbol, far above the 7.6 stop threshold —
stop rule fired. Prediction in the spec ("trained k-means over 256 entries =>
near-uniform, ~8 bits, rANS gain ~0") CONFIRMED.

## Joint-entropy upper bound [REAL-K3, gate matrix, layer 46, 32 experts, N=44,040,192 triples]

The strongest possible coder could exploit correlation BETWEEN the three
stage bytes of one vector (16.7M-symbol joint alphabet):
- H(s0,s1,s2) = 22.8225 bits vs 24 raw = **4.906% symbol saving — theoretical
  ceiling, still below the 5% gate**
- distinct triples seen: 10,496,804 of 16,777,216 (62.6% of joint space)
- per-record best case: 11,778,574 B payload vs 12,386,304 raw -> 2,881 pages
  vs 3,029 -> 4.89% net page-rounded — under gate, and this assumes an
  absurd 16.7M-entry coder model

## Verdict per reject gate
Net reduction < 5% at every level of the bound ladder:
1. marginal-only rANS: ~0.2% saving
2. per-vector joint: 4.91% ceiling (impractical alphabet)
3. page-rounded with realistic coder: ~0.2%, joint theoretical 4.89%

Colibri's ~0.76 int4 ratio comes from its 15-effective-symbol alphabet;
VQ3R indices are trained k-means codes over 256 entries and are
near-uniform. Source mechanism REPRODUCED (their skew exists), NOT
TRANSFERABLE (our indices have no skew to harvest).

## Objective check
Optimizes: physical bytes per expert record -> bytes per accepted token.
Directly connected: record bytes ARE the physical bytes fetched per expert
activation; a >=5% cut would have cut GiB/token by the same fraction.
No codec, no kernel written — the no-kernel gate held.

## Repro
- exp22_entropy_census.py / exp22_joint.py piped via stdin to winnie python
- read-only pread of headers + index segments; no writes anywhere
- sha256 in SHA256SUMS; census_raw.json is raw output
