# exp36 — Certified suppression under VQ4P gather: FALSIFIED before any kernel ran

Lane: `offline` (this Mac). Winnie at CPU 62.3% (3x Robocopy + MsMpEng + llama-server) → real_k3
exp22 released WITHOUT consuming an attempt. Pinned SHA `7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b`.
`E:\Projects\warp` untouched. This is a RECOMPUTATION over existing REAL-K3 and SYNTHETIC anchors.
No new benchmark was run, because the decisive numbers already exist.

## The load-bearing premise was already dead

exp36's prediction and arm composition were preregistered on **VQ4P kern_D delivering its 4.48x
single-thread kernel ratio in-engine**: arm2 = "VQ4P alone gives 13.349 tok/s at 10 cores (short)".

exp34 — the same pinned SHA, finished 2026-08-23 01:22, ~3h before exp36 was queued — measured the
opposite with REAL-K3 evidence (repo LEARNED §46/§47, medians of 13 VQ4P vs 5 VQ3R runs):

- end-to-end: 1.65 → 1.52 s/token = **1.086x** (not 4.48x)
- in-engine threaded scaling: 25.3 → 27.2 GB/s = **1.075x**
- cause: `waste_parallel_for` cuts one task per thread; VQ4P peaks on P-cores and degrades past
  them (91.3 → 73.2 GB/s) with an E-core straggler holding the barrier

exp36's spec itself carries the abort clause: *"If exp34 Stage 1 (distortion) fails, ABORT this
experiment ... the VQ4P arms become void."* exp34's distortion sub-gate landed inconclusive in the
spec's undefined 5–15% band (+10.82%), and the idea was falsified outright on its economic clause
(kern_D must beat kern_A by >=2.0x; measured 1.075x). Either reading voids the VQ4P arms.

## Recomputation with the MEASURED ratio [RECOMPUTATION over REAL-K3 anchors]

Substituting the measured ratios into exp36's own Stage-3 composition
(`tok/s = C × GiB/s/core × ratio / 17.0085 GiB/token`, C=10):

| arm | claimed | recomputed w/ measured VQ4P ratio |
|---|---|---|
| arm1 baseline (VQ3R, no certifier) | 2.978 tok/s @C=10 | 2.906 [recompute: 4.9427×10/17.0085; spec field used] |
| arm2 VQ4P alone | **13.349 tok/s** | **3.233** (end-to-end 1.086x) / 3.202 (threaded 1.075x) |
| arm5 VQ4P + all-selected certifier | ≥15.0 tok/s (accept gate) | **4.88 tok/s at best evidence-backed bound** |

Gates were not moved. The certifier can only REMOVE experts from the gather, so
`tok/s(arm5) ≤ tok/s(arm2) / (1 − s_cert)`.

## What the certifier can buy, from REAL-K3 margins

sprint11-route-margin-summary.json (92 layers, 6348 rows, sha256
`1cfd9927fce60aea5ec220405923641821537431e8e3ab599837f2300d772295`), log-linear interpolation of
`s_cert(B) = P(margin ≥ 2B)` per exp12's method:

| bound magnitude (score units) | s_cert (unconditional) | arm5 tok/s @C=10 |
|---|---|---|
| 9.687e-4 (exp12 reject-gate-1 inversion) | 0.2461 | 4.288 |
| **5.347e-4 (idea16's own accept-gate-2 bound)** | **0.3375** | **4.880** |
| 1.095e-4 (what 15 tok/s actually requires) | 0.7845 required | 15.0 by construction |
| 1e-4 (reference, NOT evidence-backed as achievable) | 0.8233 | 18.29 |

To clear the preregistered accept gate (arm5 ≥ 15.0 tok/s at C=10) the all-selected certifier must
suppress **78.45%** of selected experts, i.e. achieve bound ≤ 1.095e-4 — **4.9x tighter** than
idea16's own preregistered gate-2 bound. exp12 established (a) the achieved bound is not computable
from any existing artifact — it needs one real K3 expert's row norms and one batch of real hidden
states, and exhaustive search found neither on this Mac or Winnie; and (b) whitening must tighten
the Cauchy–Schwarz residual by ≥7.42x for the enabling signature to exist at all. The 1e-4 row is
arithmetic on the curve, not an achievable bound.

## Verdict

**FALSIFIED.** Accept gate clause (2) — "arm5 reaches >=15.0 tok/s at C=10 ... while neither arm2
nor arm4 does" — is unreachable at every bound magnitude with preregistered evidence backing:
arm5 ceiling = 4.880 tok/s, shortfall factor **3.07x**. The compute ceiling is a hard upper bound
on tok/s, so the mismatch-#9 fixed-point refinement cannot rescue it. The combination additionally
rests on a parent premise (4.48x VQ4P) that exp34's REAL-K3 measurement already refuted (1.086x).

Per the spec's stop rule ("Stop immediately and report NEGATIVE at the first reject-gate trip"),
Stages 2 and 3 microbenchmarks were NOT run. No kernel was written (kernel_requirement: none was
honored).

## What survives

- **idea16 standalone (miss-only certifier on VQ3R, arm3)** is NOT falsified by this run — this
  experiment only kills the *combination as specified* and the 15-tok/s-at-10-cores claim. Its
  standalone decision remains blocked on the exp12 blocker: the achieved bound is undecidable until
  one real K3 expert's row norms + one batch of real hidden states exist anywhere.
- The gather-time domain itself (mismatch #10) remains the right framing post-byte-program; this
  run changes nothing about the byte ledger (VQ3R→VQ4P leaves bytes exactly invariant, exp34 Stage 1).

## Queue hygiene finding (for the research job)

exp36 was queued at 04:36 with exp34's falsification (01:22) already recorded, yet it carried the
dead 4.48x in its prediction and had **no `experiment_deps` row on idea 32** — so `rq.py unblock`
could not auto-falsify it and it burned the top offline slot (and now two attempts). Combination
experiments should be queued with explicit dependency rows on their load-bearing parent ideas.

## Objective check

Optimized: gather **time** (ms/token) at fixed C, the mismatch-#10 time-domain framing.
Algebraic connection: `tok/s ≈ effective_bandwidth / bytes_per_accepted_token`. VQ4P leaves the
denominator EXACTLY invariant (exp34 Stage 1: byte-identical records), so it acts only on effective
bandwidth — REAL-K3 says +8.6%. The certifier acts on the denominator (fewer experts physically
read per accepted token) — algebraically a genuine byte lever — but the achievable suppression is
undecidable from existing artifacts and ≤33.75% (unconditional, REAL-K3 curve) at the only bound
magnitude with preregistered evidence backing, buying 1.51x where 4.64x was needed.

N/variance: deterministic recomputation, N=1, variance n/a. All stochastic inputs are cited
anchored measurements (REAL-K3 medians N=13/5; SYNTHETIC microbench N=5 sd 0.4549).
