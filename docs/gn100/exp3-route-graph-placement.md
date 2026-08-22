# exp3 — Route-transition graph placement: FALSIFIED

**Idea:** Build a (layer,expert) transition graph from a route trace, measure
modularity/entropy, and partition the on-disk layout to co-page frequent
successors so readahead pulls the next expert for free.

**Preregistered gates (source_sha cb05b14):**
- ACCEPT: `modularity > 0.15 AND entropy materially below uniform` → placement work justified
- REJECT: `modularity ~0 or entropy ~uniform` → DEAD, do not implement placement

## What ran

Pure offline analysis on the Mac (Winnie was at 67% CPU with aria2c +
llama-server + two hot conversion pythons — no contention with the coding loop).

- `tools/crossval/route_graph.py` — successor entropy + one-level Louvain
  modularity, with two null models.
- `tools/crossval/route_graph_payoff.py` — top-1 successor predictability vs a
  marginal-preserving null, plus the byte/IOP algebra at the K3 operating point.

Trace: `tests/trace_kimi_300.jsonl`
sha256 `06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965`
(300 tok × 26 layers × top-8 of 256). **PROXY — Kimi-Linear shaped, NOT K3.**

## Numbers

### Literal gate reading — passes [PROXY]
| quantity | value |
|---|---|
| successor entropy | 5.2463 bits |
| uniform null | 8.0 bits |
| deficit | 2.7537 bits (65.58% of uniform) |
| modularity Q | 0.6333 (6 communities, 4,878 nodes, 167,375 edges) |

Q = 0.6333 > 0.15 and entropy is 2.75 bits below uniform. Taken literally, ACCEPT.

### Why the literal reading is an artifact [PROXY, n=5 nulls]
The graph is a layered chain, so it has high modularity from *layer structure
alone*. Against nulls that preserve shape and per-layer expert popularity but
destroy all cross-layer coupling:

| null | entropy (bits) | modularity Q |
|---|---|---|
| observed | 5.2463 | 0.6333 |
| uniform resample | 6.0289 ± 0.0006 | 0.6314 ± 0.0076 |
| marginal permute | 5.7816 ± 0.0015 | 0.5986 ± 0.0179 |

**Modularity excess over the marginal null: +0.0347 — inside ~2 SD.** Essentially
all of Q = 0.6333 is layer geometry, not routing structure. Entropy excess is
0.5353 bits, real but small.

Top-1 successor probability: observed **0.09906** vs marginal null
**0.07960 ± 0.00006** → excess **+0.0195**. Even a perfect co-pager guesses the
next expert right ~9.9% of the time.

### The decisive algebra — kills it regardless [RECOMPUTATION]
Placement permutes *where* records live. It changes neither which experts are
demanded nor the 3029-page record size:

**d(bytes per accepted token)/d(layout) ≡ 0.**

Layout can only merge preads, i.e. recover seek/command overhead:

| quantity | value |
|---|---|
| physical reads/token | 668.0 |
| stream time/token @5.919 GiB/s | 1304.1 ms |
| seek time/token @80 µs | 53.44 ms (**3.94%** of read time) |
| perfect co-paging saves (≤50% of IOPs) | 26.72 ms |
| current ms/token | 1357.5 |
| budget for 15 tok/s | 66.67 ms |
| **gap remaining after perfect co-paging** | **1264.2 ms** |

The entire addressable prize is 26.72 ms against a 1264 ms deficit — and that
upper bound assumes 100% successor prediction, where the measured proxy ceiling
is 9.9%. Realistic recovery is on the order of 2.6 ms/token, ~0.2%.

## Verdict: FALSIFIED

The preregistered gate is *underspecified* — it lacks a null model, so a layered
chain graph passes it mechanically. I did not move the gate: I report that it
passes literally (Q=0.6333>0.15), and falsify the idea on the preregistered
`stop_rule` grounds plus the objective function, which is the binding
authority. Against the null, modularity excess is +0.0347 (~2 SD); against the
objective, the layout derivative of bytes/accepted token is identically zero.

**Route-transition placement is DEAD. Do not implement layout partitioning.**

## Objective check

Optimized: physical read *time* via IOP merging, **not** bytes. Bytes per
accepted token = (physical expert bytes read) / (accepted output tokens);
placement changes the denominator not at all and the numerator not at all, since
each demanded expert is still exactly one 12,406,784 B / 3029-page record. The
connection to the objective function is therefore null by construction — the
mechanism is orthogonal to the metric it was proposed to improve.
