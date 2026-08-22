#!/usr/bin/env python3
"""
exp10: certified-skip (A) x option-value-prefetch (B) FACTORIAL
Cheapest decisive form: RECOMPUTATION from real-K3 route-margin distribution
(docs/gn100/sprint11-route-margin-summary.json) + PROXY ordered-trace replay for stalls.
Sweeps the ENTIRE published tail curve instead of cherry-picking one operating point.
"""
import json, hashlib, os, collections

REPO = '/tmp/spark/warp'
OUT = os.path.expanduser('~/.hermes/state/warp-research/evidence/exp10')
os.makedirs(OUT, exist_ok=True)

def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

MARGIN = f'{REPO}/docs/gn100/sprint11-route-margin-summary.json'
TRACE  = f'{REPO}/tests/trace_kimi_300.jsonl'
m = json.load(open(MARGIN))

RECORD_B = 12406784   # exp5, page-exact 3029 x 4096
PLANE_B  = 4128768    # one VQ residual plane
M_ACT    = 1472       # expert activations/token (92L x top-16)
GIB      = 1024 ** 3
BASE_GIB_TOK = 7.719
NEED_GIB_TOK = 0.3946 # for 15 tok/s

res = {'sources': {os.path.basename(MARGIN): sha256(MARGIN),
                   os.path.basename(TRACE): sha256(TRACE)}}
res['margin_provenance'] = {
    'label': 'REAL-K3', 'layers': m['layers'], 'rows': m['rows'],
    'positions': m['positions'], 'exact_boundary_ties': m['exact_boundary_ties'],
    'margin_p50': m['margin']['p50'], 'margin_p1': m['margin']['p1'],
    'margin_min': m['margin']['min'],
}

# ---------- PROXY stall replay (order-dependent, arm-independent base) ----------
toks = [json.loads(l) for l in open(TRACE)]
accesses = [(li, e) for t in toks for li, ex in enumerate(t['layers']) for e in ex]
N = len(accesses); distinct = len(set(accesses))
cap = int(distinct / 3.41)   # K3-equivalent working-set ratio (established finding)

def replay_lru(cap):
    cache = collections.OrderedDict(); misses = 0
    for a in accesses:
        if a in cache: cache.move_to_end(a)
        else:
            misses += 1; cache[a] = 1
            if len(cache) > cap: cache.popitem(last=False)
    return misses

base_misses = replay_lru(cap)
res['stall_base_PROXY'] = {
    'label': 'PROXY (Kimi-Linear-shaped 26L x top-8), NOT K3',
    'accesses_N': N, 'distinct': distinct, 'cache_capacity': cap,
    'working_set_ratio': 3.41, 'cold_misses': base_misses,
    'miss_rate': base_misses / N,
}

# ---------- Sweep the published tail curve ----------
def arm_bytes(s, overread):
    """s = certified-skip rate; overread = frac of SKIPPED planes prefetch pulls anyway"""
    skipped = s * M_ACT
    return M_ACT * RECORD_B - skipped * PLANE_B * (1.0 - overread)

b_base = arm_bytes(0.0, 0.0)
sweep = []
for r in sorted(m['score_error_risk'], key=lambda x: x['max_score_error']):
    tail_f = r['fraction_not_certified']       # uncertifiable fraction -> prefetch's addressable traffic
    s      = 1.0 - tail_f                      # certified-skip rate
    bA   = arm_bytes(s, 0.0)                   # A: skip only
    bB   = arm_bytes(0.0, 0.0)                 # B: prefetch only -> reorders reads, same bytes
    bAB  = arm_bytes(s, 0.0)                   # A+B ideal: prefetch perfectly disjoint from skip set
    bAB5 = arm_bytes(s, 0.05)                  # A+B realistic: 5% over-read into the skip set
    gA, gB, gAB, gAB5 = b_base-bA, b_base-bB, b_base-bAB, b_base-bAB5
    inter_ideal = gAB - gA - gB
    inter_real  = gAB5 - gA - gB
    # stalls: A takes the tail cold-misses synchronously; ideal prefetch hides ALL of them
    stall_A  = base_misses * tail_f
    stall_AB = 0.0
    stall_red = 1.0 if stall_A > 0 else 0.0
    gib_A = bA / GIB
    sweep.append({
        'max_score_error': r['max_score_error'],
        'required_margin': r['required_margin'],
        'frac_uncertifiable_tail': tail_f,
        'certified_skip_rate_s': s,
        'bytes_baseline': b_base, 'bytes_A': bA, 'bytes_B': bB,
        'bytes_AB_ideal': bAB, 'bytes_AB_5pct_overread': bAB5,
        'gain_A': gA, 'gain_B': gB, 'gain_AB_ideal': gAB,
        'interaction_ideal': inter_ideal,
        'interaction_5pct_overread': inter_real,
        'bytes_AB_over_A_ideal': bAB / bA,
        'bytes_AB_over_A_5pct': bAB5 / bA,
        'GiB_per_token_A_scaled': gib_A / (b_base / GIB) * BASE_GIB_TOK,
        'tail_stalls_A_PROXY': stall_A,
        'tail_stalls_AB_PROXY': stall_AB,
        'tail_stall_reduction_frac_PROXY': stall_red,
        'tail_ge_5pct_of_traffic': bool(tail_f >= 0.05),
        'stop_rule_fires_tail_lt_5pct': bool(tail_f < 0.05),
    })
