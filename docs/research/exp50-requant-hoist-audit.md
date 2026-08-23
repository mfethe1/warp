# exp50 — kernel-lane-activation-requant-hoist-transfer — Stage 1 call-count audit

**Run:** 2026-08-23 ~22:45 EDT · lane `offline` · evidence class: RECOMPUTATION (static source audit)
**Verdict: FALSIFIED (reject gate met: r_q = 1 — WARP already hoists; colibri's ~16x requant pattern is absent)**

## Spec pin defect (recorded, did not block)
Spec `source_sha` = `33e67a9c004b6e608d1f19dfbdcc20793377f94f`. That SHA is the **colibri** pin
(prior evidence: exp24/27/28 all pin colibri at this SHA); it does NOT exist in sqliteai/warp or
mfethe1/warp (verified: `git fetch upstream <sha>` → "not our ref"; `gh api` both repos → 422).
Audit executed instead at THREE valid warp pins, all agreeing identically:
- `fd0deabc62b6e2e86d245553f61e77397a48a3b8` (canonical research pin from exp24)
- `7f1fbba3` (existing /tmp/warp-sources pin)
- `619b666a1c15404a947f92cf0f684d7c2f4c3dcd` (upstream HEAD, 2026-08-23)

## Same-input check (the decisive question)
The activation-quantization unit in WARP's VQ decode path is **vq_build_lut** (src/model.c),
which quantizes the input vector x into per-group LUT entries (+ optional int8 shadow via
vq_quant_lut). `quant_act` (model.c:415 @ fd0deabc) serves only trunk projections (matvec_t,
SDOT path) — called once per projection, never per expert. vq.c / simd_avx512.c / waste.c
contain ZERO activation-quant call sites (counts verified = 0 at all three pins).

## Call counts per MoE layer per token (decode), all three pins
| Path | gate LUT build | up LUT build | down LUT build |
|---|---|---|---|
| expert-parallel (`lut_done` flag) | **1** | **1** | K (per expert) |
| serial fallback (`lut_ready` flag) | **1** | **1** | K (per expert) |
| batched prefill (per-token `lut_ready`) | 1/token | 1/token | K/token |

file:line evidence @ fd0deabc — expert-parallel hoist: model.c:3595,3613–3621 (`lut_done`,
builds lut_gate/lut_up once from recs[0], passes shared `a->lut_gate/a->lut_up` to
moe_expert_range at 3623–3625; consumed at 2832–2834). Serial hoist: model.c:3647,3674–3695
(`lut_ready`; comment at 3672–3673 states the invariant verbatim: "gate/up see the same input
and the same per-layer codebooks for every routed expert, so their tables are built once per
token"). Same structure at 7f1fbba3:2825–2895 and HEAD:2821–2891.

**Same-input-same-output:** gate/up input is `xin` (router output, expert-independent) and the
per-layer codebook `h->codebook_id + {0,1}*stages` — identical for all K experts → TRUE common
subexpression, already hoisted. Down input is `ga = silu(gate)*up` — **expert-specific**
(different weights ⇒ different intermediate) → NOT a shared subexpression; rebuilding K times
is semantically required. vq_build_lut's own comment (model.c:2405–2409 @ fd0deabc) documents
that the hoist was done deliberately: "gate and up are built once per token and applied once
per routed expert, so doing it there ran the same pass top_k times."

## Reject gate (preregistered)
"REJECT: r_q = 1 (WARP already hoists) OR activations differ per expert call" — **first arm
met**: r_q = 1 for every expert-shared activation quantization in the decode path. The only
per-expert quantization (down, K builds) fails the same-input precondition, so hoisting it is
semantically wrong (second arm). Transfer DEAD, matching predicted Outcome A.

## Cross-check vs colibri prior
Colibri CHANGELOG v1.7.0 #1071's ~16x serial requant exists because their engine re-quantized
inside a per-expert loop. WARP's design already amortizes: hoist is load-bearing in all three
decode paths and stable across fd0deabc → HEAD (no regression introduced since). This is
corroborating negative evidence for upstream-PR context: WARP's VQ layout amortizes activation
quantization by construction.

## Objective check
Optimized: none (audit only). What was measured: redundancy factor r_q of activation
quantization in the decode path. Connection to system objective: serial-time recovery would
have been (r_q−1)/r_q of activation-quant wall time at ZERO byte cost — i.e., an effective-
bandwidth raise with unchanged bytes/accepted token. With r_q = 1 the recoverable fraction is
0; the down-projection builds that DO repeat are not hoistable (different inputs). No path to
the ≥15 tok/s goal through this mechanism.

## Numbers (labels)
- r_q (gate/up activation quant, decode) = 1 — **RECOMPUTATION**, static call-count audit, N=3
  pins, zero variance (identical structure at fd0deabc, 7f1fbba3, upstream HEAD 619b666a).
- down-LUT builds per layer per token = K (=top-16 for K3) — **RECOMPUTATION**, same audit;
  expert-specific inputs, semantically not shareable.
- quant_act sites outside MoE-VQ decode: 2 (trunk matvec_t SDOT path, batched i8mm prefill),
  both once-per-tensor-per-token — **RECOMPUTATION**.
