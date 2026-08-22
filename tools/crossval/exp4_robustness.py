#!/usr/bin/env python3
"""exp4 robustness: is the tiny EV win systematic or a cache-warming artifact?

Finer cap sweep around and above the K3-equivalent point, plus an over-read
sensitivity check. Same replay engine as exp4_ev_prefetch.py.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from exp4_ev_prefetch import load, build, replay, RECORD_BYTES

rows = load()
acc, bounds = build(rows)
L = len(rows[0]['layers']); K = len(rows[0]['layers'][0])
WS = L * K
cap_eq = int(round((92 * 16 and 5015 / (92 * 16)) * WS))

print(f"K3-equivalent cap = {cap_eq}\n")
print(f"{'cap':>6} {'xWS':>5} {'off':>7} {'uncond':>7} {'unc%':>7} "
      f"{'bestEV':>7} {'EV%':>7} {'thr':>6} {'pf_iss':>7} {'win_rd':>7}")

caps = [500, 600, 709, 800, 900, 1000, 1100, 1270, 1400, 1600, 1800,
        2033, 2400, 3049, 4000]
rowsout = []
wins = 0
for cap in caps:
    off = replay(acc, bounds, rows, cap, 'off')
    unc = replay(acc, bounds, rows, cap, 'uncond')
    best = None
    for th in [-2.0, -1.0, -0.5, -0.25, 0.0, 0.5]:
        ev = replay(acc, bounds, rows, cap, 'ev', thresh=th)
        if best is None or ev['physical_reads'] < best['physical_reads']:
            best = ev
    d_unc = (unc['physical_reads'] / off['physical_reads'] - 1) * 100
    d_ev = (best['physical_reads'] / off['physical_reads'] - 1) * 100
    win = off['physical_reads'] - best['physical_reads']
    if win > 0:
        wins += 1
    print(f"{cap:6} {cap/WS:5.2f} {off['physical_reads']:7} "
          f"{unc['physical_reads']:7} {d_unc:+6.2f}% "
          f"{best['physical_reads']:7} {d_ev:+6.2f}% {best['thresh']:6.2f} "
          f"{best['ev_prefetched']:7} {win:7}")
    rowsout.append({'cap': cap, 'xWS': cap / WS,
                    'off': off['physical_reads'],
                    'uncond': unc['physical_reads'],
                    'uncond_pct': d_unc,
                    'best_ev': best['physical_reads'],
                    'ev_pct': d_ev, 'thresh': best['thresh'],
                    'ev_prefetched': best['ev_prefetched'],
                    'win_reads': win})

print(f"\ncaps where EV strictly beats off: {wins}/{len(caps)}")
best_win = max(r['win_reads'] for r in rowsout)
worst = min(r['ev_pct'] for r in rowsout)
print(f"largest absolute win: {best_win} reads")
print(f"best relative win:    {worst:+.3f}%")
print(f"break-even needed for speculation family: 2.13%")
print(f"reduction needed for 15 tok/s:            19.56x (=94.9% fewer bytes)")

# K3-equivalent detail: every threshold
print(f"\n--- K3-equivalent cap {cap_eq}: full threshold sweep ---")
off = replay(acc, bounds, rows, cap_eq, 'off')
print(f"lookahead-off physical reads = {off['physical_reads']}")
det = []
for th in [-3.0, -2.0, -1.5, -1.0, -0.5, -0.25, -0.1, 0.0, 0.1, 0.5, 1.0]:
    ev = replay(acc, bounds, rows, cap_eq, 'ev', thresh=th)
    d = (ev['physical_reads'] / off['physical_reads'] - 1) * 100
    print(f"  thr={th:+5.2f}  reads={ev['physical_reads']:7} ({d:+6.3f}%)  "
          f"prefetched={ev['ev_prefetched']:6} skipped={ev['ev_skipped']:6} "
          f"useful={ev['prefetch_useful']:6} "
          f"evicted_unused={ev['prefetch_evicted_unused']:6}")
    det.append({'thresh': th, 'reads': ev['physical_reads'], 'pct': d,
                'prefetched': ev['ev_prefetched'],
                'useful': ev['prefetch_useful'],
                'evicted_unused': ev['prefetch_evicted_unused']})

dst = os.path.expanduser(
    '~/.hermes/state/warp-research/evidence/exp4/exp4_robustness.json')
with open(dst, 'w') as f:
    json.dump({'cap_sweep': rowsout, 'k3_equiv_cap': cap_eq,
               'k3_equiv_off_reads': off['physical_reads'],
               'k3_equiv_threshold_sweep': det,
               'caps_with_strict_win': wins, 'caps_tested': len(caps)},
              f, indent=2)
print(f"\nwrote {dst}")
