# exp46 — Non-uniform stage rate allocation (successive refinement) at constant 3.00 b/w: preregistered protocol INFEASIBLE under unmodified pinned vq.c; supplementary synthetic sweep refutes the front-loading prediction

**Verdict: INCONCLUSIVE (spec infeasible as preregistered) with a supplementary SYNTHETIC falsification signal on the idea's core prediction.**
Run: 2026-08-23 (cron warp-experiment-processor), lane `offline`, Mac M4, encoder pinned SHA `7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b` (vq.c sha256 `eb797e7c9c227f3fd29a6542ec0d557d646b5377e65297c835eb16151c360251`, byte-verified against the pinned clone at /tmp/warp-sources/warp/7f1fbba3).

## Why the preregistered protocol cannot be executed (Stage 0 feasibility)

The spec mandates: "using WARP src/vq.c UNMODIFIED at pinned SHA 7f1fbba3 … Sweep allocations {(8,8,8),(10,8,6),(12,8,4),(6,8,10),(4,8,12)}".

Structural reading of the pinned vq.c:

1. `waste_vq_encode` stores `(uint8_t)vq_step(...)` — index ids >255 are **truncated at store**.
2. `waste_vq_lloyd` stores assignments in `uint8_t asg[n]` — ids >255 **wrap and corrupt centroid recomputation**.
3. `entries` is a **single int shared by all stages** — per-stage sizes are not expressible in one call, and per-stage calls still hit the two uint8 walls above.
4. The spec's own Stage-0 geometry gate requires 3 index bytes/vector and record = 12,406,784 B = 3029 pages for EVERY allocation; only byte-aligned per-stage codes (i.e. 8/8/8) fit that record format. A 10-bit stage needs a sub-byte-tail packing the record format does not have.

Empirical confirmation (RECOMPUTATION, N=32,768 synthetic vectors, seed 46, sanity-checked: 100% id agreement between pinned encoder and exact numpy argmin at 256 entries):

| entries requested | Lloyd live clusters | encoder code max | pinned-encoder rel-err | exact-argmin rel-err (same book) | id agreement |
|---|---|---|---|---|---|
| 256  | 256  | 255  | 0.5791 | 0.5791 | 100.0% |
| 512  | 256  | 255  | 0.7160 | 0.5596 | 55.5% |
| 1024 | 256  | 255  | 0.8720 | 0.5126 | 17.8% |

The pinned encoder cannot use a >256-entry stage: Lloyd keeps exactly 256 live clusters (orphaned ids are unreachable dead weight), the encoder can never emit an id >255, and the exact-argmin oracle shows the extra entries DO carry signal (rel-err 0.5126 vs 0.5791 at 1024) — the ceiling is the API, not the statistics. Verdict on the preregistered protocol: **inconclusive — wrong spec**, per procedure rule 3. The research job should requeue a corrected version (see NEXT).

## Supplementary sweep (SYNTHETIC — NOT a gate evaluation)

To inform the requeue decision, I ran the preregistered allocations with a numpy reimplementation of the same Lloyd family (128×3072 weight sample, 5 seeds, 8 iterations, activation-weighted relative error, same generator/covariance family as exp34 stage 2; reduced rows for numpy k-means cost):

| allocation | aw err mean | vs (8,8,8) |
|---|---|---|
| (8,8,8) uniform | 0.19444 ± 0.00378 | baseline |
| (10,8,6) front | 0.18893 ± 0.00362 | **−2.83%** (better) |
| (12,8,4) front | 0.17070 ± 0.00344 | **−12.21%** (better) |
| (6,8,10) back | 0.18691 ± 0.00426 | **−3.88%** (better) |
| (4,8,12) back | 0.16565 ± 0.00317 | **−14.80%** (better) |

Label: SYNTHETIC, N=5 seeds, sd shown. Two takeaways:

- **Every interior allocation beats uniform (8,8,8)** — successive-refinement structure IS present, but…
- …quality is **TAIL-loaded, not front-loaded**: (4,8,12) −14.8% beats (12,8,4) −12.2%, and (6,8,10) −3.9% beats (10,8,6) −2.8%. The idea's prediction — "quality is front-loaded, speed is tail-loaded, an interior front point dominates" — has its quality half **refuted** on synthetic data: the error-optimal direction is back-loading, which buys no tail-gather speedup (tail table stays 256 or grows). The mechanism as pitched (front-load precision, shrink the tail for kern_D-style gather) sacrifices ~2.5pp of the available error improvement.

Caveat: synthetic weights/covariance, numpy k-means (not the pinned encoder), reduced rows. This is a directional signal, not a gate verdict.

## Objective check

The idea optimizes the **denominator-side quality at constant bytes**: bytes/vector stays 24 bits for every allocation, so physical bytes per accepted token is EXACTLY invariant (same argument as exp34 Stage 1); the only lever is distortion at fixed rate, which feeds the semantics/pricing side (KL + continuation agreement) rather than tok/s directly. Algebraic connection: none to bytes/accepted token or effective bandwidth — this is a quality-at-equal-bytes experiment. The tail-shrink speed story would connect via gather throughput (kern_D 4.7–4.9x), but only for front-loaded allocations, which the sweep says are the quality-inferior direction.

## Evidence

- `~/.hermes/state/warp-research/evidence/exp46/`: exp46_probe.py, exp46_out.json (sha256 8e1ca2dd…), exp46_sweep.py, exp46_sweep.json (sha256 9d676f52…), SHA256SUMS
- Pinned source: /tmp/warp-sources/warp/7f1fbba3 (vq.c hash-verified)
- Repo: mfethe1/warp branch `research/exp46-stage-rate-allocation` (commit with this writeup + scripts)

## NEXT (for the research job)

1. The preregistered form is dead (unmodified-encoder constraint unsatisfiable); if requeued, it must either (a) modify vq.c (uint16 codes / per-stage entries) and re-run the geometry gate with the new record format, or (b) restrict to ≤8-bit stages — where the only constant-24-bit allocation is uniform (8,8,8) itself, making the idea vacuous. Requeue cost is a vq.c patch + convert re-run.
2. If requeued with a modified encoder, the sweep predicts the interesting axis is **back-loading** ((4,8,12) −14.8% SYNTHETIC): a bigger tail table trades quality for gather cost with zero byte movement — but note kern_D speedups live in the *opposite* corner, so the quality/speed Pareto frontier must be measured, not assumed.
3. Both directions are pure denominator-quality plays; they do not advance the 15 tok/s bandwidth goal directly and should be prioritized accordingly.
