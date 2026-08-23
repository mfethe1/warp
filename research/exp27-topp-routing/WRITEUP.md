# exp27 — Adaptive top-p routing (K3_TOPP analogue) — FALSIFIED at quality contract

**Verdict:** falsified (reject gate: "cannot reduce experts materially without exceeding the KL bar")
**Lane claimed:** real_k3 → executed offline (recomputation on REAL-K3 router trace). Winnie busy (CPU 54%, llama-server + coding-loop python), but no Winnie run needed: the decisive artifact already existed locally.
**Trace:** `from-winnie/k3_scores_24tok_decode.txt.gz` — REAL-K3 router sigmoid scores, 24 decode tokens × 92 layers × 896 experts = 2,208 routing decisions (sha256 c2cbf991cbd55dc801cfcdce610d292329b670118acaa4e44f1bf7188fb6df0d).
**Colibri semantics pinned from source** `c/kimi_k3.c` @ 33e67a9c004b6e608d1f19dfbdcc20793377f94f (lines 1775–1810): top-16 by sigmoid(score)+rbias → normalize → sort desc → keep minimal prefix with cum ≥ p → renormalize. rbias not present in trace → assumed 0 (affects which 16 are selected, not the mass-concentration conclusion; top-1 mass 14.4% ± 5.8% is flat under any per-expert affine shift that preserves ranking scale).

## Result (REAL-K3 trace, recomputed; N=2208, sd noted)

| p | experts/token | reduction | KL = −log(cum) | GiB/token |
|---|---|---|---|---|
| 0.50 | 563.0 | 61.8% | 0.636 | 6.505 |
| 0.70 | 898.1 | 39.0% | 0.322 | 10.378 |
| 0.85 | 1193.9 | 18.9% | 0.135 | 13.795 |
| 0.90 | 1299.5 | 11.7% | 0.080 | 15.015 |
| 0.95 | 1401.8 | 4.8% | 0.030 | 16.198 |
| **0.97707 (=KL bar 0.0232)** | **1471.5** | **0.03%** | **0.00012** | **17.003** |

Gate quote (accept): ">=15% expert-count reduction at KL <=0.0232". At the bar: reduction **0.03%** (keep histogram: 2196/2208 decisions keep all 16). To reach the 15% reduction you need p≈0.85 → KL 0.135, **5.8× over the bar**. The mixture-weight KL is itself an *optimistic lower bound* on true output divergence, so the falsification is robust.

## Why
K3 router mass is flat: mean cumulative mass top-1 = 0.144, top-8 = 0.629, top-12 = 0.823. There is no concentrated head to truncate — the 16th expert still carries ~0.9% mass on average, and dropping it costs −log(1−0.009) ≈ 0.009 per (token,layer), accumulating over 92 layers.

## Four gates (external source: colibri)
1. **REPRODUCTION: PASS.** Colibri's own claim ("--topp 0.7: 30–40% less disk", docs/tuning.md:12) reproduces exactly on the real trace: p=0.7 → 39.0% fewer experts, 10.378 vs 17.009 GiB/token logical.
2. **TRANSFER: N/A-quality / FAIL-contract.** The mechanism is pure router selection logic, transfers trivially to VQ3R/batch-1/O_DIRECT — no format or kernel coupling. But it cannot satisfy WARP's quality contract.
3. **OBJECTIVE: FAIL.** At the quality bar the bytes/token saving is 0.03% (~5.7 MiB/token ≈ 0.95 ms at 5.919 GiB/s); the goal needs 41.6%.
4. **SEMANTICS: FAIL at any useful p.** Selection-affecting; KL at the cheapest 15%-saving point is 5.8× the accepted CCR bar (and mixture-KL is a lower bound). "Source claim REPRODUCED but NOT TRANSFERABLE to the quality contract" — recorded as such.

## Objective check
Optimizes logical bytes/token via experts kept per (token,layer): bytes/token = 92 × k̄ × 12,406,784 B — algebraically the demand-side term of tok/s = bandwidth / bytes-per-accepted-token. Directly connected; the lever itself just doesn't move far enough under the KL constraint.

## Caveats
- N=24 tokens, single decode context; sd of the mass statistics is small (0.018–0.080) and the gap to the gate is 3 orders of magnitude in reduction, so sample size cannot flip the verdict.
- rbias assumed 0 (not in trace).
- Greedy continuation agreement not computed: moot, since the KL gate already fails decisively.

## Bookkeeping bug found
Queue linkage error: exp27's spec/baseline/gates all describe adaptive top-p routing, but `idea_id=1` links to idea "kinetic-proofreading-certified-skip" (certified residual skipping), and slug/title/falsifier shown at claim time come from the idea, not the spec. The spec is internally coherent and was executed as written; the idea_id should be repointed by the research job.

## Artifacts
- `exp27_topp_analysis.py` — analysis script
- `exp27_topp_output.txt` — raw output log
- `exp27_topp_sweep.json` — machine-readable sweep + gate result
- sha256 in SHA256SUMS.txt
