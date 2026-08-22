#!/usr/bin/env python3
"""exp4 -- option-value-prefetch: EV-gated prefetch replay.

Preregistered spec:
  Replay trace with EV-gated prefetch: value = P(demanded before evict)*stall
  - bytes_cost - displacement_cost. Compare physical bytes vs lookahead-off
  and vs unconditional lookahead.
  ACCEPT: EV-gated beats lookahead-off on physical bytes.
  REJECT: cannot beat lookahead-off -> DEAD.

Trace: tests/trace_kimi_300.jsonl  [PROXY -- Kimi-Linear-shaped, NOT K3]
Cache: LRU at K3-equivalent 3.41x working set.
Metric: physical expert-record reads (bytes = reads * RECORD_BYTES).

Every arm is replayed on the IDENTICAL demand sequence; only the prefetch
policy differs. Prefetched lines enter the same LRU as demand lines, so
displacement is modelled, not assumed away.
"""
import json, os, sys
from collections import OrderedDict, defaultdict

TRACE = os.path.join(os.path.dirname(__file__), '..', '..', 'tests',
                     'trace_kimi_300.jsonl')
RECORD_BYTES = 12406784          # 3029 pages exactly (established finding)
GIB = 1024.0 ** 3


def load():
    rows = [json.loads(l) for l in open(TRACE)]
    return rows


def build(rows):
    """Flat demand access list plus (token, layer) index boundaries."""
    acc, bounds = [], []
    for r in rows:
        for li, lay in enumerate(r['layers']):
            start = len(acc)
            for e in lay:
                acc.append((li, e))
            bounds.append((r['tok'], li, start, len(acc)))
    return acc, bounds


class LRU:
    def __init__(self, cap):
        self.cap = cap
        self.od = OrderedDict()
        self.demand_miss = 0
        self.prefetch_fetch = 0
        self.prefetch_useful = 0
        self.prefetch_wasted = 0
        self.evicted_prefetch_unused = 0
        # tag -> True if line was brought in by prefetch and not yet demanded
        self.pf_pending = set()

    def _evict(self):
        k, _ = self.od.popitem(last=False)
        if k in self.pf_pending:
            self.pf_pending.discard(k)
            self.evicted_prefetch_unused += 1
        return k

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
            return False           # already resident: no physical read
        self.prefetch_fetch += 1
        if len(self.od) >= self.cap:
            self._evict()
        self.od[k] = 1
        self.pf_pending.add(k)
        return True

    @property
    def physical(self):
        return self.demand_miss + self.prefetch_fetch


def predictor_table(rows):
    """Cheap realistic predictor: experts used at (layer) in the PREVIOUS token.

    This is the only lookahead signal actually available at decode time --
    the next layer's routing is not known until the current layer completes.
    """
    return None  # built online during replay


def replay(acc, bounds, rows, cap, mode, thresh=0.0, overread=0.0):
    """mode: 'off' | 'uncond' | 'ev'"""
    c = LRU(cap)
    prev_layer_experts = {}          # layer -> list of experts (previous token)
    # online reuse statistics for the EV estimate
    hit_hist = defaultdict(lambda: [1, 2])   # (layer) -> [hits, trials] Laplace
    idx_by_tl = {(t, li): (s, e) for (t, li, s, e) in bounds}
    toks = [r['tok'] for r in rows]
    nlay = len(rows[0]['layers'])

    ev_prefetched = 0
    ev_skipped = 0

    for ti, r in enumerate(rows):
        for li, lay in enumerate(r['layers']):
            # ---- prefetch decision for the NEXT layer, issued before demand
            nli = li + 1
            if mode != 'off' and nli < nlay:
                cand = prev_layer_experts.get(nli, [])
                for e in cand:
                    k = (nli, e)
                    h, n = hit_hist[nli]
                    p = h / n                       # P(prefetch is demanded)
                    if mode == 'uncond':
                        do = True
                    else:
                        # value = p*stall - bytes_cost - displacement_cost
                        # normalised in units of one record read:
                        #   stall avoided if hit      = 1 record
                        #   bytes cost if it misses   = 1 record (always paid)
                        #   displacement cost         = P(evicted line reused)
                        occ = len(c.od) / c.cap
                        disp = occ * (h / n)
                        val = p * 1.0 - 1.0 - disp
                        do = val > thresh
                    if do:
                        c.prefetch(k)
                        ev_prefetched += 1
                    else:
                        ev_skipped += 1

            # ---- actual demand
            for e in lay:
                k = (li, e)
                c.demand(k)

            # update predictor accuracy stats for this layer
            if li in prev_layer_experts:
                prev = set(prev_layer_experts[li])
                cur = set(lay)
                if prev:
                    hit_hist[li][0] += len(prev & cur)
                    hit_hist[li][1] += len(prev)
            prev_layer_experts[li] = list(lay)

    return {
        'mode': mode, 'thresh': thresh, 'cap': cap,
        'demand_miss': c.demand_miss,
        'prefetch_fetch': c.prefetch_fetch,
        'prefetch_useful': c.prefetch_useful,
        'prefetch_evicted_unused': c.evicted_prefetch_unused,
        'physical_reads': c.physical,
        'physical_bytes': c.physical * RECORD_BYTES,
        'ev_prefetched': ev_prefetched, 'ev_skipped': ev_skipped,
    }


