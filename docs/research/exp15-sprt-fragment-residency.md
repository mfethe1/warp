# exp15 — SPRT stages plus fragment residency

**Verdict:** FALSIFIED at the preregistered residency-footprint probe.

**Evidence class:** RECOMPUTATION over `tests/trace_kimi_300.jsonl`, a Kimi-Linear-shaped PROXY trace (300 tokens × 26 layers × top-8). This is **not K3** and no tok/s measurement was made.

## Frozen gate

Reject if:

> stage-1 residency for the exercised expert coverage does not fit the resident budget alongside the coarse basis

The stop rule requires stopping at this probe and not running the four byte arms when it fires.

## Recomputation

The fixed shared resident budget is the baseline cap: 709 whole VQ3R records. Each record is 12,406,784 B, of which 12,386,304 B is the three-stage index payload and 20,480 B is fixed overhead. A stage-1 resident fragment therefore occupies:

```
12,386,304 / 3 + 20,480 = 4,149,248 B
```

The frozen trace contains N=62,400 accesses and exercises 5,083 distinct `(layer, expert)` records. Holding stage 1 for that exercised coverage requires:

```
5,083 × 4,149,248 B = 21,090,627,584 B
```

The fixed R budget is:

```
709 × 12,406,784 B = 8,796,409,856 B
```

Thus stage-1 coverage alone consumes **2.397640× R**, equivalent to **1,699.927 whole records**, and exceeds R by **12,294,217,728 B** before allocating even one byte to the coarse basis. The reject gate therefore fires decisively.

The early-stop-rate half of the probe was not computed: the trace has expert IDs but no per-expert VQ-stage certification outcomes, and the published sprint11 K3 route-margin file is percentile-only. The preregistration explicitly forbids treating those percentiles as per-expert coupling. This missing value does not make the outcome inconclusive because the stop rule is disjunctive and the independently computed residency reject fired.

## Objective connection

The mechanism targets physical bytes per accepted token by making stage 1 resident, so an early stop issues zero preads and a continuation issues one fixed-length pread. Its stage-1 residency footprint is therefore a direct feasibility constraint on the claimed physical-byte reduction. Since that footprint cannot fit under fixed R even before coarse-basis residency, the proposed enabling interaction cannot exist under the registered constraints.

## Reproduction

```sh
python3 tools/research/exp15_falsifier.py \
  tests/trace_kimi_300.jsonl \
  --output exp15_result.json
```

Raw queue evidence is stored under `~/.hermes/state/warp-research/evidence/exp15-sprt-fragment-residency/`.
