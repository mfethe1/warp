# Belady oracle bound on expert-cache policy

Question: how much of the out-of-core MoE gap is reachable by **cache policy
alone**? Belady/MIN is the optimal offline replacement policy, so its miss count
is a hard lower bound no online policy can beat.

Simulator: `tools/crossval/belady_sim.py` (lazy-deletion heap, O(N log N)).

## Provenance and its limits, stated first

The replayed trace is **`tests/trace_kimi_300.jsonl`**, already in this repo:
300 tokens x 26 layers x top-8 = 62,400 ordered `(layer, expert)` accesses,
5,083 distinct.

**This is a Kimi-Linear-shaped proxy, not K3.** K3 is 92 layers x 896 experts
top-16. The Sprint 18 raw access sequence is not in the repository — the
`gn100-sprint18-*-evidence` archive is 17,829 bytes and cannot hold 153,424
miss records — so this oracle is **not** validated against the campaign's
153,424 misses. It is a demand-only bound on a proxy, and every number below
should be read that way.

Two further caveats on the target figure:

- The "97.68% hit rate" bar assumes every miss reads one complete
  12,406,784-byte record and ignores read overlap. It is a **bandwidth-
  equivalent** target, not an information-theoretic requirement.
- The 5,015-expert residency (59,340 MiB / 12,406,784 B) is approximate; real
  accounting includes metadata and reserved bytes.

## Normalizing the proxy to K3

Comparing raw cache sizes across two different models is meaningless. The
transferable quantity is **cache capacity relative to the per-token working
set**:

    K3:    ~5,015 experts resident / (92 x 16 = 1,472) = 3.41x working set
    proxy: 3.41 x (26 x 8 = 208)                       = 709 slots

Because the trace is short, compulsory (cold) misses are 5,083 of 62,400
accesses — 8.15% of all traffic. The `steady` column amortizes those away and is
the number that transfers to a long generation run.

## Result

| cap | xWS | %distinct | LRU miss | BELADY miss | LRU hit | BELADY hit | gap | BELADY steady |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 152 | 0.73 | 3.0% | 62,400 | 33,863 | 0.00% | 45.73% | 45.73 | 53.88% |
| 309 | 1.49 | 6.1% | 41,452 | 25,460 | 33.57% | 59.20% | 25.63 | 67.34% |
| 508 | 2.44 | 10.0% | 32,225 | 20,308 | 48.36% | 67.46% | 19.10 | 75.60% |
| **709** | **3.41** | **13.9%** | **27,979** | **17,036** | **55.16%** | **72.70%** | **17.54** | **80.84%** |
| 762 | 3.66 | 15.0% | 27,277 | 16,294 | 56.29% | 73.89% | 17.60 | 82.03% |
| 1,270 | 6.11 | 25.0% | 21,132 | 11,529 | 66.13% | 81.52% | 15.39 | 89.67% |
| 2,033 | 9.77 | 40.0% | 14,367 | 7,873 | 76.98% | 87.38% | 10.41 | 95.53% |
| 3,049 | 14.66 | 60.0% | 9,199 | 5,786 | 85.26% | 90.73% | 5.47 | 98.87% |
| 4,066 | 19.55 | 80.0% | 6,209 | 5,083 | 90.05% | 91.85% | 1.80 | 100.00% |

The K3-equivalent row is 709.

## Finding 1: no cache policy reaches the 15 tok/s bar

At the K3-equivalent operating point, **optimal offline replacement gives
80.84% steady-state hit against the 97.68% bandwidth-equivalent target — a
16.84 pp shortfall.**

Belady does not clear that bar until roughly **14.66x** working set (98.87% at
cap 3,049), which is **4.3x more resident capacity than K3 currently has**. On
K3 terms that is on the order of 240 GiB of expert cache rather than ~58 GiB.

> **No online policy, however clever, reaches 15 tok/s at current residency.**
> Prefetch accuracy, admission heuristics, eviction tuning, and block-aware
> retention are all bounded above by this line. Cache-policy work should be
> retired as a path to the system target.

That is the single most useful thing the oracle tells us, and it is consistent
with the negative results already recorded here: cache replacement/admission
tuning measured a +4.5% ceiling, and the FreeToken full-layer prefill gate
failed on physical bytes.

## Finding 2: the policy gap is large, and big enough for the questions that remain

At the same operating point LRU achieves 55.16% against Belady's 72.70% —
a **17.54 pp** gap, the widest anywhere in the sweep. Roughly a quarter of
achievable hits are being left on the table by replacement policy.

That does not reach 15 tok/s. It is, however, far more than the **2.13%**
verifier byte reduction that flips speculative decoding from +1.91% to a net
win, per
[SPECULATIVE_DECODING_BYTE_ECONOMICS.md](SPECULATIVE_DECODING_BYTE_ECONOMICS.md).

So the two findings are not in tension. Cache policy is **dead as a route to the
system target** and **live as a route to making speculation pay for itself**.

## Finding 3: the curve explains the sublinearity paradox

Sprint 18 measured a 34.2% distinct-union saving converting to only 3.69%
physical byte saving. The oracle shows why: at 3.41x working set the cache is on
the steep part of the curve, where every additional resident expert still buys
hit rate. A width-4 block's larger working set displaces exactly what the next
block needs, and reuse never reaches the device.

The displacement is not a policy defect that better heuristics fix. It is a
capacity regime.

## What this redirects

- **Stop**: cache replacement/admission/prefetch tuning as a path to 15 tok/s.
  Bounded above by 80.84% steady-state at current residency.
- **Continue**: policy work aimed only at the 2.13% speculative break-even,
  where the 17.54 pp gap is ample.
- **Prioritize**: representation (fewer bytes per expert) and certified residual
  skipping (fewer expert reads per token), which move the demand itself rather
  than its scheduling. Also: more resident capacity and more bandwidth, which
  the curve says are the only brute-force levers that work.

## To make this K3-exact

The container is now byte-complete (92/92 `experts-L*.bin` at 11,116,478,464 B).
The missing input is an ordered `(layer, expert)` demand trace from real K3
decode. `WASTE_DUMP_ROUTE` already emits per-token routed ids; replaying that
through this simulator turns every number above from a proxy bound into a
measured one, with no change to inference behavior.

If the Sprint 18 raw access sequence can be published, the simulator's current
policy arm should first reproduce 153,424 misses and 1,903,498,428,416 bytes as
a validation gate before any oracle number is trusted.
