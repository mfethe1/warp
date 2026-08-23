#!/usr/bin/env python3
"""exp27: Adaptive top-p routing (K3_TOPP analogue) — offline analysis on REAL-K3
router sigmoid-score trace from Winnie (k3_scores_24tok_decode.txt.gz).

Colibri semantics (c/kimi_k3.c @ 33e67a9c004b6e608d1f19dfbdcc20793377f94f):
  - select top-K (K=16 for K3) by sigmoid(score)+rbias  [rbias not in trace: noted]
  - normalize the K selected weights to sum 1
  - sort selected weights descending
  - keep minimal prefix with cum >= p, renormalize kept weights
Mixture-weight KL of dropping+renormalizing (kept support): KL(p||q) = -log(cum).
The accepted CCR KL bar is 0.0232  =>  cum >= exp(-0.0232) = 0.97707.
"""
import gzip, json, math, hashlib, os

TRACE = os.path.join(os.path.dirname(__file__), "..", "from-winnie", "k3_scores_24tok_decode.txt.gz")
K = 16
REC = 12_406_784  # bytes per expert record (3029 pages, verified)
BASELINE_EXP_PER_TOK = 92 * K  # 1472
BASELINE_GIB = 17.009

def load():
    rows = []  # (tok, layer, [896 sigmoid scores])
    with gzip.open(TRACE, "rt") as f:
        for line in f:
            p = line.split()
            rows.append((int(p[0]), int(p[1]), [float(x) for x in p[2:]]))
    return rows

def select_topk(scores, k=K):
    """top-k experts by score (rbias unavailable in trace -> 0)."""
    idx = sorted(range(len(scores)), key=lambda e: -scores[e])[:k]
    w = [scores[i] for i in idx]
    s = sum(w)
    wn = [x / s for x in w]
    return idx, wn

def topp_keep(wn, p):
    """colibri prefix rule; returns keep count and cumulative mass kept."""
    order = sorted(range(len(wn)), key=lambda i: -wn[i])
    cum = 0.0
    for n, i in enumerate(order):
        cum += wn[i]
        if cum >= p:
            return n + 1, cum
    return len(wn), cum

def main():
    rows = load()
    n_tok = len(set(r[0] for r in rows))
    n_lay = len(set(r[1] for r in rows))
    print(f"trace: {len(rows)} (tok,layer) rows = {n_tok} tokens x {n_lay} layers, 896 experts/layer")

    # 1) mass concentration of top-16 (real K3 router weights)
    keep_at = {1,2,4,8,12,14,16}
    cum_by_n = {n: [] for n in keep_at}
    for tok, lay, scores in rows:
        idx, wn = select_topk(scores)
        order = sorted(wn, reverse=True)
        c = 0.0
        for n, w in enumerate(order, 1):
            c += w
            if n in keep_at:
                cum_by_n[n].append(c)
    print("\ncumulative top-16 router mass retained by prefix length (REAL-K3 scores):")
    for n in sorted(keep_at):
        v = cum_by_n[n]
        mean = sum(v)/len(v)
        sd = (sum((x-mean)**2 for x in v)/len(v))**0.5
        print(f"  top-{n:2d}: mean cum mass = {mean:.4f}  sd = {sd:.4f}  (N={len(v)})")

    # 2) experts/token and dropped-mass KL vs p
    ps = [0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.92, 0.94, 0.95, 0.96, 0.97707, 0.98, 0.99]
    print("\np -> experts/token, reduction vs 16, KL=-log(cum) [mean over 2208 rows], bytes/token:")
    out = []
    for p in ps:
        keeps, kls, cums = [], [], []
        for tok, lay, scores in rows:
            idx, wn = select_topk(scores)
            keep, cum = topp_keep(wn, p)
            keeps.append(keep)
            kls.append(-math.log(cum))
            cums.append(cum)
        ept = sum(keeps)/len(keeps)             # experts per (tok,layer)
        per_tok = ept * n_lay                   # experts per token
        red = 1 - ept/K
        kl = sum(kls)/len(kls)
        kl_sd = (sum((x-kl)**2 for x in kls)/len(kls))**0.5
        gib = per_tok * REC / (1<<30)
        out.append(dict(p=p, experts_per_token=round(per_tok,2),
                        pct_reduction=round(red*100,2), kl=round(kl,5), kl_sd=round(kl_sd,5),
                        gib_per_token=round(gib,3)))
        print(f"  p={p:<6} -> {ept:5.2f} exp/layer ({per_tok:7.1f}/tok), "
              f"reduction {red*100:5.2f}%, KL(mean)={kl:.5f} (sd {kl_sd:.4f}), {gib:.3f} GiB/tok")

    # 3) gate check at the CCR KL bar (0.0232 => cum>=0.97707)
    bar = 0.0232
    cum_bar = math.exp(-bar)
    keeps, kls = [], []
    for tok, lay, scores in rows:
        idx, wn = select_topk(scores)
        keep, cum = topp_keep(wn, cum_bar)
        keeps.append(keep); kls.append(-math.log(cum))
    ept = sum(keeps)/len(keeps); red = 1 - ept/K
    print(f"\nGATE @ KL bar 0.0232 (cum>={cum_bar:.5f}):")
    print(f"  experts/layer {ept:.3f} -> {ept*n_lay:.1f}/token, reduction {red*100:.2f}% "
          f"(accept needs >=15%)  mean KL {sum(kls)/len(kls):.5f}")
    hist = {}
    for k_ in keeps: hist[k_] = hist.get(k_, 0) + 1
    print("  keep-count histogram:", dict(sorted(hist.items())))

    # 4) reference points: colibri's --topp 0.7 claim (30-40% less disk)
    print("\nN =", len(rows), "(tok,layer) routing decisions; single trace, 24 decode tokens")

    res = dict(trace_rows=len(rows), tokens=n_tok, layers=n_lay, sweep=out,
               gate=dict(kl_bar=bar, cum_bar=cum_bar, experts_per_layer=ept,
                         reduction_pct=red*100, accept=red >= 0.15))
    with open("exp27_topp_sweep.json", "w") as f:
        json.dump(res, f, indent=2)
    print("wrote exp27_topp_sweep.json")

if __name__ == "__main__":
    main()
