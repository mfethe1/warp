#!/usr/bin/env python3
"""
exp14 - FACTORIAL: miss-conditioned output reuse (idea19, arm A) x
        segmented scan-resistant admission (idea3, arm B).

Preregistered spec (verbatim constraints honored):
  A0 baseline : plain LRU cap 709, one pread per miss, no memory, no segmentation.
  A1 (A alone) : idea19 miss-conditioned suppression, r_reuse in {0.05,0.10,0.20,0.40},
                 plain LRU, no segmentation.
  A2 (B alone) : idea3 segmented protected/probationary admission, total capacity 709,
                 no memory reuse.
  A3 (A+B)     : both, memory bytes charged against resident budget (see note).
  gain(X) = metric(A0) - metric(X); interaction = gain(AB) - gain(A) - gain(B).
  Overlap falsifier FIRST: |Sup(A1) ∩ Conv(A2)| / min(|Sup|,|Conv|) > 0.70 => REJECT-dominated.
  Primary accounting S1 (insertion-neutral); S2 (no-insert-on-bypass) as sensitivity.
  Invariant: preads per non-suppressed miss == 1.000 in every arm.

PROXY trace: tests/trace_kimi_300.jsonl (Kimi-Linear-shaped 26L x top-8, NOT K3).
r_reuse is an ASSUMED parameter (swept), NOT a measurement -- no activation trace exists.
Deterministic suppression: per-(layer,expert) miss ordinal m; suppressed iff (m % 1000) < 1000*r.
SLRU split not preregistered -> swept over protected fraction {0.5,0.6,0.7,0.8};
gates evaluated at the most favorable split for B (conservative for REJECT, generous for ACCEPT;
both reported). A3 capacity: 709 slots total for SLRU; idea19 FIFO memory of
stored (key,output) pairs is a separate resident array of 6,144 B pairs -- charged as
slot-equivalents: each stored pair costs 6144/12406784 = 0.000495 slots, i.e. <=0.5% of
capacity even at unbounded FIFO length on this trace; we additionally cap the library at
4096 pairs (24.6 MiB) => 2.0 slot-equivalents, and reduce SLRU capacity accordingly in A3.
"""
import json, hashlib, os, sys
from collections import OrderedDict

TRACE = '/Users/mfethe/warp/tests/trace_kimi_300.jsonl'
RECORD = 12406784           # bytes per expert record (page-exact, 3029 pages, established)
PAIR_B = 6144               # one (key, output) fp16 memory pair (idea19)
GIB = float(1 << 30)
CAP = 709                   # preregistered: 3.41x WS, K3-equivalent
R_SWEEP = [0.05, 0.10, 0.20, 0.40]
SPLITS = [0.5, 0.6, 0.7, 0.8]   # protected fraction of 709
LIB_CAP = 4096              # pairs; 4096*6144 = 24.6 MiB memory library

raw = open(TRACE, 'rb').read()
TRACE_SHA = hashlib.sha256(raw).hexdigest()
T = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]
acc = []
for r in T:
    for li, lay in enumerate(r['layers']):
        for e in lay:
            acc.append((li, e))
N = len(acc)
NTOK = len(T)
DISTINCT = len(set(acc))

def permille(r):
    return int(round(r * 1000))

# ---------------- arm A0: plain LRU ----------------
def run_A0():
    od = OrderedDict(); miss = [False] * N; preads = 0
    for i, k in enumerate(acc):
        if k in od:
            od.move_to_end(k)
        else:
            miss[i] = True; preads += 1
            od[k] = 1
            if len(od) > CAP: od.popitem(last=False)
    return {'miss_idx': miss, 'misses': sum(miss), 'preads': preads}

import zlib
def _suppress(k, m, pm):
    """Deterministic hash-Bernoulli: access with miss ordinal m (m>=1, antibody
    possible since the m=0 encounter built it) is suppressed with prob r=pm/1000.
    Keyed on (expert, m-1); crc32 for cross-process reproducibility (built-in
    hash() is salted per process)."""
    return (zlib.crc32(f"{k}|{m-1}".encode()) % 1000) < pm

