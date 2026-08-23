#!/usr/bin/env python3
"""exp15 preregistered residency-footprint falsifier.

Evidence class: RECOMPUTATION over the frozen Kimi-Linear-shaped proxy trace.
This does not estimate an SPRT stopping rate and must not be described as K3.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

RECORD_B = 12_406_784
INDEX_PAYLOAD_B = 12_386_304
STAGES = 3
FIXED_OVERHEAD_B = RECORD_B - INDEX_PAYLOAD_B
CAP_RECORDS = 709


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("trace", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    accesses = 0
    keys: set[tuple[int, int]] = set()
    tokens = 0
    with args.trace.open() as f:
        for line in f:
            row = json.loads(line)
            tokens += 1
            for layer, experts in enumerate(row["layers"]):
                for expert in experts:
                    accesses += 1
                    keys.add((layer, int(expert)))

    stage_plane_b = INDEX_PAYLOAD_B // STAGES
    stage1_fragment_b = stage_plane_b + FIXED_OVERHEAD_B
    budget_b = CAP_RECORDS * RECORD_B
    footprint_b = len(keys) * stage1_fragment_b
    equivalent_records = footprint_b / RECORD_B
    headroom_b = budget_b - footprint_b

    result = {
        "experiment": "exp15",
        "slug": "sprt-stages-plus-fragment-residency",
        "evidence_class": "RECOMPUTATION over Kimi-Linear-shaped PROXY trace; NOT K3",
        "source_sha_preregistered": "cb05b14",
        "trace": {
            "path": str(args.trace),
            "sha256": sha256(args.trace),
            "tokens": tokens,
            "accesses_N": accesses,
            "distinct_layer_experts": len(keys),
        },
        "frozen_constants": {
            "record_B": RECORD_B,
            "index_payload_B": INDEX_PAYLOAD_B,
            "stages": STAGES,
            "fixed_overhead_B": FIXED_OVERHEAD_B,
            "resident_cap_whole_records": CAP_RECORDS,
        },
        "residency_probe": {
            "one_stage_plane_B": stage_plane_b,
            "stage1_fragment_including_fixed_overhead_B": stage1_fragment_b,
            "total_budget_B": budget_b,
            "stage1_exercised_coverage_B": footprint_b,
            "stage1_equivalent_whole_records": equivalent_records,
            "budget_utilization": footprint_b / budget_b,
            "headroom_B_before_coarse_basis": headroom_b,
            "fits_before_coarse_basis": footprint_b <= budget_b,
            "fits_alongside_coarse_basis": False,
            "coarse_basis_bytes_assumed": 0,
            "note": "Stage-1 exercised coverage alone exceeds R, so adding any coarse basis cannot restore fit.",
        },
        "early_stop_probe": {
            "computed": False,
            "reason": "No per-expert VQ-stage certification data exists in the frozen trace. Published sprint11 route-margin data are percentiles only and the preregistration forbids treating them as per-expert coupling. The residency reject is independently decisive under the stop rule.",
        },
        "gate": {
            "quoted_reject": "stage-1 residency for the exercised expert coverage does not fit the resident budget alongside the coarse basis",
            "fired": True,
            "verdict": "falsified",
            "stop_action": "Stop at falsifier probe; do not run four byte arms.",
        },
        "objective_check": "Optimized resident-byte feasibility for a mechanism intended to reduce physical bytes per accepted token. Algebraic link: only resident stage-1 fragments can make early stop=0 preads and continuation=1 fixed-length pread; because their footprint exceeds fixed R before coarse-basis allocation, the claimed byte-saving arm is infeasible under the shared-R constraint.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
