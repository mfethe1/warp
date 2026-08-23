#!/usr/bin/env python3
"""exp45 stage 1+2 recomputation. Stage 1: colibri decode wall split from
published #1183 PROF split and #1178 merged measurement. Stage 2: M4 lutbw
kern_A aggregate at T=4 vs exp30 effective bandwidth 7.017 GiB/s."""
import json, statistics as st

# ---------- STAGE 1 [RECOMPUTATION from published colibri numbers] ----------
# Issue #1183 (JustVugg comment 2026-08-23T07:27Z, GLM-5.2 int4, i9-14900K+3090):
#   "attention 33.6s + expert-matmul 50.5s ~= 84s of compute in the 182s decode"
#   "expert-disk WAIT 83.4s"
attn, expert_mm, disk_wait, wall = 33.6, 50.5, 83.4, 182.0
compute = attn + expert_mm
resid = wall - compute - disk_wait
pre_share = expert_mm / wall
attn_share = attn / wall
# PR #1178 (merged a2aba48, in dev 5129f83..4032232): attn phase 172.8 -> 148.0
# ms/token = -14.4% (merged measurement, N=3 pairs interleaved, median;
# the -27.6%/172.7->125 figure in the spec was the author's gather-STUB
# upper bound, not a shipped measurement).
attn_post = attn * (148.0 / 172.8)
wall_post = wall - (attn - attn_post)
share_post = expert_mm / wall_post
attn_share_post = attn_post / wall_post

# Sensitivity: IF the stub ceiling (-27.6%) had been realized
attn_stub = attn * (125.0 / 172.7)
wall_stub = wall - (attn - attn_stub)
share_stub = expert_mm / wall_stub

# ---------- STAGE 2 [SYNTHETIC, M4, N=5, this run] ----------
a_gbs = [5.1, 4.9, 5.1, 5.2, 4.9]           # printed at 0.1 resolution
a_ms  = [47.854, 50.596, 48.511, 47.469, 50.133]
agg_T4 = [g * 4 for g in a_gbs]             # aggregate at T=4 cores
B_eff_target = 7.017                          # GiB/s, exp30 dup-4x at target miss
t_cpu_over_t_io = [g4 / B_eff_target for g4 in agg_T4]

out = {
  "stage1": {
    "class": "RECOMPUTATION (published colibri numbers, not our measurement)",
    "pre_fix": {"attn_s": attn, "expert_mm_s": expert_mm, "disk_wait_s": disk_wait,
                 "wall_s": wall, "residual_s": round(resid, 1),
                 "expert_share": round(pre_share * 100, 2),
                 "attn_share": round(attn_share * 100, 2)},
    "post_1178_merged": {"attn_delta_pct": -14.4, "attn_s": round(attn_post, 2),
                          "wall_s": round(wall_post, 2),
                          "expert_share": round(share_post * 100, 2),
                          "attn_share": round(attn_share_post * 100, 2)},
    "post_1178_stub_ceiling": {"attn_delta_pct": -27.6, "attn_s": round(attn_stub, 2),
                                "wall_s": round(wall_stub, 2),
                                "expert_share": round(share_stub * 100, 2)},
    "note": "spec quoted -27.6% (172.7->125) which is the PR's gather-stub TIMING "
            "upper bound; the merged AVX2 SIMD measurement is -14.4% (172.8->148.0)."
  },
  "stage2": {
    "class": "SYNTHETIC microbench (lutbw kern_A, M4, pinned harness, N=5)",
    "kern_A_ms": a_ms, "kern_A_per_core_GiB_s": a_gbs,
    "mean_per_core": st.mean(a_gbs), "sd_per_core": round(st.stdev(a_gbs), 3),
    "aggregate_T4_GiB_s": agg_T4, "mean_aggregate_T4": st.mean(agg_T4),
    "B_eff_target_GiB_s": B_eff_target,
    "t_cpu_over_t_io": [round(r, 3) for r in t_cpu_over_t_io],
    "mean_t_cpu_over_t_io": round(st.mean(t_cpu_over_t_io), 3)
  },
  "gates": {
    "accept": "expert share >=25% pre-fix OR post-fix share >=40% OR M4 t_cpu/t_io >= 1.0",
    "reject": "post-fix expert share <15% OR (pre-fix share <15% AND M4 t_cpu/t_io < 0.5)",
    "eval": {
      "pre_share_27_74_ge_25": pre_share >= 0.25,
      "post_share_29_58_ge_40": share_post >= 0.40,
      "m4_ratio_2_86_ge_1": st.mean(t_cpu_over_t_io) >= 1.0,
      "reject_post_lt_15": share_post < 0.15,
      "reject_pre_lt_15_and_ratio_lt_0_5": (pre_share < 0.15) and (st.mean(t_cpu_over_t_io) < 0.5)
    }
  }
}
print(json.dumps(out, indent=2))
with open("exp45_result.json", "w") as f: json.dump(out, f, indent=2)
