#!/usr/bin/env python3
"""
exp2 / objective-mismatch-audit  (WARP research queue, Lenny lane)

Standing audit: for every ACTIVE claim, state the objective it optimizes and
show the algebra connecting it to PHYSICAL EXPERT BYTES PER ACCEPTED OUTPUT
TOKEN. Flag any gate not so connected.

Evidence class: RECOMPUTATION (from pinned published constants + repo facts).
No K3 execution. No machine contention.

Pinned sources:
  RECORD_BYTES        docs/FORMAT.md:296, docs/LEARNED.md:1254,
                      docs/gn100/sprint13-vq-gpu-summary.json:70
  BANDWIDTH           docs/gn100/consolidation-task3-storage-summary.json:43
                      ("historical_sprint18_aggregate_gib_per_second")
  physical/logical    established project findings (17.009 / 7.719 GiB/token)
  repo SHA            ba3f394 (branch collab/belady-oracle), spec source cb05b14
"""
import json, hashlib, sys, datetime

GIB = 1073741824

# ---------------------------------------------------------------- constants
RECORD_BYTES = 12406784          # exactly 3029 x 4096-byte pages
PAGE         = 4096
K3_LAYERS    = 92
K3_TOPK      = 16
ACT_PER_TOK  = K3_LAYERS * K3_TOPK          # 1472 expert activations / token
BW_GIBPS     = 5.9194836464                  # sprint18 aggregate
TARGET_TOKS  = 15.0
PHYS_MEASURED_GIB = 7.719                    # GiB/token, measured physical
VQ_BITS_PER_W     = 3.00                     # VQ3R as shipped

# ------------------------------------------------------- derived invariants
logical_bytes = ACT_PER_TOK * RECORD_BYTES
logical_gib   = logical_bytes / GIB
budget_gib    = BW_GIBPS / TARGET_TOKS       # GiB/token allowed at 15 tok/s
speedup_vs_phys    = PHYS_MEASURED_GIB / budget_gib
hit_needed_logical = 1.0 - budget_gib / logical_gib
hit_current        = 1.0 - PHYS_MEASURED_GIB / logical_gib

INV = {
    "record_bytes": RECORD_BYTES,
    "record_pages": RECORD_BYTES / PAGE,
    "activations_per_token": ACT_PER_TOK,
    "logical_bytes_per_token": logical_bytes,
    "logical_gib_per_token": round(logical_gib, 6),
    "measured_physical_gib_per_token": PHYS_MEASURED_GIB,
    "bandwidth_gib_per_s": BW_GIBPS,
    "budget_gib_per_token_at_15toks": round(budget_gib, 6),
    "required_speedup_vs_measured_physical": round(speedup_vs_phys, 4),
    "required_hit_on_logical_demand": round(hit_needed_logical, 6),
    "current_hit_on_logical_demand": round(hit_current, 6),
}

# ============================================================ THE CORE MODEL
# Physical expert bytes per accepted output token:
#
#   B_acc = (M * RECORD_BYTES) / a
#
#   M = expert-record MISSES per proposed token   (cache policy sets this)
#   a = accepted output tokens per proposed token (speculation sets this)
#   RECORD_BYTES = fixed 12,406,784 B, one pread per expert, page-aligned
#
# Every legitimate lever must move M, a, or RECORD_BYTES. A gate that moves
# none of the three has coupling dB/dx = 0 and is NOT connected.
# ===========================================================================

