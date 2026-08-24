#!/usr/bin/env python3
"""Convert warp raw routing fixtures to moe-cache-lab canonical traces.

v2 (2026-08-24): CORRECTS the Kimi layer mapping.

  v1 defect: used `enumerate(r["layers"])` for BOTH models, renumbering Kimi's
  routed layers to 0..25. That is schema-valid but semantically wrong if the
  native routed layers are 1..26.

  Caught by @birkansit during moe-cache-lab #7 intake review.

KIMI LAYER MAPPING — evidence chain (each link checkable):

  1. `tools/kimi_ref.py @6e579f99` `forward()` iterates native `L` over
     `range(self.n_layers)` where `n_layers = cfg["num_hidden_layers"]`, and
     appends to the trace ONLY when
        has_moe = f"model.layers.{L}.block_sparse_moe.gate.weight" in self.t
     So the raw list index is a COMPACTED ordinal over routed layers, not the
     native layer id. They coincide only if every layer is routed.

  2. The raw fixture carries exactly 26 lists per token (verified: 300/300 rows)
     and NO native-layer metadata (keys are exactly {"tok","layers"}).

  3. Public Kimi-Linear config evidence: num_hidden_layers=27,
     first_k_dense_replace=1, moe_layer_freq=1
     -> layer 0 dense, layers 1..26 routed = 26 routed layers.
     This matches (2) exactly.

  => native routed layer ids are 1..26; raw ordinal i maps to native id i+1.

  EVIDENCE STATUS: strongly source-supported INFERENCE, NOT capture-proven.
  `kimi_ref.py` reads the container's own manifest.json/config, and that
  container manifest is NOT archived with the fixture. If the capture container
  differed from the public config, this mapping would be wrong. Declared
  contributor-supplied; do not upgrade to measured evidence without the manifest.

OLMOE MAPPING — unchanged, and correct by construction:
  `tools/trace_hf.py @dc079dad` registers `mk_hook(li)` per enumerated layer and
  emits `(layer_idx, ...)` pairs which are then sorted, so the ordinal IS the
  native layer index. OLMoE-1B-7B has 16 layers, all routed (16 lists observed).
  Mapping stays 0..15.

Sources (immutable anchors):
  Kimi-Linear-48B  : sqliteai/warp tests/trace_kimi_300.jsonl @ 6e579f99689a3e7e2ea875a88d97f68c8bfd3f70
                     raw content SHA-256 06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965
  OLMoE-1B-7B-0125 : sqliteai/warp tests/trace_olmoe_299.jsonl @ dc079dad1c35def2ee7bb3b2de5157db8d9f08a8
                     raw content SHA-256 7d8e7f63551aa24ddab98134b267b6bdf1b4f55d72a6fa7589042f54a4a4383b

Deterministic, stdlib-only. Records emitted in raw-capture order (no sorting,
no chronology repair, no inference beyond the declared layer mapping).
"""
import json
import sys

# Kimi: raw ordinal -> native layer id. See evidence chain above.
KIMI_EXPECTED_ROUTED_LAYERS = 26
KIMI_FIRST_ROUTED_LAYER = 1          # first_k_dense_replace=1 -> layer 0 is dense


def kimi_native_layer(ordinal: int) -> int:
    return ordinal + KIMI_FIRST_ROUTED_LAYER


def convert_kimi(src, dst):
    meta = {
        "format": "moe-cache-lab.routing-jsonl",
        "format_version": 2,
        "model_id": "Kimi-Linear-48B/warp-3bit-oracle (warp tests/trace_kimi_300.jsonl @6e579f99)",
        "record_type": "metadata",
        "routing_stages": [{
            "allows_unassigned": False,
            "assigned_experts_per_token": 8,
            "num_experts": 256,
            "routing_stage": "decoder",
        }],
    }
    n = 0
    with open(dst, "w") as f:
        f.write(json.dumps(meta) + "\n")
        for lineno, line in enumerate(open(src), 1):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            layers = r["layers"]
            # FAIL LOUDLY: the mapping is only valid for the observed shape.
            if len(layers) != KIMI_EXPECTED_ROUTED_LAYERS:
                raise SystemExit(
                    f"ABORT line {lineno}: expected {KIMI_EXPECTED_ROUTED_LAYERS} routed-layer "
                    f"lists, got {len(layers)}. The 1..26 native mapping is not valid for this "
                    f"fixture; re-derive it before converting.")
            for ordinal, experts in enumerate(layers):
                rec = {
                    "assignment_state": "assigned",
                    "layer": kimi_native_layer(ordinal),
                    "phase": "decoder_generated",
                    "record_type": "routing_selection",
                    "routing_stage": "decoder",
                    "selected_experts": experts,
                    "selected_probabilities": [],
                    "token_position": r["tok"],
                }
                f.write(json.dumps(rec) + "\n")
                n += 1
    return n


OLMOE_HISTORICAL_MODEL_ID = (
    "OLMoE-1B-7B-0125/warp-fixture (warp tests/trace_olmoe_299.jsonl @dc079dad)"
)
# The 2026-08-24 receipted re-capture is a DIFFERENT capture generation and carries
# its own model_id. It must not be conflated with the historical fixture above.
OLMOE_RECAPTURE_MODEL_ID = (
    "OLMoE-1B-7B-0125/recapture-mac-mps (rev 9b0c1aa8, NEW capture 2026-08-24)"
)


def convert_olmoe(src, dst, model_id=OLMOE_HISTORICAL_MODEL_ID):
    meta = {
        "format": "moe-cache-lab.routing-jsonl",
        "format_version": 1,
        "model_id": model_id,
        "record_type": "metadata",
        "num_experts": 64,
        "experts_per_token": 8,
    }
    n = 0
    with open(dst, "w") as f:
        f.write(json.dumps(meta) + "\n")
        for line in open(src):
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            # ordinal IS the native layer index for trace_hf.py (see module docstring)
            for li, experts in enumerate(r["layers"]):
                rec = {
                    "layer": li,
                    "phase": "generated",
                    "record_type": "routing_selection",
                    "selected_experts": experts,
                    "token_position": r["tok"],
                }
                f.write(json.dumps(rec) + "\n")
                n += 1
    return n


if __name__ == "__main__":
    which = sys.argv[1]
    if which == "kimi":
        print("kimi records:", convert_kimi(sys.argv[2], sys.argv[3]))
    elif which == "olmoe":
        print("olmoe records:", convert_olmoe(sys.argv[2], sys.argv[3]))
    else:
        raise SystemExit("usage: convert_kimi_olmoe_canonical_v2.py {kimi|olmoe} SRC DST")
