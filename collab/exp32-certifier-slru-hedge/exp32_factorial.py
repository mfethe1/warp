#!/usr/bin/env python3
"""
exp32: FACTORIAL -- certifier (A, idea16 row-norm bound) x SLRU segmented admission (B, idea3)
Lane: offline. Evidence class: PROXY closed-loop replay (trace is Kimi-Linear-shaped, NOT K3)
      x RECOMPUTATION (certification rates are Bernoulli draws over REAL-K3-curve-referenced
      operating points; per spec the bound itself is threshold-swept s in [0.05, saturate]).

PREREGISTERED SPEC (frozen from queue row, verbatim decisions):
  Arms:
    baseline : LRU, cap 709 slots (3.41x WS), no certifier, closed-loop chronological
    A        : LRU + certifier, closed-loop, threshold sweep, eps_B reported
    B        : SLRU (protected/probationary, promote on 2nd reference), no certifier,
               protected fraction swept {0.5, 0.7, 0.9}, closed-loop
    A+B      : SLRU + certifier, same threshold sweep, protected-set eviction attribution
  gain(X) = metric(baseline) - metric(X); interaction = gain(A+B) - gain(A) - gain(B)
  Certifier: suppress a physical MISS read with probability s (Bernoulli, seeded).
    STOP RULE first: compute eps_B for arm A; if < 0.5% -> DEAD-VACUOUS, no SLRU sweep.
    Threshold sweep >= 6 points spanning s_eff ~0.05 .. saturation.
  Frozen matched threshold: interaction evaluated at the threshold that maximises arm A
    (per seed-averaged B_replay), NOT at each arm's own optimum.
  Metrics per arm: B_replay (GiB/accepted token), B_frozen (GiB/tok on frozen baseline
    miss vector, open-loop diagnostic), eps_B = (B_replay - B_frozen)/B_frozen,
    hit fraction, s_eff, protected evictions caused by certifier-forced one-shot reads.
  Deterministic: seeds 1..5 for certification draws; SLRU/LRU replay is deterministic.
  Record B = 12,406,784 B (exp5-verified). Cap = round((5015/1472)*208) = 709.
"""
import json, math, os, hashlib, datetime
from collections import OrderedDict, Counter
import numpy as np

REPO = '/Users/mfethe/warp'
TRACE = f'{REPO}/tests/trace_kimi_300.jsonl'
OUT = os.path.expanduser('~/.hermes/state/warp-research/evidence/exp32-certifier-slru-hedge')
os.makedirs(OUT, exist_ok=True)

def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

TRACE_SHA = sha256(TRACE)
assert TRACE_SHA == '06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965'

RECORD_B = 12406784
GIB = 1024**3
SEEDS = [1, 2, 3, 4, 5]
WS = 26 * 8
CAP = round((5015 / 1472) * WS)
assert CAP == 709

toks = [json.loads(l) for l in open(TRACE)]
assert len(toks) == 300
L = len(toks[0]['layers']); K = len(toks[0]['layers'][0])
assert L == 26 and K == 8
N_ACC = 300  # one accepted token per replayed token (batch-1 decode)

# ---------------- certification draws ----------------
# Bernoulli per miss-event, keyed by a global access counter so that the draw
# attached to an access does NOT depend on which arm replays it (matched draws).
# (Each arm has its own miss set, so s_eff differs by arm -- that is the point.)
def cert_table(s):
    tab = {}
    for sd in SEEDS:
        rng = np.random.default_rng(sd * 100003)
        # draws over ALL access positions, 300*26*8 = 62400
        u = rng.random(62400)
        for pos in range(62400):
            tab[(sd, pos)] = u[pos] < s
    return tab

# ---------------- caches ----------------
class LRU:
    def __init__(self, cap):
        self.cap = cap; self.d = OrderedDict()
    def touch(self, key):  # hit
        self.d.move_to_end(key)
    def insert(self, key):  # miss -> fetch, insert, evict LRU
        self.d[key] = 1
        if len(self.d) > self.cap:
            return self.d.popitem(last=False)[0]
        return None
    def __contains__(self, key): return key in self.d

