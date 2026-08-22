# exp13 — Closed-loop counterfactual gating (frozen mask vs stateful replay)

**Verdict: CONFIRMED** (mismatch #7 is real) — with one preregistered sub-question recorded as
BLOCKED, and a stronger-than-expected structure: the correction is **exactly zero** under one
bypass semantics and **enormous** under the other. The mismatch is not a modelling error in the
threshold; it is a modelling error in *what a bypass does to the cache*.

## Inputs (pinned)
| artifact | sha256 | label |
|---|---|---|
| `tests/trace_kimi_300.jsonl` | `06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965` | **PROXY** (Kimi-Linear-shaped, NOT K3) |
| `tools/crossval/closed_loop_gating.py` | see evidence dir | harness |

300 tok × 26 layers × top-8 → N = 62,400 accesses, D = 5,083 distinct, per-token WS = 208.
Capacities swept: 0.5× (104), 1× (208), 3.41× (**709**, K3-equivalent), 8× (1664).
Thresholds swept: τ ∈ {0.1 … 0.9}. RECORD = 12,406,784 B.
Replay is **fully deterministic** — no sampling variance. The one stochastic rule (`random-iid`)
uses a single pinned seed = 1234.

Baseline reproduces exp4/exp11 exactly: LRU cap 709 → **27,979 physical reads** [PROXY]. ✔

## Preregistered stop rule: partially BLOCKED, honestly
> *"if the trace lacks chronological ordering **or** per-access top-k margin ranks, abort and record
> BLOCKED rather than inventing a skip proxy."*

The trace **is** chronological (`tok` 0…299 ascending). It does **not** carry per-access margin
ranks: each token-layer expert list is stored **sorted ascending by expert ID**, so list position is
ID magnitude, not routing margin. This is the same defect exp11 found in sprint11. Therefore:

* The **τ-indexed, margin-conditioned** portion of the spec — "the threshold ranking under the two
  estimators" *for the routing-margin gate specifically* — is **BLOCKED**. No margin proxy was
  invented; nothing below is presented as the preregistered margin gate.
* The **estimator-comparison** portion is decidable **without any margin at all**, because ε_B under
  S1 turns out to be identically zero for *every* skip vector, and the S2 divergence is reproduced
  across four structurally opposite skip rules that bracket the plausible coupling space
  (`random-iid`, `skip-popular`, `skip-rare`, `id-order`). The finding does not depend on which
  proxy is chosen — that is exactly why it is reportable.

## Result 1 — S1 (insertion-neutral): ε_B ≡ 0, exactly [RECOMPUTATION]

**MAX |ε_B| under S1 across the entire (rule × τ × capacity) grid = 0.000e+00.** Not "small" —
bit-identical, 144 cells, every cell.

This is a theorem, not a coincidence. Under insertion-neutral bypass the skip decision suppresses
the *read* but leaves the insert/refresh, so the LRU stack evolves along the **same** trajectory as
the unmodified baseline. The miss indicator at access *i* is therefore independent of the skip
vector, and physical reads collapse algebraically to
`B_replay = Σ_i miss_i·(1−skip_i) = B_frozen`. For a stack algorithm with an
insertion-neutral bypass, **the frozen-mask arithmetic used by slugs 1, 6, 7, 12, 13, 16, 17 is
exact.** That is a real defence of the existing queue arithmetic — under an assumption nobody had
written down.

## Result 2 — S2 (no-insert-on-bypass): the mask is catastrophically wrong [RECOMPUTATION]

**MAX |ε_B| under S2 = 179.76 (17,976%).** At the K3-equivalent capacity 3.41× (cap 709):

| rule | τ=0.1 | τ=0.3 | τ=0.5 | τ=0.7 | τ=0.9 |
|---|---|---|---|---|---|
| random-iid   | **−2.62%** | −8.21% | −13.41% | −18.22% | −27.79% |
| skip-popular | +1.34% | +4.64% | **+10.23%** | +21.53% | +31.19% |
| skip-rare    | +7.18% | +63.82% | **+1137.9%** | +1241.1% | +814.7% |
| id-order     | +0.68% | +2.89% | +17.86% | +57.34% | +106.7% |

**The correction changes SIGN**, exactly as the idea predicted. `random-iid` is negative — the
frozen mask *overstates* the saving, because bypasses starve the cache and manufacture future
misses. `skip-popular` / `skip-rare` are positive — bypassing keeps hot lines from being evicted, so
closed-loop is *cheaper* than the mask claims. ε_B ≥ 5% is exceeded at capacity 3.41× by every one
of the four rules, at τ well inside [0.1, 0.9].

## Gate

> **ACCEPT:** *"|eps_B| >= 5% anywhere in tau in [0.1,0.9] at capacity 3.41x WS under EITHER bypass
> semantics, OR any reversal of threshold ranking between estimators."*

**MET, on the first clause, by a wide margin** — max |ε_B| = 17,976% ≫ 5%, at the specified capacity,
under S2. The REJECT gate (`|eps_B| < 1%` everywhere under **BOTH** semantics **AND** identical
ranking) fails on S2 despite S1 satisfying its first half.

Second clause — ranking reversal — **did NOT occur**: Kendall τ(B_frozen, B_S2) = **+1.0000** in all
16 (rule × capacity) cells. Monotone in τ under both estimators. So the mask misprices the *level*
of every gate, but preserves the *ordering* of thresholds within a fixed rule. Useful and narrowing:
threshold selection sweeps are safe; absolute byte projections are not.

## Consequence for the queue
1. Every demand-side accept gate must now declare its bypass semantics. Under **S1** the existing
   `B_acc = M·RECORD·mf·(1−s_eff)/a` arithmetic stands **exact** — no restatement needed.
2. Under **S2** it must be restated against `B_replay`; the naive s_eff = 0.50 → 3.860 GiB/token
   projection is not trustworthy to better than tens of percent, in an unknown sign.
3. exp11's `s_eff` algebra is hereby annotated **frozen-state / insertion-neutral only**.
4. None of this rescues the target. Best S2 cell at 3.41× is 0.0013 GiB/tok [PROXY] but only at
   τ=0.9 skip-rare, i.e. discarding 90% of activations — an exactness catastrophe, not a win. The
   correction changes *the error bars on demand-side gates*; it does not move 7.719 → 0.3946.

## Objective check
Optimized: the **estimator** for physical expert bytes per accepted token, not the byte count itself.
Algebraic connection is direct — `GiB/accepted-token = reads · RECORD / 2^30 / (TOK · a)`, and this
experiment measures the error in `reads` induced by the frozen-mask approximation, with `RECORD` and
`a` untouched. ε_B is therefore a *multiplicative error on the numerator* of the objective:
`B_frozen/B_replay = 1 + ε_B`. A 17,976% estimator error is a 180× error in the reported objective.
This is a measurement-validity result: it makes future demand-side numbers trustworthy (or exposes
them), rather than reducing bytes.
