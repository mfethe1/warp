#!/usr/bin/env python3
"""exp40 preregistration/identifiability audit.

Cheapest decisive test for the claimed 2x2 factorial. This script does not
invent per-access certifier or SPRT labels. It determines whether the frozen
spec and pinned sources make the preregistered overlap stop statistic and
factorial identifiable.

Labels:
  * REAL-K3: published aggregate route-margin summary only.
  * PROXY: Kimi-Linear-shaped routing trace, not K3.
  * RECOMPUTATION: deterministic geometry/accounting from pinned constants.
"""
from __future__ import annotations

import collections
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRACE = ROOT / "tests" / "trace_kimi_300.jsonl"
MARGIN = ROOT / "docs" / "gn100" / "sprint11-route-margin-summary.json"
OUT = ROOT / "docs" / "research" / "exp40_prereg_audit.json"

PAGE = 4096
RECORD_B = 12_406_784
RECORD_PAGES = 3029
STAGES = 3
LATENT = 3584
MOE_INTER = 3072
VEC_DIM = 8
SOURCE_SHA = "cb05b1424eaefd5f777f62215c31d4af760e6e86"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_json_lines(path: Path):
    # Ignore blank lines: the trace has one separator line.
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def lru_misses(accesses, cap):
    cache = collections.OrderedDict()
    misses = 0
    for key in accesses:
        if key in cache:
            cache.move_to_end(key)
        else:
            misses += 1
            cache[key] = None
            if len(cache) > cap:
                cache.popitem(last=False)
    return misses


def main():
    trace = load_json_lines(TRACE)
    margin = json.loads(MARGIN.read_text())
    accesses = [
        (layer_i, expert)
        for token in trace
        for layer_i, experts in enumerate(token["layers"])
        for expert in experts
    ]
    distinct = len(set(accesses))
    cap = int(distinct / 3.41)
    misses = lru_misses(accesses, cap)

    # Bottom-up VQ3R record geometry. Three index bytes per 8-weight vector.
    weights = 3 * LATENT * MOE_INTER
    vectors = weights // VEC_DIM
    index_payload_b = vectors * STAGES
    overhead_b = RECORD_B - index_payload_b
    stage_plane_b = vectors
    # Page-segregated counterfactual boundaries, if a corrected spec chooses it.
    stage_boundaries_pages = [1008, 2016, RECORD_PAGES]

    # The published certifier evidence is a marginal CDF at five tolerances.
    cert_curve = [
        {
            "max_score_error": row["max_score_error"],
            "certified_fraction": 1.0 - row["fraction_not_certified"],
        }
        for row in margin["score_error_risk"]
    ]

    # Identifiability proof: for marginal rates c=P(C) and p=P(S), joint
    # overlap q=P(C & S) is only bounded by Frechet bounds. Neither p nor a
    # per-access joint sample exists in the pinned sources, and c is not frozen.
    identifiability = {
        "required_joint_statistic": "q=P(certifier_suppressed AND SPRT_stage1)",
        "available_REAL_K3": "aggregate certifier margin CDF only; no per-access identities",
        "available_PROXY": "routing identities only; no margins, hidden states, row norms, or VQ stage outputs",
        "missing": [
            "frozen certifier tolerance or bound",
            "frozen exact SPRT stopping inequality",
            "per-access certifier verdicts aligned to the trace",
            "per-access SPRT stop-stage labels aligned to the same trace",
            "accepted-token and KL observations for the same arms",
        ],
        "frechet_bounds": "max(0,c+p-1) <= q <= min(c,p)",
        "conclusion": "The >=80% overlap stop gate and all conditional marginals are not identifiable.",
    }

    result = {
        "experiment": 40,
        "source_sha": SOURCE_SHA,
        "sources": {
            str(TRACE.relative_to(ROOT)): sha256(TRACE),
            str(MARGIN.relative_to(ROOT)): sha256(MARGIN),
        },
        "PROXY_trace": {
            "tokens_N": len(trace),
            "layers": len(trace[0]["layers"]),
            "top_k": len(trace[0]["layers"][0]),
            "accesses_N": len(accesses),
            "distinct_layer_experts": distinct,
            "cache_capacity_at_3_41x": cap,
            "LRU_misses_N": misses,
            "LRU_miss_rate": misses / len(accesses),
        },
        "REAL_K3_aggregate_margin_source": {
            "layers": margin["layers"],
            "rows_N": margin["rows"],
            "positions_N": margin["positions"],
            "certifier_curve": cert_curve,
            "per_access_joint_labels_present": False,
        },
        "RECOMPUTATION_geometry": {
            "weights_per_expert": weights,
            "vectors_per_expert": vectors,
            "index_payload_B": index_payload_b,
            "header_plus_corrections_B": overhead_b,
            "record_B": RECORD_B,
            "record_pages": RECORD_PAGES,
            "record_page_exact": RECORD_B == RECORD_PAGES * PAGE,
            "one_stage_plane_B": stage_plane_b,
            "counterfactual_stage_boundaries_pages": stage_boundaries_pages,
            "all_counterfactual_boundaries_page_aligned": all(
                pages * PAGE % PAGE == 0 for pages in stage_boundaries_pages
            ),
            "shipped_layout_fact": "three stage bytes are adjacent/interleaved per vector; one whole-record pread",
            "shipped_R_B_at_stages_1_2_3": [RECORD_B, RECORD_B, RECORD_B],
            "shipped_SPRT_physical_byte_gain_B": 0,
        },
        "identifiability": identifiability,
        "gate_evaluation": {
            "stop_gate_overlap_ge_80pct": "UNEVALUABLE",
            "accept_gate": "UNEVALUABLE",
            "reject_gate": "UNEVALUABLE",
            "reason": "The spec omits the parameters and joint observations needed to instantiate its own arms.",
        },
        "objective_check": {
            "objective": "physical bytes per accepted token",
            "algebra": "B_acc = sum(page-rounded bytes of non-suppressed physical misses) / accepted_tokens",
            "connection": "Direct if stage planes are physically separable and verdicts are observed jointly; as shipped SPRT changes decode work only and dB_acc/d(stop_stage)=0.",
        },
        "verdict": "inconclusive",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2) + "\n")

    print("exp40 preregistration audit")
    print(f"PROXY N={len(accesses)} accesses, {misses} LRU misses at cap={cap}")
    print(f"REAL-K3 aggregate margin N={margin['rows']} rows; joint labels: absent")
    print(f"RECOMPUTATION record={RECORD_B} B={RECORD_PAGES} pages; shipped SPRT byte gain=0 B")
    print("STOP GATE: UNEVALUABLE (no frozen parameters; no joint labels)")
    print("VERDICT: inconclusive")


if __name__ == "__main__":
    main()
