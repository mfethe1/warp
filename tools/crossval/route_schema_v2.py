#!/usr/bin/env python3
"""exp24 / idea8: CANONICAL TELEMETRY SCHEMA + CONVERTER (10-field superset).

Supersedes exp18's 6-field comparison. Preregistered canonical field list:
  1 token             2 layer                3 ordered routed expert ids
  4 router weights    5 resident-before-demand   6 physical bytes
  7 read start/end    8 device id            9 eviction
 10 route/output hash

Sources of truth (pinned, read-only, never modified):
  colibri @ 33e67a9c004b6e608d1f19dfbdcc20793377f94f
    .coli_usage    docs/routing-telemetry.md ; c/route_trace.h rt_save
    ROUTE_TRACE    c/route_trace.h rt_trace  "<call> <row> <layer> <id>:<gate> ..."
  warp @ fd0deabc62b6e2e86d245553f61e77397a48a3b8
    WASTE_DUMP_ROUTE         src/model.c:3513 "<pos> <L> ids[K] w[K] look[K]"
    WASTE_DUMP_ROUTE_MARGIN  src/model.c:3268 (separate CSV, fixed 3K shape reason)
    WASTE_DUMP_PREFILL       tools/prefill_trace.py SCHEMA=waste-prefill-v1
    ecache counters          src/ecache.h:82 clock/hits/misses/bytes_read/evictions
  ours  tests/trace_kimi_300.jsonl  {"tok": n, "layers": [[e,...],...]}

Canonical target: waste-route-v2 JSONL, one object per (token, layer).
"""
import json, sys, hashlib, os

FIELDS = [
    "token", "layer", "ordered_expert_ids", "router_weights",
    "resident_before_demand", "physical_bytes", "read_start_end",
    "device_id", "eviction", "route_output_hash",
]

Y, N, P = "yes", "no", "partial"

COVERAGE = {
    "colibri/.coli_usage": {
        "token": (N, "aggregate over the whole run; no token axis at all"),
        "layer": (Y, "first field of every triple"),
        "ordered_expert_ids": (N, "(layer,expert,count) with order destroyed"),
        "router_weights": (N, "counts only, gates never persisted"),
        "resident_before_demand": (N, ""),
        "physical_bytes": (N, ""),
        "read_start_end": (N, ""),
        "device_id": (N, ""),
        "eviction": (N, ""),
        "route_output_hash": (P, "-2 record carries fmt_ver + engine hash: "
                                 "identity of the WRITER, not of the route"),
    },
    "colibri/ROUTE_TRACE": {
        "token": (P, "call//n_layers at batch-1 only; call is a flat moe counter"),
        "layer": (Y, "third field"),
        "ordered_expert_ids": (Y, "selection order preserved"),
        "router_weights": (Y, "post-normalisation gates, %.4f"),
        "resident_before_demand": (N, ""),
        "physical_bytes": (N, ""),
        "read_start_end": (N, ""),
        "device_id": (N, ""),
        "eviction": (N, ""),
        "route_output_hash": (P, "engine identity only via sibling .coli_usage"),
    },
    "warp/WASTE_DUMP_ROUTE": {
        "token": (Y, "dump_pos0 absolute position, no boundary re-derivation"),
        "layer": (Y, "second field"),
        "ordered_expert_ids": (Y, "idx[0..K-1] in selection order"),
        "router_weights": (Y, "renormalised w[j] * routed_scale, %.6g"),
        "resident_before_demand": (N, "third group is predict_next_moe LOOKAHEAD, "
                                      "a prediction, not residency"),
        "physical_bytes": (N, ""),
        "read_start_end": (N, ""),
        "device_id": (N, ""),
        "eviction": (N, ""),
        "route_output_hash": (N, ""),
    },
    "warp/WASTE_DUMP_ROUTE_MARGIN": {
        "token": (Y, "pos"),
        "layer": (Y, "L"),
        "ordered_expert_ids": (P, "kth selected + best unselected only"),
        "router_weights": (Y, "SCORE-SPACE: prob+bias, the real decision boundary"),
        "resident_before_demand": (N, ""),
        "physical_bytes": (N, ""),
        "read_start_end": (N, ""),
        "device_id": (N, ""),
        "eviction": (N, ""),
        "route_output_hash": (N, ""),
    },
    "warp/WASTE_DUMP_PREFILL": {
        "token": (P, "pos + tokens = chunk coordinates, not per-token"),
        "layer": (Y, "layer"),
        "ordered_expert_ids": (N, "experts_unique/experts_total union counts, ids not listed"),
        "router_weights": (N, ""),
        "resident_before_demand": (Y, "cache_hits / cache_misses"),
        "physical_bytes": (Y, "physical_bytes_read + expert_record_bytes + "
                              "logical_expert_bytes + full_bank_bytes"),
        "read_start_end": (P, "expert_acquire_ms is a per-layer DURATION SUM; "
                              "no per-read start/end timestamps"),
        "device_id": (N, ""),
        "eviction": (N, "cache_hits/misses deltas only, no evicted key"),
        "route_output_hash": (P, "schema string waste-prefill-v1 = format id, not route id"),
    },
    "warp/ecache counters": {
        "token": (N, "process-lifetime counters"),
        "layer": (N, "key is layer<<16|expert but counters are global"),
        "ordered_expert_ids": (N, ""),
        "router_weights": (N, ""),
        "resident_before_demand": (Y, "hits / misses / prefetched / spec_issued"),
        "physical_bytes": (Y, "bytes_read"),
        "read_start_end": (N, "clock is a logical LFRU tick, not a timestamp"),
        "device_id": (N, "single fetch_fn, no per-device attribution"),
        "eviction": (P, "evictions COUNT exists (ecache.h:82); the evicted KEY does not"),
        "route_output_hash": (N, ""),
    },
    "ours/trace_kimi_300.jsonl": {
        "token": (Y, "tok"),
        "layer": (Y, "array position"),
        "ordered_expert_ids": (Y, "layers[li]"),
        "router_weights": (N, ""),
        "resident_before_demand": (N, ""),
        "physical_bytes": (N, ""),
        "read_start_end": (N, ""),
        "device_id": (N, ""),
        "eviction": (N, ""),
        "route_output_hash": (N, ""),
    },
}


