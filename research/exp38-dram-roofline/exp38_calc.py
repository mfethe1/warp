#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# exp38 STAGE 2-4: recomputation from the measured Stage 1 roofline.
# NO new measurement. Pure algebra over exp38_stage1_T4.json + published nameplates.
import json, os, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
S1 = json.load(open(os.path.join(HERE, "exp38_stage1_T4.json")))

L_LOGICAL = 17.0085          # GiB logical demand per token (established finding)
L_PHYS    = 7.719            # GiB physical per token (established finding)
GOAL      = 15.0             # tok/s
GB_TO_GIB = 1e9 / (1024**3)  # vendor GB/s -> GiB/s

D     = S1["arms"]["D"]["mean_read_GiB_s"]
CPY   = S1["arms"]["CPY"]["mean_read_GiB_s"]
RDSUM = S1["arms"]["RDSUM"]["mean_read_GiB_s"]
T     = S1["T"]

M4_NAMEPLATE_GBs = 120.0
M4_NAMEPLATE = M4_NAMEPLATE_GBs * GB_TO_GIB     # 111.759 GiB/s

# ---- gate adjudication -------------------------------------------------
# literal preregistered control = memcpy/STREAM-triad. memcpy moves 2 bytes of
# DRAM traffic per byte of SOURCE read, so comparing D's read rate to memcpy's
# read rate compares two different physical quantities.
lit_ratio  = D / CPY                 # literal gate arithmetic
read_ratio = D / RDSUM               # dimensionally-matched read-only control
# total-DRAM-traffic normalization
D_write_gib_per_stream = (S1["m_rows"] * 4) / (1024**3)
D_read_gib_per_stream  = S1["nidx_bytes"] / (1024**3)
D_total = D * (1.0 + D_write_gib_per_stream / D_read_gib_per_stream)
CPY_total = CPY * 2.0
total_ratio = D_total / CPY_total

# ---- Stage 2: ceilings -------------------------------------------------
r_measured = D / M4_NAMEPLATE                  # this run, T=4 P-cores
r_exp35    = 90.659 / M4_NAMEPLATE             # exp35 best-ever D (higher T)

def ceiling(b_achiev):  return b_achiev / L_LOGICAL
req_achiev = GOAL * L_LOGICAL                  # 255.13 GiB/s achievable

PLATFORMS = [
    # name, nameplate GB/s, DRAM capacity GiB, verified?, note
    ("M4 24GB (this Mac)",            120.0,   24, True,  "MEASURED this run"),
    ("DDR5-5600 dual-channel desktop", 89.6,  192, False, "NAMEPLATE-UNVERIFIED"),
    ("8-channel DDR4-3200 server",    204.8,  512, False, "NAMEPLATE-UNVERIFIED"),
    ("12-channel DDR5-4800 server",   460.8,  768, False, "NAMEPLATE-UNVERIFIED; >$3000"),
    ("RTX 5060 Ti 16GB VRAM",         448.0,   16, False, "NAMEPLATE-UNVERIFIED"),
    ("used M1 Ultra 128GB",           800.0,  128, False, "NAMEPLATE-UNVERIFIED"),
]
WS_VQ3R_GIB = 952.0

rows = []
for name, nm_gbs, cap, verified, note in PLATFORMS:
    nm = nm_gbs * GB_TO_GIB
    row = {
        "platform": name, "nameplate_GB_s": nm_gbs, "nameplate_GiB_s": round(nm, 3),
        "dram_capacity_GiB": cap, "measured_here": verified, "flag": note,
        "ceiling_at_r_measured_%.4f" % r_measured: round(ceiling(nm * r_measured), 3),
        "ceiling_at_r_exp35_%.4f" % r_exp35:       round(ceiling(nm * r_exp35), 3),
        "ceiling_at_r_1.0_absolute_roof":          round(ceiling(nm), 3),
        "L_reduction_factor_required_at_r_measured": round(req_achiev / (nm * r_measured), 3),
        "capacity_holds_952GiB_VQ3R": cap >= WS_VQ3R_GIB,
    }
    if not row["capacity_holds_952GiB_VQ3R"]:
        row["binding_resource"] = "SSD/PCIe, not DRAM -- DRAM roof is NOT the binding constraint"
    else:
        row["binding_resource"] = "DRAM"
    rows.append(row)