# ---------------- arm A1: LRU + miss-conditioned suppression ----------------
def run_A1(r, s1=True):
    pm = permille(r)
    od = OrderedDict()
    miss_ord = {}                 # per (l,e) miss ordinal
    lib = OrderedDict()           # (l,e) -> pair count (bounded FIFO library)
    sup = [False] * N; nonsup_misses = 0; preads = 0
    for i, k in enumerate(acc):
        if k in od:
            od.move_to_end(k); continue
        m = miss_ord.get(k, 0); miss_ord[k] = m + 1
        # m==0 is the FIRST encounter of this (layer,expert): no antibody can exist
        # (idea19: reuse restricted to strictly earlier decode positions).
        if m >= 1 and _suppress(k, m, pm):
            # antibody found: suppress the pread, emit stored output
            sup[i] = True
            lib[k] = 1; lib.move_to_end(k)
            if len(lib) > LIB_CAP: lib.popitem(last=False)
            if s1:                # S1: still insert/refresh
                od[k] = 1; od.move_to_end(k)
                if len(od) > CAP: od.popitem(last=False)
        else:
            nonsup_misses += 1; preads += 1
            od[k] = 1
            if len(od) > CAP: od.popitem(last=False)
    return {'sup_idx': sup, 'suppressed': sum(sup), 'nonsup_misses': nonsup_misses,
            'preads': preads, 'lib_pairs': len(lib)}

# ---------------- arm A2: SLRU segmented admission ----------------
def run_A2(prot_frac):
    prot_cap = int(round(CAP * prot_frac)); prob_cap = CAP - prot_cap
    prot = OrderedDict(); prob = OrderedDict()
    hit = [False] * N; misses = 0; preads = 0
    def insert_prob(k):
        prob[k] = 1
        if len(prob) > prob_cap:
            prob.popitem(last=False)
    for i, k in enumerate(acc):
        if k in prot:
            prot.move_to_end(k); hit[i] = True; continue
        if k in prob:
            prob.move_to_end(k)
            # demonstrated reuse -> promote to protected MRU
            prot[k] = 1
            if len(prot) > prot_cap:
                vk, _ = prot.popitem(last=False)   # demote protected LRU to probationary MRU
                insert_prob(vk)
            hit[i] = True; continue
        misses += 1; preads += 1
        insert_prob(k)
    return {'hit_idx': hit, 'misses': misses, 'preads': preads}

