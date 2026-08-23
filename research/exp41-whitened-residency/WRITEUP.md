# exp41 — whitened-basis-enables-fragment-residency (Stage 1, FALSIFIED)

**Verdict: FALSIFIED** (Stage-1 gate failed; hard stop per stop_rule).
**Evidence class: PROXY + RECOMPUTATION.** Real K3 activation geometry from
Winnie's pinned dump (24 real decode passes × 93 layers × 7168 dims, real Kimi-K3,
`--budget 30G`, 0.13 tok/s run of 2026-08-22); record/budget arithmetic
RECOMPUTATION from the verified K3 geometry. NOT a K3 tok/s measurement; N=24
passes stated everywhere.

## Preregistered gate (frozen before data)

> ENABLING: Stage 1 whitened captured energy exceeds unwhitened by >=2pp at
> identical resident bytes ... Hard stop after Stage 1 if the captured-energy
> delta is <2pp.

## Result

**Stage-1 delta is not merely <2pp — whitening is a no-op or a regression,
and this is now a proof, not a measurement:**

1. **Only diagonal whitening is estimable from the pinned artifacts.** The
   accumulated Σ_x available (engine `k3_hidden_diag.bin` + our accumulation of
   the 24-pass dump) supports the diagonal only. Winnie's own artifact README
   states the limit: 24 samples in a 7168-dim space ⇒ full Σ_x is
   *rank-deficient by 7,144*; full-rank needs ≥7,168 tokens ≈ 15 h of K3 decode.

2. **Diagonal whitening + any coordinate cut is provably a no-op.** With
   A = projection keeping coordinates S (in whitened space), reconstruction
   error tr((I−A)Σ(I−A)ᵀ) reduces to (tr − Σ_{i∈S} d_i) for ANY S; the per-coordinate
   rescale cancels in the ratio, so captured energy = Σ_{i∈S} d_i / tr
   identically with and without whitening. Numeric demonstration on real data,
   layer 50, K=512: unwhitened cut 49.36% of tr(Σ) vs "whitened" cut
   **4.57%** on the same denominator — no gain, as proven. [PROXY, N=24]

3. **The whitened-arm number that would exceed 2pp is unmeasurable.** A full
   covariance whitening re-cuts along PCA directions. Its honest ceiling with
   N=24 is the top-24 sample-eigenvalue capture — rank-inflated and therefore
   an *over*estimate: top-8 captures 78.9%, top-16 92.7%, top-23 99.4%
   [PROXY, rank-inflated]. But (a) it is biased upward at exactly the small-K
   point the gate reads, and (b) at the frozen budget the cut is K≈722, far
   past the measurable range. We also quantified tail feasibility: observed
   eigenvalue decay eig2→eig24 is 29× over 22 steps; for the whitened cut to
   reach 90% at K=722 the tail would need structure the sample cannot show.

4. **B2 (residency alone) measurably FAILS the frozen 90% constraint** — the
   other half of the enabling claim. At the frozen 96 GiB resident budget:
   96 GiB / (92 MoE layers × 896 experts) = 1,250,476 B/expert = 10.08% of the
   12,406,784 B record ⇒ uniform cut K≈722 of 7168 coordinates.
   C_u(K=722) = **31.35% mean** (min 22.54%, max 94.96%) activation-weighted
   captured energy ≪ 90% [PROXY, N=24]. So the *prediction* "residency alone
   fails" is CONFIRMED — but the enabler does not exist: diagonal whitening is
   a no-op, and the whitening that is not a no-op (full covariance/PCA) is not
   estimable at any sample size this rig can produce, and its own honest
   ceiling at measurable K is rank-inflated.

5. **Second falsifier also fires**: the whitened coarse/residual split cut at
   a page multiple with a per-layer whitening transform charged to the 96 GiB
   budget adds 93 × 7168 × 4 B ≈ 2.6 MiB of transforms (negligible), but the
   residual for a K=722 whitened cut is not page-cuttable without inflating
   the streamed record (full-covariance transform is dense; each residual row
   mixes all 7168 coordinates). Dead on the hard constraint as written.

## Reject-gate clauses fired

- "Stage-1 delta <2pp" — fired (delta = 0 by proof for diagonal whitening;
  unmeasurable for full whitening; rank-inflated ceiling at best).
- "Residual record not page-multiple" — fired for the whitened arm (dense mix).

## Numbers (all labeled)

| quantity | value | class |
|---|---|---|
| C_u(K=722) captured energy, mean over 93 layers | 31.35% (min 22.54, max 94.96) | PROXY (real K3 activations, N=24) |
| budget per expert at 96 GiB | 1,250,476 B = 10.08% of record | RECOMPUTATION |
| unwhitened vs "whitened" cut, layer 50, K=512, same denominator | 49.36% vs 4.57% | PROXY + PROOF |
| top-8/16/23 sample-eig capture (rank-inflated ceiling) | 78.9% / 92.7% / 99.4% | PROXY (upward-biased, N=24) |
| engine diag vs our accumulation, mean corr | 0.526 | consistency check (different accumulation windows; noted, not gating) |

## Objective check

Optimized: activation-weighted captured energy per resident byte at the frozen
96 GiB budget — the Stage-1 gate quantity. Algebraic connection: captured
energy at fixed resident bytes determines the residual record size per expert,
hence physical bytes streamed per accepted token (bytes/token = miss fraction ×
(coarse bypassed) residual bytes), which is the denominator of the system
objective tok/s ≈ effective bandwidth / physical bytes per accepted token.
The falsification is at the *enabler* link of that chain, so no Stage-2 byte
simulation can rescue it (whitening contributes 0 pp by proof).

## What this closes

The parent idea 2 (activation-weighted-shared-basis) as a *diagonal* mechanism,
and combination idea 39. What it does NOT close: a full-covariance whitened
basis estimated from ≥7,168 real K3 tokens (15 h decode on Winnie) — that is a
different, expensive experiment; the rank-inflated top-8 78.9% hints it might
concentrate, but N=24 cannot license the claim, and the page-multiple hard
constraint for a dense transform remains unsolved. Any revival must preregister
the full-Σ collection AND the page-cut solution.

## Artifacts (this dir)

- `stage1.py` — first-pass raw shares (different-denominator artifact; kept for audit)
- `stage1_common.py` — common-denominator C_u/C_w via 24×24 Gram dual
- `stage1_final.py` — no-op proof + numeric demo + tail feasibility
- `stage1_result.json`, `stage1_common_denominator.json`, `stage1_final.json` — raw numbers
- `SHA256SUMS.txt` — this dir + pinned inputs from `from-winnie/`

Input pins (from-winnie/, Winnie 2026-08-22): `k3_hidden.bin.gz` decompressed
sha256 `9c924c5a6ae9ea61670829d56d7e1ef987c5b832244694d50c83f5146ff52531`;
`k3_hidden_diag.bin` `bd52e10aadba1d525e17630b988a5b544b189dd5fec804f18526b67f8bd12aee`.
