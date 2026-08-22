# Sprint 17/18 re-read: bytes per accepted token, not seconds per block

Source: `docs/gn100/sprint17-k3-selfdraft-summary.json` and
`docs/gn100/sprint18-exact-verifier-summary.json` (mccoyspace/warp-spark).
No new measurements. Every number below is recomputed from those two files.

Sprint 18 rejected an integrated speculative decoder on a **wall-time** gate:
421.947 s against a 263.439 s limit, "28.20% less throughput". That gate is
correct for a compute-bound engine. For an out-of-core MoE the governing
quantity is different:

    accepted output tokens per physical expert byte read

Recomputing Sprint 18 against that objective gives a materially different
disposition, and it changes which experiment should come next.

## Recomputation

Serial baseline, from the Sprint 18 pilot's own serial arms (8 steps):

    (35,247,673,344 + 31,054,180,352) / 8 = 7.719 GiB per token

Speculative campaign, 67 blocks committing 256 tokens:

| Term | Bytes |
| --- | ---: |
| verifier | 1,772.771 GiB (26.459 GiB/block) |
| draft | 241.008 GiB (3.597 GiB/block) |
| **total** | **2,013.779 GiB** |

| Quantity | GiB / accepted token | vs serial |
| --- | ---: | ---: |
| verifier only | 6.925 | **-10.28%** |
| draft + verifier | 7.866 | **+1.91%** |
| serial decode | 7.719 | — |

**The complete speculative path reads 1.91% more bytes per accepted token than
ordinary decode — not 28% worse.** The wall-time gap is a bandwidth-utilization
artifact, not a byte-efficiency one.

## Break-even is 2.13%, and 3.69% has already been demonstrated

To reach parity the verifier must fall from 26.459 to 25.895 GiB/block:

    required verifier byte reduction = 2.13%

The Sprint 18 pilot already measured **3.69%** byte reduction from causal
layer-major scheduling alone (3.661% rejection block, 3.716% full-accept).

The campaign was run at the *unreduced* rate. Applying the pilot's own measured
reduction to the campaign verifier puts the path at roughly **-1.7% bytes per
accepted token**, i.e. slightly ahead of serial. Sprint 18's conclusion and
Sprint 18's own pilot disagree, and the disagreement is only visible in byte
units.

Sensitivity, holding acceptance fixed:

| verifier byte reduction | GiB/accepted token | vs serial |
| ---: | ---: | ---: |
| 0% (as run) | 7.866 | +1.91% |
| 5% | 7.520 | -2.57% |
| 10% | 7.174 | -7.06% |
| 15% | 6.828 | -11.54% |
| 20% | 6.481 | -16.03% |

Acceptance is nearly saturated and is *not* the lever: 3.8209 of 4 tokens
commit per block (74.33% of proposals). Perfect acceptance would give only
-2.65%. Every remaining gain is on the byte axis.

## The verifier is I/O bound, so the stated reopening condition targets the wrong term

Sprint 18 names its next credible reopening condition as "a verifier that
reduces CUDA launch/synchronization granularity across positions". The same
JSON rules that out:

- VQ launches are **identical** across arms: 18,032 serial, 18,032 exact.
- VQ synchronizations are **identical**: 11,776 and 11,776.
- 26.459 GiB/block / 5.919 GiB/s = **4.470 s**, exactly the measured
  4.470 s/block.

I/O accounts for 100.0% of verifier wall time to three decimals. Launch
granularity was never the bottleneck and was already equal between arms.
Reducing it cannot move a term that is fully explained by bytes over bandwidth.

The productive target is the byte term, and the pilot shows it is movable.

## Why the union reuse does not reach the disk

Expert union across a width-4 block, against a single token's full route set
(92 layers x 16 experts = 1,472):

| block | U(4) | U(4)/U(1) |
| --- | ---: | ---: |
| rejection pilot | 3,929 | 2.669 |
| full-accept pilot | 3,572 | 2.427 |
| campaign mean | 3,876 | 2.633 |

Linear growth would be 4.000. **Measured sublinearity is 0.658** — about 34% of
routed accesses across four causal positions are cross-position reuse. That is
a large, real, structural saving.

It does not arrive at the device:

| | saving |
| --- | ---: |
| distinct expert union vs 4 serial tokens | -34.2% |
| measured physical bytes (pilot) | -3.69% |

59.07% of the 259,712-entry union still becomes a physical miss. The union
shrinks by a third; physical bytes move by a thirtieth. The residency policy is
not converting demonstrated reuse into avoided reads — a width-4 working set
displaces exactly what the next block needs.

**That gap, 34.2% available against 3.69% realized, is the largest unexploited
quantity in either sprint**, and it is a cache-policy question rather than a
speculation question. Break-even needs 2.13% of it.

## Proposed next experiment: simulate before building

The instrument that would settle this is offline and needs no engine change.
Sprint 18 already emits the required trace.

Replay the recorded `(layer, expert)` access sequence for the 67 blocks against
a simulated cache of 59,340 MiB under:

1. the current policy (reproduce 153,424 misses as a validity check);
2. block-aware retention — pin the width-4 union for the block's lifetime;
3. cross-block lookahead — retain entries the *next* block's draft predicts;
4. width sweep B in {2,3,4,6,8} to locate the sublinearity/displacement optimum.

Success is any policy putting verifier bytes 2.13% below 26.459 GiB/block.
The pilot already reached 3.69% by scheduling alone, so this is not a
speculative target.

**Cache-aware adaptive speculation** follows naturally: vary *how many* tokens
are verified based on predicted residency of the verification set, never *which*
experts are selected. That keeps it strictly post-selection — it cannot alter
route identity, so it needs no KL argument and no quality gate. It sits on the
safe side of the boundary described in
[ROUTE_MARGIN_VS_CACHE_RANKING.md](ROUTE_MARGIN_VS_CACHE_RANKING.md).

## Scope and limits

- Recomputation only; we ran no model. Provenance is the two cited JSON files.
- The serial baseline is the pilot's 8 serial steps, one case (`color_value_a`).
  A campaign-wide serial byte baseline would tighten the +1.91% figure and we
  do not have one.
- Byte parity is not throughput parity. Sprint 18's wall-time gate is not wrong;
  it answers a different question, and on GB10 with 5.919 GiB/s that question
  has a different answer than on a bandwidth-starved rig.
- Rejection replay and integration overhead remain unimplemented and uncharged,
  as Sprint 18 states. They are charged against neither arm here.
- This does not reverse Sprint 18's disposition. It argues the *gate* should be
  byte-denominated, and that the pilot already cleared the byte bar it implies.
