# exp32: Certifier × SLRU hedge factorial — FALSIFIED (reject gate fired)

**Experiment:** exp32 / idea30 — certifier-bypass-starvation-chaperone-hedge
**Verdict:** falsified (attempt 2/3; reject gate fired exactly as preregistered)
**Lane:** offline (this Mac). **Evidence class:** PROXY closed-loop replay (Kimi-Linear-shaped trace, 26L × top-8, NOT K3) × RECOMPUTATION (Bernoulli certification draws).

## Setup (frozen before running)

- Trace: `tests/trace_kimi_300.jsonl`, sha256 `06ad026c…4965` (pinned, verified).
- Cap 709 slots = 3.41× WS (5015/1472 × 208), record B = 12,406,784 B (exp5-verified).
- Closed loop: each arm's own bypass decisions feed its own cache state (exp18 semantics). Position-stamped Bernoulli certification draws, seeds 1–5, matched across arms.
- SLRU: protected/probationary, promote on 2nd reference, protected fraction ∈ {0.5, 0.7, 0.9}.
- Primary metric B_replay = closed-loop physical GiB per accepted token. B_frozen = same arm's cert draws applied to the frozen baseline miss vector (open-loop diagnostic). eps_B = (B_replay − B_frozen)/B_frozen.

## Results

Baseline LRU: **B_replay 1.0776 GiB/tok**, hit 0.5516, 27,979 misses (deterministic).

### Stop rule first — arm A eps_B sweep [PROXY × RECOMPUTATION, N=5 seeds]

| s | B_replay | B_frozen | eps_B | s_eff |
|---|---|---|---|---|
| 0.05 | 1.0365 | 1.0240 | +1.22% | 0.050 |
| 0.10 | 0.9895 | 0.9701 | +2.00% | 0.100 |
| 0.20 | 0.8976 | 0.8627 | +4.04% | 0.199 |
| 0.30 | 0.8058 | 0.7540 | +6.87% | 0.300 |
| 0.40 | 0.7076 | 0.6470 | +9.38% | 0.399 |
| 0.50 | 0.6021 | 0.5395 | +11.61% | 0.499 |
| 0.65 | 0.4355 | 0.3781 | +15.20% | 0.649 |
| 0.80 | 0.2593 | 0.2152 | **+20.52%** | 0.799 |

**Not vacuous** — max eps_B(A) = +20.5% ≥ 0.5% floor, so the full factorial ran. (Closed-loop starvation is real and large: at the exp12/exp36 operating point s≈0.3375 the closed-loop penalty is ~7.6% on this trace.)

### Factorial at the matched frozen threshold s* = 0.8 (maximises arm A), pf* = 0.5 (best SLRU)

| arm | B_replay GiB/tok | gain |
|---|---|---|
| baseline LRU | 1.0776 | — |
| A (certifier) | 0.2593 (sd 0.0018) | 0.8183 (75.9%) |
| B (SLRU pf=0.5) | 1.0733 | 0.0043 (0.40%) |
| A+B | 0.2552 (sd 0.0019) | 0.8224 (76.3%) |

**Interaction = gain(A+B) − gain(A) − gain(B) = −0.00022 GiB/tok = −0.020 pp of baseline.**

### Gates (quoted verbatim, evaluated as preregistered)

- ACCEPT requires: (a) eps_B(A) ≥ 0.5% ✓ (+20.5%); (b) **interaction ≥ +0.8 pp ✗ (−0.02 pp)**; (c) gain(A+B) ≥ 2.13% ✓ (76.3%); (d) frozen threshold ✓.
- REJECT fires on: interaction < 0.8 pp ✓ AND gain(A+B) ≤ max(gain A, gain B) + 0.5 pp ✓ (A dominates; B adds 0.4 pp).

**REJECTED.** Two independent reject clauses fired.

### Post-hoc diagnostic (explicitly NOT gate-relevant — gates were frozen at s*=0.8)

Interaction at moderate s: +2.10 pp (s=0.2), +2.43 pp (s=0.3), +1.98 pp (s=0.5), −0.02 pp (s=0.8), all at pf=0.5. So the sign of the interaction flips with s: SLRU does help under moderate bypass pressure on this trace, but the effect collapses exactly where the certifier is strongest. Under the preregistered protocol the matched threshold follows arm A's optimum, and there the hedge is worthless — the certifier at s*=0.8 already suppresses the one-shot scan traffic SLRU was meant to absorb. Both mechanisms compete for the same bytes, and the cheaper one wins outright. Recorded as falsified; the moderate-s numbers are published for the research job, not as a pass.

Also: SLRU pf=0.9 collapses (B_replay 2.4034, hit 0.0) — probation capacity 70 slots cannot absorb the insertion stream; protect-fraction is a real cliff on this trace, consistent with exp6's cache-policy ceiling.

## Objective check

Optimised **physical bytes per accepted token** in closed loop — the direct denominator of tok/s ≈ effective bandwidth / bytes-per-accepted-token at fixed 5.919 GiB/s. gain(A)=0.818 GiB/tok at s*=0.8 would buy ~138 ms/token [PROXY arithmetic: 0.8183 GiB / 5.919 GiB/s]. Every number above is PROXY/RECOMPUTATION on a Kimi-Linear-shaped trace; none is a K3 measurement, and s here is a Bernoulli abstraction of the idea16 row-norm bound, not a measured certification rate.

## Reproduce

```bash
python3 exp32_factorial.py   # deterministic; seeds 1-5 for cert draws
```

Artifacts: `exp32_factorial.py`, `exp32_run.log`, `exp32_result.json`, `exp32_posthoc_interaction.json` (SHA256SUMS alongside).
