# exp45 — decode-kernel-critical-path-reweighting

**Verdict: CONFIRMED** — accept gate fired on condition 1 AND condition 3; kernel lane live for BOTH regimes. Evidence classes: Stage 1 RECOMPUTATION (published colibri numbers, not our measurement), Stage 2 SYNTHETIC (M4 microbench, pinned harness, N=5). No K3 measurement anywhere in this writeup.

Date: 2026-08-23. Lane: `offline`. Machine: Mac only (CPU ~80% busy from the parallel coding loop — Winnie untouched, E:\Projects\warp untouched).

Sources, pinned read-only:
- colibri dev `40322324` worktree at `/tmp/warp-sources/colibri/40322324` (fetched via existing clone 33e67a9 + git worktree, $0)
- Issue #1183 comment JustVugg 2026-08-23T07:27Z (GLM-5.2 int4, i9-14900K + RTX 3090): "attention 33.6s + expert-matmul 50.5s ≈ 84s of compute in the 182s decode"; "expert-disk WAIT 83.4s"; "caching is not the binding constraint at 71.0% hit rate"
- PR #1178 (merged `a2aba48`, in dev 5129f83..4032232): attn 172.8 → 148.0 ms/token = **−14.4%** merged measurement (3 interleaved pairs, median); stub ceiling −27.6% (172.7→125) is the PR's timing-only upper bound

## STAGE 1 — colibri wall split [RECOMPUTATION]

| quantity | pre-fix | post-#1178 (merged −14.4%) | post (stub ceiling −27.6%) |
|---|---:|---:|---:|
| attention | 33.6 s | 28.81 s | 24.36 s |
| expert-matmul | 50.5 s | 50.5 s | 50.5 s |
| disk WAIT | 83.4 s | 83.4 s | 83.4 s |
| wall | 182.0 s | 177.2 s | 172.8 s |
| **expert-FFN compute share** | **27.74%** | **28.50%** | 29.24% |
| attention share | 18.46% | 16.26% | 14.10% |

- Spec prediction "expert share ≥25% pre-fix": **PASS** (27.74%).
- Spec prediction "post-fix share ≥40%": **FAIL** — directionally right but unreachable via attention-kernel fixes alone; even attn→0 gives only 50.5/148.4 = 34.0%. Crossing 40% additionally requires shrinking the 83.4 s disk WAIT (their #1180-family work), i.e. the two lanes compose.
- **Spec correction on record:** the spec's provenance quote "−27.6% with no change in bytes" is the PR's gather-STUB timing bound; the merged AVX2 SIMD measurement is −14.4%. Gate arithmetic evaluated on both; outcome identical.

## STAGE 2 — M4 t_cpu/t_io [SYNTHETIC, N=5]

Pinned unmodified `tools/lutbw.c` (sha256 f22f3e3a…b3986, same as exp33), `-DM_ROWS=196608`, 252 MB DRAM-resident index stream:

kern_A per-core: 5.1, 4.9, 5.1, 5.2, 4.9 GiB/s → mean **5.04, sd 0.134** (reproduces exp33's 4.9427/5.065 band).

| interpretation | formula | value |
|---|---|---:|
| spec-literal (byte-volume-agnostic) | (4 × 5.04) / 7.017 | **2.873** |
| physically correct (exp33 fixed point) | t_cpu/t_io = (17.009/20.16)/(0.3946/7.017) | **15.00** |

Both ≥ 1.0 → **accept condition 3 fires on M4 too.** Note honestly: the spec's own prediction text ("~19.7 GiB/s vs 7.017 gives t_cpu/t_io < 1") was arithmetically inconsistent with its own quoted inputs (19.7/7.017 = 2.81); the measured quantity is reported, the gate is evaluated on the measurement, and gates were not moved. Bonus: kern_D (VQ4P tbl4q) re-measured 23.5–25.0 GiB/s per core, speedup 4.73–4.92x, consistent with exp33/exp34's 4.48x.

## GATES (preregistered, verbatim)

> ACCEPT: expert share ≥25% pre-fix OR post-fix share ≥40% OR Stage-2 M4 t_cpu/t_io ≥ 1.0. REJECT: post-fix share <15% OR (pre-fix <15% AND M4 ratio <0.5).

- 27.74% ≥ 25% → **ACCEPT (cond 1)**
- 28.50% ≥ 40% → no (cond 2)
- 2.873 (and 15.00) ≥ 1.0 → **ACCEPT (cond 3)**
- reject: 28.50% not < 15%; pre 27.74% not < 15% → **REJECT gate does not fire**

## OBJECTIVE CHECK

Optimized: the **effective-bandwidth term**, not bytes. Connection is algebraic: `tok/s = 1 / max(B_phys/BW_eff, B_log/(r·C))`. The kernel lane raises r (gather/dequant rate); exp33 gives break-even `B* = B_log·BW/(r·C)`, so raising r 4.73–4.92x (kern_D, re-confirmed today) divides B* by the same factor — e.g. B*(4 cores) 4.969 → ~1.03 GiB/token, which would make the byte program (target 0.3946) pay again below the wall. min() law NOT invalidated — it is the composition model, and it is what makes the kernel lane the prerequisite lever. Upstream transfer candidate for colibri-class x86 rigs: colibri PR#41 vq_rows_p6 VBMI kernel (author thanked @mfethe1) remains the ready-made k_cat lever.

## EVIDENCE

`~/.hermes/state/warp-research/evidence/exp45-kernel-critical-path/`: stage2_raw.log, calc.py, exp45_result.json, lutbw.c, SHA256SUMS.txt (sha256s inside). Colibri worktree /tmp/warp-sources/colibri/40322324 (HEAD 4032232).

## NEXT

1. Queue a corrected successor for the ≥40% sub-question: "expert-share ≥40% requires disk-WAIT reduction composed with attention fixes — test composition of #1178+#1180-family on colibri's own PROF telemetry" (external-source, 4 gates apply).
2. exp34 kern_D substitution remains the top internal item — today's re-run (4.73–4.92x) strengthens it; it converts this experiment's M4 finding into tok/s.
3. Re-score remaining I/O-term ideas (exp19/exp31/exp35 family) per exp33's retro-gate: worth 1.00x until the gather term moves.
