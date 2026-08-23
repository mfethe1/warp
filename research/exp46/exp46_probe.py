#!/usr/bin/env python3
"""exp46 STAGE 0 feasibility probe -- can UNMODIFIED pinned vq.c express a
non-uniform allocation like (10,8,6)?

Structural facts from reading vq.c @ 7f1fbba3 (sha256 eb797e7c...):
  - waste_vq_encode writes (uint8_t)vq_step(...)  -> code ids >255 are truncated
  - waste_vq_lloyd stores assignments in uint8_t asg[n] -> ids >255 wrap and
    corrupt centroid recomputation
  - `entries` is ONE int for ALL stages -> non-uniform per-stage sizes are not
    expressible in a single call; per-stage calls still hit the uint8 walls.

Empirical test: fit a 512-entry codebook (the smallest >8-bit stage) with the
pinned encoder on synthetic data, encode, decode, and compare against exact
numpy argmin over the SAME codebook. If the pinned API could exploit >256
entries, its codes would match numpy argmin (ids in [0,512)). Expectation:
max(code) <= 255 and distortion ~= that of a 256-entry book, i.e. the API
cannot use the extra entries at all.
"""
import ctypes, hashlib, json
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

DIM, NTH = 8, 8
fp = lambda a: a.ctypes.data_as(ctypes.POINTER(ctypes.c_float))
up = lambda a: a.ctypes.data_as(ctypes.POINTER(ctypes.c_ubyte))

def rel_err(X, Xh):
    return float(np.sqrt(np.sum((X - Xh) ** 2) / np.sum(X ** 2)))

rng = np.random.default_rng(46)
n = 32768
# same shape family as exp34 stage 2 (normalized rows -> unit-ish scale)
X = np.ascontiguousarray(rng.standard_normal((n, DIM), dtype=np.float32) * 0.1)

results = {}
for entries in (256, 512, 1024):
    # codebook init: random distinct rows (convert.py protocol)
    C = np.ascontiguousarray(X[rng.choice(n, entries, replace=False)].copy())
    live = LIB.waste_vq_lloyd(fp(X), n, fp(C), entries, DIM, NTH)
    # encode with pinned encoder
    codes = np.zeros(n, dtype=np.uint8)
    LIB.waste_vq_encode(fp(X), n, fp(C), 1, entries, DIM, up(codes), NTH)
    # decode via shim
    out = np.zeros(n * DIM, dtype=np.float32)
    LIB.exp34_decode(up(codes), fp(C), n, 1, entries, DIM, fp(out))
    Xh_vq = out.reshape(n, DIM)
    # exact numpy argmin over the SAME codebook
    d2 = ((X[:, None, :] - C[None, :, :]) ** 2).sum(-1)
    exact_ids = d2.argmin(1)
    Xh_np = C[exact_ids]
    agree = float((exact_ids.astype(np.int64) == codes.astype(np.int64)).mean())
    results[f"entries_{entries}"] = dict(
        lloyd_live_clusters=int(live),
        vqc_code_max=int(codes.max()),
        vqc_rel_err=rel_err(X, Xh_vq),
        numpy_exact_rel_err=rel_err(X, Xh_np),
        numpy_exact_id_max=int(exact_ids.max()),
        id_agreement_pct=agree * 100.0,
        truncated=bool(exact_ids.max() > 255))

summary = dict(
    experiment="exp46", stage=0, label="RECOMPUTATION",
    purpose="feasibility of non-uniform stage allocation under UNMODIFIED pinned vq.c",
    source_sha="7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b",
    vq_c_sha256=hashlib.sha256(open("/tmp/exp34/vq.c","rb").read()).hexdigest(),
    shim="/tmp/exp34/libexp34.dylib (exp34 build, vq.c+threads.h byte-identical to pinned SHA)",
    N_vectors=n, dim=DIM, seed=46,
    structural_facts=[
        "waste_vq_encode stores (uint8_t)vq_step(...) -> ids >255 truncated at store",
        "waste_vq_lloyd stores assignments in uint8_t asg[n] -> ids >255 wrap, corrupting centroids",
        "single `entries` int for all stages -> per-stage sizes not expressible in one call",
        "record format: 3 index bytes/vector, per-stage byte-aligned -> only (8,8,8) is byte-aligned at 24 bits",
    ],
    results=results)
json.dump(summary, open("/tmp/exp46/exp46_out.json", "w"), indent=2)
print(json.dumps(summary, indent=2))
