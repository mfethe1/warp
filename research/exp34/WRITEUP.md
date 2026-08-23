# exp34 — VQ4P iso-byte kernel substitution: geometry CONFIRMED, distortion in the spec's dead band, prediction REFUTED by the repo's own REAL-K3 data

Pinned SHA: `7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b`
Lane: `offline` (this Mac, M4). No K3 weights touched. `E:\Projects\warp` untouched.

## Stage 1 — GEOMETRY [RECOMPUTATION] — PASS, exactly

Bottom-up from `src/waste_format.h` + `docs/FORMAT.md` at the pinned SHA, over the
established K3 expert shape (3 matrices x 3072 x 3584 = 33,030,144 weights, 4,128,768
8-dim vectors):

| | VQ3R | VQ4P |
|---|---|---|
| stages x entries x index_bits | 3 x 256 x 8 | 4 x 64 x 6 |
| bits/weight | **3.00** | **3.00** |
| index bytes per vector | **3** | **3** |
| index payload | 12,386,304 B | 12,386,304 B |
| record | **12,406,784 B** | **12,406,784 B** |
| pages | **3029** | **3029** |
| stage table (int8, dim 8) | 2048 B (16 vec regs) | **512 B** |

All seven preregistered geometry checks pass. The 6-bit packing in FORMAT.md
(`s0=b0&0x3f`, `s1=(b0>>6)|(b1&0x0f)<<2`, `s2=(b1>>4)|(b2&0x03)<<4`, `s3=b2>>2`)
was verified bijective over 147,456 cases.

**d(bytes per accepted token)/d(format) = 0 EXACTLY.** The record is byte- and
page-identical, so O_DIRECT alignment is preserved and the byte program is
entirely unaffected. Stage 1 is not the falsifier; it is the gate that says the
falsifier is worth running. It passed.

## Stage 2 — DISTORTION [SYNTHETIC] — lands in the spec's undefined band

WARP's own `src/vq.c` at the pinned SHA, compiled unmodified
(sha256 `eb797e7c9c227f3fd29a6542ec0d557d646b5377e65297c835eb16151c360251`).
`waste_vq_lloyd` fits each stage, `waste_vq_encode` produces the codes; the only
added code is a decode shim that is the algebraic inverse of residual VQ.

**This machine has no K3 weights.** Weights are SYNTHETIC (low-rank correlated +
iid, heavy-tailed per-input-channel scale) and the activation second moment is
SYNTHETIC (log-normal, the AWQ salient-channel shape). Per-output-row f16 scale
applied as the format specifies. Decision metric is activation-weighted relative
error — Frobenius is diagnostic only (established mismatch #4).

N=5 seeds, 12 Lloyd iterations, 393,216 vectors per fit:

| | mean | sd |
|---|---|---|
| VQ3R activation-weighted rel err | 0.19753 | 0.00395 |
| VQ4P activation-weighted rel err | 0.21889 | 0.00397 |
| **VQ4P degradation** | **+10.82%** | **0.23%** (range +10.56 .. +11.15) |

Preregistered gates: ACCEPT if <=5%. REJECT if >15%. **+10.82% is neither.**
The spec has an undefined 5–15% band and the measurement landed in it. Per
procedure, that is `inconclusive` on the distortion gate, and the gate is not
moved after seeing data.

Direction is corroborated by the repo's own measurement: LEARNED §41 records
**+2.7% perplexity** on Kimi-Linear for VQ4P (10.937 -> 11.237), all of it from
the codebook shape, with the int8 table free. My synthetic overstates the
magnitude, as expected — synthetic weights lack K3's QAT homogenization — so the
right reading is "same sign, magnitude not transferable."

## The prediction is REFUTED by REAL-K3 data already in the repo at this SHA

The idea predicted **4.48x** at 4 cores, cores-for-15-tok/s from 50.37 to 11.24,
and the compute ceiling at 10 cores from 2.978 to 13.349 tok/s. The repo already
measured this end to end [REAL-K3, LEARNED §46], both containers on the same disk,
same build, `kda` control unchanged, medians of 13 VQ4P vs 5 VQ3R runs:

| | VQ3R | VQ4P | |
|---|---|---|---|
| **s/token** | **1.65** | **1.52** | **1.086x** |
| LUT apply | 11.21 | ~9.6 | 1.17x |
| expert I/O | 3.15 | 3.69 | more exposed |

The kernel really is 3.88x in isolation against a gigabyte of indices (so it is
not a cache artefact), and 3.32x on K3's gate shape — but in the engine VQ4P runs
at essentially its single-thread rate: 25.3 GB/s alone vs 27.2 GB/s at ~10
threads (**1.07x scaling**), while VQ3R scales 6.5 -> 23.3 GB/s (3.6x). §47
explains it: VQ4P peaks on P-cores and degrades past them (91.3 -> 73.2 GB/s)
because `waste_parallel_for` cuts one task per thread and an E-core straggler
holds the barrier.

So the 4.48x in the prediction is a single-thread kernel ratio being applied to a
threaded engine. Measured end-to-end on K3 it is **1.09x**. The gap between
3.88x on a bench and 1.17x in place is the whole finding, and it was already
recorded before this experiment was queued.

## Objective check

Optimized: the arithmetic term (`LUT apply`), not the byte term. Algebraically,
`tok/s = effective_bandwidth / physical_bytes_per_accepted_token`. Stage 1 proves
the denominator is *exactly* invariant under VQ3R->VQ4P (identical 12,406,784 B
record). So VQ4P cannot move bytes/accepted token at all — it can only raise
effective bandwidth by removing a compute stall that was hiding reads. REAL-K3
says that is worth 1.09x, and expert I/O becomes *more* exposed (3.15 -> 3.69),
which is the signature of a compute win handing the bottleneck back to the disk.

## Recommendation

Do not fund the AVX2/`vpshufb` port as a 4.48x lever; the ARM-side end-to-end
number at the same SHA is 1.09x and the binding constraint is fork-join
scheduling, not table width. The scheduling defect (§47: one task per thread,
E-core stragglers, oversubscription partially recovering) is the cheaper and
larger target, and it needs no reconversion of 982 GB.
