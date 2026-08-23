#!/usr/bin/env python3
"""exp34 STAGE 2 -- activation-weighted distortion, VQ3R vs VQ4P at equal 3.00 b/w.

Uses WARP's OWN src/vq.c encoder (waste_vq_lloyd + waste_vq_encode) at pinned SHA
7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b, compiled unmodified. Only a decode shim
was added (algebraic inverse of residual VQ: sum of chosen stage vectors).

NO K3 WEIGHTS AVAILABLE ON THIS MACHINE -> weights are SYNTHETIC with LLM-like
structure (heavy-tailed per-input-channel scale + low-rank correlated component),
and the activation covariance is SYNTHETIC (log-normal per-channel second moment,
the standard AWQ/GPTQ salient-channel shape). Label accordingly: SYNTHETIC.

Decision metric is ACTIVATION-WEIGHTED relative error, NOT Frobenius
(established mismatch #4). Frobenius is reported only as a diagnostic.
"""
import ctypes, hashlib, json, sys, time
import numpy as np

LIB = ctypes.CDLL("/tmp/exp34/libexp34.dylib")
LIB.waste_vq_encode.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_int,
    ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(ctypes.c_ubyte), ctypes.c_int]
LIB.waste_vq_lloyd.argtypes = [ctypes.POINTER(ctypes.c_float), ctypes.c_int,
    ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int, ctypes.c_int]
LIB.waste_vq_lloyd.restype = ctypes.c_int
LIB.exp34_decode.argtypes = [ctypes.POINTER(ctypes.c_ubyte),
    ctypes.POINTER(ctypes.c_float), ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.POINTER(ctypes.c_float)]

DIM, NTH, LLOYD_ITERS = 8, 8, 12
fp = lambda a: a.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
up = lambda a: a.ctypes.data_as(ctypes.POINTER(ctypes.c_ubyte))

def fit_residual_vq(X, stages, entries, seed):
    """Stage-wise residual VQ fit with WARP's own Lloyd. Returns books, codes."""
    rng = np.random.default_rng(seed)
    n = X.shape[0]
    books = np.zeros((stages, entries, DIM), dtype=np.float32)
    R = np.ascontiguousarray(X.copy())
    for s in range(stages):
        # k-means++-free init: random distinct sample rows (what convert.py does)
        C = np.ascontiguousarray(R[rng.choice(n, entries, replace=False)].copy())
        for _ in range(LLOYD_ITERS):
            if LIB.waste_vq_lloyd(fp(R), n, fp(C), entries, DIM, NTH) < 0:
                raise RuntimeError("lloyd failed")
        books[s] = C
        codes_s = np.zeros(n, dtype=np.uint8)
        LIB.waste_vq_encode(fp(R), n, fp(C), 1, entries, DIM, up(codes_s), NTH)
        R = np.ascontiguousarray(R - C[codes_s])
    codes = np.zeros(n * stages, dtype=np.uint8)
    bflat = np.ascontiguousarray(books.reshape(-1))
    LIB.waste_vq_encode(fp(X), n, fp(bflat), stages, entries, DIM, up(codes), NTH)
    return bflat, codes

def decode(codes, bflat, n, stages, entries):
    out = np.zeros(n * DIM, dtype=np.float32)
    LIB.exp34_decode(up(codes), fp(bflat), n, stages, entries, DIM, fp(out))
    return out.reshape(n, DIM)

def make_weights(rows, cols, rng):
    """LLM-expert-like: low-rank correlated part + iid part, heavy-tailed channel scale."""
    rank = 32
    U = rng.standard_normal((rows, rank), dtype=np.float32)
    V = rng.standard_normal((rank, cols), dtype=np.float32)
    W = (U @ V) / np.sqrt(rank) * 0.6 + rng.standard_normal((rows, cols), dtype=np.float32) * 0.8
    chan = np.exp(rng.normal(0.0, 0.5, cols)).astype(np.float32)   # per-input-channel scale
    return (W * chan).astype(np.float32)

