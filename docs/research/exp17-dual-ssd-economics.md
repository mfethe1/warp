# exp17 — Dual-SSD Bandwidth Economics (RECOMPUTATION)

**Queue item:** exp17 / idea8 `objective-mismatch-audit` lane=`offline`
**Method:** pure arithmetic over established WARP constants + published vendor spec sheets. No purchase, no device access, **no K3 measurement**.
**Evidence class:** RECOMPUTATION (deterministic; N=1, variance not estimated — arithmetic, not sampling).
**Artifacts:** `tools/crossval/exp17_dual_ssd.py`, `docs/research/exp17_dual_ssd.out.json`

## Preregistered gates (quoted verbatim)

- **ACCEPT:** "striping materially reduces the required byte reduction within budget — queue a placement design"
- **REJECT:** "duplication infeasible at 952 GiB within budget, or imbalance/queue-depth erases the gain"
- **STOP:** "Pure arithmetic + published spec sheets. No purchase. Report dollars per unit of gap closed."

## Inputs (established, not re-derived)

| constant | value |
|---|---|
| logical demand | 17.009 GiB/token |
| physical demand (VQ3R 3.00 bpw) | 7.719 GiB/token |
| measured single-drive effective BW | 5.919 GiB/s (O_DIRECT, 3029-page records) |
| target | 15 tok/s batch-1 |
| container | 952 GiB |
| K3 shape | 92 layers × top-16 |

Derated efficiency of our O_DIRECT path vs. spec sheet: **0.8531** (5.919 GiB/s measured ÷ 6.938 GiB/s spec for the Samsung 990 Pro 2TB at 7450 MB/s). All spec-sheet drives below are derated by this same factor — this is the honest way to convert marketing seq-read into WARP-path bandwidth.

## Result 1 — required bytes/accepted token vs. aggregate bandwidth [RECOMPUTATION]

`required_GiB_per_token = aggregate_BW / 15`

| aggregate BW (GiB/s) | required GiB/accepted token | byte-reduction factor still needed |
|---|---|---|
| 5.919 (today, single) | 0.3946 | **19.56×** |
| 9.000 | 0.6000 | 12.87× |
| 11.838 (2× matched, duplicated) | 0.7892 | **9.78×** |
| 12.000 | 0.8000 | 9.65× |
| 18.000 | 1.2000 | 6.43× |

Doubling bandwidth exactly halves the required byte reduction. This is real and it is the largest single lever available for $150.

## Result 2 — colibri's "9+3 GB/s pair, ~33% faster" claim, audited [RECOMPUTATION]

This is an **objective-mismatch finding**, which is exactly what idea8 exists to catch.