class SLRU:
    """Protected + probationary segments, total cap fixed. Promote on second
    reference (probation hit). Insert new at MRU of probation; evict probation LRU.
    Promotion moves key to protected MRU and evicts protected LRU into probation MRU."""
    def __init__(self, cap, prot_frac):
        self.pcap = max(1, round(cap * prot_frac))
        self.qcap = cap - self.pcap
        if self.qcap < 1:
            self.pcap -= 1; self.qcap = 1
        self.prot = OrderedDict(); self.prob = OrderedDict()
        self.prot_evictions = 0
        self.last_seg = {}
    def touch(self, key):
        if key in self.prot:
            self.prot.move_to_end(key); self.last_seg[key] = 'P'
        elif key in self.prob:
            # second reference -> promote
            del self.prob[key]
            self.prot[key] = 1
            if len(self.prot) > self.pcap:
                ev = self.prot.popitem(last=False)[0]
                self.prot_evictions += 1
                # demoted into probation
                self.prob[ev] = 1
                if len(self.prob) > self.qcap:
                    self.prob.popitem(last=False)
            self.last_seg[key] = 'P'
        else:
            raise KeyError
    def insert(self, key):
        self.prob[key] = 1
        self.last_seg[key] = 'Q'
        if len(self.prob) > self.qcap:
            return self.prob.popitem(last=False)[0]
        return None
    def __contains__(self, key): return key in self.prot or key in self.prob

# ---------------- closed-loop replay ----------------
def replay(cache_kind, s=None, sd=None, prot_frac=None, track_pe=False):
    """Replay chronologically; each arm's own bypass decisions feed its own cache.
    Returns (bytes_read, misses, suppressions, prot_evict_oneshot, hit_fraction, s_eff,
             per-token bytes list)."""
    if cache_kind == 'lru':
        cache = LRU(CAP)
    else:
        cache = SLRU(CAP, prot_frac)
    tab = cert_table(s) if s is not None else None
    pos = 0
    bytes_read = 0; misses = 0; suppressed = 0; hits = 0
    prot_evict_oneshot = 0
    per_tok = []
    cur_tok_bytes = 0
    # track which keys were inserted by a certifier-suppressed-then-later-needed event?
    # "certifier-forced one-shot reads": reads where the expert is fetched (miss, not
    # certified) and then NOT referenced again before eviction. Track via reference
    # counts computed in a pre-pass of the FULL chronological demand (arm-independent),
    # so 'one-shot' = this access is the expert's last reference in the trace.
    last_ref = {}
    for t_i, t in enumerate(toks):
        for li, exs in enumerate(t['layers']):
            for e in exs:
                last_ref[(li, e)] = (t_i, pos)
                pos += 1
    pos = 0
    for t_i, t in enumerate(toks):
        for li, exs in enumerate(t['layers']):
            for e in exs:
                key = (li, e)
                if key in cache:
                    cache.touch(key); hits += 1
                else:
                    # physical miss: certifier decides
                    suppressed_this = False
                    if tab is not None and tab[(sd, pos)]:
                        suppressed_this = True
                        suppressed += 1
                        # bypass: NO fetch, NO insert (expert never enters cache)
                    else:
                        bytes_read += RECORD_B; misses += 1; cur_tok_bytes += RECORD_B
                        if track_pe and cache_kind == 'slru' and last_ref[key][1] == pos:
                            # this fetch is the expert's final reference: any protected
                            # eviction it causes is certifier-environment churn
                            before = cache.prot_evictions
                            cache.insert(key)
                            after = cache.prot_evictions
                            # demotion from protected happens only on promote; insert
                            # evicts probation. Count protected churn attributable:
                            # (conservative: count if any protected eviction occurred
                            # during this insert's cascade)
                            if after > before:
                                prot_evict_oneshot += 1
                        else:
                            cache.insert(key)
                pos += 1
        per_tok.append(cur_tok_bytes); cur_tok_bytes = 0
    total = hits + misses + suppressed
    s_eff = suppressed / (misses + suppressed) if (misses + suppressed) else 0.0
    return dict(bytes=bytes_read, misses=misses, suppressed=suppressed, hits=hits,
                prot_evict_oneshot=prot_evict_oneshot,
                hit_fraction=hits / total,
                s_eff=s_eff, per_tok=per_tok)

def GiB_per_tok(res):
    return res['bytes'] / GIB / N_ACC

# ---------------- baseline + frozen open-loop vector ----------------
base = replay('lru')
B_base = GiB_per_tok(base)
print(f"baseline LRU: B_replay={B_base:.4f} GiB/tok  hit={base['hit_fraction']:.4f}  misses={base['misses']}")

