#!/usr/bin/env python3
"""exp41 Stage 1 — HONEST common-denominator form.

Gate (frozen): whitened captured energy >= unwhitened + 2pp at identical
resident bytes. Both arms must report captured fraction of the SAME
quantity: tr(Sigma_x) per layer, activation-weighted (real samples).

Arms:
  C_u(K) = sum of top-K DIAGONAL entries / tr        (coordinate cut — the
           unwhitened coarse fragment keeps K coordinate axes)
  C_w(K) = sum of top-K EIGENVALUES / tr             (the whitened re-cut:
           diagonal whitening makes the optimal rank-K cut = PCA; this is
           the CEILING of any whitening scheme at that K)

Estimable K <= 23 (N=24 samples, rank limit) — stated, not hidden.
For K > 23 we report the eigenvalue spectrum so the shape of the decay is
visible, with extrapolation flagged as UNMEASURED.
"""
import gzip, json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.expanduser("~/.hermes/state/warp-research/evidence/from-winnie")
N_PASS, N_LAYER, DIM = 24, 93, 7168
K_EVAL = [8, 16, 23]                      # honestly estimable ranks

def main():
    with gzip.open(os.path.join(SRC, "k3_hidden.bin.gz"), "rb") as f:
        X = np.frombuffer(f.read(), dtype="<f4").reshape(N_PASS, N_LAYER, DIM).astype(np.float64)
    diag = np.fromfile(os.path.join(SRC, "k3_hidden_diag.bin"), dtype="<f4").reshape(N_LAYER, DIM).astype(np.float64)

    rows = []
    spec_all = np.zeros((N_LAYER, 24))
    for L in range(N_LAYER):
        XL = X[:, L, :]
        # accumulated Sigma (mean outer product over real passes) — same
        # accumulator the engine runs (WASTE_DUMP_HIDDEN), on real data.
        # Nonzero eigenvalues of S = X^T X / N equal those of the 24x24
        # Gram G = X X^T / N (dual trick) — exact, and seconds instead of
        # minutes per layer.
        tr = float((XL * XL).sum() / N_PASS)
        d = (XL * XL).sum(axis=0) / N_PASS
        ds = np.sort(d)[::-1]
        G = (XL @ XL.T) / N_PASS
        ev = np.linalg.eigvalsh(G)[::-1]   # descending, rank <= 23
        ev = np.clip(ev, 0, None)
        spec_all[L] = ev[:24]
        row = {"layer": L, "trace": tr}
        for K in K_EVAL:
            row[f"C_u_{K}"] = float(ds[:K].sum() / tr)
            row[f"C_w_{K}"] = float(ev[:K].sum() / tr)
        # spectrum shape for extrapolation honesty
        row["ev_top8"] = [float(x) for x in ev[:8]]
        rows.append(row)

    # cross-check our accumulated diag vs the engine's shipped diag
    eng = diag / diag.sum(axis=1, keepdims=True)
    ours = np.array([r["trace"] for r in rows])
    mismatch = 0.0
    for L in range(N_LAYER):
        mine = np.sort(np.diag((X[:, L, :].T @ X[:, L, :]) / N_PASS))[::-1]
        theirs = np.sort(diag[L])[::-1]
        theirs = theirs / theirs.sum() * mine.sum()
        mismatch = max(mismatch, float(np.abs(mine - theirs).max() / (mine.max() + 1e-30)))

    out = {"layers": rows, "diag_vs_engine_max_rel_mismatch": mismatch,
           "engine_diag_note": "engine diag normalised then rescaled to our trace for comparison"}
    with open(os.path.join(HERE, "stage1_common_denominator.json"), "w") as f:
        json.dump(out, f, indent=1)

    print(f"diag accumulator cross-check vs engine diag: max rel mismatch = {mismatch:.3e}")
    print(f"{'K':>4} {'C_u mean%':>10} {'C_w mean%':>10} {'delta_pp':>9}  (n=93 layers)")
    for K in K_EVAL:
        u = np.mean([r[f"C_u_{K}"] for r in rows]) * 100
        w = np.mean([r[f"C_w_{K}"] for r in rows]) * 100
        print(f"{K:>4} {u:>10.3f} {w:>10.3f} {w-u:>+9.3f}")
    # budget point: what rank does 96 GiB buy, and what C_u does it give?
    n_experts = 92 * 896            # K3: 92 MoE layers x 896 experts
    budget = 96 * 2**30
    per_exp = budget / n_experts
    rec_bytes = 3029 * 4096         # 12,406,784 B verified
    frac = per_exp / rec_bytes
    K_budget = int(frac * DIM)
    print(f"\nbudget point: {per_exp:,.0f} B/expert = {frac*100:.2f}% of record "
          f"-> K ~= {K_budget} of {DIM} (if fragment cut is uniform per coordinate)")
    print("top-24 eigenvalue spectrum, layer-0..4 (trace-normalised):")
    for L in range(5):
        s = spec_all[L] / spec_all[L].sum()
        print(f"  L{L:02d}: " + " ".join(f"{v:.4f}" for v in s))

if __name__ == "__main__":
    main()
