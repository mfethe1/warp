#!/usr/bin/env python3
"""exp18 / idea8: routing telemetry schema comparison + canonical converter.

Formats compared (all read from pinned sources, none modified):
  A. colibri .coli_usage        (docs/routing-telemetry.md, c/route_trace.h:358-363)
       "-1 <n_layers> <n_experts>" / "-2 <fmt_ver> <engine_hash>" / "<layer> <expert> <count>"
  B. colibri ROUTE_TRACE        (c/route_trace.h:142-143)
       "<call> <row> <layer> <id>:<gate> ..."
  C. warp WASTE_DUMP_ROUTE      (tools/routing_stats.py:173-198 read_trace)
       "<pos> <layer> id0..idK-1 w0..wK-1 look0..lookK-1"
  D. warp WASTE_DUMP_PREFILL    (tools/prefill_trace.py SCHEMA waste-prefill-v1)
  E. ours: trace_kimi_300.jsonl {"tok": n, "layers": [[e,...],...]}

Canonical target: waste-route-v1 JSONL, one object per (token, layer).
"""
import json, sys, hashlib, os

# ---- the 6 fields the spec requires a canonical schema to capture ----
FIELDS = ["ordered_layer_expert", "residency_state", "physical_bytes",
          "timing", "evictions", "route_identity"]

COVERAGE = {
    # format: {field: "yes"|"no"|"partial: note"}
    "colibri/.coli_usage": {
        "ordered_layer_expert": "no: aggregated counts, order destroyed",
        "residency_state": "no",
        "physical_bytes": "no",
        "timing": "no",
        "evictions": "no",
        "route_identity": "yes: -2 record carries fmt_ver + engine hash",
    },
    "colibri/ROUTE_TRACE": {
        "ordered_layer_expert": "yes: (call,row,layer)+ids, call is monotone",
        "residency_state": "no",
        "physical_bytes": "no",
        "timing": "no",
        "evictions": "no",
        "route_identity": "partial: engine identity only in the sibling .coli_usage",
    },
    "warp/WASTE_DUMP_ROUTE": {
        "ordered_layer_expert": "yes: absolute pos + layer, no boundary re-derivation",
        "residency_state": "partial: lookahead prediction, not residency",
        "physical_bytes": "no",
        "timing": "no",
        "evictions": "no",
        "route_identity": "no",
    },
    "warp/WASTE_DUMP_PREFILL": {
        "ordered_layer_expert": "partial: union+density per layer, ids not listed",
        "residency_state": "yes: cache_hits/cache_misses",
        "physical_bytes": "yes: physical_bytes_read, expert_record_bytes, logical, full_bank",
        "timing": "yes: layer/attn/ff/moe/expert_acquire ms",
        "evictions": "no: deltas only, no evicted key",
        "route_identity": "yes: schema string waste-prefill-v1",
    },
    "ours/trace_kimi_300.jsonl": {
        "ordered_layer_expert": "yes: tok index + layer position",
        "residency_state": "no",
        "physical_bytes": "no",
        "timing": "no",
        "evictions": "no",
        "route_identity": "no",
    },
}

# ---------------- readers ----------------
def read_jsonl_ours(path):
    """E -> [(tok, layer, [ids], [gates|None])]"""
    out = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            for li, lay in enumerate(r["layers"]):
                out.append((r["tok"], li, list(lay), None))
    return out

def read_route_trace_colibri(path):
    """B -> [(call, row, layer, ids, gates)]"""
    out = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 4:
                continue
            call, row, layer = int(p[0]), int(p[1]), int(p[2])
            ids, gates = [], []
            for tokf in p[3:]:
                i, g = tokf.split(":")
                ids.append(int(i)); gates.append(float(g))
            out.append((call, row, layer, ids, gates))
    return out

def read_waste_dump_route(path):
    """C -> [(pos, layer, ids, weights, look)] -- mirrors routing_stats.py read_trace"""
    out = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 3:
                continue
            pos, layer = int(p[0]), int(p[1])
            k = (len(p) - 2) // 3
            ids = [int(x) for x in p[2:2 + k]]
            w = [float(x) for x in p[2 + k:2 + 2 * k]]
            look = [int(float(x)) for x in p[2 + 2 * k:2 + 3 * k]]
            out.append((pos, layer, ids, w, look))
    return out

