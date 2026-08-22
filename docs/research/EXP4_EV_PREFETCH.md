# exp4 — Option-value prefetch (EV-gated): FALSIFIED

**Verdict: falsified.** At the preregistered K3-equivalent operating point the
EV gate **cannot beat lookahead-off**. Its optimum is to prefetch *nothing* —
it ties lookahead-off exactly (0 reads difference, +0.0000 %).

## Method (cheapest decisive form)

Offline replay, Mac-local, no Winnie compute (Winnie was at 42 % CPU with
`aria2c` + `llama-server` active — offline-only tick).

Trace: `tests/trace_kimi_300.jsonl` — **PROXY** (Kimi-Linear-shaped, NOT K3):
300 tok × 26 layers × top-8 = 62,400 accesses, 5,083 distinct.
Cache: LRU at the K3-equivalent **3.41×** working set → cap 709 slots.
Metric: physical expert-record reads (`bytes = reads × 12,406,784 B`).

Three arms replayed on the **identical** demand sequence, differing only in
prefetch policy. Prefetched lines enter the same LRU as demand lines, so
displacement is *modelled*, not assumed away:

- `off` — lookahead disabled (baseline)
- `uncond` — unconditional lookahead (the published +6.9 % regression arm)
- `ev` — value = `P(demanded before evict)·stall − bytes_cost − displacement_cost`,
  prefetch iff `value > threshold`; `P` estimated online (Laplace-smoothed
  per-layer previous-token reuse), 11 thresholds swept from −3.0 to +1.0.

The lookahead signal is the previous token's experts at the same layer — the
only signal actually available at decode time, since the next layer's routing
is not known until the current layer completes.

## Result at the preregistered operating point (cap 709 = 3.41× WS)

| threshold | reads | Δ vs off | prefetched | useful | evicted unused |
|---|---|---|---|---|---|
| −3.00 … −1.50 | 27,997 | **+0.064 %** | 59,800 | **0** | 0 |
| −1.00 | 27,982 | +0.011 % | 912 | **0** | 0 |
| −0.50 … +1.00 | 27,979 | **+0.000 %** | **0** | 0 | 0 |

lookahead-off = **27,979** reads. Best EV-gated = **27,979** reads.
**Δ = 0 reads (+0.0000 %). Beats lookahead-off: FALSE.**

`prefetch_useful == 0` at *every* threshold: not one prefetched record was
demanded before eviction. 7 of 11 thresholds degenerate to "prefetch nothing".
The EV gate's best available move is to disable itself.

## Robustness — the off-design "wins" are noise, not signal

Widening to 15 capacities (2.40×–19.23× WS), EV strictly beat `off` at 10/15.
That looks like a win until attributed:

- **7 of those 10** have `best_ev == uncond` — the optimal threshold was
  "prefetch everything", so the **EV gate contributed zero**.
- Reads attributable to the gate itself, summed over **all 15 caps**: **93**
  (out of ~250k reads across the sweep).
- Unconditional lookahead's sign is **not stable**: 6 regressions, 8 gains,
  1 tie, max magnitude |0.606 %|. A systematic effect does not flip sign with
  cache size — this is LRU eviction-order jitter.
- Largest relative win anywhere: **−0.606 %**, at cap 500, an off-design point
  *below* the K3 operating ratio.

## Gate

Preregistered gates, verbatim:

> ACCEPT: EV-gated beats lookahead-off on physical bytes
> REJECT: cannot beat lookahead-off -> DEAD, confirms prefetch is structurally
> negative here

At the operating point the accept gate **fails** (Δ = 0, strict "beats" not
met). The **reject gate is met**. Even the most generous off-design reading
(−0.606 %) is 3.5× under the 2.13 % speculative break-even and 157× under the
94.9 % byte reduction needed for 15 tok/s.

## Relation to exp10

exp10 predicted this by algebra — `gain(B) == 0`, prefetch changes *when* a
page is read, never *whether*. exp4 was run as an **empirical** check because
its gate is empirical, and the replay lands exactly where the algebra said:
`prefetch_useful == 0`, Δ = 0. Independent confirmation, not a re-derivation.

The displacement term is real but second-order here: with `useful == 0` the
EV numerator `P·stall` is empirically ~0, so no threshold can produce positive
value. The gate is correct *and* inert.

## Consequence for the queue

The prefetch-as-byte-optimizer family is now closed both by algebra (exp10) and
by measurement (exp4). **exp6** (chaperone-plus-EV-prefetch) inherits
`gain(B) == 0` from its EV-prefetch component and should be dropped or requeued
with the prefetch arm removed. Surviving ideas must **delete** bytes — skip,
shrink, or reuse them — not reschedule them.
