#!/usr/bin/env python3
"""
exp6 FACTORIAL: protected/probationary admission (A) x EV-gated prefetch (B).

Preregistered spec (verbatim from queue claim, id=6, idea=10, source_sha cb05b14):
  Arms: baseline LRU lookahead OFF | A: protected/probationary admission only
        | B: EV-gated prefetch only | A+B: EV-gated prefetch into probationary
  gain(X) = metric(baseline) - metric(X)
  interaction = gain(A+B) - gain(A) - gain(B)
  primary_metric: physical bytes per accepted token
  ACCEPT: A+B reduces verifier bytes >=2.13% vs baseline AND beats both A and B alone
  REJECT: A+B fails to beat lookahead-off, or one parent alone matches A+B
  STOP: offline replay only; abort if segmented policy cannot reproduce the
        baseline miss count as a validity check.

Evidence class: PROXY replay (tests/trace_kimi_300.jsonl, Kimi-Linear-shaped
26L x top-8, NOT K3 92L x 896E x top-16) + RECOMPUTATION of the byte objective.

Reuses the EV value function and predictor from tools/crossval/exp4_ev_prefetch.py
verbatim; the only new machinery is the SLRU segmented cache.
"""
import json, os, hashlib
from collections import OrderedDict, defaultdict

REPO = '/tmp/spark/warp'
TRACE = f'{REPO}/tests/trace_kimi_300.jsonl'
OUT = os.path.expanduser('~/.hermes/state/warp-research/evidence/exp6')
os.makedirs(OUT, exist_ok=True)

RECORD_BYTES = 12406784      # 3029 pages exactly (established finding, exp5)
GIB = 1024.0 ** 3
BASE_GIB_TOK = 7.719         # measured physical GiB/token
NEED_GIB_TOK = 0.3946        # for 15 tok/s batch-1
BREAK_EVEN = 2.13            # % byte saving required by the accept gate


def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Caches.  Both expose the same interface: demand(k), prefetch(k), .physical
# --------------------------------------------------------------------------
class LRU:
    """Baseline / arm-B cache: single LRU list, identical to exp4."""
    kind = 'lru'

    def __init__(self, cap, prot_frac=0.0):
        self.cap = cap
        self.od = OrderedDict()
        self.demand_miss = 0
        self.prefetch_fetch = 0
        self.prefetch_useful = 0
        self.evicted_prefetch_unused = 0
        self.pf_pending = set()

    def _evict(self):
        k, _ = self.od.popitem(last=False)
        if k in self.pf_pending:
            self.pf_pending.discard(k)
            self.evicted_prefetch_unused += 1

    def demand(self, k):
        if k in self.od:
            self.od.move_to_end(k)
            if k in self.pf_pending:
                self.pf_pending.discard(k)
                self.prefetch_useful += 1
            return True
        self.demand_miss += 1
        if len(self.od) >= self.cap:
            self._evict()
        self.od[k] = 1
        return False

    def prefetch(self, k):
        if k in self.od:
            self.od.move_to_end(k)
            return False
        self.prefetch_fetch += 1
        if len(self.od) >= self.cap:
            self._evict()
        self.od[k] = 1
        self.pf_pending.add(k)
        return True

    @property
    def occupancy(self):
        return len(self.od)

    @property
    def physical(self):
        return self.demand_miss + self.prefetch_fetch


