# exp10 — Certified-skip × option-value-prefetch: FACTORIAL (FALSIFIED)

**Verdict: falsified.** The interaction term is **identically zero** on the
bytes/accepted-token objective at *every* published operating point, and strictly
negative with any prefetch over-read.

## Method (cheapest decisive form)

RECOMPUTATION over the **REAL-K3** route-margin distribution
(`docs/gn100/sprint11-route-margin-summary.json`: 92 layers, 6,348 rows,
69 positions, 0 exact boundary ties) crossed with the byte algebra of the expert
record from exp5. Stall counting uses the in-repo ordered **PROXY** trace
(`tests/trace_kimi_300.jsonl`, 62,400 accesses, 5,083 distinct, LRU at the
K3-equivalent 3.41× working set). No engine change, no Winnie compute.

Rather than cherry-pick one operating point, the whole published
`score_error_risk` curve is swept — the uncertifiable tail spans 0.221 % → 100 %.

## Results

| max score err | tail % | skip rate s % | gain(A) B/tok | gain(B) | **interaction** | bytes(A+B)/bytes(A) | GiB/tok arm A |
|---|---|---|---|---|---|---|---|
| 1e-06 | 0.221 | 99.779 | 6,064,142,959 | 0 | **0** | 1.0000 | 5.1559 |
| 1e-05 | 1.985 | 98.015 | 5,956,914,666 | 0 | **0** | 1.0000 | 5.2012 |
| 1e-04 | 17.675 | 82.325 | 5,003,348,769 | 0 | **0** | 1.0000 | 5.6043 |
| 1e-03 | 75.803 | 24.197 | 1,470,559,455 | 0 | **0** | 1.0000 | 7.0974 |
| 1e-02 | 99.512 | 0.488 | 29,679,260 | 0 | **0** | 1.0000 | 7.7065 |
| 5e-02 | 100.000 | 0.000 | 0 | 0 | **0** | 1.0000 | 7.7190 |
| 1e-01 | 100.000 | 0.000 | 0 | 0 | **0** | 1.0000 | 7.7190 |

PROXY stall base: 18,786 cold misses / 62,400 accesses = 30.106 % miss rate at
capacity 1,490.

Best arm-A byte position: **5.1559 GiB/token** [RECOMPUTATION] vs the
**0.3946 GiB/token** required for 15 tok/s — short by **13.1×**. Certified-skip
alone does not reach the goal even at a 99.779 % skip rate.

## Gate

Preregistered accept gate, verbatim:

> interaction = gain(A+B)-gain(A)-gain(B) > 0 AND bytes(A+B) <= bytes(A)
> [no net extra bandwidth] AND tail-cold stall count of A+B < A by >20%.

Condition 1 **fails everywhere**: max interaction over the entire sweep = 0.0,
min = 0.0. Conditions 2 and 3 are satisfiable but moot — the conjunction cannot
be met. The reject gate is met: the interaction is inert; do not combine.

Note the reject gate's stated *reason* ("tail <5 % of reads") is not what killed
it. At 1e-03 the tail is 75.8 % of reads — enormous — and the interaction is
*still* exactly zero. The gate reaches the right verdict for the wrong reason.

## Why this is structural, not empirical

    B_acc = M * (RECORD_B - s*PLANE_B*(1 - overread)) / a

Prefetch enters `B_acc` **only** through `overread`, the pages it pulls that the
skip verdict omits:

    dB_acc/d(overread) = +M*s*PLANE_B/a  >=  0

Prefetch changes **when** a page is read, never **whether**. Therefore
`gain(B) == 0` and `gain(A+B) == gain(A)` identically, so

    interaction = gain(A+B) - gain(A) - gain(B) == 0

for every tail size, every cache capacity, and every trace. No measurement can
make it positive. Prefetch buys only latency hiding — a different objective, and
one already foreclosed by the established 100 % I/O-bound verifier finding: with
the bus saturated there is no idle bandwidth to prefetch into.

## Consequence for the queue

This retires the whole *prefetch-as-byte-optimizer* family by algebra rather than
by one experiment at a time. **exp4** (option-value-prefetch) and **exp6**
(chaperone-plus-EV-prefetch) inherit `gain(B) == 0` and should be requeued as
latency-only studies or dropped. Any surviving idea must delete bytes —
skip them, shrink them, or reuse them — not reschedule them.
