#!/usr/bin/env python3
"""Route-transition graph analysis for exp3 (metabolic-channeling-route-graph).

Builds the (layer,expert) -> (layer+1,expert) transition graph from an ordered
route trace and measures:
  1. conditional successor entropy H(next | current) vs the uniform null
  2. weighted modularity Q via one-level Louvain, against BOTH
       (a) the absolute preregistered gate Q > 0.15
       (b) a route-shuffled null (experts permuted within layer, per token),
           which is the honest control because a layered chain graph has high
           modularity from layer structure alone.

Every number produced here is a PROXY: the in-repo trace is Kimi-Linear
shaped (26 layers x 256 experts x top-8), NOT K3 (92 x 896 x top-16).
"""
import argparse
import hashlib
import json
import math
import random
from collections import defaultdict


def load_trace(path):
    toks = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            toks.append([list(x) for x in rec["layers"]])
    return toks


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_edges(toks):
    """Return dict (u,v)->weight over node ids (layer,expert)."""
    edges = defaultdict(float)
    for layers in toks:
        for l in range(len(layers) - 1):
            cur, nxt = layers[l], layers[l + 1]
            w = 1.0 / (len(cur) * len(nxt))  # one unit of transition mass / token / layer
            for u in cur:
                for v in nxt:
                    edges[((l, u), (l + 1, v))] += w
    return edges


def successor_entropy(toks, n_experts):
    """H(next expert | current (layer,expert)) in bits, weighted by traffic,
    and the uniform-null entropy log2(n_experts)."""
    counts = defaultdict(lambda: defaultdict(float))
    for layers in toks:
        for l in range(len(layers) - 1):
            cur, nxt = layers[l], layers[l + 1]
            w = 1.0 / (len(cur) * len(nxt))
            for u in cur:
                cu = counts[(l, u)]
                for v in nxt:
                    cu[v] += w
    tot = 0.0
    hsum = 0.0
    per_node = []
    for node, dist in counts.items():
        m = sum(dist.values())
        h = -sum((p / m) * math.log2(p / m) for p in dist.values() if p > 0)
        hsum += m * h
        tot += m
        per_node.append(h)
    mean_h = hsum / tot
    var = sum((h - (sum(per_node) / len(per_node))) ** 2 for h in per_node) / len(per_node)
    return mean_h, math.log2(n_experts), len(counts), var


def louvain_one_level(edges, passes=12, seed=0):
    """One-level (repeated) Louvain modularity maximisation on an undirected
    weighted graph. Returns (Q, communities)."""
    rng = random.Random(seed)
    adj = defaultdict(lambda: defaultdict(float))
    for (u, v), w in edges.items():
        adj[u][v] += w
        adj[v][u] += w
    nodes = list(adj)
    k = {u: sum(adj[u].values()) for u in nodes}
    two_m = sum(k.values())
    comm = {u: i for i, u in enumerate(nodes)}
    # sum of degrees per COMMUNITY id (not per node)
    sigma_tot = {i: k[u] for i, u in enumerate(nodes)}

    for _ in range(passes):
        moved = 0
        rng.shuffle(nodes)
        for u in nodes:
            cu = comm[u]
            ku = k[u]
            sigma_tot[cu] -= ku
            links = defaultdict(float)
            for v, w in adj[u].items():
                links[comm[v]] += w
            best_c, best_gain = cu, links.get(cu, 0.0) - sigma_tot.get(cu, 0.0) * ku / two_m
            for c, w in links.items():
                gain = w - sigma_tot.get(c, 0.0) * ku / two_m
                if gain > best_gain + 1e-12:
                    best_c, best_gain = c, gain
            sigma_tot[best_c] = sigma_tot.get(best_c, 0.0) + ku
            if best_c != cu:
                comm[u] = best_c
                moved += 1
        if moved == 0:
            break

    # modularity of final partition
    inside = defaultdict(float)
    for (u, v), w in edges.items():
        if comm[u] == comm[v]:
            inside[comm[u]] += 2 * w  # undirected: count both directions
    tot_deg = defaultdict(float)
    for u in k:
        tot_deg[comm[u]] += k[u]
    q = sum(inside[c] / two_m - (tot_deg[c] / two_m) ** 2 for c in tot_deg)
    ncomm = len(set(comm.values()))
    return q, ncomm


