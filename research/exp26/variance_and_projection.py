#!/usr/bin/env python3
"""exp26 part 2: per-cell variance at C=32 + K3-shape uniform projection."""
import json, math

TRACE = "/Users/mfethe/e3-policy/trace_kimi_300.jsonl"
RECORD_BYTES = 12_406_784
GiB = 1024**3

toks = [json.loads(l)["layers"] for l in open(TRACE) if l.strip()]
N, L, K = len(toks), len(toks[0]), len(toks[0][0])

# per-(chunk,layer) distinct counts at C=32
C = 32
cells = []
for c0 in range(0, N, C):
    chunk = toks[c0:c0 + C]
    for li in range(L):
        cells.append(len(set().union(*[t[li] for t in chunk])))
m = sum(cells) / len(cells)
var = sum((x - m) ** 2 for x in cells) / len(cells)
sd = math.sqrt(var)
print(f"[PROXY] C=32 per-(chunk,layer) distinct experts: "
      f"mean={m:.2f} sd={sd:.2f} min={min(cells)} max={max(cells)} "
      f"ncells={len(cells)}")
print(f"        uniform-routing expectation for this shape "
      f"(E=256,k=8,C=32): {256*(1-(1-8/256)**C):.1f}  -> measured/uniform "
      f"= {m/(256*(1-(1-8/256)**C)):.3f} (locality factor)")

# K3 shape, uniform routing bound (SYNTHETIC, analytic)
for Ck in (8, 16, 32, 64):
    E, k = 896, 16
    exp_dist = E * (1 - (1 - k / E) ** Ck)
    dedup = (Ck * k) / exp_dist
    print(f"[SYNTHETIC-uniform] K3 (E=896,k=16) C={Ck:2d}: expected distinct "
          f"{exp_dist:6.1f} / {Ck*k} accesses -> dedup {dedup:.3f}x")
print()
print("If K3 locality factor matches the trace (~0.49x of uniform distinct),")
print("projected K3 dedup at C=32 ~ ", end="")
loc = m / (256 * (1 - (1 - 8 / 256) ** 32))
E, k, Ck = 896, 16, 32
uni = E * (1 - (1 - k / E) ** Ck)
proj = (Ck * k) / (uni * loc)
print(f"{proj:.2f}x [SYNTHETIC projection - MUST be re-measured on real K3 trace]")
print(f"Colibri measured on real K3 text at C=32: 2.7x [REAL-K3, their claim, sha 33e67a9]")
