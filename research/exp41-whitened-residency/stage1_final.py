#!/usr/bin/env python3
"""exp41 Stage 1 final analysis — three decisive checks.

1. Engine-diag cross-check (honest): correlation between our accumulated
   per-coordinate energy and the engine's shipped k3_hidden_diag.bin.
2. Exact C_u at the budget point K=722 (unwhitened coordinate cut).
3. Tail-decay feasibility: what must eigenvalues 25..722 average for the
   whitened (PCA) cut to reach 90% at K=722, vs the observed decay of
   eigenvalues 2..24. Also the analytic no-op proof for diagonal whitening.
"""
import gzip, json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.expanduser("~/.hermes/state/warp-research/evidence/from-winnie")
N_PASS, N_LAYER, DIM = 24, 93, 7168
K_BUDGET = 722

with gzip.open(os.path.join(SRC, "k3_hidden.bin.gz"), "rb") as f:
    X = np.frombuffer(f.read(), dtype="<f4").reshape(N_PASS, N_LAYER, DIM).astype(np.float64)
diag = np.fromfile(os.path.join(SRC, "k3_hidden_diag.bin"), dtype="<f4").reshape(N_LAYER, DIM).astype(np.float64)

# --- 1. honest cross-check ---
corrs, ratio_med = [], []
for L in range(N_LAYER):
    ours = (X[:, L, :] ** 2).sum(axis=0)
    theirs = diag[L]
    if ours.sum() > 0 and theirs.sum() > 0:
        corrs.append(np.corrcoef(ours, theirs)[0, 1])
        ratio_med.append(np.median(theirs / np.maximum(ours, 1e-30)))
print(f"[1] engine diag vs our accumulated energy: mean corr = {np.mean(corrs):.4f}, "
      f"min {np.min(corrs):.4f}; median ratio theirs/ours = {np.median(ratio_med):.4g}")

# --- 2. exact C_u at K=722 ---
cu = []
for L in range(N_LAYER):
    d = (X[:, L, :] ** 2).sum(axis=0)
    ds = np.sort(d)[::-1]
    cu.append(ds[:K_BUDGET].sum() / d.sum())
print(f"[2] C_u(K=722) over 93 layers: mean {np.mean(cu)*100:.2f}%, "
      f"min {np.min(cu)*100:.2f}%, max {np.max(cu)*100:.2f}%  [PROXY, N=24 real passes]")

# --- 3. tail feasibility ---
# observed sample-eig decay for eigs 2..24, then what eigs 25..722 must do
need = []
for L in range(N_LAYER):
    XL = X[:, L, :]
    G = (XL @ XL.T) / N_PASS
    ev = np.clip(np.linalg.eigvalsh(G)[::-1], 0, None)
    tr = ev.sum()
    top24 = ev[:24].sum() / tr
    # required average share per eigenvalue 25..722 to reach 90%
    req = (0.90 - top24) / (722 - 24) if top24 < 0.90 else 0.0
    e24 = ev[23] / tr
    need.append({"top24": top24, "e24_share": e24, "req_avg_25_722": req,
                 "drop_factor": e24 / req if req > 0 else float("inf")})
top24s = np.array([n["top24"] for n in need])
e24s = np.array([n["e24_share"] for n in need])
reqs = np.array([n["req_avg_25_722"] for n in need])
drops = np.array([n["drop_factor"] for n in need])
print(f"[3] sample top-24 capture: mean {top24s.mean()*100:.1f}% (RANK-INFLATED CEILING, N=24)")
print(f"    observed eig24 share: mean {e24s.mean()*100:.3f}% of trace")
print(f"    required avg share for eigs 25..722 to hit 90%: mean {reqs.mean()*100:.4f}%")
print(f"    => tail must drop {drops.mean():.0f}x BELOW eig24 immediately (mean over layers); "
      f"observed decay eig2->eig24 is only {np.mean([ (lambda ev: ev[1]/ev[23])(np.clip(np.linalg.eigvalsh((X[:,L,:]@X[:,L,:].T)/N_PASS)[::-1],0,None)) for L in range(N_LAYER)]):.0f}x over 22 steps")

# --- 4. analytic no-op: diagonal whitening + coordinate cut ---
print("[4] diagonal whitening + coordinate cut: captured energy in ORIGINAL space")
print("    = sum_{i in S} d_i / tr for ANY S (proof: error = tr((I-A) Sigma (I-A)^T),")
print("    A zeroes coords outside S in whitened space <=> zeroes same coords in original")
print("    space up to per-coordinate rescale that cancels in the ratio). The only")
print("    choice left is WHICH S — and whitened importance is uniform => no-op.")
# numeric demonstration on layer 50
L = 50
XL = X[:, L, :]
d = (XL ** 2).sum(axis=0)
S_unwh = np.argsort(d)[::-1][:512]
w = 1.0 / np.sqrt(np.maximum(d, 1e-30))
Ew = ((XL * w) ** 2).sum(axis=0)
S_wh_in_whspace = np.argsort(Ew)[::-1][:512]
cap_unwh = d[S_unwh].sum() / d.sum()
cap_wh_same_denominator = d[S_wh_in_whspace].sum() / d.sum()
print(f"    layer 50, K=512: unwhitened cut captures {cap_unwh*100:.2f}% of tr(Sigma);")
print(f"    'whitened' cut, SAME denominator: {cap_wh_same_denominator*100:.2f}%  (no gain — as proven)")

out = {"engine_diag_mean_corr": float(np.mean(corrs)),
       "C_u_K722_mean_pct": float(np.mean(cu) * 100),
       "C_u_K722_min_pct": float(np.min(cu) * 100),
       "C_u_K722_max_pct": float(np.max(cu) * 100),
       "sample_top24_capture_mean_pct": float(top24s.mean() * 100),
       "eig24_share_mean_pct": float(e24s.mean() * 100),
       "required_avg_share_25_722_pct": float(reqs.mean() * 100),
       "required_tail_drop_factor": float(drops.mean()),
       "diag_whitening_noop_layer50": {"unwhitened_pct": cap_unwh * 100,
                                        "whitened_same_denom_pct": cap_wh_same_denominator * 100}}
with open(os.path.join(HERE, "stage1_final.json"), "w") as f:
    json.dump(out, f, indent=1)
print("\nwrote stage1_final.json")