# ---------------- readers / writers ----------------
def read_jsonl_ours(path):
    out = []
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            for li, lay in enumerate(r["layers"]):
                out.append((r["tok"], li, list(lay), None))
    return out


def write_canonical_v2(recs, path, n_layers, n_experts, engine, rec_bytes, provenance):
    with open(path, "w") as f:
        f.write(json.dumps({
            "schema": "waste-route-v2", "record": "header",
            "n_layers": n_layers, "n_experts": n_experts, "engine": engine,
            "expert_record_bytes": rec_bytes,
            "provenance": provenance,
            "n_devices": None, "device_map": None,
        }) + "\n")
        for seq, (tok, layer, ids, gates) in enumerate(recs):
            f.write(json.dumps({
                "schema": "waste-route-v2", "seq": seq,
                "pos": tok, "layer": layer, "ids": ids,
                "gates": gates, "gate_space": None,
                "resident": None, "physical_bytes_read": None,
                "read_ns": None, "dev": None,
                "evicted": None, "route_hash": None, "layer_ms": None,
            }, separators=(",", ":")) + "\n")


def read_canonical_v2(path):
    recs, hdr = [], None
    with open(path) as f:
        for line in f:
            o = json.loads(line)
            if o.get("record") == "header":
                hdr = o
                continue
            assert o["schema"] == "waste-route-v2"
            recs.append((o["pos"], o["layer"], o["ids"], o["gates"]))
    return hdr, recs


def write_route_trace_colibri(recs, path):
    with open(path, "w") as f:
        for call, (tok, layer, ids, gates) in enumerate(recs):
            g = gates if gates else [1.0 / len(ids)] * len(ids)
            f.write("%d %d %d %s\n" % (call, 0, layer,
                    " ".join("%d:%.4f" % (i, x) for i, x in zip(ids, g))))


def read_route_trace_colibri(path):
    out = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 4:
                continue
            call, row, layer = int(p[0]), int(p[1]), int(p[2])
            ids, gates = [], []
            for t in p[3:]:
                i, g = t.split(":")
                ids.append(int(i)); gates.append(float(g))
            out.append((call, row, layer, ids, gates))
    return out


def write_waste_dump_route(recs, path):
    with open(path, "w") as f:
        for tok, layer, ids, gates in recs:
            g = gates if gates else [1.0 / len(ids)] * len(ids)
            f.write("%d %d %s %s %s\n" % (tok, layer,
                    " ".join(str(i) for i in ids),
                    " ".join("%.6g" % x for x in g),
                    " ".join("-1" for _ in ids)))


def read_waste_dump_route(path):
    out = []
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 3:
                continue
            pos, layer = int(p[0]), int(p[1])
            k = (len(p) - 2) // 3
            out.append((pos, layer, [int(x) for x in p[2:2 + k]],
                        [float(x) for x in p[2 + k:2 + 2 * k]]))
    return out


def write_coli_usage(recs, path, n_layers, n_experts, engine_hash=3815245270):
    counts = {}
    for _, layer, ids, _ in recs:
        for e in ids:
            counts[(layer, e)] = counts.get((layer, e), 0) + 1
    with open(path, "w") as f:
        f.write("-1 %d %d\n" % (n_layers, n_experts))
        f.write("-2 %d %u\n" % (1, engine_hash))
        for (l, e) in sorted(counts):
            f.write("%d %d %u\n" % (l, e, counts[(l, e)]))
    return counts


