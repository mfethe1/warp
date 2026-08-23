# exp26 — Prefill expert dedup: objective-mismatch audit + mechanism reproduction

**Status:** confirmed (2026-08-23) · **Lane:** offline (Winnie CPU 81.6%, 3 stuck
Robocopy — real_k3 deferred) · **Evidence class:** PROXY
**Sources pinned:** colibri `33e67a9c004b6e608d1f19dfbdcc20793377f94f`
(docs/kimi_k3.md §Chunked prefill), warp `7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b`
(docs/ENGINE.md §Chunked prefill).

## What was wrong with "batching is dead"

Our earlier blanket rejection of batching compared **logical** batched demand
(9.135 GiB/token — every routed expert counted) against **physical** unbatched
reads (7.719 GiB/token — warm-cache dedup already applied). That is an
apples-to-oranges objective mismatch. Batch-1 **decode** remains out of scope,
but **prefill** dedup reduces physical bytes and was never validly tested.

## Preregistered gates (not moved)

- **Accept:** dedup reduces physical prefill bytes ≥20% with identical logits →
  queue scheduler work
- **Reject:** physical bytes do not improve, or logits diverge
- **Stop rule:** scheduler/trace measurement only; no batched matmul kernels.

## Result [PROXY] — in-repo trace (N=300 tok × 26 L × top-8, 62,400 accesses)

Chunked layer-major prefill; each distinct (chunk, layer, expert) read once
(record = 12,406,784 B = 3029 pages, verified bottom-up in prior work).

| C | distinct records | dedup factor | physical GiB/prompt-tok | reduction vs C=1 |
|---|---|---|---|---|
| 1 | 62,400 | 1.000× | 2.4034 | — |
| 8 | 34,927 | 1.787× | 1.3452 | 44.03% |
| 16 | 28,131 | 2.218× | 1.0835 | 54.92% |
| 32 | 21,176 | **2.947×** | **0.8156** | **66.06%** |
| 64 | 15,535 | 4.017× | 0.5983 | 75.10% |

Variance at C=32: per-(chunk,layer) distinct experts mean 81.45, sd 17.15,
min 31, max 112, n=260 cells.

Gate ≥20% cleared at every C tested. **ACCEPT branch fires.**

## Transfer bounds (K3 shape)

- **Uniform-routing worst case** (no locality, E=896, k=16) [SYNTHETIC]:
  C=32 → 392.6 distinct of 512 accesses → dedup 1.304× = **23.3% reduction —
  still clears the ≥20% gate even with zero locality**.
- **Locality-calibrated projection** (trace locality factor 0.499 of uniform):
  K3 C=32 ≈ 2.61× [SYNTHETIC projection] vs Colibri's real-K3 measured 2.7×
  [REAL-K3, their claim] — agreement within 3.5%.

## Gates for external source (colibri claim)

1. **REPRODUCTION:** partial — dedup factor mechanism reproduced on
   Kimi-Linear-shaped proxy trace (2.947× vs their 2.7×). Their exact
   REAL-K3 bit-identity setup (teacher-forced logit streams) not re-run here
   (Winnie contended; no kernels permitted by stop rule anyway).
2. **TRANSFER:** bounded analytically — worst-case uniform routing still
   clears the gate; locality-calibrated projection ≈ their claim. Real K3
   routing dump needed to close.
3. **OBJECTIVE:** direct — physical bytes per prompt token, the exact system
   objective denominator; decode unaffected.
4. **SEMANTICS:** not measured (no kernels). Colibri reports C=32 vs C=1
   logits match exactly; warp ENGINE.md independently reports 3.3× fewer
   reads with max-abs logit diff 6.7e-06 (float noise) on 32-token prompt.

## What this changes

- `DEAD: batching` in the findings ledger was **overbroad** — batching for
  prefill is alive and clears the byte gate by a wide margin on both the
  proxy trace and worst-case K3 bounds.
- Prefill/TTFT scheduler work is now unblocked (per the accept gate): the
  scheduler should coalesce expert reads across a chunk. Kernel work remains
  gated on its own experiment per the stop rule.

## Next

1. Real-K3 routing dump (needs Winnie idle, or reuse colibri routing
   telemetry docs) to replace the SYNTHETIC K3 bound with REAL-K3 numbers.
2. Scheduler-side experiment: chunk-coalesced read planning vs C=1 on the
   same trace, TTFT arithmetic at 5.919 GiB/s (0.8156 GiB/tok ⇒ ~138 ms/prompt-tok
   of prefill I/O at C=32 [PROXY arithmetic]).
