#!/usr/bin/env python3
"""exp11: miss-conditioned exactness shadow price.

Question: published demand-side projections use s = P(skip) over ALL activations.
The byte that matters is only removed if the skipped activation would have MISSED.
So the operative rate is s_eff = P(skip AND miss)/P(miss). Report r = s_eff/s.

Inputs (pinned):
  tests/trace_kimi_300.jsonl  sha256 06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965
    300 tok x 26 layers x top-8 = 62,400 accesses, 5,083 distinct  [PROXY, Kimi-Linear-shaped, NOT K3]
  docs/gn100/sprint11-route-margin-summary.json  sha256 1cfd9927fce60aea5ec220405923641821537431e8e3ab599837f2300d772295
    REAL-K3 routing margins, 92 layers, 6,348 rows -- PERCENTILES ONLY, no per-(layer,expert) rows.

All numbers labeled in the output.
"""
import json, random, hashlib
from collections import OrderedDict, Counter

ROOT = '/tmp/spark/warp/'
TRACE = ROOT + 'tests/trace_kimi_300.jsonl'
MARGIN = ROOT + 'docs/gn100/sprint11-route-margin-summary.json'

def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

T = [json.loads(l) for l in open(TRACE)]
acc = []
for r in T:
    for li, lay in enumerate(r['layers']):
        for e in lay:
            acc.append((li, e))
N = len(acc)
D = len(set(acc))
L = len(T[0]['layers'])
K = len(T[0]['layers'][0])
WS = L * K
CAP = 709                      # K3-equivalent 3.41x working set, per preregistration

def lru_missmask(cap):
    od = OrderedDict(); mask = []
    for k in acc:
        if k in od:
            od.move_to_end(k); mask.append(0)
        else:
            mask.append(1)
            if len(od) >= cap: od.popitem(last=False)
            od[k] = 1
    return mask

miss = lru_missmask(CAP)
M = sum(miss)
m_frac = M / N
h_frac = 1 - m_frac

print("=== exp11 miss-conditioned exactness shadow price ===")
print(f"trace  sha256 {sha(TRACE)}")
print(f"margin sha256 {sha(MARGIN)}")
print(f"[PROXY] {len(T)} tok x {L} lay x top-{K}: N={N} accesses, {D} distinct, per-token WS={WS}")
print(f"[PROXY] LRU cap={CAP} ({CAP/WS:.2f}x WS): misses={M}  miss_frac={m_frac:.6f}  hit_frac={h_frac:.6f}")
print()

# ---------- margin availability audit ----------
mj = json.load(open(MARGIN))
per_layer_rows = sum(x['rows'] for x in mj['per_layer'])
print("=== margin-source audit (REAL-K3, sprint11) ===")
print(f"  layers={mj['layers']}  per_layer rows total={per_layer_rows}  exact_boundary_ties={mj['exact_boundary_ties']}")
print(f"  margin p1={mj['margin']['p1']:.3e} p50={mj['margin']['p50']:.3e} p99={mj['margin']['p99']:.3e}")
print("  CONTENT: percentiles/aggregates ONLY. No per-(layer,expert) or per-access margin rows.")
print("  => sprint11 can supply a MARGINAL DISTRIBUTION but NOT a COUPLING to expert identity.")
print("  => any per-access assignment fixes the (skip,miss) dependence structure BY ASSUMPTION.")
print()

# ---------- Arm A: marginal-matched i.i.d. assignment (the only defensible use of sprint11) ----------
# Reconstruct a margin sampler from the published percentiles by log-linear interpolation.
pts = [(0.001, mj['margin']['p0_1']), (0.01, mj['margin']['p1']), (0.05, mj['margin']['p5']),
       (0.50, mj['margin']['p50']), (0.95, mj['margin']['p95']), (0.99, mj['margin']['p99']),
       (1.0, mj['margin']['max'])]
import math
def sample_margin(u):
    if u <= pts[0][0]: return mj['margin']['min']
    for i in range(1, len(pts)):
        if u <= pts[i][0]:
            (q0, v0), (q1, v1) = pts[i-1], pts[i]
            f = (u - q0) / (q1 - q0)
            return math.exp(math.log(v0) + f * (math.log(v1) - math.log(v0)))
    return mj['margin']['max']

