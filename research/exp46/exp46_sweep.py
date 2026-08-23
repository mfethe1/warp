#!/usr/bin/env python3
"""exp46 SUPPLEMENTARY -- numpy-only sweep of the preregistered allocations.

NOT the preregistered protocol (spec demands UNMODIFIED pinned vq.c, which
cannot express >8-bit stages -- see exp46_probe). This sweep exists only to
inform the requeue decision: does successive-refinement allocation show ANY
signal on synthetic data? Everything here is SYNTHETIC / PROXY-labeled.

Allocations (entries per stage, constant 24 bits/vector):
  (8,8,8) baseline, (10,8,6), (12,8,4), (6,8,10), (4,8,12)
Metric: activation-weighted relative error, identical generator/covariance
family to exp34 stage 2 (reduced rows for numpy k-means cost, declared).
"""
import json
import numpy as np

ROWS, COLS, DIM, SEEDS = 128, 3072, 8, [1, 2, 3, 4, 5]
ITERS = 8
ALLOC = {
    "uniform_888": (256, 256, 256),
    "front_10_8_6": (1024, 256, 64),
    "front_12_8_4": (4096, 256, 16),
    "back_6_8_10": (64, 256, 1024),
    "back_4_8_12": (16, 256, 4096),
}

def chunked_argmin_assign(R, C, chunk=4096):
    """Return (ids, Xhat) via exact chunked nearest-centroid."""
    n = R.shape[0]
    ids = np.empty(n, dtype=np.int64)
    for i in range(0, n, chunk):
        blk = R[i:i + chunk]                       # [b, 8]
        d2 = ((blk[:, None, :] - C[None, :, :]) ** 2).sum(-1)
        ids[i:i + chunk] = d2.argmin(1)
    return ids, C[ids]

def fit_stage(R, entries, rng):
    """Lloyd k-means with sample init, ITERS iterations (numpy reimplementation
    of the same algorithm family as vq.c waste_vq_lloyd)."""
    n = R.shape[0]
    C = R[rng.choice(n, min(entries, n), replace=False)].copy()
    for _ in range(ITERS):
        ids, _ = chunked_argmin_assign(R, C)
        for c in range(entries):
            m = ids == c
            if m.any():
                C[c] = R[m].mean(0)
    return C

def make_weights(rows, cols, rng):
    rank = 32
    U = rng.standard_normal((rows, rank), dtype=np.float32)
    V = rng.standard_normal((rank, cols), dtype=np.float32)
    W = (U @ V) / np.sqrt(rank) * 0.6 + rng.standard_normal((rows, cols), dtype=np.float32) * 0.8
    chan = np.exp(rng.normal(0.0, 0.5, cols)).astype(np.float32)
    return (W * chan).astype(np.float32)

def run_seed(seed):
    rng = np.random.default_rng(seed)
    W = make_weights(ROWS, COLS, rng)
    a = np.exp(rng.normal(0.0, 1.0, COLS)).astype(np.float32)
    a /= a.mean()
    sa = np.sqrt(a).astype(np.float32)
    rs = np.abs(W).max(axis=1, keepdims=True).astype(np.float16).astype(np.float32)
    rs[rs == 0] = 1.0
    X = np.ascontiguousarray((W / rs).reshape(-1, DIM))
    out = {}
    for name, ent in ALLOC.items():
        rng_s = np.random.default_rng(seed)  # same init stream per allocation
        R = X.copy()
        rec = np.zeros_like(X)
        for s, e in enumerate(ent):
            C = fit_stage(R, e, rng_s)
            ids, xh = chunked_argmin_assign(R, C)
            rec += xh
            R = R - xh
        Wh = (rec.reshape(ROWS, COLS) * rs).astype(np.float32)
        E = W - Wh
        aw = float(np.sqrt(np.sum((E * sa) ** 2) / np.sum((W * sa) ** 2)))
        out[name] = aw
    base = out["uniform_888"]
    return {k: dict(aw=v, degradation_pct=(v - base) / base * 100.0)
            for k, v in out.items()}

if __name__ == "__main__":
    runs = [run_seed(s) for s in SEEDS]
    summary = dict(experiment="exp46", stage="supplementary", label="SYNTHETIC",
        note="numpy reimplementation (NOT pinned vq.c -- it cannot express >8-bit stages). "
             "Informs requeue decision only; not a gate evaluation.",
        rows=ROWS, cols=COLS, iters=ITERS, seeds=SEEDS, allocations=ALLOC,
        runs=runs)
    for name in ALLOC:
        d = np.array([r[name]["degradation_pct"] for r in runs])
        aw = np.array([r[name]["aw"] for r in runs])
        summary[name] = dict(aw_mean=float(aw.mean()), aw_sd=float(aw.std(ddof=1)),
            degradation_pct_mean=float(d.mean()), degradation_pct_sd=float(d.std(ddof=1)))
    json.dump(summary, open("/tmp/exp46/exp46_sweep.json", "w"), indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=2))