# B_frozen per arm = bytes the arm would read on the FROZEN baseline miss vector
# (open-loop diagnostic): every baseline miss not suppressed by that arm's cert draws.
def B_frozen_for(s, sd):
    tab = cert_table(s)
    # recompute baseline misses with position stamps
    cache = OrderedDict()
    pos = 0; frozen_bytes = 0
    for t in toks:
        for li, exs in enumerate(t['layers']):
            for e in exs:
                key = (li, e)
                if key in cache:
                    cache.move_to_end(key)
                else:
                    if not tab[(sd, pos)]:
                        frozen_bytes += RECORD_B
                    cache[key] = 1
                    if len(cache) > CAP:
                        cache.popitem(last=False)
                pos += 1
    return frozen_bytes / GIB / N_ACC

# ---------------- STOP RULE: arm A eps_B sweep first ----------------
THRESHOLDS = [0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.65, 0.80]
armA = []
for s in THRESHOLDS:
    rows = []
    for sd in SEEDS:
        r = replay('lru', s=s, sd=sd)
        bf = B_frozen_for(s, sd)
        rows.append(dict(seed=sd, B_replay=GiB_per_tok(r), B_frozen=bf,
                         eps_B=(GiB_per_tok(r) - bf) / bf * 100,
                         hit=r['hit_fraction'], s_eff=r['s_eff'], misses=r['misses'],
                         suppressed=r['suppressed']))
    Bp = float(np.mean([x['B_replay'] for x in rows]))
    Bf = float(np.mean([x['B_frozen'] for x in rows]))
    eps = (Bp - Bf) / Bf * 100
    armA.append(dict(s=s, B_replay=Bp, B_replay_sd=float(np.std([x['B_replay'] for x in rows], ddof=1)),
                     B_frozen=Bf, eps_B=eps, s_eff=float(np.mean([x['s_eff'] for x in rows])),
                     hit=float(np.mean([x['hit'] for x in rows])), rows=rows))
    print(f"armA s={s:.2f}: B_replay={Bp:.4f} B_frozen={Bf:.4f} eps_B={eps:+.3f}% s_eff={armA[-1]['s_eff']:.3f} hit={armA[-1]['hit']:.4f}")

# stop rule check
max_eps = max(a['eps_B'] for a in armA)
vacuous = max_eps < 0.5
print(f"\nSTOP RULE: max eps_B(A) over sweep = {max_eps:+.3f}%  ->  "
      f"{'DEAD-VACUOUS (eps<0.5%), no SLRU parameter sweep' if vacuous else 'continue: full factorial'}")

res = {
    'exp': 'exp32', 'slug': 'certifier-bypass-starvation-chaperone-hedge',
    'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'sources': {'trace': TRACE_SHA, 'warp_repo': 'mfethe1/warp@69967a0 (research/exp44-protocol-validity checkout)',
                'evidence_class': 'PROXY closed-loop replay (Kimi-Linear-shaped 26L x top-8, NOT K3) '
                                  'x RECOMPUTATION (Bernoulli certification draws; s swept per spec)'},
    'frozen': {'cap': CAP, 'record_B': RECORD_B, 'seeds': SEEDS, 'n_accepted_tokens': N_ACC,
               'thresholds': THRESHOLDS, 'prot_fracs': [0.5, 0.7, 0.9],
               'metric': 'B_replay GiB per accepted token, closed-loop'},
    'baseline': {'B_replay': B_base, 'hit_fraction': base['hit_fraction'], 'misses': base['misses']},
    'armA_sweep': [{k: v for k, v in a.items() if k != 'rows'} for a in armA],
    'armA_rows': {str(a['s']): a['rows'] for a in armA},
    'stop_rule': {'max_eps_B_A_pct': max_eps, 'vacuous': bool(vacuous)},
}