def shuffled_null(toks, n_experts, seed):
    """Degree-agnostic null: resample each layer's top-k uniformly at random,
    preserving shape (tokens x layers x k). Destroys any successor coupling."""
    rng = random.Random(seed)
    out = []
    for layers in toks:
        out.append([rng.sample(range(n_experts), len(sel)) for sel in layers])
    return out


def permute_null(toks, n_experts, seed):
    """Marginal-preserving null: independently permute the token order of each
    layer's selections. Keeps per-layer expert frequencies exactly, destroys
    only the cross-layer (successor) correlation."""
    rng = random.Random(seed)
    n_lay = len(toks[0])
    cols = [[toks[t][l] for t in range(len(toks))] for l in range(n_lay)]
    for c in cols:
        rng.shuffle(c)
    return [[cols[l][t] for l in range(n_lay)] for t in range(len(toks))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--experts", type=int, default=256)
    ap.add_argument("--nulls", type=int, default=5)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    toks = load_trace(a.trace)
    n_lay = len(toks[0])
    k = len(toks[0][0])
    res = {
        "trace": a.trace,
        "trace_sha256": sha256(a.trace),
        "label": "PROXY (Kimi-Linear-shaped, NOT K3)",
        "shape": {"tokens": len(toks), "layers": n_lay, "topk": k, "experts": a.experts},
    }

    h, h_unif, n_nodes, hvar = successor_entropy(toks, a.experts)
    edges = build_edges(toks)
    q, ncomm = louvain_one_level(edges)
    res["observed"] = {
        "successor_entropy_bits": round(h, 4),
        "uniform_null_bits": round(h_unif, 4),
        "entropy_deficit_bits": round(h_unif - h, 4),
        "entropy_pct_of_uniform": round(100 * h / h_unif, 2),
        "modularity_Q": round(q, 4),
        "n_communities": ncomm,
        "n_nodes_with_successors": n_nodes,
        "n_edges": len(edges),
        "per_node_entropy_var": round(hvar, 4),
    }

    for name, fn in (("uniform_resample", shuffled_null), ("marginal_permute", permute_null)):
        hs, qs = [], []
        for s in range(a.nulls):
            nt = fn(toks, a.experts, 1000 + s)
            nh, _, _, _ = successor_entropy(nt, a.experts)
            nq, _ = louvain_one_level(build_edges(nt), seed=s)
            hs.append(nh)
            qs.append(nq)
        mh = sum(hs) / len(hs)
        mq = sum(qs) / len(qs)
        res["null_" + name] = {
            "n": a.nulls,
            "successor_entropy_bits_mean": round(mh, 4),
            "successor_entropy_sd": round((sum((x - mh) ** 2 for x in hs) / len(hs)) ** 0.5, 4),
            "modularity_Q_mean": round(mq, 4),
            "modularity_Q_sd": round((sum((x - mq) ** 2 for x in qs) / len(qs)) ** 0.5, 4),
        }

    obs = res["observed"]
    npm = res["null_marginal_permute"]
    res["gate"] = {
        "accept": "modularity >0.15 AND entropy materially below uniform",
        "reject": "modularity ~0 or entropy ~uniform -> DEAD",
        "modularity_gt_0_15": obs["modularity_Q"] > 0.15,
        "entropy_below_uniform": obs["entropy_deficit_bits"],
        "modularity_excess_over_marginal_null": round(
            obs["modularity_Q"] - npm["modularity_Q_mean"], 4
        ),
        "entropy_excess_over_marginal_null_bits": round(
            npm["successor_entropy_bits_mean"] - obs["successor_entropy_bits"], 4
        ),
    }
    out = json.dumps(res, indent=2)
    print(out)
    if a.out:
        with open(a.out, "w") as f:
            f.write(out + "\n")


if __name__ == "__main__":
    main()
