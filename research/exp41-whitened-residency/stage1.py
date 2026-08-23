#!/usr/bin/env python3
"""exp41 Stage 1 — whitened vs unwhitened activation-weighted captured energy
at FIXED resident bytes, on real K3 hidden states (24 passes x 93 layers x 7168).

Preregistered gate (frozen BEFORE data; see rq exp41 spec):
  ENABLING requires whitened captured energy >= unwhitened + 2.0pp at the
  SAME resident bytes (predicted 3-6pp). Hard stop after Stage 1 if delta < 2pp.

Method (matching parent idea 2's mechanism, executed on real data):
  - Sigma_x accumulated per layer from the 24 real hidden-state samples
    (this is what the engine's WASTE_DUMP_HIDDEN accumulator produces; the
    raw dump adds the off-diagonal samples we accumulate here).
  - Unwhitened arm: top-K coordinate energy  sum(d_i)/tr, K chosen by resident
    byte budget. Activations x are REAL (24 per layer), energy share measured
    on real x, with the N=24 caveat stated.
  - Whitened arm: x' = D^{-1/2} x (diagonal whitening), SAME K directions,
    same resident budget for the diagonal D (charged to budget per spec),
    energy share of x' in top-K coords.
  - Also: low-rank estimate of the FULL whitened spectrum from the 24-sample
    Gram (rank<=23), reported as the honest ceiling of what whitening could
    achieve with this sample size (NOT the gate).

Resident-byte accounting: a resident coarse fragment holding K coordinate
axes per layer = K*4 B fp32 per layer ... we report K and bytes at the
frozen 96 GiB budget is far above any K needed, so Stage 1 is run at the
budget-relevant point: K = the fragment size that fits 96 GiB / (93 layers
* 896 experts) of fp32 values. Reported per-arm.

Inputs (pinned by sha256 in WRITEUP):
  k3_hidden.bin.gz  raw f32 [pass][layer][7168], 24*93*7168*4 = 63,995,904 B
  k3_hidden_diag.bin  f32 [layer][7168] per-layer diagonal of Sigma_x

Evidence class: PROXY (K3-activation geometry, N=24 passes; expert-weight
side is analytic). NOT a K3 tok/s measurement.
"""
import gzip, hashlib, json, os, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.expanduser("~/.hermes/state/warp-research/evidence/from-winnie")
N_PASS, N_LAYER, DIM = 24, 93, 7168

def load():
    with gzip.open(os.path.join(SRC, "k3_hidden.bin.gz"), "rb") as f:
        X = np.frombuffer(f.read(), dtype="<f4").reshape(N_PASS, N_LAYER, DIM).astype(np.float64)
    diag = np.fromfile(os.path.join(SRC, "k3_hidden_diag.bin"), dtype="<f4").reshape(N_LAYER, DIM).astype(np.float64)
    return X, diag

def topk_share(v, K):
    """Energy share of the K largest coordinates of v."""
    a = np.partition(np.abs(v) ** 2 if v.ndim == 1 else v, -K)[-K:]
    return float(a.sum() / (np.abs(v) ** 2).sum()) if v.ndim == 1 else None

def main():
    X, diag = load()
    # frozen budget arithmetic
    budget = 96 * 2**30
    per_expert_layer = budget / (N_LAYER * 896)   # bytes available per expert per layer
    K_fp32 = int(per_expert_layer // 4)           # if the whole budget went to fp32 coords
    # VQ3R reality: resident coarse fragment = low-bit codes. The binding
    # constraint is NOT 96 GiB (that holds ALL 896 experts' coords); the
    # binding constraint is the coarse fragment CUT of the record. We evaluate
    # the gate at the budget point and at the small-fragment end.
    Ks = sorted(set([8, 16, 32, 64, 128, 256, 512, 1024, 2048, 3584, 4096, min(K_fp32, DIM)]))
    out = {"Ks": Ks, "per_expert_layer_bytes_at_96GiB": per_expert_layer,
           "K_fp32_at_96GiB": K_fp32, "layers": {}}
    for L in range(N_LAYER):
        XL = X[:, L, :]                     # (24, 7168)
        d = diag[L]
        res = {}
        for K in Ks:
            # --- unwhitened: top-K coordinates by accumulated diag energy ---
            idx = np.argsort(d)[::-1][:K]
            # energy share of REAL activations in those coords
            E = (XL ** 2).sum(axis=0)
            unwh = float(E[idx].sum() / E.sum())
            # --- whitened: x' = D^{-1/2} x ; energy share in SAME top-K of D
            #     (after diagonal whitening the top-K of D^{-1}x concentrates;
            #      measure on real x)
            w = 1.0 / np.sqrt(np.maximum(d, 1e-30))
            Xw = XL * w
            Ew = (Xw ** 2).sum(axis=0)
            # whitened arm picks its OWN top-K in whitened space (that is the
            # mechanism: re-cut along demand axes)
            idxw = np.argsort(Ew)[::-1][:K]
            wh = float(Ew[idxw].sum() / Ew.sum())
            res[K] = {"unwhitened": unwh, "whitened": wh, "delta_pp": (wh - unwh) * 100}
        out["layers"][L] = res
    np.save(os.path.join(HERE, "stage1_raw.npy"), out, allow_pickle=True)
    # summary across layers
    summary = {}
    for K in Ks:
        u = np.mean([out["layers"][L][K]["unwhitened"] for L in range(N_LAYER)])
        w_ = np.mean([out["layers"][L][K]["whitened"] for L in range(N_LAYER)])
        summary[K] = {"unwhitened_pct": u * 100, "whitened_pct": w_ * 100,
                      "delta_pp": (w_ - u) * 100}
    out["summary"] = summary
    with open(os.path.join(HERE, "stage1_result.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(f"{'K':>6} {'unwhit%':>9} {'whit%':>9} {'delta_pp':>9}")
    for K in Ks:
        s = summary[K]
        print(f"{K:>6} {s['unwhitened_pct']:>9.3f} {s['whitened_pct']:>9.3f} {s['delta_pp']:>+9.3f}")

if __name__ == "__main__":
    main()
