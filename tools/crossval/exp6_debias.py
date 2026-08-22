#!/usr/bin/env python3
"""
exp6 ADDENDUM: selection-bias de-biasing + K3-equivalent operating point.

The headline factorial picks each arm's best cell from grids of different
sizes (A: 5 prot_fracs; B: 9 thresholds; A+B: 45 cells). A best-of-45 arm
will beat a best-of-5 arm on a finite trace even if the two policies are
identical in expectation. This addendum removes that bias two ways:

 1. MATCHED PAIRS: at each (cap, prot_frac), compare A(pf) against
    AB(pf, best-threshold). Same protected fraction, so the ONLY difference
    is the prefetcher. This isolates the true marginal effect of B given A.
 2. K3-EQUIVALENT ONLY: the goal is K3 at 3.41x working set. Report the
    gate at cap_eq alone, since the other capacities are not reachable
    configurations for the target rig.

Label: PROXY replay (tests/trace_kimi_300.jsonl) + RECOMPUTATION.
"""
import json, os, statistics
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'exp6', os.path.join(HERE, 'exp6_chaperone_ev_factorial.py'))
exp6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp6)

OUT = os.path.expanduser('~/.hermes/state/warp-research/evidence/exp6')
BREAK_EVEN = 2.13

rows = [json.loads(l) for l in open(exp6.TRACE)]
L, K = len(rows[0]['layers']), len(rows[0]['layers'][0])
WS = L * K
cap_eq = int(round((92 * 16 and 5015 / (92 * 16)) * WS))

prot_fracs = [0.2, 0.4, 0.5, 0.6, 0.8]
ev_thresholds = [-2.0, -1.5, -1.0, -0.5, -0.25, -0.1, 0.0, 0.1, 0.5]
caps = sorted({cap_eq, 762, 1270, 2033, 3049})

res = {'label': 'PROXY replay + RECOMPUTATION',
       'sources': {'tests/trace_kimi_300.jsonl': exp6.sha256(exp6.TRACE)},
       'cap_eq': cap_eq, 'note': 'de-biased matched-pair analysis of exp6'}

matched = []
for cap in caps:
    base = exp6.replay(rows, cap, 'lru', 'off')
    b_base = base['physical_bytes']
    for pf in prot_fracs:
        a = exp6.replay(rows, cap, 'slru', 'off', prot_frac=pf)
        best_ab, best_th = None, None
        for th in ev_thresholds:
            r = exp6.replay(rows, cap, 'slru', 'ev', thresh=th, prot_frac=pf)
            if best_ab is None or r['physical_reads'] < best_ab['physical_reads']:
                best_ab, best_th = r, th
        marginal = (a['physical_bytes'] - best_ab['physical_bytes'])
        matched.append({
            'cap': cap, 'prot_frac': pf,
            'A_reads': a['physical_reads'],
            'AB_reads': best_ab['physical_reads'],
            'best_threshold': best_th,
            'prefetches_issued': best_ab['prefetch_fetch'],
            'prefetch_useful': best_ab['prefetch_useful'],
            'marginal_B_given_A_bytes': marginal,
            'marginal_B_given_A_pct_of_base': marginal / b_base * 100.0,
            'B_helps': bool(best_ab['physical_reads'] < a['physical_reads']),
        })
res['matched_pairs'] = matched

n_help = sum(1 for m in matched if m['B_helps'])
marg = [m['marginal_B_given_A_pct_of_base'] for m in matched]
res['matched_summary'] = {
    'cells': len(matched), 'cells_where_B_helps_given_A': n_help,
    'marginal_pct_mean': statistics.mean(marg),
    'marginal_pct_max': max(marg), 'marginal_pct_min': min(marg),
    'marginal_pct_stdev': statistics.pstdev(marg),
    'total_prefetches_issued_across_cells':
        sum(m['prefetches_issued'] for m in matched),
}

# ---- K3-equivalent operating point, gate evaluated there only ----
base = exp6.replay(rows, cap_eq, 'lru', 'off')
b_base = base['physical_bytes']
bA = min((exp6.replay(rows, cap_eq, 'slru', 'off', prot_frac=pf)
          for pf in prot_fracs), key=lambda r: r['physical_reads'])
bB = min((exp6.replay(rows, cap_eq, 'lru', 'ev', thresh=th)
          for th in ev_thresholds), key=lambda r: r['physical_reads'])
bAB = min((exp6.replay(rows, cap_eq, 'slru', 'ev', thresh=th, prot_frac=pf)
           for pf in prot_fracs for th in ev_thresholds),
          key=lambda r: r['physical_reads'])
sv = lambda r: (1 - r['physical_bytes'] / b_base) * 100
res['k3_equivalent_point'] = {
    'cap': cap_eq, 'working_set_ratio': 3.41,
    'baseline_reads': base['physical_reads'],
    'A_saving_pct': sv(bA), 'B_saving_pct': sv(bB), 'AB_saving_pct': sv(bAB),
    'interaction_bytes': ((b_base - bAB['physical_bytes'])
                          - (b_base - bA['physical_bytes'])
                          - (b_base - bB['physical_bytes'])),
    'AB_beats_A': bool(bAB['physical_reads'] < bA['physical_reads']),
    'AB_beats_B': bool(bAB['physical_reads'] < bB['physical_reads']),
    'AB_meets_2_13pct': bool(sv(bAB) >= BREAK_EVEN),
    'B_prefetches_issued_at_best': bAB['prefetch_fetch'],
    'accept_gate_met_at_K3_equiv': bool(sv(bAB) >= BREAK_EVEN
                                        and bAB['physical_reads'] < bA['physical_reads']
                                        and bAB['physical_reads'] < bB['physical_reads']),
}
k = res['k3_equivalent_point']
res['reject_gate_met_at_K3_equiv'] = bool(not k['accept_gate_met_at_K3_equiv'])

json.dump(res, open(f'{OUT}/exp6_debias.json', 'w'), indent=2)

print("=== MATCHED-PAIR: marginal effect of EV prefetch GIVEN protected admission ===")
print(f"{'cap':>6} {'pf':>5} {'A_rd':>8} {'AB_rd':>8} {'thr':>6} {'pf_iss':>7} "
      f"{'marg%':>8} {'Bhelps':>7}")
for m in matched:
    print(f"{m['cap']:6} {m['prot_frac']:5.1f} {m['A_reads']:8} {m['AB_reads']:8} "
          f"{m['best_threshold']:6.2f} {m['prefetches_issued']:7} "
          f"{m['marginal_B_given_A_pct_of_base']:+7.3f}% {str(m['B_helps']):>7}")
s = res['matched_summary']
print(f"\ncells where B helps given A: {s['cells_where_B_helps_given_A']}/{s['cells']}")
print(f"marginal effect of B: mean {s['marginal_pct_mean']:+.4f}%  "
      f"max {s['marginal_pct_max']:+.4f}%  stdev {s['marginal_pct_stdev']:.4f}%")
print(f"total prefetches issued across all cells: "
      f"{s['total_prefetches_issued_across_cells']}")
print(f"\n=== K3-EQUIVALENT OPERATING POINT (cap={cap_eq}, 3.41x WS) ===")
print(json.dumps(k, indent=2))
print(f"\nREJECT gate met at K3-equivalent point: {res['reject_gate_met_at_K3_equiv']}")
print(f"wrote {OUT}/exp6_debias.json")