def audit_exp3():
    """metabolic-channeling-route-graph -- placement via modularity."""
    # Placement is a permutation pi of record OFFSETS in the container.
    # B_acc = M * RECORD_BYTES / a.
    #   M            : set by demand sequence + cache policy -> independent of pi
    #   RECORD_BYTES : fixed by FORMAT.md -> independent of pi
    #   a            : selection untouched (idea's own "conserved") -> indep of pi
    # => dB_acc/dpi == 0 EXACTLY, for ALL pi, for ALL modularity values.
    #
    # The ONLY channel by which placement could touch bytes is OS readahead
    # merging two co-demanded records into one transfer. That requires the
    # readahead window R to span a record.
    readahead_max = 128 * 1024          # Linux default; even "huge" tunings <= a few MiB
    span_needed   = RECORD_BYTES
    coverage      = readahead_max / span_needed
    # And warp reads experts with O_DIRECT, one pread per expert -> readahead
    # is BYPASSED entirely, so the effective coverage is 0.
    o_direct_coverage = 0.0
    return {
        "exp_id": 3, "slug": "metabolic-channeling-route-graph",
        "stated_metric": "transition entropy vs uniform; graph modularity",
        "stated_accept_gate": ("ACCEPT: modularity >0.15 AND entropy materially "
                               "below uniform -> placement work justified"),
        "objective_derivation":
            "B_acc = M*RECORD_BYTES/a. Placement is a permutation pi of record "
            "offsets. M is fixed by the demand sequence and cache policy; "
            "RECORD_BYTES is fixed at 12,406,784 B by FORMAT.md; a is untouched "
            "(the idea itself asserts 'Bytes are conserved; only PLACEMENT "
            "changes'). Therefore dB_acc/dpi = 0 identically.",
        "coupling_dBytes_dGate": 0.0,
        "readahead_coverage_of_one_record_buffered": round(coverage, 6),
        "readahead_coverage_with_O_DIRECT": o_direct_coverage,
        "verdict": "MISMATCH (new)",
        "why": ("Modularity is a graph-partition quality score with units of "
                "nothing; it has no algebraic path to bytes. The gate can PASS "
                "at modularity 1.0 while physical bytes/accepted token are "
                "bit-for-bit unchanged. The idea's own 'conserved' clause "
                "('bytes are conserved') is a proof that the accept gate is "
                "measuring a quantity the objective is invariant to."),
        "corrected_gate":
            "Placement can only pay in LATENCY (seek/queue depth), never bytes. "
            "The decisive gate is: does co-paging reduce the NUMBER of preads, "
            "i.e. can two co-demanded records be merged into one transfer? With "
            "one pread per 3029-page record under O_DIRECT the merge count is 0, "
            "so the correct preregistered gate is a wall-clock gate "
            "(GiB/s effective at fixed byte count), NOT a byte gate. Since the "
            "engine is already 100% I/O-bound at 5.919 GiB/s aggregate "
            "(sequential vs random is within noise for 11.83 MiB transfers), "
            "expected gain is ~0. Recommend DEAD before implementation, on the "
            "algebra, without running the graph analysis.",
    }

def audit_exp1():
    """activation-weighted-shared-basis -- error gate at a bits/weight COST."""
    # Gate: ACCEPT if >1.5pp error improvement at <= 0.15 bits/weight.
    # The 0.15 bits/weight is SPENT, i.e. bytes go UP.
    d_bits = 0.15
    rel_byte_increase = d_bits / VQ_BITS_PER_W          # 5.00%
    phys_after = PHYS_MEASURED_GIB * (1 + rel_byte_increase)
    toks_before = BW_GIBPS / PHYS_MEASURED_GIB
    toks_after  = BW_GIBPS / phys_after
    rel_tok_loss = 1 - toks_after / toks_before
    # For B_acc = M*RECORD/a to not regress, the acceptance rate a must rise by
    # at least the same relative amount that bytes rose.
    required_rel_accept_gain = rel_byte_increase
    return {
        "exp_id": 1, "slug": "activation-weighted-shared-basis",
        "stated_metric": ("activation-weighted error tr((W-W')Sigma_x(W-W')^T) "
                          "at matched bits/weight"),
        "stated_accept_gate": ("ACCEPT: >1.5pp error improvement at <=0.15 "
                               "bits/weight (threshold frozen in FORMAT.md)"),
        "objective_derivation":
            "B_acc = M*RECORD_BYTES/a. Spending +0.15 bits/weight on a 3.00 "
            "bits/weight baseline enlarges RECORD_BYTES by 0.15/3.00 = 5.00%. "
            "Error (a distortion in logit space) touches B_acc ONLY through the "
            "acceptance rate a. The gate states the byte COST but supplies no "
            "error->acceptance conversion, so the sign of dB_acc is undetermined "
            "by the gate as written.",
        "byte_cost_relative": round(rel_byte_increase, 6),
        "phys_gib_per_token_after": round(phys_after, 4),
        "toks_before": round(toks_before, 4),
        "toks_after": round(toks_after, 4),
        "throughput_loss_relative": round(rel_tok_loss, 6),
        "required_relative_acceptance_gain_to_break_even":
            round(required_rel_accept_gain, 6),
        "verdict": "MISMATCH (new)",
        "why": ("The gate accepts a configuration that provably INCREASES "
                "physical bytes/token by 5.00% (7.719 -> 8.105 GiB/token, "
                "0.7668 -> 0.7303 tok/s, a 4.76% throughput loss) in exchange "
                "for a 1.5pp error improvement whose byte value is never "
                "stated. 'Error improvement' is the Frobenius-mismatch of "
                "2026 in new clothing: the metric was corrected from Frobenius "
                "to activation-weighted, but the GATE was never re-derived "
                "against bytes/accepted token."),
        "corrected_gate":
            "Run the fit at MATCHED error and gate on BITS SAVED, not at "
            "matched bits gating on error. ACCEPT iff the whitened basis "
            "reaches VQ3R's activation-weighted error at <= 2.85 bits/weight "
            "(a >=5% byte reduction, worth ~223 ms of arithmetic budget at the "
            "44.7 ms-per-1% conversion). If the fit is only expressible at "
            "+0.15 bits/weight, ACCEPT requires a measured relative acceptance "
            "gain >= 5.00% on a speculative arm -- otherwise it is a byte "
            "regression and must be rejected.",
    }

