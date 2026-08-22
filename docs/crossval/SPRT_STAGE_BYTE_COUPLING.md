# exp5 — whitened-basis + SPRT staged refinement (factorial)

**Verdict: `inconclusive` — the preregistered gate is denominated in a unit
(`mean VQ stages read per expert`) whose derivative on bytes/accepted token is
identically zero, and the interaction term is not measurable offline. A generous
counterfactual additionally bounds the whole family 6.5x short of the goal.**

Source SHA `cb05b14`. Working clone `/tmp/spark/warp`. **Offline-only tick**
(Winnie `CPU_LOAD_PCT=80`, RAM free 46.3/127.9 GB → over the 40% contention bar).
`E:\Projects\warp` untouched. No model was executed.
**Every number below is [RECOMPUTATION] from pinned published constants. Nothing
here is a K3 measurement.** N=1, deterministic algebra, variance N/A.

## Objective

    B_acc = M * R / a

M = physical expert-record transfers per attempted token; R = physical bytes per
transferred record; a = accepted output tokens per attempted token.

## Independent reconstruction of the expert record (validation)

Built bottom-up from `docs/K3.md` dims, with no fitting:

| quantity | value | source |
|---|---|---|
| weights/expert | 3 x 3584 x 3072 = **33,030,144** | K3.md:11,44 (latent MoE) |
| 8-dim vectors | **4,128,768** | FORMAT.md:26 |
| index payload | 4,128,768 x 3 stages x 1 B = **12,386,304 B** | waste_format.h:50 |
| header + per-channel corrections | **20,480 B** (5 pages) | FORMAT.md:284-292 |
| **total** | **12,406,784 B = exactly 3029 pages** | **matches FORMAT.md:296** |
| implied bits/weight | **3.000** | matches WQ_VQ3R spec |

The reconstruction lands byte-exact on the published record and recovers 3.00 b/w
to the digit. The record model used below is therefore not assumed — it is verified.

## Why `stages read` has zero coupling to bytes

Two published invariants:

1. **One pread, whole record.** FORMAT.md:295 — *"One `pread` of
   `record_4k_blocks * 4096` bytes yields the whole expert."*
2. **Stages are byte-interleaved, not planar.** GPU_VQ_GB10.md:57-59 — a CTA
   *"walks vector positions in ascending order and reads the **three adjacent
   stage bytes** for each row."*

SPRT early-stop is a **post-fetch decode decision**. The bytes have already
crossed the NVMe link before stage 1 is evaluated, and the three stage bytes for
a given vector are physically adjacent, so no stage is independently addressable.
Hence for stages-read s ∈ {1,2,3}:

    R(s) = 12,406,784 B  (invariant)      dR/ds = 0
    M unchanged (routing is upstream)      dM/ds = 0
    a held fixed by the spec's own metric  da/ds = 0
    ==> dB_acc/ds = 0

The primary metric is parenthetically declared a *"proxy for bytes/accepted
token"*. It is not a proxy; it is orthogonal. The accept gate can pass by a wide
margin with **byte-for-byte identical** I/O and identical tok/s. SPRT here buys
arithmetic, and the verifier is already established as **100% I/O bound** — so
even the arithmetic saving cashes out at zero.

## Generous counterfactual: what if stages *were* separable?

Segregating stages into three planes would break the one-pread contract and the
fixed-length O_DIRECT record, but it bounds the ceiling of the entire family.
Page-quantised (4 KiB granularity is still mandatory):

| mean stages read | R (B) | GiB/token | tok/s | speedup |
|---|---|---|---|---|
| 1.0 | 4,149,248 | 2.5815 | 2.293 | 2.99x |
| 1.5 | 6,213,632 | 3.8659 | 1.531 | 2.00x |
| 2.0 | 8,278,016 | 5.1502 | 1.149 | 1.50x |
| 2.5 | 10,342,400 | 6.4346 | 0.920 | 1.20x |
| 3.0 (baseline) | 12,406,784 | 7.7190 | 0.767 | 1.00x |

**Ceiling = 2.99x** (perfect oracle, one stage always sufficient, zero SPRT error).
**15 tok/s needs 19.56x.** The most generous physically-impossible version of this
idea is **6.5x short of the goal**, and that is before charging for the O_DIRECT
regression that separable planes would cause.

## The factorial itself is not measurable this tick

gain(A), gain(B) and gain(A+B) each require refitting VQ stages on real Kimi
expert weights against an activation importance matrix. Neither the weights nor
an activation covariance are in-repo, and `docs/gn100/*.json` publishes **no
per-stage certification counts** (searched: the only `accept*` keys remain
`accepted_scope`, `accepted_cuda_vq`, `accepted_vq_group` — scope counters).
Winnie at 80% CPU forbids generating them. So the interaction term is unmeasured;
the reject gate (`interaction <= 0`) is **not** claimed to have been crossed.
That is why this is `inconclusive` and not `falsified`.

Inherited constraint: parent A (exp1) was already ruled undecidable — its bit
budget is self-contradictory and it has no measured error→acceptance mapping.
A factorial cannot be better-posed than its arms.

## What a corrected gate must say

    ACCEPT iff  (M * R_page_quantised) / a  strictly decreases

with R measured **after** 4 KiB page quantisation. For SPRT specifically this
requires a prior format change — stage-segregated planes with independently
addressable, page-aligned per-stage extents — whose ceiling is bounded at 2.99x
above. Recommend the research job **retire the SPRT-on-bytes framing** and, if
staged refinement is revived at all, preregister it against latency under a
regime where expert I/O is *not* the binding constraint.