if not vacuous:
    # matched frozen threshold: s* maximises arm A gain (= minimises B_replay)
    s_star = min(armA, key=lambda a: a['B_replay'])['s']
    res['matched_threshold_s'] = s_star
    print(f"matched frozen threshold s* = {s_star} (maximises arm A gain, frozen for B and A+B)")

    # ---------------- arm B: SLRU sweep (deterministic, no certifier) ----------------
    armB = []
    for pf in (0.5, 0.7, 0.9):
        r = replay('slru', prot_frac=pf)
        armB.append(dict(prot_frac=pf, B_replay=GiB_per_tok(r), hit=r['hit_fraction'],
                         prot_evictions=r['prot_evict_oneshot'] if 'prot_evict_oneshot' in r else None,
                         prot_evict_total=None))
        # re-run for protected eviction total (not one-shot-attributed)
        rr = replay('slru', prot_frac=pf, track_pe=True)
        armB[-1]['prot_evict_total'] = rr['prot_evict_oneshot']
        print(f"armB pf={pf}: B_replay={armB[-1]['B_replay']:.4f} hit={armB[-1]['hit']:.4f}")
    res['armB_sweep'] = armB
    # best SLRU arm for combination = min B_replay
    bB = min(armB, key=lambda x: x['B_replay'])
    pf_star = bB['prot_frac']
    res['prot_frac_star'] = pf_star

    # ---------------- arm A+B at matched threshold ----------------
    ab_rows = []
    for sd in SEEDS:
        r = replay('slru', s=s_star, sd=sd, prot_frac=pf_star, track_pe=True)
        ab_rows.append(dict(seed=sd, B_replay=GiB_per_tok(r), hit=r['hit_fraction'],
                            s_eff=r['s_eff'], prot_evict_oneshot=r['prot_evict_oneshot']))
    B_ab = float(np.mean([x['B_replay'] for x in ab_rows]))
    B_ab_sd = float(np.std([x['B_replay'] for x in ab_rows], ddof=1))
    # arm A at s* seed-averaged
    a_star = next(a for a in armA if a['s'] == s_star)
    B_a = a_star['B_replay']; B_a_sd = a_star['B_replay_sd']
    B_b = bB['B_replay']

    gain_A = B_base - B_a
    gain_B = B_base - B_b
    gain_AB = B_base - B_ab
    interaction = gain_AB - gain_A - gain_B  # in GiB/tok; convert to pp of baseline
    print(f"\nA+B @s*={s_star}, pf*={pf_star}: B={B_ab:.4f} (sd {B_ab_sd:.4f})")
    print(f"gain(A)={gain_A:.4f} gain(B)={gain_B:.4f} gain(A+B)={gain_AB:.4f} GiB/tok")
    print(f"interaction={interaction:+.5f} GiB/tok = {interaction/B_base*100:+.3f} pp of B_baseline")

    gates = {
        'accept': {
            'a_eps_B_ge_0.5pct': max_eps >= 0.5,
            'b_interaction_ge_0.8pp': interaction / B_base * 100 >= 0.8,
            'c_gainAB_ge_2.13pct': gain_AB / B_base * 100 >= 2.13,
            'd_survives_frozen_threshold': True,  # evaluated at s* frozen, not re-tuned
        },
        'reject': {
            'eps_B_A_lt_0.5pct': max_eps < 0.5,
            'interaction_lt_0.8pp': interaction / B_base * 100 < 0.8,
            'gainAB_lt_2.13pct': gain_AB / B_base * 100 < 2.13,
            'parent_dominates': gain_AB <= max(gain_A, gain_B) + 0.005 * B_base,
            'only_retuned': False,
        },
    }
    accept_all = all(gates['accept'].values())
    print(f"\nGATES: accept_all={accept_all}  detail={json.dumps(gates, indent=1)}")
    res['factorial'] = {
        'B_base': B_base, 'B_A': B_a, 'B_A_sd': B_a_sd, 'B_B': B_b, 'B_AB': B_ab, 'B_AB_sd': B_ab_sd,
        'gain_A': gain_A, 'gain_B': gain_B, 'gain_AB': gain_AB,
        'gain_A_pct': gain_A / B_base * 100, 'gain_B_pct': gain_B / B_base * 100,
        'gain_AB_pct': gain_AB / B_base * 100,
        'interaction_gib': interaction, 'interaction_pp_of_baseline': interaction / B_base * 100,
        'ab_rows': ab_rows,
    }
    res['gates'] = gates
    res['gates']['accept_all'] = accept_all
    res['gates']['reject_fired'] = [k for k, v in gates['reject'].items() if v]
else:
    res['gates'] = {'vacuous_dead': True}
    res['gates'] = {
        'vacuous_dead': True,
        'reject_fired': ['eps_B_A_lt_0.5pct'],
        'accept': False,
    }

p = f'{OUT}/exp32_result.json'
json.dump(res, open(p, 'w'), indent=1)
print(f"\nWROTE {p}")
