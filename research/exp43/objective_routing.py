#!/usr/bin/env python3
"""exp43: route exp26's 66.06% prefill byte reduction to the objectives it provably moves.

RECOMPUTATION ONLY over frozen inputs (zero hardware):
  - exp26 artifacts (sweep.out: dedup ladder; variance.out: per-cell distinct stats)
  - exp30 B_eff(miss-rate) published ladder (exp30_fixed_point.json / WRITEUP.md)
  - exp40 miss mass (18,786/62,400 = 30.106% LRU misses at cap=1490)
  - trace: tests/trace_kimi_300.jsonl (300 tok x 26L x top-8, Kimi-Linear-shaped PROXY)

Evidence classes: every number labeled PROXY (trace-based), RECOMPUTATION
(arithmetic over frozen measured inputs), or SYNTHETIC (exp30's binomial
miss-multiplicity model). NO REAL-K3 MEASUREMENT ANYWHERE.

Deliverables per preregistered spec:
  (1) TTFT ms saved per 300-tok prefill at dup-4x B_eff for each published B_eff point.
  (2) Measurement-loop multiplier (exp/hr) from upstream's 48s-of-50s load+prefill fraction.
  (3) Residency side-effect on decode E[k]: LRU at cap=1490, dedup-altered warm state.
  (4) Explicit statement: 66.06% is NOT credited toward the 19.562x decode gap.
"""
import json, hashlib, collections

TRACE = "/Users/mfethe/warp-exp43/tests/trace_kimi_300.jsonl"
RECORD_BYTES = 12_406_784          # exp26/verified: exactly 3029 pages
GiB = 1024**3
B_DEV = 5.919301308397259          # GiB/s single 990 Pro [MEASURED, exp30 input]