# ---------------- writers ----------------
def write_route_trace_colibri(recs, path):
    """recs: [(tok, layer, ids, gates)] -> B. call = token index (one moe call/layer/token
    at batch-1 -> call must be monotone across (tok,layer)); row = 0 at batch-1."""
    with open(path, "w") as f:
        call = 0
        for tok, layer, ids, gates in recs:
            g = gates if gates else [1.0 / len(ids)] * len(ids)
            f.write("%d %d %d %s\n" % (call, 0, layer,
                    " ".join("%d:%.4f" % (i, x) for i, x in zip(ids, g))))
            call += 1

def write_waste_dump_route(recs, path):
    with open(path, "w") as f:
        for tok, layer, ids, gates in recs:
            g = gates if gates else [1.0 / len(ids)] * len(ids)
            f.write("%d %d %s %s %s\n" % (tok, layer,
                    " ".join(str(i) for i in ids),
                    " ".join("%.6f" % x for x in g),
                    " ".join("-1" for _ in ids)))

def write_canonical(recs, path, n_layers, n_experts, engine, rec_bytes):
    """waste-route-v1: superset carrying all 6 fields; residency/bytes/timing/evict
    are OPTIONAL and null when the producing format could not supply them."""
    with open(path, "w") as f:
        f.write(json.dumps({"schema": "waste-route-v1", "record": "header",
                            "n_layers": n_layers, "n_experts": n_experts,
                            "engine": engine, "expert_record_bytes": rec_bytes}) + "\n")
        for seq, (tok, layer, ids, gates) in enumerate(recs):
            f.write(json.dumps({
                "schema": "waste-route-v1", "seq": seq, "pos": tok, "layer": layer,
                "ids": ids, "gates": gates,
                "resident": None, "physical_bytes_read": None,
                "evicted": None, "layer_ms": None,
            }, separators=(",", ":")) + "\n")

def read_canonical(path):
    recs, hdr = [], None
    with open(path) as f:
        for line in f:
            o = json.loads(line)
            if o.get("record") == "header":
                hdr = o; continue
            recs.append((o["pos"], o["layer"], o["ids"], o["gates"]))
    return hdr, recs

def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()

# ---------------- round trip ----------------
if __name__ == "__main__":
    src = sys.argv[1]
    outdir = sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    base = read_jsonl_ours(src)
    recs = [(t, l, i, None) for (t, l, i, _) in base]
    n_layers = max(l for _, l, _, _ in recs) + 1
    n_experts = max(max(i) for _, _, i, _ in recs) + 1

    p_can = os.path.join(outdir, "canonical.jsonl")
    p_b = os.path.join(outdir, "as_colibri_route_trace.txt")
    p_c = os.path.join(outdir, "as_waste_dump_route.txt")
    write_canonical(recs, p_can, n_layers, n_experts, "warp_vq3r", 12406784)
    write_route_trace_colibri(recs, p_b)
    write_waste_dump_route(recs, p_c)

    hdr, back_can = read_canonical(p_can)
    back_b = [(call, layer, ids, None)
              for call, row, layer, ids, g in read_route_trace_colibri(p_b)]
    back_c = [(pos, layer, ids, None) for pos, layer, ids, w, lk in read_waste_dump_route(p_c)]

    ids_only = [(t, l, i) for t, l, i, _ in recs]
    r_can = [(t, l, i) for t, l, i, _ in back_can]
    # colibri's call counter is a flat sequence, not (tok,layer): recover (tok,layer)
    r_b = [(c // n_layers, l, i) for c, l, i, _ in back_b]
    r_c = [(t, l, i) for t, l, i, _ in back_c]

    res = {
        "source": src, "source_sha256": sha(src),
        "n_records": len(recs), "n_layers": n_layers, "n_experts": n_experts,
        "roundtrip_canonical_lossless": r_can == ids_only,
        "roundtrip_colibri_route_trace_lossless": r_b == ids_only,
        "roundtrip_waste_dump_route_lossless": r_c == ids_only,
        "colibri_call_is_flat_sequence_not_token": True,
        "coverage": COVERAGE,
        "field_union_covered_by_canonical": FIELDS,
        "artifacts": {os.path.basename(p): sha(p) for p in (p_can, p_b, p_c)},
    }
    # which fields NO existing format captures
    res["fields_no_single_format_captures"] = [
        f for f in FIELDS
        if not any(COVERAGE[k][f].startswith("yes") for k in COVERAGE)
    ]
    res["fields_requiring_merge_of_2_formats"] = [
        f for f in FIELDS
        if sum(1 for k in COVERAGE if COVERAGE[k][f].startswith("yes")) >= 1
        and not any(COVERAGE[k]["ordered_layer_expert"].startswith("yes")
                    and COVERAGE[k][f].startswith("yes") for k in COVERAGE)
    ]
    print(json.dumps(res, indent=2))
