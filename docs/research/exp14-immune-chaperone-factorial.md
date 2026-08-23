# exp14 — Miss-conditioned output reuse × scan-resistant admission (FACTORIAL) — FALSIFIED

**Verdict: falsified (REJECT — dominated component).** The combination is strictly
dominated by arm A alone at every r_reuse in the preregistered sweep; arm B
(idea3 segmented admission) is **negative on its own** on the frozen proxy trace.

All numbers below are **PROXY** (frozen `tests/trace_kimi_300.jsonl` replay,
cap 709 = 3.41×WS, Kimi-Linear-shaped, NOT K3). r_reuse values are **ASSUMED
parameters, not measurements** — no per-expert activation/output trace exists
(idea19's own falsifier carries a HARD STOP on promoting without one; the
from-winnie `k3_hidden` dump is per-layer residual x, 24 samples, rank-deficient,
and contains no expert outputs).

## Baseline reproduction
A0 plain LRU cap 709: **27,979 misses / 62,400 accesses** — exactly the frozen
exp4 figure. preads/miss = 1.000. Determinism verified (two runs byte-identical;
crc32-keyed suppression, not salted `hash()`).

## Falsifier (overlap), computed FIRST
| r_reuse | \|Sup\| | \|Conv\| | ∩ | overlap |
|---:|---:|---:|---:|---:|
| 0.05 | 1,070 | 4,184 | 188 | 0.176 |
| 0.10 | 2,231 | 4,184 | 397 | 0.178 |
| 0.20 | 4,491 | 4,184 | 813 | 0.194 |
| 0.40 | 9,091 | 4,184 | 1,689 | 0.404 |

Overlap ≤ 0.40 < 0.70 at every r → falsifier does NOT fire; byte arms run.

## Arm results (S1 primary)
SLRU split was not preregistered → swept {0.5, 0.6, 0.7, 0.8}; **best-for-B split
is 0.7 and is still net-negative**: converted = **−1,581 misses (−5.651 pp)**.
(0.5: −1,747; 0.6: −1,631; 0.8: total collapse, 62,400 misses — probation capacity
142 slots < per-token working set 208, the working-set cliff, a real phase
transition verified separately.)

| r_reuse | gain(A)% | gain(B)% | gain(A+B)% | interaction pp |
|---:|---:|---:|---:|---:|
| 0.05 | +3.824 | −5.651 | **−1.580** | +0.247 |
| 0.10 | +7.974 | −5.651 | **+2.916** | +0.593 |
| 0.20 | +16.051 | −5.651 | **+11.609** | +1.208 |
| 0.40 | +32.492 | −5.651 | **+29.265** | +2.423 |

**gain(A+B) < gain(A) at every r** — adding segmentation strictly subtracts from
the suppression gain. S2 sensitivity (r=0.05): A1 +2.83%, A3 −2.06% — magnitude
changes, ordering does not; S1/S2 agree on the verdict, so no exp13-style
inconclusive.

## Reject gate clauses fired
- "gain(A+B) fails to exceed the larger single parent by ≥ 0.5pp" — fires at every r.
- "gain(A+B) < 2.13% of baseline bytes" — fires at r=0.05 (−1.58%).
- Overlap clause did NOT fire (0.18–0.40). Preads-per-non-suppressed-miss = 1.000
  in all arms (invariant clean).

## Why B fails here (mechanism, not mystery)
Segmentation converts 4,184 positions to hits but **corrupts 5,765 positions**
that plain LRU had retained (net −1,581): protecting reuse-proven entries evicts
entries LRU would have kept, and on this trace the eviction loss exceeds the
scan-resistance win. Consistent with the established DEAD finding "cache
replacement tuning": LRU trails Belady 17.54pp, but SLRU moves in the wrong
direction. idea3's premise (recover part of the 17.54pp gap) is falsified *for
segmented admission specifically* — the gap remains real, the mechanism is not.

## Objective check
Optimized: physical bytes/accepted token = (non-suppressed misses × 12,406,784 B)/token
under identical resident budget (idea19 library charged at 6,144 B/pair, 2
slot-equivalents at the 4,096-pair cap, subtracted from A3's SLRU capacity).
Algebraically connected: bytes/accepted-token is the objective term; B_arm's
contribution is negative in that exact metric. The verdict is **independent of
the assumed r_reuse** because B harms the metric at every r.

## Consequence for parents
- **idea3 (chaperone-scan-resistant-admission): falsified on the only trace the
  family is runnable on** — its own experiment should be finished as falsified or
  the research job should preregister a different trace before requeueing.
- **idea19 (immune-memory): remains unmeasured** (HARD STOP stands: needs a
  chronological per-expert (key, output) trace; none exists; k3_hidden is 24
  samples/layer of residual x — Winnie estimated ≥7,168 tokens ≈ 15 h decode for
  full-rank Σ_x). The parametric A-arm table above bounds what any r would buy
  and confirms it cannot be a sole lever (needs r ≈ 94.9%).

## Provenance
- Trace: tests/trace_kimi_300.jsonl, sha256 06ad026c928d1c05… (full hash in JSON).
- Script: exp14_factorial.py (deterministic, crc32-keyed); result: exp14_result.json;
  SHA256SUMS covers both.
- Source SHAs pinned: warp trace per repo; established constants (RECORD=12,406,784 B,
  cap 709, 27,979) reproduced from exp4/exp10 evidence.
