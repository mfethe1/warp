#!/usr/bin/env python3
"""exp1 activation-weighted-shared-basis: preregistered-gate decision audit.

ALL NUMBERS ARE [RECOMPUTATION] FROM PINNED PUBLISHED CONSTANTS.
NOTHING HERE IS A K3 MEASUREMENT. No model was executed.

Objective:  B_acc = M * R / a
  M = physical expert-record transfers per attempted token
  R = physical bytes per transferred record  (RECORD_BYTES, 4KiB-quantised)
  a = accepted output tokens per attempted token

The claimed spec and the claimed accept_gate disagree about the bit budget:
  spec:        "compare error vs VQ3R at MATCHED bits/weight"   -> R invariant
  accept_gate: ">1.5pp error improvement at <=0.15 bits/weight" -> R additive
Both readings are evaluated.
"""
import hashlib, json, math, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---- pinned constants (source-of-truth paths recorded in manifest) ----
RECORD_BYTES   = 12406784          # sprint13-vq-gpu-summary.json:/standalone_real_record_pilot/record_bytes_each
PAGE           = 4096              # FORMAT.md expert bank record: [4 KiB-aligned]
BASE_BPW       = 3.00              # VQ3R as shipped: 3 stages x 256 entries, dim 8
GATE_EXTRA_BPW = 0.15              # FORMAT.md:278-279 accept gate budget
GATE_ERR_PP    = 1.5               # FORMAT.md:278 ">1.5 pp of error"
STOP_PP        = 0.5               # stop_rule: stop after one layer if effect <0.5pp

PHYS_GIB_TOK   = 7.719             # established: measured physical GiB/token
STORAGE_GIBS   = 5.9194836464      # consolidation-task3-storage-summary.json
TARGET_TOKS    = 15.0

# published Gate-3 / subspace measurements (2026-07-27, real Kimi-Linear-48B) [PROXY, unweighted]
PUB_RANK_BPW   = 0.12              # FORMAT.md:259 rank N/128 basis cost
PUB_RANK_PP    = 0.3               # FORMAT.md:260 error reduction -- "noise"
PUB_MATCH_KBVQ = 28.87             # FORMAT.md:261-262 kbvq2 @4.01 bits
PUB_MATCH_INT4 = 15.20             # FORMAT.md:262 per-row INT4 @4.01 bits
SUBSP_SHARED   = 7.1               # FORMAT.md:265-266 % energy captured by shared basis
SUBSP_RANDOM   = 3.1
SUBSP_OWN      = 20.0

# established speculative headroom (recomputation, prior tick)
SPEC_BREAKEVEN = 2.13              # % acceptance gain needed to pay for speculation
SPEC_MEASURED  = 3.69              # % their pilot actually measured

def pages(nbytes):
    return math.ceil(nbytes / PAGE)