def main():
    rows = load()
    acc, bounds = build(rows)
    N = len(acc)
    D = len(set(acc))
    L = len(rows[0]['layers'])
    K = len(rows[0]['layers'][0])
    WS = L * K
    K3_WS, K3_CACHE = 92 * 16, 5015
    ratio = K3_CACHE / K3_WS
    cap_eq = int(round(ratio * WS))

    out = {
        'trace': {'tokens': len(rows), 'layers': L, 'topk': K,
                  'accesses': N, 'distinct': D,
                  'label': 'PROXY (Kimi-Linear-shaped, NOT K3)'},
        'cache': {'K3_working_set': K3_WS, 'K3_cache': K3_CACHE,
                  'ratio': ratio, 'proxy_cap_equiv': cap_eq},
        'record_bytes': RECORD_BYTES,
        'arms': [], 'sweep': [],
    }

    caps = sorted({cap_eq, 762, 1270, 2033, 3049})
    for cap in caps:
        off = replay(acc, bounds, rows, cap, 'off')
        unc = replay(acc, bounds, rows, cap, 'uncond')
        row = {'cap': cap, 'off': off, 'uncond': unc, 'ev': []}
        best = None
        for th in [-2.0, -1.5, -1.0, -0.5, -0.25, -0.1, 0.0, 0.1, 0.5]:
            ev = replay(acc, bounds, rows, cap, 'ev', thresh=th)
            ev['delta_vs_off_pct'] = (ev['physical_reads'] /
                                      off['physical_reads'] - 1) * 100
            row['ev'].append(ev)
            if best is None or ev['physical_reads'] < best['physical_reads']:
                best = ev
        row['best_ev'] = best
        row['uncond_delta_vs_off_pct'] = (unc['physical_reads'] /
                                          off['physical_reads'] - 1) * 100
        row['best_ev_delta_vs_off_pct'] = best['delta_vs_off_pct']
        row['beats_off'] = best['physical_reads'] < off['physical_reads']
        out['sweep'].append(row)

    print(f"exp4 EV-gated prefetch -- [PROXY] trace {len(rows)} tok x {L} lay "
          f"x top-{K}, {N} accesses, {D} distinct")
    print(f"K3-equivalent cap = {cap_eq} slots ({ratio:.2f}x working set)\n")
    hdr = (f"{'cap':>6} {'off_rd':>8} {'uncond':>8} {'unc%':>7} "
           f"{'bestEV':>8} {'EV%':>7} {'thr':>6} {'pf_iss':>8} {'beats?':>7}")
    print(hdr)
    for row in out['sweep']:
        b = row['best_ev']
        print(f"{row['cap']:6} {row['off']['physical_reads']:8} "
              f"{row['uncond']['physical_reads']:8} "
              f"{row['uncond_delta_vs_off_pct']:+6.2f}% "
              f"{b['physical_reads']:8} {b['delta_vs_off_pct']:+6.2f}% "
              f"{b['thresh']:6.2f} {b['ev_prefetched']:8} "
              f"{str(row['beats_off']):>7}")

    any_beat = any(r['beats_off'] for r in out['sweep'])
    out['verdict'] = 'confirmed' if any_beat else 'falsified'
    out['gate'] = ('ACCEPT: EV-gated beats lookahead-off on physical bytes; '
                   'REJECT: cannot beat lookahead-off -> DEAD')
    print(f"\nAny cap where EV-gated BEATS lookahead-off on physical bytes: "
          f"{any_beat}")
    print(f"VERDICT: {out['verdict']}")

    dst = os.path.expanduser(
        '~/.hermes/state/warp-research/evidence/exp4/exp4_result.json')
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"wrote {dst}")


if __name__ == '__main__':
    main()