random.seed(11)
REPS = 5
sweep = [0.05,0.10,0.20,0.30,0.40,0.50,0.60,0.70,0.80,0.90,0.95,0.977,0.99]
arm_a = {s: [] for s in sweep}
for rep in range(REPS):
    marg = [sample_margin(random.random()) for _ in range(N)]
    order = sorted(range(N), key=lambda i: marg[i])   # skip lowest-margin first
    for s in sweep:
        nskip = int(round(s * N))
        sk = order[:nskip]
        both = sum(miss[i] for i in sk)
        arm_a[s].append((both / M) / s if s > 0 else float('nan'))

# ---------- Arm B: Frechet-Hoeffding admissible range (assumption-free) ----------
def fh(s):
    lo = max(0.0, (s - h_frac) / m_frac)
    hi = min(1.0, s / m_frac)
    return lo, hi

# ---------- Arm C: identity-coupled sensitivity, measured on the real trace ----------
# Plausible mechanism: margin correlates with expert popularity. Skip by popularity rank.
freq = Counter(acc)
pop = [freq[k] for k in acc]
ord_unpop = sorted(range(N), key=lambda i: (pop[i], i))          # skip rarest experts first
ord_pop   = sorted(range(N), key=lambda i: (-pop[i], i))         # skip most popular first
def arm_c(order, s):
    nskip = int(round(s * N))
    both = sum(miss[i] for i in order[:nskip])
    return (both / M) / s

print("=== r = s_eff/s  sweep ===")
print(f"{'s':>7} | {'A iid r':>9} {'sd':>7} | {'FH r_lo':>8} {'FH r_hi':>8} | {'C rare':>8} {'C pop':>8} | "
      f"{'naive GiB':>10} {'phys@A':>9} {'phys@Clo':>9}")
LOGICAL, PHYS = 17.0085, 7.719
rows = []
for s in sweep:
    a = sum(arm_a[s]) / REPS
    sd = (sum((x - a) ** 2 for x in arm_a[s]) / (REPS - 1)) ** 0.5
    lo, hi = fh(s)
    cr, cp = arm_c(ord_unpop, s), arm_c(ord_pop, s)
    r_lo, r_hi = lo / s, hi / s
    naive = LOGICAL * (1 - s)
    p_a = PHYS * (1 - a * s)
    p_c = PHYS * (1 - min(cr, cp) * s)
    print(f"{s:7.3f} | {a:9.4f} {sd:7.4f} | {r_lo:8.4f} {r_hi:8.4f} | {cr:8.4f} {cp:8.4f} | "
          f"{naive:10.4f} {p_a:9.4f} {p_c:9.4f}")
    rows.append(dict(s=s, r_iid=a, r_iid_sd=sd, r_fh_lo=r_lo, r_fh_hi=r_hi,
                     r_pop_rare=cr, r_pop_common=cp,
                     naive_logical_GiB=naive, phys_iid_GiB=p_a, phys_worst_coupling_GiB=p_c))
print()
print("=== gate evaluation (preregistered, not moved) ===")
band = [r for r in rows if 0.30 <= r['s'] <= 0.99]
print(f"ACCEPT: r < 0.90 anywhere in s in [0.30,0.99]")
print(f"  Arm A (iid, marginal-matched): min r = {min(r['r_iid'] for r in band):.4f}")
print(f"  Arm C (popularity coupling)  : min r = {min(min(r['r_pop_rare'], r['r_pop_common']) for r in band):.4f}")
print(f"REJECT: 0.95 <= r <= 1.05 across the whole sweep")
print(f"  Arm A range over full sweep = [{min(r['r_iid'] for r in rows):.4f}, {max(r['r_iid'] for r in rows):.4f}]")
print()
print("=== exp8 s>=50% HARD STOP, restated ===")
lo, hi = fh(0.50)
print(f"  at s=0.50: s_eff admissible in [{lo:.4f}, {hi:.4f}]  -> physical bytes/token in "
      f"[{PHYS*(1-hi):.4f}, {PHYS*(1-lo):.4f}] GiB")
print(f"  hit_frac={h_frac:.4f}: any s <= {h_frac:.4f} CAN remove zero physical bytes.")
need = 1 - 0.3946 / PHYS
print(f"  15 tok/s needs 0.3946 GiB/token -> s_eff >= {need:.6f} (miss-conditioned), "
      f"vs naive s >= {1-0.3946/LOGICAL:.6f} on logical demand")

out = dict(trace_sha=sha(TRACE), margin_sha=sha(MARGIN), N=N, distinct=D, cap=CAP,
           misses=M, miss_frac=m_frac, hit_frac=h_frac, reps=REPS, rows=rows,
           required_s_eff_for_15tps=need)
with open('/tmp/exp11_result.json', 'w') as f:
    json.dump(out, f, indent=2)
print("\nwrote /tmp/exp11_result.json")