def audit_exp4():
    return {
        "exp_id": 4, "slug": "option-value-prefetch",
        "stated_metric": "physical bytes per accepted token",
        "stated_accept_gate": "ACCEPT: EV-gated beats lookahead-off on physical bytes",
        "objective_derivation":
            "The stated metric IS the objective. EV gating acts on M (misses / "
            "wasted prefetch reads) with a and RECORD_BYTES held fixed, so "
            "dB_acc/dM = RECORD_BYTES/a > 0 and the gate tracks the goal with "
            "the correct sign.",
        "coupling_dBytes_dGate": RECORD_BYTES,
        "verdict": "CONNECTED",
        "why": "No correction needed. Note the premium term must count "
               "SPECULATIVELY-READ bytes in the numerator, not only demand reads.",
        "corrected_gate": None,
    }

def audit_exp2():
    return {
        "exp_id": 2, "slug": "objective-mismatch-audit",
        "stated_metric": "count of gates found to be measuring a non-connected proxy",
        "stated_accept_gate": "ACCEPT: identifies >=1 new objective mismatch with the corrected algebra",
        "objective_derivation":
            "Meta-gate. Not required to be dimensionally connected; it is a "
            "second-order control that protects the connectedness of the "
            "first-order gates. Declared as such -- exempt.",
        "verdict": "META (exempt)",
        "why": "Self-referential audit gate; exempt by construction.",
        "corrected_gate": None,
    }

def audit_pending_idea1():
    """Not yet an experiment row, but its PREDICTION is a de-facto gate."""
    s_stated = 1.0 - budget_gib / logical_gib          # against LOGICAL 17.009
    s_correct = 1.0 - budget_gib / PHYS_MEASURED_GIB   # against PHYSICAL 7.719
    return {
        "exp_id": None, "slug": "kinetic-proofreading-certified-skip (idea 1, pending)",
        "stated_metric": "certified-skip rate s",
        "stated_accept_gate": ("prediction: 'bytes/token = 17.009*(1-s) GiB; "
                               "15 tok/s needs s >= 97.7%'"),
        "objective_derivation":
            "A certified skip avoids a read ONLY when that read would have been "
            "a physical MISS. 54.62% of logical demands are already cache hits "
            "costing zero bytes, so the saving is s*PHYSICAL, not s*LOGICAL. "
            "Setting budget = PHYS*(1-s) gives the correct required skip rate.",
        "s_required_against_logical_baseline": round(s_stated, 6),
        "s_required_against_physical_baseline": round(s_correct, 6),
        "gate_overstatement_pp": round((s_stated - s_correct) * 100, 4),
        "verdict": "MISMATCH (new, pending gate)",
        "why": ("The gate is stated against the LOGICAL 17.009 GiB/token "
                "baseline, demanding s >= 97.68%. Against the MEASURED PHYSICAL "
                "7.719 GiB/token baseline the requirement is s >= 94.89% -- the "
                "preregistered bar is 2.79pp too harsh. This is a false-negative "
                "risk: it could kill the project's highest-expected-gain idea "
                "(0.95) on a baseline error."),
        "corrected_gate":
            "Preregister s >= 94.89% measured against physical misses, and "
            "state explicitly whether the resident coarse basis B_e is counted "
            "inside or outside the 7.719 GiB/token figure (it changes the "
            "denominator). Do NOT write the gate against logical demand.",
    }

def main():
    audits = [audit_exp2(), audit_exp1(), audit_exp3(), audit_exp4(),
              audit_pending_idea1()]
    new_mismatches = [a for a in audits if a["verdict"].startswith("MISMATCH")]
    out = {
        "experiment": "exp2 / objective-mismatch-audit",
        "evidence_class": "RECOMPUTATION",
        "generated_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "repo_sha": "ba3f394", "spec_source_sha": "cb05b14",
        "machine": "offline-only (Winnie CPU_LOAD_PCT=100, contention avoided)",
        "objective": "physical expert bytes per ACCEPTED output token; B_acc = M*RECORD_BYTES/a",
        "invariants": INV,
        "N_active_gates_audited": len(audits),
        "N_new_mismatches": len(new_mismatches),
        "new_mismatch_slugs": [a["slug"] for a in new_mismatches],
        "audits": audits,
        "prior_known_mismatches_not_reaudited": [
            "hit% not bytes", "nominal bits not trajectory reads",
            "verifier wall-time not bytes/accepted-token",
            "Frobenius not activation-weighted",
            "per-decision not per-token divergence"],
    }
    js = json.dumps(out, indent=2)
    print(js)
    return js

if __name__ == "__main__":
    js = main()
    if len(sys.argv) > 1:
        open(sys.argv[1], "w").write(js)
        print("\nsha256=" + hashlib.sha256(js.encode()).hexdigest(), file=sys.stderr)