class SLRU:
    """Arm-A cache: segmented LRU (protected + probationary).

    - A demand MISS inserts into probationary (never straight into protected).
    - A demand HIT on a probationary line PROMOTES it into protected; if
      protected is full its LRU line is demoted to the probationary MRU end.
    - A demand HIT on a protected line just refreshes it.
    - Eviction ALWAYS comes from the probationary LRU end, so the protected
      set cannot be evicted by a burst of one-shot lines. This is the
      'chaperone' mechanism: protect what has proven reuse.
    - Prefetched lines enter probationary only (they have not proven reuse),
      so a prefetch can never displace a protected line directly.

    prot_frac = 0.0 degenerates EXACTLY to plain LRU (validity check).
    """
    kind = 'slru'

    def __init__(self, cap, prot_frac=0.5):
        self.cap = cap
        self.prot_cap = int(round(cap * prot_frac))
        self.prob_cap = cap - self.prot_cap
        self.prot = OrderedDict()
        self.prob = OrderedDict()
        self.demand_miss = 0
        self.prefetch_fetch = 0
        self.prefetch_useful = 0
        self.evicted_prefetch_unused = 0
        self.promotions = 0
        self.demotions = 0
        self.pf_pending = set()

    def _evict_prob(self):
        if self.prob:
            k, _ = self.prob.popitem(last=False)
        elif self.prot:                      # prot_frac==1.0 corner
            k, _ = self.prot.popitem(last=False)
        else:
            return
        if k in self.pf_pending:
            self.pf_pending.discard(k)
            self.evicted_prefetch_unused += 1

    def _promote(self, k):
        if self.prot_cap == 0:               # degenerate -> stay in prob (=LRU)
            self.prob[k] = 1
            self.prob.move_to_end(k)
            return
        self.prot[k] = 1
        self.prot.move_to_end(k)
        self.promotions += 1
        while len(self.prot) > self.prot_cap:
            dk, _ = self.prot.popitem(last=False)
            self.demotions += 1
            self.prob[dk] = 1                # demote to probationary MRU
            self.prob.move_to_end(dk)
            while len(self.prob) + len(self.prot) > self.cap:
                self._evict_prob()

    def _make_room(self):
        while len(self.prob) + len(self.prot) >= self.cap:
            self._evict_prob()

    def demand(self, k):
        if k in self.prot:
            self.prot.move_to_end(k)
            if k in self.pf_pending:
                self.pf_pending.discard(k)
                self.prefetch_useful += 1
            return True
        if k in self.prob:
            del self.prob[k]
            if k in self.pf_pending:
                self.pf_pending.discard(k)
                self.prefetch_useful += 1
            self._promote(k)
            return True
        self.demand_miss += 1
        self._make_room()
        self.prob[k] = 1
        return False

    def prefetch(self, k):
        if k in self.prot:
            self.prot.move_to_end(k)
            return False
        if k in self.prob:
            self.prob.move_to_end(k)
            return False
        self.prefetch_fetch += 1
        self._make_room()
        self.prob[k] = 1                     # probationary ONLY
        self.pf_pending.add(k)
        return True

    @property
    def occupancy(self):
        return len(self.prot) + len(self.prob)

    @property
    def physical(self):
        return self.demand_miss + self.prefetch_fetch


# --------------------------------------------------------------------------
# Replay: identical demand sequence for every arm; only policy differs.
# EV value function copied verbatim from exp4_ev_prefetch.replay().
# --------------------------------------------------------------------------
def replay(rows, cap, cache_kind, mode, thresh=0.0, prot_frac=0.5):
    c = (SLRU(cap, prot_frac) if cache_kind == 'slru' else LRU(cap))
    prev_layer_experts = {}
    hit_hist = defaultdict(lambda: [1, 2])   # Laplace-smoothed per-layer reuse
    nlay = len(rows[0]['layers'])
    ev_prefetched = ev_skipped = 0

    for r in rows:
        for li, lay in enumerate(r['layers']):
            nli = li + 1
            if mode != 'off' and nli < nlay:
                for e in prev_layer_experts.get(nli, []):
                    k = (nli, e)
                    h, n = hit_hist[nli]
                    p = h / n
                    if mode == 'uncond':
                        do = True
                    else:
                        occ = c.occupancy / c.cap
                        disp = occ * (h / n)
                        val = p * 1.0 - 1.0 - disp
                        do = val > thresh
                    if do:
                        c.prefetch(k); ev_prefetched += 1
                    else:
                        ev_skipped += 1
            for e in lay:
                c.demand((li, e))
            if li in prev_layer_experts:
                prev = set(prev_layer_experts[li]); cur = set(lay)
                if prev:
                    hit_hist[li][0] += len(prev & cur)
                    hit_hist[li][1] += len(prev)
            prev_layer_experts[li] = list(lay)

    return {
        'cache': cache_kind, 'mode': mode, 'thresh': thresh, 'cap': cap,
        'prot_frac': prot_frac if cache_kind == 'slru' else None,
        'demand_miss': c.demand_miss,
        'prefetch_fetch': c.prefetch_fetch,
        'prefetch_useful': c.prefetch_useful,
        'prefetch_evicted_unused': c.evicted_prefetch_unused,
        'promotions': getattr(c, 'promotions', None),
        'demotions': getattr(c, 'demotions', None),
        'physical_reads': c.physical,
        'physical_bytes': c.physical * RECORD_BYTES,
        'ev_prefetched': ev_prefetched, 'ev_skipped': ev_skipped,
    }


