#!/usr/bin/env python3
"""exp4 attribution: are the off-design 'wins' caused by EV GATING, or are they
just unconditional prefetch reordering LRU evictions?

If best-EV == uncond at a winning cap, the EV gate contributed nothing: the
optimum threshold was simply 'prefetch everything'.
"""
import json, os

p = os.path.expanduser(
    '~/.hermes/state/warp-research/evidence/exp4/exp4_robustness.json')
d = json.load(open(p))

print(f"{'cap':>6} {'win_rd':>7} {'thr':>6} {'bestEV':>7} {'uncond':>7} "
      f"{'EV==uncond?':>12} {'gate_credit':>11}")
gate_credit_total = 0
wins = []
for r in d['cap_sweep']:
    same = r['best_ev'] == r['uncond']
    # reads saved attributable to the GATE = uncond - bestEV (positive only)
    credit = r['uncond'] - r['best_ev']
    gate_credit_total += max(credit, 0)
    if r['win_reads'] > 0:
        wins.append(r)
    print(f"{r['cap']:6} {r['win_reads']:7} {r['thresh']:6.2f} "
          f"{r['best_ev']:7} {r['uncond']:7} {str(same):>12} {credit:11}")

print(f"\nwins vs lookahead-off: {len(wins)}/{len(d['cap_sweep'])} caps")
degenerate = [r for r in wins if r['best_ev'] == r['uncond']]
print(f"  of those, EV optimum == unconditional prefetch (gate inert): "
      f"{len(degenerate)}/{len(wins)}")
print(f"  reads attributable to the EV GATE itself, summed over ALL caps: "
      f"{gate_credit_total}")

# sign consistency
signs = [1 if r['win_reads'] > 0 else (0 if r['win_reads'] == 0 else -1)
         for r in d['cap_sweep']]
print(f"\nuncond sign flips across caps (a systematic effect should not flip):")
for r in d['cap_sweep']:
    print(f"  cap {r['cap']:5}: uncond {r['uncond_pct']:+6.3f}%  "
          f"{'REGRESSION' if r['uncond_pct'] > 0 else ('tie' if r['uncond_pct'] == 0 else 'gain')}")

pos = sum(1 for r in d['cap_sweep'] if r['uncond_pct'] > 0)
neg = sum(1 for r in d['cap_sweep'] if r['uncond_pct'] < 0)
zer = sum(1 for r in d['cap_sweep'] if r['uncond_pct'] == 0)
print(f"\nunconditional lookahead: {pos} regressions, {neg} gains, {zer} ties "
      f"-> sign is NOT stable; magnitude max |{max(abs(r['uncond_pct']) for r in d['cap_sweep']):.3f}|%")

# the preregistered operating point
ce = d['k3_equiv_cap']
off = d['k3_equiv_off_reads']
best = min(x['reads'] for x in d['k3_equiv_threshold_sweep'])
print(f"\n=== PREREGISTERED OPERATING POINT (K3-equivalent cap {ce}) ===")
print(f"lookahead-off reads      = {off}")
print(f"best EV-gated reads      = {best}")
print(f"delta                    = {best - off} reads "
      f"({(best/off - 1)*100:+.4f}%)")
print(f"BEATS lookahead-off?     = {best < off}")
zero_pf = [x for x in d['k3_equiv_threshold_sweep']
           if x['prefetched'] == 0]
print(f"thresholds where the gate prefetches NOTHING (degenerates to 'off'): "
      f"{len(zero_pf)}/{len(d['k3_equiv_threshold_sweep'])}")
print(f"prefetch_useful at every threshold: "
      f"{sorted({x['useful'] for x in d['k3_equiv_threshold_sweep']})}")

out = {
    'k3_equiv_cap': ce, 'off_reads': off, 'best_ev_reads': best,
    'delta_reads': best - off, 'delta_pct': (best / off - 1) * 100,
    'beats_off_at_operating_point': best < off,
    'wins_caps': len(wins), 'caps_tested': len(d['cap_sweep']),
    'degenerate_wins': len(degenerate),
    'gate_attributable_reads_all_caps': gate_credit_total,
    'uncond_sign': {'regressions': pos, 'gains': neg, 'ties': zer},
    'max_abs_uncond_pct': max(abs(r['uncond_pct']) for r in d['cap_sweep']),
    'break_even_pct': 2.13,
    'required_reduction_pct': 94.9,
}
dst = os.path.expanduser(
    '~/.hermes/state/warp-research/evidence/exp4/exp4_attribution.json')
json.dump(out, open(dst, 'w'), indent=2)
print(f"\nwrote {dst}")
