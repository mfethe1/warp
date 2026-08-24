#!/usr/bin/env python3
"""
OLMoE re-capture with full environment receipt.

DERIVED FROM: sqliteai/warp tools/trace_hf.py @ dc079dad1c35def2ee7bb3b2de5157db8d9f08a8

THIS IS A NEW CAPTURE. It does NOT recover the provenance of the historical
fixture tests/trace_olmoe_299.jsonl @dc079dad. Model revision, torch/transformers
versions, device/dtype, and the active gate-output branch were never recorded for
that run and cannot be established by running the script again today.

ROUTING SEMANTICS ARE UNCHANGED from the source script. The only additions are
receipt-only: we record WHICH gate-output branch fired, without altering what is
selected or executed. The `sorted()` call is preserved deliberately -- changing it
would change the artifact; instead we record that native rank order is destroyed.
"""
import json, os, platform, subprocess, sys, time, hashlib

OUT_RAW   = sys.argv[1] if len(sys.argv) > 1 else "trace_olmoe_new.jsonl"
MODEL     = sys.argv[2] if len(sys.argv) > 2 else "allenai/OLMoE-1B-7B-0125"
N_NEW     = int(sys.argv[3]) if len(sys.argv) > 3 else 300
REVISION  = sys.argv[4] if len(sys.argv) > 4 else None   # pinned by caller

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
import transformers

# --- identical to source script @dc079dad ---
PROMPT = (
    "Write a C function that parses a JSON array of integers without using "
    "any external library, then explain its memory usage and edge cases, "
    "and finally propose unit tests for it."
)
dev = "mps" if torch.backends.mps.is_available() else "cpu"
dtype = torch.bfloat16 if dev == "mps" else torch.float32
print(f"device={dev} dtype={dtype}", flush=True)

tok = AutoTokenizer.from_pretrained(MODEL, revision=REVISION)
model = AutoModelForCausalLM.from_pretrained(
    MODEL, dtype=dtype, low_cpu_mem_usage=True, revision=REVISION
).to(dev).eval()

cfg = model.config
top_k = cfg.num_experts_per_tok
print(f"layers={cfg.num_hidden_layers} experts={cfg.num_experts} top_k={top_k}", flush=True)

step_layers = []
trace = []
# RECEIPT ONLY: which observation boundary actually fired
branch_counts = {"native_topk_index_tuple": 0, "recomputed_from_logits": 0}
gate_out_types = set()

def mk_hook(layer_idx):
    def hook(module, inp, out):
        # IDENTICAL branch logic to trace_hf.py @dc079dad
        if isinstance(out, tuple):
            branch_counts["native_topk_index_tuple"] += 1
            gate_out_types.add(f"tuple[len={len(out)}]")
            idx = out[2].reshape(-1, top_k)
        else:
            branch_counts["recomputed_from_logits"] += 1
            gate_out_types.add(f"tensor{tuple(out.shape)}")
            idx = torch.topk(out.float(), top_k).indices.reshape(-1, top_k)
        # sorted() PRESERVED from source: destroys native rank order.
        # Membership evidence only; NOT rank-preserving.
        step_layers.append((layer_idx, sorted(idx[-1].tolist())))
    return hook

for li, layer in enumerate(model.model.layers):
    layer.mlp.gate.register_forward_hook(mk_hook(li))

ids = tok(PROMPT, return_tensors="pt").input_ids.to(dev)
n_prompt = int(ids.shape[1])
print(f"prompt tokens: {n_prompt}; generating {N_NEW}...", flush=True)

t0 = time.time()
torch.manual_seed(0)
with torch.no_grad():
    cur = ids
    for i in range(N_NEW):
        out = model(cur)                 # full re-forward, as in source
        step_layers.sort()
        if i > 0 and len(step_layers) == cfg.num_hidden_layers:
            trace.append({"tok": i, "layers": [l for _, l in step_layers]})
        step_layers.clear()
        probs = torch.softmax(out.logits[0, -1].float() / 0.7, dim=-1)
        nxt = torch.multinomial(probs, 1).reshape(1, 1).to(cur.device)
        cur = torch.cat([cur, nxt], dim=1)
        if (i + 1) % 25 == 0:
            print(f"  {i+1}/{N_NEW}  ({time.time()-t0:.0f}s)", flush=True)
elapsed = time.time() - t0

with open(OUT_RAW, "w") as f:
    for t in trace:
        f.write(json.dumps(t) + "\n")
print(f"wrote {len(trace)} tokens of trace in {elapsed:.0f}s", flush=True)

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(65536), b""):
            h.update(b)
    return h.hexdigest()

# resolve the ACTUAL revision that was loaded
resolved_rev = REVISION
try:
    from huggingface_hub import HfApi
    resolved_rev = HfApi().model_info(MODEL, revision=REVISION).sha
except Exception as e:
    resolved_rev = f"{REVISION} (hub lookup failed: {e})"

receipt = {
    "capture_kind": "NEW RECEIPTED CAPTURE",
    "does_not_recover": ("provenance of sqliteai/warp tests/trace_olmoe_299.jsonl "
                         "@dc079dad1c35def2ee7bb3b2de5157db8d9f08a8"),
    "derived_from_script": "sqliteai/warp tools/trace_hf.py @dc079dad1c35def2ee7bb3b2de5157db8d9f08a8",
    "routing_semantics_modified": False,
    "additions": "receipt-only branch counters; no change to selection or execution",
    "model_id": MODEL,
    "model_revision_requested": REVISION,
    "model_revision_resolved": resolved_rev,
    "observation_boundary": {
        "branch_counts": branch_counts,
        "gate_output_types_seen": sorted(gate_out_types),
        "active_branch": max(branch_counts, key=branch_counts.get),
        "native_rank_order_preserved": False,
        "reason": "source script applies sorted(idx[-1].tolist()) -- membership only",
        "coverage": "routed experts only",
    },
    "generation": {
        "prompt": PROMPT, "prompt_tokens": n_prompt,
        "n_new_requested": N_NEW, "events_written": len(trace),
        "sampling": "multinomial, temperature 0.7",
        "torch_manual_seed": 0,
        "forward_mode": "full re-forward each step (cache-agnostic)",
    },
    "environment": {
        "os": platform.platform(), "machine": platform.machine(),
        "processor": platform.processor() or "Apple M4",
        "python": sys.version.split()[0],
        "torch": torch.__version__, "transformers": transformers.__version__,
        "device": dev, "dtype": str(dtype),
        "mps_available": bool(torch.backends.mps.is_available()),
    },
    "model_config": {
        "num_hidden_layers": cfg.num_hidden_layers,
        "num_experts": cfg.num_experts,
        "num_experts_per_tok": top_k,
    },
    "run": {"elapsed_seconds": round(elapsed, 1),
            "command": " ".join([sys.executable] + sys.argv)},
    "artifacts": {"raw_trace": OUT_RAW, "raw_trace_sha256": sha(OUT_RAW)},
}
with open("recapture_receipt.json", "w") as f:
    json.dump(receipt, f, indent=1)
print(json.dumps({k: receipt[k] for k in
                  ("observation_boundary", "environment", "model_revision_resolved")}, indent=1))