def run_seed(seed, rows, cols):
    rng = np.random.default_rng(seed)
    W = make_weights(rows, cols, rng)
    # SYNTHETIC activation second moment per input channel (AWQ salient-channel shape)
    a = np.exp(rng.normal(0.0, 1.0, cols)).astype(np.float32)
    a /= a.mean()
    sa = np.sqrt(a).astype(np.float32)

    # WARP normalizes per output row by an f16 scale before VQ (one scale/row).
    rs = np.abs(W).max(axis=1, keepdims=True).astype(np.float16).astype(np.float32)
    rs[rs == 0] = 1.0
    Wn = W / rs

    X = np.ascontiguousarray(Wn.reshape(-1, DIM))
    n = X.shape[0]
    res = {}
    for name, stages, entries in (("VQ3R", 3, 256), ("VQ4P", 4, 64)):
        t0 = time.time()
        bflat, codes = fit_residual_vq(X, stages, entries, seed)
        Xh = decode(codes, bflat, n, stages, entries)
        Wh = (Xh.reshape(rows, cols) * rs).astype(np.float32)
        E = (W - Wh)
        aw_num = float(np.sum((E * sa) ** 2)); aw_den = float(np.sum((W * sa) ** 2))
        fr_num = float(np.sum(E ** 2));        fr_den = float(np.sum(W ** 2))
        res[name] = dict(
            stages=stages, entries=entries, bits_per_weight=stages*(8 if entries==256 else 6)/DIM,
            act_weighted_rel_err=float(np.sqrt(aw_num/aw_den)),
            frobenius_rel_err_DIAGNOSTIC_ONLY=float(np.sqrt(fr_num/fr_den)),
            fit_seconds=round(time.time()-t0, 1))
    v3, v4 = res["VQ3R"]["act_weighted_rel_err"], res["VQ4P"]["act_weighted_rel_err"]
    res["vq4p_relative_degradation_pct"] = (v4 - v3) / v3 * 100.0
    res["seed"] = seed; res["vectors"] = n; res["shape"] = [rows, cols]
    return res

if __name__ == "__main__":
    rows, cols, seeds = 512, 3072, [1, 2, 3, 4, 5]
    runs = []
    for s in seeds:
        r = run_seed(s, rows, cols)
        print(f"seed {s}: VQ3R aw={r['VQ3R']['act_weighted_rel_err']:.6f}  "
              f"VQ4P aw={r['VQ4P']['act_weighted_rel_err']:.6f}  "
              f"deg={r['vq4p_relative_degradation_pct']:+.3f}%", flush=True)
        runs.append(r)
    d = np.array([r["vq4p_relative_degradation_pct"] for r in runs])
    a3 = np.array([r["VQ3R"]["act_weighted_rel_err"] for r in runs])
    a4 = np.array([r["VQ4P"]["act_weighted_rel_err"] for r in runs])
    summary = dict(experiment="exp34", stage=2, label="SYNTHETIC",
        note="synthetic weights + synthetic activation covariance; encoder is WARP's own vq.c at pinned SHA",
        source_sha="7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b",
        vq_c_sha256=hashlib.sha256(open("/tmp/exp34/vq.c","rb").read()).hexdigest(),
        N=len(seeds), lloyd_iters=LLOYD_ITERS,
        vq3r_aw_mean=float(a3.mean()), vq3r_aw_sd=float(a3.std(ddof=1)),
        vq4p_aw_mean=float(a4.mean()), vq4p_aw_sd=float(a4.std(ddof=1)),
        degradation_pct_mean=float(d.mean()), degradation_pct_sd=float(d.std(ddof=1)),
        degradation_pct_min=float(d.min()), degradation_pct_max=float(d.max()),
        accept_gate_within_5pct=bool(d.mean() <= 5.0),
        reject_gate_worse_than_15pct=bool(d.mean() > 15.0),
        runs=runs)
    json.dump(summary, open("/tmp/exp34/stage2_out.json","w"), indent=2)
    print(json.dumps({k: v for k, v in summary.items() if k != "runs"}, indent=2))