# ---------------- arm A3: SLRU + suppression ----------------
def run_A3(r, prot_frac, s1=True):
    pm = permille(r)
    # charge library against resident budget: LIB_CAP pairs * PAIR_B / RECORD slot-equivalents
    lib_slots = int(LIB_CAP * PAIR_B // RECORD) or 1
    cap = CAP - lib_slots
    prot_cap = int(round(cap * prot_frac)); prob_cap = cap - prot_cap
    prot = OrderedDict(); prob = OrderedDict()
    miss_ord = {}; lib = OrderedDict()
    sup = [False] * N; nonsup_misses = 0; preads = 0
    def insert_prob(k):
        prob[k] = 1
        if len(prob) > prob_cap: prob.popitem(last=False)
    for i, k in enumerate(acc):
        in_cache = False
        if k in prot:
            prot.move_to_end(k); in_cache = True
        elif k in prob:
            prob.move_to_end(k)
            prot[k] = 1
            if len(prot) > prot_cap:
                vk, _ = prot.popitem(last=False)
                insert_prob(vk)
            in_cache = True
        if in_cache: continue
        m = miss_ord.get(k, 0); miss_ord[k] = m + 1
        # m==0: first encounter, no antibody can exist (strictly-earlier rule)
        if m >= 1 and _suppress(k, m, pm):
            sup[i] = True
            lib[k] = 1; lib.move_to_end(k)
            if len(lib) > LIB_CAP: lib.popitem(last=False)
            if s1: insert_prob(k)
        else:
            nonsup_misses += 1; preads += 1
            insert_prob(k)
    return {'sup_idx': sup, 'suppressed': sum(sup), 'nonsup_misses': nonsup_misses,
            'preads': preads, 'lib_pairs': len(lib), 'lib_slots_charged': lib_slots}

# ================= run =================
A0 = run_A0()
B0_bytes = A0['misses'] * RECORD
res = {
  'trace': {'path': TRACE, 'sha256': TRACE_SHA, 'accesses': N, 'distinct': DISTINCT,
            'tokens': NTOK, 'cap': CAP},
  'labels': 'ALL numbers below are PROXY (frozen Kimi-Linear-shaped trace replay, cap 709); '
            'r_reuse values are ASSUMED parameters, not measurements.',
  'A0': A0 | {'bytes': B0_bytes, 'gib_per_token_proxy': B0_bytes / NTOK / GIB},
  'arms': [], 'overlap': [], 'gates': {},
}

best_split = SPLITS[0]; best_conv = None
A2_by_split = {}
for sf in SPLITS:
    a2 = run_A2(sf)
    conv = A0['misses'] - a2['misses']
    A2_by_split[sf] = (a2, conv)
    if best_conv is None or conv > best_conv: best_conv, best_split = conv, sf
res['A2_split_sweep'] = [
    {'protected_frac': sf, 'misses': A2_by_split[sf][0]['misses'],
     'converted': A2_by_split[sf][1],
     'conv_pp_of_baseline': 100.0 * A2_by_split[sf][1] / A0['misses']}
    for sf in SPLITS]
res['best_split_for_B'] = {'protected_frac': best_split, 'converted': best_conv}

A2, conv_total = A2_by_split[best_split]
missA0 = A0['miss_idx']; hitA2 = A2['hit_idx']
Conv_set = {i for i in range(N) if missA0[i] and hitA2[i]}

for r in R_SWEEP:
    a1 = run_A1(r, s1=True)
    Sup_set = {i for i in range(N) if a1['sup_idx'][i]}
    inter = Sup_set & Conv_set
    ov = len(inter) / min(len(Sup_set), len(Conv_set)) if min(len(Sup_set), len(Conv_set)) else 0.0
    a3 = run_A3(r, best_split, s1=True)
    def gain(nonsup): return 100.0 * (A0['misses'] - nonsup) / A0['misses']
    safe_div = lambda p, m: (p / m) if m else 0.0
    gA = gain(a1['nonsup_misses']); gB = gain(A2['misses']); gAB = gain(a3['nonsup_misses'])
    res['arms'].append({
        'r_reuse': r, 'protected_frac': best_split,
        'A1': {'suppressed': a1['suppressed'], 'nonsup_misses': a1['nonsup_misses'],
               'preads': a1['preads'], 'gain_pct': gA,
               'preads_per_nonsup_miss': safe_div(a1['preads'], a1['nonsup_misses']),
               'gib_per_token_proxy': a1['nonsup_misses'] * RECORD / NTOK / GIB},
        'A2': {'misses': A2['misses'], 'preads': A2['preads'], 'gain_pct': gB,
               'preads_per_miss': A2['preads'] / A2['misses'],
               'gib_per_token_proxy': A2['misses'] * RECORD / NTOK / GIB},
        'A3': {'suppressed': a3['suppressed'], 'nonsup_misses': a3['nonsup_misses'],
               'preads': a3['preads'], 'gain_pct': gAB,
               'preads_per_nonsup_miss': safe_div(a3['preads'], a3['nonsup_misses']),
               'lib_slots_charged': a3['lib_slots_charged'],
               'gib_per_token_proxy': a3['nonsup_misses'] * RECORD / NTOK / GIB},
        'gainB_pct': gB, 'interaction_pp': gAB - gA - gB,
        'interaction_floor_ratio': (gAB - gA - gB) / min(gA, gB) if min(gA, gB) > 0 else None,
    })
    res['overlap'].append({
        'r_reuse': r, '|Sup|': len(Sup_set), '|Conv|': len(Conv_set),
        '|Sup∩Conv|': len(inter),
        'overlap_coefficient': round(ov, 4),
        'falsifier_fired': ov > 0.70,
    })

# S2 sensitivity at smallest r with gain(A)>0 (all r qualify under S1; use r=0.05)
a1s2 = run_A1(0.05, s1=False); a3s2 = run_A3(0.05, best_split, s1=False)
res['S2_sensitivity_r005'] = {
    'A1_S2': {'nonsup_misses': a1s2['nonsup_misses'], 'gain_pct': 100.0*(A0['misses']-a1s2['nonsup_misses'])/A0['misses']},
    'A3_S2': {'nonsup_misses': a3s2['nonsup_misses'], 'gain_pct': 100.0*(A0['misses']-a3s2['nonsup_misses'])/A0['misses']},
    'note': 'S2 = no-insert-on-bypass; trajectory diverges from A0 (exp13 regime)',
}

# invariant checks
viol = []
for arm in res['arms']:
    for k in ('A1', 'A3'):
        if abs(arm[k]['preads_per_nonsup_miss'] - 1.0) > 1e-12:
            viol.append((arm['r_reuse'], k))
if abs(A2['preads'] / A2['misses'] - 1.0) > 1e-12: viol.append(('A2',))
res['invariant_preads_per_nonsup_miss_1.000'] = {'violations': viol}

print(json.dumps(res, indent=1))