def read_coli_usage_legacy(path):
    """A literal copy of the pre-header reader loop from docs/routing-telemetry.md:
       while(fscanf(f,"%d %d %u",&l,&e,&cnt)==3) if(l>=0 && ...)"""
    toks, admitted = [], {}
    with open(path) as f:
        for w in f.read().split():
            toks.append(w)
    i = 0
    while i + 2 < len(toks) + 1:
        if i + 3 > len(toks):
            break
        try:
            l, e, c = int(toks[i]), int(toks[i + 1]), int(toks[i + 2])
        except ValueError:
            break
        i += 3
        if l >= 0:
            admitted[(l, e)] = admitted.get((l, e), 0) + c
    return admitted


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


if __name__ == "__main__":
    src, outdir = sys.argv[1], sys.argv[2]
    os.makedirs(outdir, exist_ok=True)
    base = read_jsonl_ours(src)
    recs = [(t, l, i, None) for (t, l, i, _) in base]
    n_layers = max(l for _, l, _, _ in recs) + 1
    n_experts = max(max(i) for _, _, i, _ in recs) + 1

    p_can = os.path.join(outdir, "canonical_v2.jsonl")
    p_b = os.path.join(outdir, "as_colibri_route_trace.txt")
    p_c = os.path.join(outdir, "as_waste_dump_route.txt")
    p_u = os.path.join(outdir, "as_coli_usage.txt")

    write_canonical_v2(recs, p_can, n_layers, n_experts, "warp_vq3r", 12406784,
                       {"src": os.path.basename(src), "src_sha256": sha(src),
                        "producer": "ours/trace_kimi_300.jsonl"})
    write_route_trace_colibri(recs, p_b)
    write_waste_dump_route(recs, p_c)
    counts = write_coli_usage(recs, p_u, n_layers, n_experts)

    hdr, back_can = read_canonical_v2(p_can)
    r_can = [(t, l, i) for t, l, i, _ in back_can]
    r_b = [(c // n_layers, l, i)
           for c, row, l, i, g in read_route_trace_colibri(p_b)]
    r_c = [(t, l, i) for t, l, i, _ in read_waste_dump_route(p_c)]
    ids_only = [(t, l, i) for t, l, i, _ in recs]

    legacy = read_coli_usage_legacy(p_u)
    usage_ok = legacy == counts

    # -------- coverage census --------
    def score(v):
        return {"yes": 1.0, "partial": 0.5, "no": 0.0}[v]

    cov_counts = {k: sum(score(v[0]) for v in c.values())
                  for k, c in COVERAGE.items()}
    full_yes = {k: [f for f, v in c.items() if v[0] == Y]
                for k, c in COVERAGE.items()}
    # fields no single format captures with a full YES
    orphan = [f for f in FIELDS
              if not any(COVERAGE[k][f][0] == Y for k in COVERAGE)]
    # fields captured somewhere, but never in a format that also has ordered ids
    joinable_ids = [k for k in COVERAGE if COVERAGE[k]["ordered_expert_ids"][0] == Y]
    needs_merge = [f for f in FIELDS
                   if any(COVERAGE[k][f][0] == Y for k in COVERAGE)
                   and not any(COVERAGE[k][f][0] == Y for k in joinable_ids)]

    res = {
        "experiment": "exp24", "idea": 8, "schema": "waste-route-v2",
        "evidence_class": "RECOMPUTATION",
        "source_trace": src, "source_sha256": sha(src),
        "source_class": "PROXY (Kimi-Linear-shaped 26L x 256E top-8, NOT K3 92L x 896E top-16)",
        "colibri_sha": "33e67a9c004b6e608d1f19dfbdcc20793377f94f",
        "warp_sha": "fd0deabc62b6e2e86d245553f61e77397a48a3b8",
        "n_records": len(recs), "n_layers": n_layers, "n_experts": n_experts,
        "roundtrip_canonical_v2_lossless": r_can == ids_only,
        "roundtrip_colibri_route_trace_lossless": r_b == ids_only,
        "roundtrip_waste_dump_route_lossless": r_c == ids_only,
        "coli_usage_legacy_reader_agrees": usage_ok,
        "coli_usage_distinct_pairs": len(counts),
        "coverage": {k: {f: {"level": v[0], "note": v[1]}
                         for f, v in c.items()} for k, c in COVERAGE.items()},
        "coverage_score_of_10": cov_counts,
        "fully_captured_by": full_yes,
        "fields_no_format_captures": orphan,
        "fields_captured_but_not_joinable_to_route": needs_merge,
        "canonical_covers_all_10": True,
        "artifacts": {os.path.basename(p): sha(p)
                      for p in (p_can, p_b, p_c, p_u)},
    }
    print(json.dumps(res, indent=2))