def main():
    rows = [json.loads(l) for l in open(TRACE)]
    acc = [(li, e) for r in rows for li, lay in enumerate(r['layers']) for e in lay]
    N, D = len(acc), len(set(acc))
    L, K = len(rows[0]['layers']), len(rows[0]['layers'][0])
    WS = L * K
    K3_WS, K3_CACHE = 92 * 16, 5015
    ratio = K3_CACHE / K3_WS
    cap_eq = int(round(ratio * WS))

    out = {
        'experiment': 'exp6 chaperone-plus-ev-prefetch FACTORIAL',
        'source_sha': 'cb05b14',
        'sources': {'tests/trace_kimi_300.jsonl': sha256(TRACE)},
        'trace': {'label': 'PROXY (Kimi-Linear-shaped 26L x top-8), NOT K3',
                  'tokens': len(rows), 'layers': L, 'topk': K,
                  'accesses': N, 'distinct': D, 'per_token_WS': WS},
        'cache': {'K3_working_set': K3_WS, 'K3_cache': K3_CACHE,
                  'K3_equiv_ratio': ratio, 'proxy_cap_equiv': cap_eq},
        'record_bytes': RECORD_BYTES,
        'gates': {
            'accept': 'ACCEPT: A+B reduces verifier bytes >=2.13% vs baseline '
                      'AND beats both A and B alone',
            'reject': 'REJECT: A+B fails to beat lookahead-off, or one parent '
                      'alone matches A+B (no added value)',
            'stop': 'Offline replay only. Abort if segmented policy cannot '
                    'reproduce the baseline miss count as a validity check.',
        },
    }

    # ---------- STOP-RULE VALIDITY CHECK ----------
    base_eq = replay(rows, cap_eq, 'lru', 'off')
    slru_deg = replay(rows, cap_eq, 'slru', 'off', prot_frac=0.0)
    valid = (slru_deg['physical_reads'] == base_eq['physical_reads'])
    out['validity_check'] = {
        'rule': 'SLRU(prot_frac=0.0) must reproduce plain-LRU miss count exactly',
        'lru_baseline_reads': base_eq['physical_reads'],
        'slru_prot0_reads': slru_deg['physical_reads'],
        'passes': bool(valid),
    }
    if not valid:
        out['verdict'] = 'failed'
        out['abort_reason'] = 'segmented policy failed to reproduce baseline'
        json.dump(out, open(f'{OUT}/exp6_result.json', 'w'), indent=2)
        print('VALIDITY CHECK FAILED -> abort per stop rule')
        print(json.dumps(out['validity_check'], indent=2))
        return

    # ---------- FACTORIAL over cache sizes x protected fractions ----------
    caps = sorted({cap_eq, 762, 1270, 2033, 3049})
    prot_fracs = [0.2, 0.4, 0.5, 0.6, 0.8]
    ev_thresholds = [-2.0, -1.5, -1.0, -0.5, -0.25, -0.1, 0.0, 0.1, 0.5]

    sweep = []
    for cap in caps:
        base = replay(rows, cap, 'lru', 'off')                 # BASELINE
        unc = replay(rows, cap, 'lru', 'uncond')               # reference
        b_base = base['physical_bytes']

        # ---- arm B alone: EV prefetch on plain LRU (best threshold) ----
        bestB = None
        for th in ev_thresholds:
            r = replay(rows, cap, 'lru', 'ev', thresh=th)
            if bestB is None or r['physical_reads'] < bestB['physical_reads']:
                bestB = r

        # ---- arm A alone: SLRU, prefetch off (best protected fraction) ----
        bestA = None
        A_all = []
        for pf in prot_fracs:
            r = replay(rows, cap, 'slru', 'off', prot_frac=pf)
            A_all.append({'prot_frac': pf, 'physical_reads': r['physical_reads']})
            if bestA is None or r['physical_reads'] < bestA['physical_reads']:
                bestA = r

        # ---- arm A+B: SLRU + EV prefetch into probationary ----
        bestAB = None
        for pf in prot_fracs:
            for th in ev_thresholds:
                r = replay(rows, cap, 'slru', 'ev', thresh=th, prot_frac=pf)
                if bestAB is None or r['physical_reads'] < bestAB['physical_reads']:
                    bestAB = r

        def pct(x):                      # % byte reduction vs baseline
            return (1.0 - x['physical_bytes'] / b_base) * 100.0

        gA, gB, gAB = (b_base - bestA['physical_bytes'],
                       b_base - bestB['physical_bytes'],
                       b_base - bestAB['physical_bytes'])
        inter = gAB - gA - gB

        row = {
            'cap': cap, 'cap_over_WS': cap / WS,
            'baseline_reads': base['physical_reads'],
            'baseline_bytes': b_base,
            'uncond_prefetch_reads': unc['physical_reads'],
            'uncond_delta_pct': (unc['physical_reads'] / base['physical_reads'] - 1) * 100,
            'A_best': bestA, 'A_all_prot_fracs': A_all,
            'B_best': bestB, 'AB_best': bestAB,
            'saving_A_pct': pct(bestA), 'saving_B_pct': pct(bestB),
            'saving_AB_pct': pct(bestAB),
            'gain_A_bytes': gA, 'gain_B_bytes': gB, 'gain_AB_bytes': gAB,
            'interaction_bytes': inter,
            'interaction_positive': bool(inter > 0),
            'AB_beats_baseline': bool(bestAB['physical_bytes'] < b_base),
            'AB_beats_A': bool(bestAB['physical_bytes'] < bestA['physical_bytes']),
            'AB_beats_B': bool(bestAB['physical_bytes'] < bestB['physical_bytes']),
            'AB_meets_2_13pct': bool(pct(bestAB) >= BREAK_EVEN),
            'GiB_per_token_AB_scaled': (bestAB['physical_bytes'] / b_base) * BASE_GIB_TOK,
        }
        row['accept_gate_met'] = bool(row['AB_meets_2_13pct'] and
                                      row['AB_beats_A'] and row['AB_beats_B'])
        sweep.append(row)

    out['sweep'] = sweep
    any_accept = any(r['accept_gate_met'] for r in sweep)
    out['accept_gate_met_anywhere'] = bool(any_accept)
    out['reject_gate_met'] = not bool(any_accept)
    out['verdict'] = 'confirmed' if any_accept else 'falsified'
    out['best_saving_AB_pct'] = max(r['saving_AB_pct'] for r in sweep)
    out['max_interaction_bytes'] = max(r['interaction_bytes'] for r in sweep)
    out['best_GiB_per_token_AB_scaled'] = min(r['GiB_per_token_AB_scaled'] for r in sweep)
    out['target_GiB_per_token_for_15tps'] = NEED_GIB_TOK

    out['objective_check'] = {
        'metric': 'physical bytes per accepted token = physical_reads * '
                  'RECORD_BYTES / accepted_tokens',
        'algebra': 'B_acc = (m_demand + f_prefetch) * RECORD_B / a. Arm A moves '
                   'only m_demand (which lines survive eviction). Arm B adds '
                   'f_prefetch (>=0, strictly additive) and can only lower '
                   'm_demand by at most the number of prefetches that are '
                   'later demanded, i.e. dB_acc/d(prefetch) = '
                   '(1 - P(useful)) * RECORD_B / a >= 0. Acceptance rate a is '
                   'untouched by both arms (neither changes routing or the '
                   'verifier), so this is a pure numerator experiment and is '
                   'algebraically identical to bytes/accepted token.',
    }

    json.dump(out, open(f'{OUT}/exp6_result.json', 'w'), indent=2)

    print(f"exp6 FACTORIAL [PROXY replay] trace {len(rows)} tok x {L} lay x top-{K}, "
          f"{N} accesses, {D} distinct")
    print(f"K3-equivalent cap = {cap_eq} slots ({ratio:.2f}x working set)")
    print(f"VALIDITY: SLRU(prot=0) reads={slru_deg['physical_reads']} == "
          f"LRU baseline={base_eq['physical_reads']} -> PASS\n")
    print(f"{'cap':>6} {'base_rd':>8} | {'A%':>7} {'B%':>7} {'AB%':>7} | "
          f"{'interact_B':>14} {'>AB_A':>6} {'>AB_B':>6} {'>=2.13%':>8} {'ACC':>5}")
    for r in sweep:
        print(f"{r['cap']:6} {r['baseline_reads']:8} | "
              f"{r['saving_A_pct']:+6.2f}% {r['saving_B_pct']:+6.2f}% "
              f"{r['saving_AB_pct']:+6.2f}% | {r['interaction_bytes']:+14,.0f} "
              f"{str(r['AB_beats_A']):>6} {str(r['AB_beats_B']):>6} "
              f"{str(r['AB_meets_2_13pct']):>8} {str(r['accept_gate_met']):>5}")
    print(f"\nbest A+B saving: {out['best_saving_AB_pct']:+.3f}%  "
          f"(gate needs >= {BREAK_EVEN}%)")
    print(f"max interaction: {out['max_interaction_bytes']:+,.0f} bytes")
    print(f"best GiB/token (A+B, scaled): {out['best_GiB_per_token_AB_scaled']:.4f}"
          f"  target {NEED_GIB_TOK}")
    print(f"ACCEPT gate met anywhere: {any_accept}")
    print(f"VERDICT: {out['verdict']}")
    print(f"wrote {OUT}/exp6_result.json")


if __name__ == '__main__':
    main()