res['sweep_REAL_K3_tail_x_RECOMPUTATION_bytes'] = sweep

# ---------- Gate evaluation, quoted verbatim ----------
acc = ("interaction = gain(A+B)-gain(A)-gain(B) > 0 AND bytes(A+B) <= bytes(A) "
       "[no net extra bandwidth] AND tail-cold stall count of A+B < A by >20%.")
rej = ("if the uncertifiable tail is <5% of reads so that (A+B) bytes >= bytes(A)+2% "
       "or stall improvement <20%, interaction is inert -> do not combine.")
stop = ("Stop early if the certified-skip rate is so high (>=97.7% with margin so tight "
        "the tail is tiny) that prefetch has <5% of total traffic to act on.")

# interaction is identically 0 everywhere on the byte objective (proved below)
max_inter_ideal = max(x['interaction_ideal'] for x in sweep)
min_inter_ideal = min(x['interaction_ideal'] for x in sweep)
max_inter_real  = max(x['interaction_5pct_overread'] for x in sweep)
any_positive    = max_inter_ideal > 0

# regimes where the byte-objective is even survivable (A must approach the 0.3946 target)
best_A = min(x['GiB_per_token_A_scaled'] for x in sweep)
res['best_arm_A_GiB_per_token_scaled'] = best_A
res['target_GiB_per_token_for_15tps'] = NEED_GIB_TOK
res['arm_A_alone_reaches_target'] = bool(best_A <= NEED_GIB_TOK)

res['gates'] = {
    'accept_gate': acc, 'reject_gate': rej, 'stop_rule': stop,
    'max_interaction_ideal_bytes_per_token': max_inter_ideal,
    'min_interaction_ideal_bytes_per_token': min_inter_ideal,
    'max_interaction_5pct_overread': max_inter_real,
    'accept_c1_interaction_gt_0_anywhere': bool(any_positive),
    'accept_gate_met': bool(any_positive),
    'reject_gate_met': not bool(any_positive),
}
res['verdict'] = 'confirmed' if any_positive else 'falsified'

res['objective_check'] = {
    'algebra': 'B_acc = M * (RECORD_B - s*PLANE_B*(1-overread)) / a',
    'd_prefetch': ('Prefetch appears in B_acc ONLY through `overread` (pages it pulls that the '
                   'skip verdict omits). dB_acc/d(overread) = +M*s*PLANE_B/a >= 0.'),
    'conclusion': ('Prefetch has NO byte-reducing term. It changes WHEN a page is read, never '
                   'WHETHER. Hence gain(B) == 0 and gain(A+B) == gain(A) identically, so '
                   'interaction = gain(A+B)-gain(A)-gain(B) == 0 for every operating point, '
                   'and strictly < 0 with any over-read. This is a structural result, not a '
                   'measurement: no trace, no tail size, and no cache capacity can make it positive '
                   'on the bytes/accepted-token objective. Prefetch can only buy LATENCY hiding, '
                   'which is a different objective and is already bandwidth-saturated per the '
                   '100% I/O-bound verifier finding.'),
}

p = f'{OUT}/exp10_result.json'
json.dump(res, open(p, 'w'), indent=2)

print("=== TAIL SWEEP (REAL-K3 margins x RECOMPUTATION bytes) ===")
print(f"{'err':>8} {'tail%':>8} {'s%':>8} {'gainA_B/tok':>14} {'gainB':>7} {'interact':>9} {'AB/A':>7} {'GiB/tok_A':>10}")
for x in sweep:
    print(f"{x['max_score_error']:>8.0e} {x['frac_uncertifiable_tail']*100:>8.3f} "
          f"{x['certified_skip_rate_s']*100:>8.3f} {x['gain_A']:>14,.0f} {x['gain_B']:>7.0f} "
          f"{x['interaction_ideal']:>9.0f} {x['bytes_AB_over_A_ideal']:>7.4f} "
          f"{x['GiB_per_token_A_scaled']:>10.4f}")
print()
print("PROXY stalls:", json.dumps(res['stall_base_PROXY']))
print("best arm-A GiB/token (scaled):", round(best_A,4), " target:", NEED_GIB_TOK,
      " reaches:", res['arm_A_alone_reaches_target'])
print("interaction range (ideal):", min_inter_ideal, "..", max_inter_ideal)
print("VERDICT:", res['verdict'])
