# exp11 — Miss-conditioned exactness shadow price (s_eff vs s)

**Verdict: INCONCLUSIVE** (preregistration not decidable from available inputs) — with two
decidable side-results that stand on their own.

## Claim
Every demand-side projection in the queue uses `s = P(skip)` over **all** activations. A skipped
activation only removes a physical byte if it would have **missed**. The operative rate is therefore
`s_eff = P(skip AND miss) / P(miss)`, and the correction factor is `r = s_eff / s`.

## Inputs (pinned)
| artifact | sha256 | label |
|---|---|---|
| `tests/trace_kimi_300.jsonl` | `06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965` | PROXY (Kimi-Linear-shaped, NOT K3) |
| `docs/gn100/sprint11-route-margin-summary.json` | `1cfd9927fce60aea5ec220405923641821537431e8e3ab599837f2300d772295` | REAL-K3 margins |

LRU cap 709 = 3.41x working set (K3-equivalent). N = 62,400 accesses, 5,083 distinct.
**Measured [PROXY]: misses = 27,979, miss_frac = 0.448381, hit_frac = 0.551619.**

## Why the preregistration is not decidable
The stop rule says: *"if the trace cannot supply per-access margins AND the sprint11 margin
assignment is not defensible, abort and record BLOCKED rather than inventing margins."*

Audit of sprint11 (92 layers, 6,348 rows): the file contains **percentiles and aggregates only** —
`min/p0_1/p1/p5/p50/p95/p99/max` by layer, by phase, by attention type. There are **no
per-(layer,expert) or per-access margin rows**. sprint11 can supply a *marginal distribution* of
margins but **cannot supply a coupling between margin and expert identity** — and the coupling is
the entire quantity under test. Any per-access assignment therefore *fixes the answer by
assumption* rather than measuring it.

This is demonstrated, not asserted, by running three arms:

| s | Arm A: iid marginal-matched `r` (sd, N=5) | Arm C: skip-rarest `r` | Arm C: skip-most-popular `r` | Fréchet–Hoeffding admissible `r` |
|---|---|---|---|---|
| 0.30 | 1.0032 (0.0032) | 1.6729 | 0.2951 | [0.0000, 2.2302] |
| 0.50 | 1.0023 (0.0040) | 1.4889 | 0.5111 | [0.0000, 2.0000] |
| 0.80 | 1.0008 (0.0022) | 1.2020 | 0.8089 | [0.6924, 1.2500] |
| 0.977| 0.9995 (0.0007) | 1.0226 | 0.9740 | [0.9710, 1.0235] |

Arm A returns `r = 1.000 ± 0.002` — but that is a **tautology**, not evidence: assigning margins
i.i.d. from a marginal distribution makes skip independent of residency *by construction*, so it can
only ever return r = 1. Arm C shows that a *single* plausible identity coupling (margin correlates
with expert popularity) moves `r` across **0.295 → 1.67** at s = 0.30 — spanning the ACCEPT gate
(`r < 0.90`) and the REJECT gate (`0.95 ≤ r ≤ 1.05`) simultaneously, depending only on the sign of
the correlation. The data cannot pick between them.

**Gate as written cannot be evaluated.** Reporting Arm A as a REJECT would be reporting an artifact
of the imputation method as a physical finding.

## Two results that ARE decidable [RECOMPUTATION]

**1. exp8's `s >= 50%` HARD STOP is uninformative as written.** From the measured hit fraction, the
Fréchet–Hoeffding bounds on the 2×2 joint give, at s = 0.50, `s_eff ∈ [0.0000, 1.0000]`, i.e.
physical bytes/token anywhere in **[0.000, 7.719] GiB**. The gate can pass while saving *zero*
bytes. More generally: **any `s <= hit_frac = 0.5516` can remove zero physical bytes.** No
assumption about margins is needed for this — it follows from the measured miss fraction alone.

**2. The 15 tok/s requirement restated on the physical axis.** 0.3946 GiB/token against the measured
physical 7.719 GiB/token requires **`s_eff >= 94.8879%`** (miss-conditioned), versus the published
`s >= 97.68%` stated against logical demand 17.0085. These are *different quantities on different
denominators*; the 19.562x physical reduction, not the 43.103x logical one, is the operative target.
The miss-conditioned bar is lower in nominal terms but strictly harder to hit, because it must be
achieved **on the miss set only** — the hit set contributes no bytes and therefore no credit.

## Objective check
Optimized: `B_acc = M * RECORD * mf * (1 - s_eff) / a`. The connection is exact and algebraic —
`s_eff` enters `B_acc` linearly and `s` does not appear at all except through `s_eff = r * s`. That
is precisely why substituting `s` for `s_eff` (implicitly assuming r = 1) is an error of the same
order as `r`'s deviation from 1, and why the magnitude of `r` had to be measured rather than assumed.
This run establishes the correct *functional form* and bounds it, but does not pin `r`.

## What the queue should run next
Requeue as **exp11b** with a coupling that the data can actually supply: dump per-(layer,expert)
routing margins from a real K3 or Kimi forward pass so margin↔identity is *observed*, or replay the
skip decision jointly with the cache in one pass so the 2×2 is measured rather than imputed.
Until then, treat every demand-side gate as bounded by Fréchet–Hoeffding, and **replace exp8's
`s >= 50%` stop with a miss-conditioned `s_eff` threshold** — that substitution is justified now.
