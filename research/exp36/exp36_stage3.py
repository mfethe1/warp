#!/usr/bin/env python3
"""exp36 Stage-3 recomputation: does the VQ4P+certifier combination still reach 15 tok/s at C=10?

exp36 was preregistered on the premise that VQ4P kern_D delivers the 4.48x single-thread
kernel ratio in-engine (arm2 = 13.349 tok/s at 10 cores). exp34 (same pinned SHA
7f1fbba3) measured VQ4P end-to-end on REAL K3: 1.65 -> 1.52 s/token = 1.086x, because
waste_parallel_for cuts one task per thread and VQ4P degrades past P-cores (LEARNED s46/s47).

This script substitutes the MEASURED ratio into exp36's own arm composition and asks
what the all-selected certifier would now have to do for arm5 to clear the preregistered
accept gate (>=15.0 tok/s at C=10).

Every input anchor is labeled. No gate is moved.
"""
import json, math, hashlib, os

HERE = os.path.dirname(os.path.abspath(__file__))

# ---- anchors (each labeled with evidence class + provenance) ----
# [exp36 spec baseline; originally exp33/exp35 lineage, SYNTHETIC microbench N=5 M4]
gather_GiBs_per_core = 4.9427      # GiB/s/core, kern_A VQ3R, sd 0.4549, N=5
gather_sd            = 0.4549
logical_demand_GiB   = 17.0085     # GiB/token logical demand (established finding)
C                    = 10          # cores, per spec
baseline_ceiling_spec = 2.978      # tok/s compute-only ceiling as preregistered in exp36 baseline

# [REAL-K3, exp34 citing repo LEARNED s46, pinned SHA 7f1fbba3, medians of 13 VQ4P vs 5 VQ3R runs]
vq3r_s_per_token = 1.65
vq4p_s_per_token = 1.52
vq4p_end_to_end_ratio = vq3r_s_per_token / vq4p_s_per_token   # = 1.086x
# [REAL-K3, LEARNED s47 via exp34: VQ4P in-engine threaded scaling 25.3 -> 27.2 GB/s]
vq4p_threaded_scaling = 27.2 / 25.3                            # = 1.075x

# [REAL-K3, sprint11-route-margin-summary.json, 92 layers, 6348 rows; via exp12 recomputation]
sprint11 = '/tmp/spark/warp/docs/gn100/sprint11-route-margin-summary.json'
d = json.load(open(sprint11))
curve = [(r['max_score_error'], 1.0 - r['fraction_not_certified'])
         for r in d['score_error_risk']]
curve.sort()
sprint11_sha = hashlib.sha256(open(sprint11, 'rb').read()).hexdigest()

def s_cert_at(bound):
    """Log-linear interpolation of s_cert(B) between published points (exp12 method)."""
    if bound <= curve[0][0]: return curve[0][1]
    if bound >= curve[-1][0]: return curve[-1][1]
    for (b0, s0), (b1, s1) in zip(curve, curve[1:]):
        if b0 <= bound <= b1:
            f = (math.log(bound) - math.log(b0)) / (math.log(b1) - math.log(b0))
            return math.exp(math.log(s0) + f * (math.log(s1) - math.log(s0)))
    raise RuntimeError

def bound_for(s_target):
    """Invert the curve: bound magnitude needed for certified fraction s_target."""
    if s_target >= curve[0][1]: return curve[0][0]
    if s_target <= curve[-1][1]: return curve[-1][0]
    for (b0, s0), (b1, s1) in zip(curve, curve[1:]):
        if s1 <= s_target <= s0:
            f = (math.log(s_target) - math.log(s0)) / (math.log(s1) - math.log(s0))
            return math.exp(math.log(b0) + f * (math.log(b1) - math.log(b0)))
    raise RuntimeError