def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for c in iter(lambda: f.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()

out = {"label": "RECOMPUTATION", "N": 1, "variance": "n/a (deterministic algebra)"}

# ---- sanity: baseline record is an exact page multiple ----
assert RECORD_BYTES % PAGE == 0, "baseline record not page aligned"
out["baseline_pages"] = RECORD_BYTES // PAGE

# =========================================================================
# READING B -- accept_gate literal: basis costs an ADDITIONAL <=0.15 bits/weight
# =========================================================================
scale = (BASE_BPW + GATE_EXTRA_BPW) / BASE_BPW
raw = RECORD_BYTES * scale
new_pages = pages(raw)
new_bytes = new_pages * PAGE
dR = new_bytes / RECORD_BYTES - 1.0

new_phys = PHYS_GIB_TOK * (1 + dR)
tps_base = STORAGE_GIBS / PHYS_GIB_TOK
tps_new = STORAGE_GIBS / new_phys

out["readingB_additive"] = {
    "bits_per_weight": BASE_BPW + GATE_EXTRA_BPW,
    "record_bytes_raw": raw,
    "record_bytes_page_quantised": new_bytes,
    "record_pages": new_pages,
    "R_increase_pct": round(dR * 100, 4),
    "phys_GiB_per_token": round(new_phys, 4),
    "tok_s_baseline": round(tps_base, 5),
    "tok_s_with_basis": round(tps_new, 5),
    "throughput_change_pct": round((tps_new / tps_base - 1) * 100, 3),
    # break-even: B_acc = M*R/a unchanged requires a to rise by exactly dR
    "required_acceptance_gain_pct_to_break_even": round(dR * 100, 4),
    "entire_measured_speculative_acceptance_headroom_pct": SPEC_MEASURED,
    "headroom_covers_cost": SPEC_MEASURED >= dR * 100,
    "gate_can_pass_while_B_acc_regresses": True,
}

# =========================================================================
# READING A -- spec literal: MATCHED bits/weight, R and M invariant
# =========================================================================
matched_deficit = PUB_MATCH_KBVQ - PUB_MATCH_INT4   # shared-basis loss at equal budget
out["readingA_matched"] = {
    "R_change_pct": 0.0,
    "M_change_pct": 0.0,
    "dB_acc_d_error": "0 unless error maps to acceptance rate a",
    "calibrated_error_to_acceptance_mapping_found_in_docs_gn100": False,
    "matched_budget_published_deficit_pp": round(matched_deficit, 2),
    "swing_needed_to_pass_gate_pp": round(matched_deficit + GATE_ERR_PP, 2),
}

# =========================================================================
# Effect-size prior vs the preregistered STOP RULE
# =========================================================================
scaled_pp = PUB_RANK_PP * (GATE_EXTRA_BPW / PUB_RANK_BPW)  # linear extrapolation, generous
out["stop_rule_prior"] = {
    "published_unweighted_pp_at_0.12bpw": PUB_RANK_PP,
    "linear_extrapolation_pp_at_0.15bpw": round(scaled_pp, 4),
    "stop_rule_threshold_pp": STOP_PP,
    "prior_trips_stop_rule": scaled_pp < STOP_PP,
    "accept_gate_pp": GATE_ERR_PP,
    "multiple_needed_over_published": round(GATE_ERR_PP / scaled_pp, 2),
    "note": "published figure is the UNWEIGHTED metric; the whitened/weighted "
            "number is genuinely unmeasured. This is a prior, not a result.",
}

# ceiling argument: a SHARED basis cannot beat each expert's OWN dominant subspace
out["subspace_ceiling"] = {
    "shared_energy_pct": SUBSP_SHARED,
    "random_energy_pct": SUBSP_RANDOM,
    "own_expert_energy_pct": SUBSP_OWN,
    "shared_over_random": round(SUBSP_SHARED / SUBSP_RANDOM, 3),
    "max_possible_energy_gain_pp": round(SUBSP_OWN - SUBSP_SHARED, 2),
    "note": "own-subspace capture is the unreachable ceiling for any shared basis; "
            "energy-pp does not convert to error-pp without a measurement.",
}

# ---- what 15 tok/s needs, for context ----
out["target_context"] = {
    "GiB_per_token_for_15_tok_s": round(STORAGE_GIBS / TARGET_TOKS, 4),
    "current_phys_GiB_per_token": PHYS_GIB_TOK,
    "reduction_factor_needed": round(PHYS_GIB_TOK / (STORAGE_GIBS / TARGET_TOKS), 3),
}

out["verdict"] = "inconclusive"
out["reason"] = (
    "The preregistration is internally contradictory (spec says MATCHED bits/weight, "
    "accept gate says <=0.15 additional bits/weight) and neither reading is "
    "algebraically connected to B_acc = M*R/a. Reading B accepts a +5.018% R "
    "regression; reading A leaves B_acc identically invariant because no calibrated "
    "error->acceptance mapping exists in any published artifact. Gate cannot be "
    "moved by the processor; requeue a corrected byte/acceptance-aware version."
)

srcs = ["docs/FORMAT.md", "docs/LEARNED.md",
        "docs/gn100/sprint13-vq-gpu-summary.json",
        "docs/gn100/sprint11-route-margin-summary.json",
        "docs/gn100/consolidation-task3-storage-summary.json"]
out["source_sha256"] = {p: sha256(os.path.join(REPO, p)) for p in srcs if os.path.exists(os.path.join(REPO, p))}

json.dump(out, sys.stdout, indent=2)
print()