toks = []
with open(TRACE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if "layers" in d:
            toks.append(d["layers"])
N, L, K = len(toks), len(toks[0]), len(toks[0][0])
assert (N, L, K) == (300, 26, 8), (N, L, K)
raw_accesses = N * L * K           # 62,400

def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()

print(f"# inputs: trace sha256={sha(TRACE)} N={N} L={L} top-{K} raw={raw_accesses}")

# ---------------------------------------------------------------- dedup ladder
def dedup_reads(C):
    reads = 0
    cells = []  # per (chunk,layer) distinct count, for prefill-concurrency B_eff
    for c0 in range(0, N, C):
        chunk = toks[c0:c0 + C]
        for li in range(L):
            s = set()
            for t in chunk:
                s.update(t[li])
            reads += len(s)
            cells.append(len(s))
    return reads, cells

reads = {}
cells = {}
for C in (1, 32):
    reads[C], cells[C] = dedup_reads(C)

phys = {C: reads[C] * RECORD_BYTES for C in reads}
bytes_prompt_C1  = phys[1]                    # naive prefill, whole 300-tok prompt
bytes_prompt_C32 = phys[32]                   # dedup prefill
saved = bytes_prompt_C1 - bytes_prompt_C32
print(f"\n## exp26 recomputation [RECOMPUTATION over trace=PROXY]")
print(f"C=1  records={reads[1]}  prompt bytes={bytes_prompt_C1/GiB:9.3f} GiB")
print(f"C=32 records={reads[32]} prompt bytes={bytes_prompt_C32/GiB:9.3f} GiB")
print(f"saved={saved/GiB:.3f} GiB = {100*(1-phys[32]/phys[1]):.2f}% (exp26 published 66.06%)")

# --------------------------------------------- (1) TTFT at published B_eff points
# exp30 WRITEUP published dup-4x ladder (bytes/tok GiB -> dup4 B_eff GiB/s):
ladder = [
    (7.7190, 668.0, 19.634),
    (3.6704, 317.7, 16.569),
    (1.7453, 151.0, 11.542),
    (0.8299,  71.8,  8.377),
    (0.3946,  34.2,  7.017),
]
print(f"\n## (1) TTFT saving per 300-tok prefill, dup-4x, at exp30's published B_eff points")
print(f"#    [SYNTHETIC bandwidth model (exp30) x PROXY byte counts (trace); NOT REAL-K3]")
print(f"#    NOTE: B_eff(miss) is a DECODE barrier model; prefill concurrency is high,")
print(f"#    so the ladder brackets the saving; the prefill-correct row is given last.")
for bt, misses, beff in ladder:
    ms = saved / (beff * GiB) * 1000.0
    print(f"  B_eff={beff:7.3f} GiB/s (bytes/tok {bt:.4f}, {misses:5.1f} misses/tok): "
          f"TTFT saved = {ms:9.1f} ms  ({ms/1000:6.2f} s)")

# prefill-correct B_eff: per-(chunk,layer) barrier over k=distinct experts, D=4
import math
kk = cells[32]
E_ceil = sum(math.ceil(k / 4) for k in kk) / len(kk)
E_k = sum(kk) / len(kk)
b_eff_prefill = B_DEV * E_k / E_ceil
ms_pref = saved / (b_eff_prefill * GiB) * 1000.0
print(f"  prefill-correct dup4 B_eff = {b_eff_prefill:.3f} GiB/s "
      f"(per-cell k: mean={E_k:.2f}, E[ceil(k/4)]={E_ceil:.2f}, ncells={len(kk)}) "
      f"[SYNTHETIC barrier model x PROXY cell stats]")
print(f"  -> TTFT saved = {ms_pref:.1f} ms ({ms_pref/1000:.2f} s) [PROXY]")

# ------------------------------------------- (2) measurement-loop exp/hr multiplier
# upstream (warp-spark) claim frozen in spec: a K3 measurement ~50 s, ~48 s load+prefill.
UP_TOTAL, UP_LOAD_PREFILL = 50.0, 48.0
print(f"\n## (2) measurement-loop multiplier (upstream {UP_TOTAL}s total, "
      f"{UP_LOAD_PREFILL}s load+prefill, bandwidth-bound)")
mult_proxy = UP_TOTAL / (UP_TOTAL - UP_LOAD_PREFILL + UP_LOAD_PREFILL * (phys[32] / phys[1]))
# REAL-K3 anchor: colibri measured 2.7x chunk dedup @ C=32 on real K3 text (their claim, sha 33e67a9)
mult_k3anchor = UP_TOTAL / (UP_TOTAL - UP_LOAD_PREFILL + UP_LOAD_PREFILL / 2.7)
print(f"  PROXY (trace 2.947x dedup):  48s -> {UP_LOAD_PREFILL*(phys[32]/phys[1]):.2f}s, "
      f"exp/hr x{mult_proxy:.3f}")
print(f"  REAL-K3-anchored (colibri 2.7x @C=32): 48s -> {UP_LOAD_PREFILL/2.7:.2f}s, "
      f"exp/hr x{mult_k3anchor:.3f}")

# --------------------------- (3) residency side-effect on decode E[k], LRU cap=1490
class LRU:
    def __init__(self, cap):
        self.cap = cap
        self.d = collections.OrderedDict()
        self.misses = 0
        self.accesses = 0
    def touch(self, key):
        self.accesses += 1
        if key in self.d:
            self.d.move_to_end(key)
        else:
            self.misses += 1
            if len(self.d) >= self.cap:
                self.d.popitem(last=False)
            self.d[key] = True

def warm_prefill(lru, upto, C):
    """Prefill tokens [0, upto) in layer-major chunked order; dedup drops repeats within (chunk,layer)."""
    for c0 in range(0, upto, C):
        chunk = toks[c0:c0 + C]
        for li in range(L):
            if C == 1:
                for e in chunk[0][li]:
                    lru.touch((li, e))
            else:
                s = set()
                for t in chunk:
                    s.update(t[li])
                for e in s:
                    lru.touch((li, e))

def decode_replay(lru, frm, to):
    """Returns DECODE-PHASE misses/accesses only (prefill warm phase excluded):
    both arms replay the identical access sequence here, so phase-only counts
    are directly comparable."""
    m0, a0 = lru.misses, lru.accesses
    for ti in range(frm, to):
        for li in range(L):
            for e in toks[ti][li]:
                lru.touch((li, e))
    return lru.misses - m0, lru.accesses - a0

CAP = 1490
print(f"\n## (3) residency side-effect on decode miss rate, LRU cap={CAP}, key=(layer,expert)")
print(f"#    warm=prefill tokens[0,split), decode=tokens[split,300) at C=1; deterministic N=1 per arm")
reject = False
for split in (150, 200, 250):
    lru_a = LRU(CAP); warm_prefill(lru_a, split, C=1)     # naive prefill warm state
    m_a, a_a = decode_replay(lru_a, split, N)
    lru_b = LRU(CAP); warm_prefill(lru_b, split, C=32)    # dedup-altered warm state
    m_b, a_b = decode_replay(lru_b, split, N)
    dpct = 100 * (m_b - m_a) / m_a
    tripped = abs(dpct) > 5.0
    reject |= tripped
    print(f"  split={split}: naive warm -> decode misses {m_a:5d}/{a_a} "
          f"({100*m_a/a_a:.3f}%) | dedup warm -> {m_b:5d}/{a_b} "
          f"({100*m_b/a_b:.3f}%) | dE[k] = {dpct:+.3f}%"
          f"{'  ** |dE[k]|>5% REJECT-GATE TRIP **' if tripped else ''}")
print(f"  (exp40 steady-state whole-trace reference: 18,786/62,400 = 30.106% at same cap)")

# --------------------------------------------------- (4) decode non-credit statement
print(f"""
## (4) DECODE NON-CREDIT STATEMENT [RECOMPUTATION]
exp26's 66.06% is a PREFILL-phase byte reduction. At batch-1 decode there is no
chunk to dedup within: C=1 dedup factor on this trace is exactly 1.000x (phys
2.4034 GiB/tok == raw logical demand), i.e. decode bytes/token is UNCHANGED by
the mechanism. Therefore 66.06% is NOT credited toward the 19.562x decode gap
(7.719 -> 0.3946 GiB/token at B_eff 5.919 GiB/s): credit toward that gap from
exp26 = 0.00x. The objectives it does move are TTFT (deliverable 1) and lab
measurement throughput (deliverable 2).""")

verdict_reject = reject
print(f"\n# REJECT GATE (preregistered): residency side-effect shifts decode E[k] by >5% -> "
      f"{'TRIPPED (requeue as decode lever)' if verdict_reject else 'not tripped'}")
