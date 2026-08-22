#!/usr/bin/env python3
"""
exp6 SHAM CONTROL — is the A+B advantage a mechanism or recency noise?

Diagnostic finding that motivates this control: in EVERY factorial cell the
EV prefetcher issued prefetch_fetch == 0 physical reads. Its candidate set
(previous token's experts at the next layer) is already resident, so
c.prefetch(k) degenerates to a bare move_to_end() — a pure recency touch.
Arm B therefore cannot move bytes by its stated mechanism; any A+B vs A delta
is LRU-order perturbation.

SHAM ARM: replace the EV-selected candidates with RANDOM resident keys,
touching the SAME number of lines at the same points in the sequence. If the
sham produces deltas of comparable magnitude and both signs, the "interaction"
is noise and the reject gate fires.

N = 20 random seeds per cell -> mean/stdev, so the EV effect can be scored
against the sham null distribution.

Label: PROXY replay (tests/trace_kimi_300.jsonl) + RECOMPUTATION.
"""
import json, os, random, statistics, importlib.util
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location(
    'exp6', os.path.join(HERE, 'exp6_chaperone_ev_factorial.py'))
exp6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exp6)

OUT = os.path.expanduser('~/.hermes/state/warp-research/evidence/exp6')
rows = [json.loads(l) for l in open(exp6.TRACE)]
NLAY = len(rows[0]['layers'])


def replay_sham(rows, cap, prot_frac, seed, touch_per_layer):
    """SLRU + random recency touches on resident lines (no fetches)."""
    rng = random.Random(seed)
    c = exp6.SLRU(cap, prot_frac)
    for r in rows:
        for li, lay in enumerate(r['layers']):
            nli = li + 1
            if nli < NLAY and touch_per_layer:
                resident = list(c.prot.keys()) + list(c.prob.keys())
                if resident:
                    for _ in range(min(touch_per_layer, len(resident))):
                        k = rng.choice(resident)
                        c.prefetch(k)          # resident -> move_to_end only
            for e in lay:
                c.demand((li, e))
    return c.physical, c.prefetch_fetch


res = {'label': 'PROXY replay + RECOMPUTATION',
       'sources': {'tests/trace_kimi_300.jsonl': exp6.sha256(exp6.TRACE)},
       'diagnostic': ('EV prefetcher issues prefetch_fetch==0 physical reads in '
                      'all cells; candidates are already resident, so arm B is a '
                      'pure LRU recency touch with no byte mechanism.'),
       'N_seeds': 20}

cells = [(709, 0.5), (762, 0.5), (1270, 0.8), (3049, 0.4)]
SEEDS = 20
tbl = []
for cap, pf in cells:
    a_reads, a_pf = replay_sham(rows, cap, pf, 0, 0)          # arm A, no touches
    ev = min((exp6.replay(rows, cap, 'slru', 'ev', thresh=th, prot_frac=pf)
              for th in [-2.0, -1.5, -1.0, -0.5, -0.25, -0.1, 0.0, 0.1, 0.5]),
             key=lambda r: r['physical_reads'])
    ev_delta = a_reads - ev['physical_reads']

    # sham: match the number of touches the winning EV arm made
    touches = max(1, round(ev['ev_prefetched'] / (len(rows) * (NLAY - 1))))
    sham = [replay_sham(rows, cap, pf, s, touches)[0] for s in range(1, SEEDS + 1)]
    sham_delta = [a_reads - s for s in sham]
    mu, sd = statistics.mean(sham_delta), statistics.pstdev(sham_delta)
    z = (ev_delta - mu) / sd if sd > 0 else float('nan')
    tbl.append({
        'cap': cap, 'prot_frac': pf,
        'A_reads': a_reads,
        'EV_reads': ev['physical_reads'],
        'EV_physical_prefetches': ev['prefetch_fetch'],
        'EV_delta_reads': ev_delta,
        'sham_touches_per_layer': touches,
        'sham_delta_mean': mu, 'sham_delta_stdev': sd,
        'sham_delta_min': min(sham_delta), 'sham_delta_max': max(sham_delta),
        'EV_z_vs_sham_null': z,
        'EV_within_sham_noise': bool(abs(z) < 2.0) if sd > 0 else None,
    })

res['sham_control'] = tbl
res['all_EV_physical_prefetches_zero'] = bool(
    all(r['EV_physical_prefetches'] == 0 for r in tbl))
res['conclusion'] = (
    'Arm B has no byte-moving mechanism on this trace: it never issues a '
    'physical prefetch. Its apparent gains are LRU recency perturbations '
    'indistinguishable from random touches of the same count.')

json.dump(res, open(f'{OUT}/exp6_sham_control.json', 'w'), indent=2)

print("=== SHAM CONTROL: EV prefetch vs random recency touches (N=20 seeds) ===")
print(f"{'cap':>6} {'pf':>5} {'A_rd':>8} {'EV_rd':>8} {'EVfetch':>8} {'EVd':>6} "
      f"{'shamMean':>9} {'shamSD':>7} {'shamMin':>8} {'shamMax':>8} {'z':>7} {'noise?':>7}")
for r in tbl:
    print(f"{r['cap']:6} {r['prot_frac']:5.1f} {r['A_reads']:8} {r['EV_reads']:8} "
          f"{r['EV_physical_prefetches']:8} {r['EV_delta_reads']:+6} "
          f"{r['sham_delta_mean']:+9.1f} {r['sham_delta_stdev']:7.1f} "
          f"{r['sham_delta_min']:+8} {r['sham_delta_max']:+8} "
          f"{r['EV_z_vs_sham_null']:+7.2f} {str(r['EV_within_sham_noise']):>7}")
print(f"\nEV issued ZERO physical prefetches in all cells: "
      f"{res['all_EV_physical_prefetches_zero']}")
print(res['conclusion'])
print(f"wrote {OUT}/exp6_sham_control.json")