out = {"anchors": {
    "gather_GiBs_per_core": {"value": gather_GiBs_per_core, "sd": gather_sd, "N": 5,
        "class": "SYNTHETIC microbench (exp36 baseline field, M4 NEON lutbw)"},
    "logical_demand_GiB_per_token": {"value": logical_demand_GiB, "class": "established finding"},
    "baseline_ceiling_tok_s_C10": {"spec_value": baseline_ceiling_spec,
        "recomputed": round(gather_GiBs_per_core * C / logical_demand_GiB, 4),
        "class": "RECOMPUTATION"},
    "vq4p_end_to_end_ratio": {"value": round(vq4p_end_to_end_ratio, 4),
        "class": "REAL-K3 (exp34, LEARNED s46, medians N=13 vs 5, pinned 7f1fbba3)"},
    "vq4p_threaded_scaling": {"value": round(vq4p_threaded_scaling, 4),
        "class": "REAL-K3 (LEARNED s47 via exp34)"},
    "sprint11_sha256": sprint11_sha,
    "sprint11_rows": d['rows'],
}, "arms": {}}

# ---- arm ceilings under MEASURED VQ4P ----
base = baseline_ceiling_spec
arm2_claimed = 13.349                                   # [exp36 prediction, from 4.48x]
arm2_measured_ee  = base * vq4p_end_to_end_ratio        # end-to-end ratio applied
arm2_measured_thr = base * vq4p_threaded_scaling        # threaded-scaling ratio applied
out["arms"]["arm2_vq4p_alone"] = {
    "claimed_tok_s_C10": arm2_claimed,
    "measured_ratio_end_to_end": round(vq4p_end_to_end_ratio, 4),
    "tok_s_C10_under_measured_ratio_end_to_end": round(arm2_measured_ee, 3),
    "tok_s_C10_under_measured_ratio_threaded": round(arm2_measured_thr, 3),
    "class": "RECOMPUTATION over REAL-K3 anchors"}

# ---- what arm5 now needs ----
target = 15.0
for label, arm2 in [("end_to_end", arm2_measured_ee), ("threaded", arm2_measured_thr)]:
    needed = 1.0 - arm2 / target
    out["arms"][f"arm5_required_skip_{label}"] = {
        "arm2_tok_s": round(arm2, 3),
        "required_certified_skip_fraction_all_selected": round(needed, 4),
        "required_bound_for_that_skip_REAL_K3_curve": round(bound_for(needed), 8),
        "note": "certifier can only REMOVE experts from gather: tok/s <= arm2/(1-s)",
        "class": "RECOMPUTATION; bound from REAL-K3 sprint11 curve (unconditional)"}

# ---- what the evidence-backed bound magnitudes actually buy ----
idea16_gate2_bound = 5.34724e-4   # [exp12 inversion of idea16 accept gate 2, REAL-K3 margins]
for label, B in [("idea16_accept_gate2_bound_5.35e-4", idea16_gate2_bound),
                 ("exp12_reject_gate1_bound_9.69e-4", 9.68677e-4),
                 ("bound_1e-4_reference", 1e-4)]:
    s = s_cert_at(B)
    out["arms"]["arm5_at_" + label] = {
        "bound": B, "s_cert_unconditional_REAL_K3": round(s, 4),
        "arm5_tok_s_C10_end_to_end": round(arm2_measured_ee / (1 - s), 3),
        "arm5_tok_s_C10_threaded": round(arm2_measured_thr / (1 - s), 3),
        "class": "RECOMPUTATION; s_cert from REAL-K3 sprint11 curve"}

# ---- verdict arithmetic ----
a5 = out["arms"]["arm5_at_idea16_accept_gate2_bound_5.35e-4"]
out["verdict_arithmetic"] = {
    "accept_gate_quote": "arm5 reaches >=15.0 tok/s at C=10 at the fixed point, while neither arm2 nor arm4 does",
    "arm2_measured_tok_s_C10": round(arm2_measured_ee, 3),
    "arm5_tok_s_C10_at_evidence_backed_bound": a5["arm5_tok_s_C10_end_to_end"],
    "shortfall_factor_vs_15": round(target / a5["arm5_tok_s_C10_end_to_end"], 2),
    "skip_needed_for_15_end_to_end": out["arms"]["arm5_required_skip_end_to_end"]["required_certified_skip_fraction_all_selected"],
    "skip_bought_at_evidence_backed_bound": a5["s_cert_unconditional_REAL_K3"],
    "note": ("fixed-point (mismatch #9) refinement cannot rescue: compute ceiling is a hard "
             "upper bound on tok/s; arm5 ceiling < 15 at every bound magnitude with "
             "preregistered evidence backing")}

with open(os.path.join(HERE, 'exp36_out.json'), 'w') as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