# M4 direct, no ratio extrapolation
m4_direct = ceiling(D)
m4_absolute_roof = ceiling(M4_NAMEPLATE)
m4_L_reduction = req_achiev / D

out = {
  "exp": 38, "slug": "dram-roofline-on-logical-demand",
  "source_sha": "exp35-pinned-lutbw (WARP 7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b)",
  "host": "Apple M4, 4 P-core + 6 E-core, 24 GiB, macOS 15.6",
  "stage1_class": "SYNTHETIC", "stage2_4_class": "RECOMPUTATION",
  "stage1": {
    "T": T, "N_per_arm": S1["nrep"], "per_thread_stream_MB": round(S1["nidx_bytes"]/1048576.0, 2),
    "qos": "USER_INTERACTIVE (P-core preference)",
    "arms_source_read_GiB_s": {k: v["mean_read_GiB_s"] for k, v in S1["arms"].items()},
    "arms_sd": {k: v["sd"] for k, v in S1["arms"].items()},
  },
  "gate_adjudication": {
    "preregistered_accept": "kern_D within 10% of the memcpy control AND recomputed M4 ceiling <= 6.6 tok/s",
    "preregistered_reject": "kern_D exceeds the memcpy control by >10%, OR a <=$3000 platform delivers >=315.0 GiB/s achievable",
    "literal_D_over_CPY_read_rate": round(lit_ratio, 4),
    "literal_gate_verdict": "REJECT fires literally (+%.1f%%)" % ((lit_ratio-1)*100),
    "why_literal_control_is_invalid": (
      "memcpy moves 2 bytes of DRAM traffic per byte of SOURCE read (1 read + 1 write); "
      "kern_D moves 1.003. Comparing D's read rate to memcpy's read rate compares "
      "different physical quantities, so the literal gate cannot test its own stated "
      "mechanism ('LUT reuse defeats the roofline denominator L')."),
    "dimensionally_matched_read_only_control_RDSUM": round(RDSUM, 4),
    "D_over_RDSUM": round(read_ratio, 4),
    "read_control_verdict": "ACCEPT condition 1 holds: D is %.1f%% of the read-only roof (within 10%%)" % (read_ratio*100),
    "total_DRAM_traffic_normalization": {
      "D_total_GiB_s": round(D_total, 3), "CPY_total_GiB_s": round(CPY_total, 3),
      "D_over_CPY_total": round(total_ratio, 4),
      "verdict": "D is %.1f%% BELOW memcpy total traffic -- neither accept nor reject as written" % ((1-total_ratio)*100)},
    "reject_clause_2_any_platform_>=315_GiB_s_achievable": "NOT DEMONSTRATED (no such measurement exists)",
  },
  "stage2_ceilings": {
    "L_logical_GiB_per_token": L_LOGICAL,
    "required_achievable_GiB_s_for_15_tok_s": round(req_achiev, 3),
    "m4_measured_ceiling_tok_s": round(m4_direct, 4),
    "m4_absolute_nameplate_roof_tok_s": round(m4_absolute_roof, 4),
    "m4_accept_condition2_ceiling_le_6.6": m4_absolute_roof <= 6.6,
    "m4_L_reduction_factor_required": round(m4_L_reduction, 3),
    "m4_max_remaining_kernel_headroom_x": round(RDSUM / D, 4),
    "r_measured_T4": round(r_measured, 4), "r_exp35_bestT": round(r_exp35, 4),
  },
  "stage3_platform_table": rows,
  "stage4_retro_gate": {
    "rule": "every iso-rate kernel/codec idea is capped at B_achievable / L on its own platform",
    "m4_cap_tok_s": round(m4_direct, 4),
    "consequence": ("no iso-rate substitution (VQ4P, rANS, any gather kernel) can exceed "
                    "%.3f tok/s on M4; the only remaining levers are (a) reduce L, "
                    "(b) buy bandwidth WITH capacity >= working set." % m4_direct),
    "capacity_corollary": ("every platform in the table with >=315 GiB/s nameplate has DRAM "
                           "capacity far below the 952 GiB VQ3R working set, so its DRAM roof "
                           "is not reachable -- the binding resource reverts to SSD/PCIe. "
                           "Bandwidth-per-dollar must be scored jointly with capacity-per-dollar."),
  },
}
p = os.path.join(HERE, "exp38_result.json")
json.dump(out, open(p, "w"), indent=2)
print(json.dumps(out, indent=2))