- Fast drive **alone**: 9.0 GB/s
- **Bandwidth-proportional** placement (f* = a/(a+b)): 12.0 GB/s → **1.333× vs. fast drive alone** — this reproduces the claimed 33% exactly.
- **Uniform hash** placement (colibri's stated "deterministic hash placement", f = 0.5): aggregate = 2·min(a,b) = **6.0 GB/s → 0.667× — 33% SLOWER than just using the fast drive alone.**

The claimed 1.33× is only achievable under bandwidth-proportional placement. A deterministic uniform hash across a 9+3 asymmetric pair **loses** to the single fast drive, because the step ends at `max(f/a, (1−f)/b)` and the slow drive dominates. **The mechanism reproduces arithmetically, but the stated placement policy does not produce the stated speedup on an asymmetric pair.** Symmetric pairs are the only configuration where uniform hash is optimal.

## Result 3 — batch-1 per-layer barrier tax on a SHARDED container [RECOMPUTATION]

At batch-1 the next layer's expert set is unknown until this layer completes, so each layer step ends at `max(load_A, load_B)`, not at the mean. With n=16 records uniformly hashed across 2 drives:

- `E[max(X, 16−X)]` = **9.571** records vs. ideal 8.0 → **+19.64% slowdown**
- Effective dual-sharded BW: 11.838 → **9.895 GiB/s** → gap **11.70×** (not 9.78×)
- (Hypothetical full-token read-ahead, n=1472: only +2.08% — the tax is entirely a small-n barrier effect. Read-ahead across layers would recover it, but that requires knowing routes ahead of time, which batch-1 does not.)

**Duplication avoids this tax entirely**: with both drives holding the full container, any record can be served by either drive, so the split is chosen at dispatch rather than fixed by hash → perfectly additive 11.838 GiB/s.

## Result 4 — capacity and cost [RECOMPUTATION, published spec sheets]

Container is 952 GiB. Usable 1TB = 931.3 GiB → **1TB drives cannot hold a duplicate**. 2TB usable = 1862.6 GiB → duplication fits comfortably on 2TB.

| drive | iface | spec MB/s | derated GiB/s | 2TB street $ | $/effective GiB/s |
|---|---|---|---|---|---|
| Samsung 990 Pro 2TB | PCIe 4.0 | 7450 | 5.919 | $150 | 25.34 |
| WD SN850X 2TB | PCIe 4.0 | 7300 | 5.800 | $140 | 24.14 |
| Crucial T705 2TB | PCIe 5.0 | 14100 | 11.202 | $250 | 22.32 |
| Samsung 9100 Pro 2TB | PCIe 5.0 | 14800 | 11.759 | $260 | 22.11 |

**Marginal economics of adding one matched 990 Pro 2TB (duplicated container):**

- aggregate 5.919 → **11.838 GiB/s**
- gap factor 19.562 → **9.781** (2.000× reduction)
- ms/token at current physical demand: 1304.1 → **652.1 ms**
- tok/s with no algorithmic change: 0.767 → **1.534** (still 10× short — bandwidth alone never gets there)
- **cost: $150, i.e. $25.34 per added effective GiB/s, or ~$15.3 per 1× of gap factor closed**

## VERDICT: **CONFIRMED** (with a placement correction)

Against the preregistered ACCEPT gate — "striping materially reduces the required byte reduction within budget":

- Duplication onto a second 2TB drive is **feasible** (952 GiB fits in 1862.6 GiB usable), **within budget** ($150 of a $3,000 envelope, 5%), and **materially** reduces the required byte reduction from 19.56× to 9.78× — a full 2.000× of the gap.
- The REJECT gate's two conditions both fail to trigger: duplication is *not* infeasible at 952 GiB (only on 1TB drives, which are excluded), and imbalance does *not* erase the gain **for the duplicated layout** (it costs 19.64% for the sharded layout, which is why the design must be duplication, not sharding).

**Placement design to queue: DUPLICATE, DO NOT SHARD.** Two matched 2TB drives, full container on each, dispatch-time load balancing. Rejected alternatives: uniform-hash sharding (−19.64% batch-1 barrier tax), asymmetric pairs (uniform hash is 33% *worse* than the fast drive alone).

## OBJECTIVE CHECK

`time/token = physical_bytes_per_accepted_token ÷ effective_bandwidth`, and `tok/s = 1 / (time/token)`.

This experiment moves the **denominator** only. It does not touch bytes/accepted token — 7.719 GiB/token is unchanged, no compression, no routing change, no semantics change (gate 4 trivially passes: identical bytes, identical routes, identical logits, bit-exact output). The algebraic connection is direct and exact: doubling effective bandwidth halves required time/token, equivalently halves the byte-reduction factor `physical / (BW/15)` still owed by the compression/residency side.

The honest framing: **$150 buys exactly half the remaining problem, and no more.** 19.56× → 9.78× is the single cheapest lever measured to date (compare: 1% byte saving ≈ 44.7 ms; this is worth 652 ms), but 9.78× of byte reduction is still required and remains the binding constraint. This is a denominator win that does not substitute for the numerator work.

## Caveats

- Vendor seq-read figures are marketing numbers; the 0.8531 derating is anchored on exactly one measured drive (N=1). PCIe 5.0 derated figures are **projections**, not measurements — a 5.0 drive on WARP's O_DIRECT 3029-page path may derate differently.
- Assumes two free PCIe 4.0 x4 M.2 slots with independent lanes. A shared-lane or chipset-attached slot would cap aggregate below 11.838 GiB/s. Host platform not audited here.
- Duplication doubles capacity cost (952 GiB of redundant storage), which is free on 2TB drives but forecloses using that space for anything else.
- No thermal sustained-read derating applied; sustained 100% read duty may throttle below these figures.
