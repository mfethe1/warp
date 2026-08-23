#!/usr/bin/env python3
"""
exp21: certified-skip (A, idea16) x miss-conditioned makespan coloring (B, idea24)
FACTORIAL -- does certified skip invalidate device placement?

Lane: offline. Evidence class target: PROXY replay + RECOMPUTATION over REAL-K3
certification curve. NO kernel, NO Winnie, NO K3 measurement.

PREREGISTERED FROZEN DECISIONS (written BEFORE running; see WRITEUP):
  F1 Cache: LRU, capacity cap_eq = round((5015/1472)*208) = 709 slots
     (K3-equivalent cache/working-set ratio; established finding 3.41x WS).
  F2 Metric: per token t, per layer l, surviving miss set -> device bytes
     n_{l,d} * RECORD_B (RECORD_B=12,406,784 B, exp5-verified 3029 pages);
     per-layer time = max_d(n_{l,d}*RECORD_B/beta_d); beta=(5.919,5.919) GiB/s
     symmetric measured pair (exp17, Samsung 990 Pro derated).
     Primary metric = MEAN over held-out tokens 200-299 of the per-token mean
     over the 26 layers of that per-layer max-device time (ms/token).
     p95 over layer-steps reported as diagnostic only.
  F3 Certification model: each MISS is independently certified (pread suppressed)
     with probability s_cert (Bernoulli, seeded RNG). s_cert values are the
     REAL-K3 sprint11-route-margin-summary.json published curve points with
     s_cert >= 0.03 (stop-rule floor), plus the exp12/exp36 evidence-backed
     operating point s_cert=0.3375 (bound <= 5.34724e-4). Certification
     is per-miss-event, identical draw shared across all arms at a given (s, seed).
     NO expert-identity conditioning: exp11 established sprint11 carries no
     margin<->expert coupling, so no color-correlated certification is assumed.
  F4 Coloring: per layer, conflict graph on (expert_i, expert_j) miss
     co-occurrence within a layer-step, weighted by counts on calibration
     tokens 0-199. Balanced 2-coloring = spectral bisection (Fiedler vector,
     median split, sign fixed by positive-sum convention) + up to 3 greedy
     Kernighan-Lin passes maximizing mean-calibration-makespan reduction.
     One global color per expert per layer (static placement).
     Deterministic; seed affects only certification draws.
  F5 Arms:
     baseline   : static expert-id-parity split (capacity-weighted: rates equal), no certifier
     A          : certifier ON, static parity split
     B          : certifier OFF, coloring fit on FULL (uncertified) calibration miss trace
     A+B naive  : certifier ON, B's coloring (fit on uncertified trace)
     A+B cond   : certifier ON, coloring fit on SURVIVING (post-certification,
                  seed-averaged weights) calibration miss trace
  F6 Fit window tokens 0-199, evaluate ONLY tokens 200-299. No refit after
     seeing held-out numbers. N=5 certification seeds (1..5); byte counts and
     colorings are deterministic given seed. Report mean and sample sd.
  F7 Stop rule: if s_cert < 0.03 at an operating point -> inconclusive for
     that point, do not mine. All chosen points satisfy >= 0.03.
"""
import json, math, os, hashlib, datetime
from collections import OrderedDict, defaultdict
import numpy as np

REPO = '/tmp/warp-exp21'
OUT  = os.path.expanduser('~/.hermes/state/warp-research/evidence/exp21-certified-skip-coloring-factorial')
os.makedirs(OUT, exist_ok=True)

def sha256(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()

TRACE  = f'{REPO}/tests/trace_kimi_300.jsonl'
MARGIN = f'{REPO}/sprint11-route-margin-summary.json'
WARP_SHA   = '7f1fbba'  # pinned repo HEAD (main), mfethe1/warp
TRACE_SHA  = sha256(TRACE)
MARGIN_SHA = sha256(MARGIN)
assert TRACE_SHA == '06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965', TRACE_SHA
assert MARGIN_SHA == '1cfd9927fce60aea5ec220405923641821537431e8e3ab599837f2300d772295', MARGIN_SHA

RECORD_B = 12406784
GIB = 1024**3
BETA = (5.919 * GIB, 5.919 * GIB)  # bytes/s, symmetric measured pair (exp17)
SEEDS = [1, 2, 3, 4, 5]
CAL, HELD = range(0, 200), range(200, 300)
WS = 26 * 8
CAP = round((5015 / 1472) * WS)
assert CAP == 709

# ---------------- load trace ----------------
toks = [json.loads(l) for l in open(TRACE)]
assert len(toks) == 300
L = len(toks[0]['layers']); K = len(toks[0]['layers'][0]); E = 256
assert L == 26 and K == 8
accesses = [(li, e) for t in toks for li, ex in enumerate(t['layers']) for e in ex]
N = len(accesses); D = len(set(accesses))
assert N == 62400 and D == 5083

# ---------------- LRU replay -> per-token per-layer miss sets (deterministic) ----------------
cache = OrderedDict()
miss_sets = [[set() for _ in range(L)] for _ in range(300)]
for t in toks:
    for li, exs in enumerate(t['layers']):
        for e in exs:
            key = (li, e)
            if key in cache:
                cache.move_to_end(key)
            else:
                cache[key] = 1
                miss_sets[t['tok']][li].add(e)
                if len(cache) > CAP:
                    cache.popitem(last=False)
tot_miss = sum(len(s) for tt in miss_sets for s in tt)
print(f"LRU replay done: cap={CAP} ({CAP/WS:.2f}x WS), total miss events={tot_miss} "
      f"({tot_miss/N*100:.2f}% of {N} accesses)")

def per_layer_max_time(miss_by_dev, layer):
    """miss_by_dev: dict dev -> count for one layer-step."""
    ts = [miss_by_dev.get(d, 0) * RECORD_B / BETA[d] for d in (0, 1)]
    return max(ts)

def arm_metric(color_or_none, cert_mask_fn, token_range):
    """color: dict (layer,expert)->dev or None (parity). cert_mask_fn(t,l)->set of suppressed experts or None.
    Returns (mean ms/token over held-out tokens, p95 layer-step ms)."""
    per_tok = []
    all_layerstep = []
    for t in token_range:
        vals = []
        for l in range(L):
            m = miss_sets[t][l]
            if cert_mask_fn is not None:
                m = m - cert_mask_fn(t, l)
            if not m:
                vals.append(0.0); all_layerstep.append(0.0); continue
            cnt = {0: 0, 1: 0}
            for e in m:
                if color_or_none is None:
                    dev = e % 2
                else:
                    dev = color_or_none[(l, e)]
                cnt[dev] += 1
            v = per_layer_max_time(cnt, l)
            vals.append(v); all_layerstep.append(v)
        per_tok.append(sum(vals) / L)
    return float(np.mean(per_tok)) * 1000.0, float(np.percentile(all_layerstep, 95)) * 1000.0

# ---------------- certification draws (rebuilt per operating point, seed-deterministic) ----------------
def build_cert(s_cert):
    cm = {}
    for s in SEEDS:
        rng = np.random.default_rng(s)
        for t in range(300):
            for l in range(L):
                m = sorted(miss_sets[t][l])
                if m:
                    u = rng.random(len(m))
                    cm[(s, t, l)] = frozenset(e for e, x in zip(m, u) if x < s_cert)
                else:
                    cm[(s, t, l)] = frozenset()
    return cm

# ---------------- coloring machinery ----------------
C_TIME = RECORD_B / BETA[0] / 2.0  # symmetric rates: layer-step time = C_TIME*(|m| + |imbalance|)

def cooc_weights(token_range, cert=None):
    """cert: dict (t,l)->frozenset suppressed, or None. Returns per-layer edge weight dict."""
    W = [defaultdict(float) for _ in range(L)]
    for t in token_range:
        for l in range(L):
            m = miss_sets[t][l]
            if cert is not None:
                m = m - cert[(t, l)]
            m = sorted(m)
            for i in range(len(m)):
                for j in range(i + 1, len(m)):
                    W[l][(m[i], m[j])] += 1.0
    return W

def calib_layer_struct(l, cert=None):
    """Calibration SURVIVING miss lists for one layer: sorted tuples, non-empty steps only."""
    out = []
    for t in CAL:
        m = miss_sets[t][l]
        if cert is not None:
            m = m - cert[(t, l)]
        if m:
            out.append(tuple(sorted(m)))
    return out

def spectral_bisection(Wl):
    nodes = sorted({e for (i, j) in Wl for e in (i, j)})
    idx = {e: i for i, e in enumerate(nodes)}
    n = len(nodes)
    if n == 0:
        return {}
    if n == 1:
        return {nodes[0]: 0}
    A = np.zeros((n, n))
    for (i, j), w in Wl.items():
        A[idx[i], idx[j]] = w; A[idx[j], idx[i]] = w
    deg = A.sum(axis=1)
    Lap = np.diag(deg) - A
    evals, evecs = np.linalg.eigh(Lap)
    f = evecs[:, 1]
    if f.sum() < 0:
        f = -f
    order = sorted(nodes, key=lambda e: (f[idx[e]], e))
    half = n // 2
    color = {}
    lo = set(order[:half])
    for e in nodes:
        color[e] = 0 if e in lo else 1
    return color

def makespan_of_color(l, color, steps):
    tot = 0.0
    for m in steps:
        imb = sum(1 if color[e] == 0 else -1 for e in m)
        tot += C_TIME * (len(m) + abs(imb))
    return tot / len(steps) if steps else 0.0

def kl_refine(l, color, steps, passes=3):
    """Greedy Kernighan-Lin on calibration makespan, numpy-vectorized candidate scan.

    layer-step time = C_TIME*(|m| + |S_t|), S_t = sum_e sign(e), sign=+1 dev0, -1 dev1.
    Flipping expert e changes S_t by -2*sign(e) for every step containing e.
    """
    if not steps:
        return color
    color = dict(color)
    nodes = sorted({e for m in steps for e in m})
    exp_idx = {e: i for i, e in enumerate(nodes)}
    NE = len(nodes)
    # flat incidence: (step_idx, expert_idx)
    fs, fe = [], []
    for si, m in enumerate(steps):
        for e in m:
            fs.append(si); fe.append(exp_idx[e])
    fs = np.array(fs, dtype=np.int64); fe = np.array(fe, dtype=np.int64)
    S = np.array([sum(1 if color[e] == 0 else -1 for e in m) for m in steps], dtype=np.int64)
    sign = np.array([1 if color[e] == 0 else -1 for e in nodes], dtype=np.int64)
    NS = len(steps)

    def makespan_now():
        return float(C_TIME * (sum(len(m) for m in steps) + np.abs(S).sum()) / NS)

    base = makespan_now()
    best_global_color, best_global = dict(color), base
    for _p in range(passes):
        locked = np.zeros(NE, dtype=bool)
        best_prefix_color, best_prefix = dict(color), base
        made_move = False
        for _step in range(NE):
            flat_S = S[fs]
            contrib = np.abs(flat_S - 2 * sign[fe]) - np.abs(flat_S)
            delta = np.zeros(NE)
            np.add.at(delta, fe, contrib)
            delta[locked] = 0.0
            e_i = int(np.argmin(delta))
            best_delta = delta[e_i]
            if best_delta >= 0:
                break
            S[fs[fe == e_i]] -= 2 * sign[e_i]
            sign[e_i] = -sign[e_i]
            e = nodes[e_i]
            color[e] = 0 if sign[e_i] == 1 else 1
            locked[e_i] = True
            made_move = True
            cur = makespan_now()
            if cur < best_prefix - 1e-15:
                best_prefix, best_prefix_color = cur, dict(color)
        color, base = best_prefix_color, best_prefix
        # rebuild S/sign for best_prefix coloring (moves after prefix were rolled back)
        S = np.array([sum(1 if color[e] == 0 else -1 for e in m) for m in steps], dtype=np.int64)
        sign = np.array([1 if color[e] == 0 else -1 for e in nodes], dtype=np.int64)
        if base < best_global - 1e-15:
            best_global, best_global_color = base, dict(color)
        if not made_move:
            break
    return best_global_color

def fit_coloring(token_range, cert=None, kl_passes=3):
    W = cooc_weights(token_range, cert)
    color = {}
    for l in range(L):
        steps = calib_layer_struct(l, cert)
        c = spectral_bisection(W[l])
        # isolated nodes (appear in steps but no co-occurrence edge): parity fallback
        for m in steps:
            for e in m:
                if e not in c:
                    c[e] = e % 2
        if kl_passes > 0:
            c = kl_refine(l, c, steps, passes=kl_passes)
        # experts never seen in calibration: parity fallback (deterministic)
        for e in range(E):
            if e not in c:
                c[e] = e % 2
        for e in range(E):
            color[(l, e)] = c[e]
    return color

def fit_coloring_conditioned(cm_seedavg_steps, kl_passes=3):
    """Conditioned fit on per-layer SURVIVING steps concatenated across seeds (F5: seed-averaged)."""
    color = {}
    for l in range(L):
        steps = cm_seedavg_steps[l]
        Wl = defaultdict(float)
        for m in steps:
            for i in range(len(m)):
                for j in range(i + 1, len(m)):
                    Wl[(m[i], m[j])] += 1.0
        c = spectral_bisection(Wl)
        # isolated nodes (in steps but no co-occurrence edge): parity fallback before KL
        for m in steps:
            for e in m:
                if e not in c:
                    c[e] = e % 2
        if kl_passes > 0:
            c = kl_refine(l, c, steps, passes=kl_passes)
        for e in range(E):
            if e not in c:
                c[e] = e % 2
        for e in range(E):
            color[(l, e)] = c[e]
    return color

# ---------------- operating points (REAL-K3 sprint11 curve) ----------------
m = json.load(open(MARGIN))
ops = []
for r in sorted(m['score_error_risk'], key=lambda x: x['max_score_error']):
    s = 1.0 - r['fraction_not_certified']
    if s >= 0.03:  # stop-rule floor F7
        ops.append({'max_score_error': r['max_score_error'],
                    'required_margin': r['required_margin'],
                    's_cert_REAL_K3': s})
ops.append({'max_score_error': 5.34724e-4, 'required_margin': 1.06945e-3,
            's_cert_REAL_K3': 0.3375,
            'note': 'exp12/exp36 evidence-backed bound 5.34724e-4 operating point'})
ops.sort(key=lambda x: x['s_cert_REAL_K3'])

res = {
    'exp': 'exp21', 'slug': 'certified-skip-conditioned-makespan-coloring',
    'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'sources': {
        'warp_repo': f'mfethe1/warp@{WARP_SHA} (main)',
        'trace': TRACE_SHA, 'margin_summary': MARGIN_SHA,
        'margin_provenance': {'label': 'REAL-K3', 'rows': m['rows'], 'layers': m['layers'],
                              'positions': m['positions'], 'ties': m.get('exact_boundary_ties')},
        'evidence_class': 'PROXY replay (trace is Kimi-Linear-shaped 26L x top-8, NOT K3) x '
                          'RECOMPUTATION over REAL-K3 certification curve',
    },
    'frozen': {'cap': CAP, 'record_B': RECORD_B, 'beta_GiBs': [5.919, 5.919],
               'seeds': SEEDS, 'cal': '0-199', 'held': '200-299',
               'kl_passes': 3, 'spectral': 'eigh, fiedler, median split, positive-sum sign'},
    'replay': {'accesses_N': N, 'distinct': D, 'total_miss_events': tot_miss,
               'miss_rate': tot_miss / N},
}

# ---------------- arm B and baseline: seed-free ----------------
print("Fitting B coloring (uncertified calibration trace) ...")
color_B = fit_coloring(CAL, cert=None, kl_passes=3)
# A+B-conditioned colorings depend on s_cert; built per operating point below.

# baseline & B metrics (deterministic, single eval)
base_mean, base_p95 = arm_metric(None, None, HELD)
B_mean, B_p95 = arm_metric(color_B, None, HELD)
print(f"baseline mean={base_mean:.5f} ms/tok p95={base_p95:.5f}")
print(f"B alone  mean={B_mean:.5f} ms/tok p95={B_p95:.5f}")

# ---------------- operating-point loop ----------------
op_results = []
for op in ops:
    s = op['s_cert_REAL_K3']
    cm = build_cert(s)
    # conditioned coloring: fit on SURVIVING calibration miss trace, all seeds concatenated
    # (F5: conditioning on the seed-averaged surviving trace; no cherry-picking per seed)
    cond_steps = [[] for _ in range(L)]
    for sd in SEEDS:
        for t in CAL:
            for l in range(L):
                m = miss_sets[t][l] - cm[(sd, t, l)]
                if m:
                    cond_steps[l].append(tuple(sorted(m)))
    color_C = fit_coloring_conditioned(cond_steps, kl_passes=3)

    rows = []
    for sd in SEEDS:
        cert_fn = lambda t, l, sd=sd: cm[(sd, t, l)]
        A_mean, A_p95 = arm_metric(None, cert_fn, HELD)
        ABn_mean, ABn_p95 = arm_metric(color_B, cert_fn, HELD)
        ABc_mean, ABc_p95 = arm_metric(color_C, cert_fn, HELD)
        # certified fractions per color (held-out, using B's coloring as reference partition)
        ncol = {0: [0, 0], 1: [0, 0]}
        for t in HELD:
            for l in range(L):
                for e in sorted(miss_sets[t][l]):
                    d = color_B[(l, e)]
                    ncol[d][0] += 1
                    if e in cm[(sd, t, l)]:
                        ncol[d][1] += 1
        cr = [ncol[d][1] / ncol[d][0] if ncol[d][0] else 0.0 for d in (0, 1)]
        rows.append({'seed': sd,
                     'A_ms_per_tok': A_mean, 'ABnaive_ms_per_tok': ABn_mean,
                     'ABcond_ms_per_tok': ABc_mean,
                     'cert_rate_color0': cr[0], 'cert_rate_color1': cr[1]})
    A_ms = [r['A_ms_per_tok'] for r in rows]
    ABn_ms = [r['ABnaive_ms_per_tok'] for r in rows]
    ABc_ms = [r['ABcond_ms_per_tok'] for r in rows]
    gains = {  # gain(X) = baseline - X, on mean metric
        'A': base_mean - float(np.mean(A_ms)),
        'B': base_mean - B_mean,
        'ABnaive': base_mean - float(np.mean(ABn_ms)),
        'ABcond': base_mean - float(np.mean(ABc_ms)),
    }
    interaction = gains['ABcond'] - gains['A'] - gains['B']
    cond_vs_naive = gains['ABcond'] - gains['ABnaive']
    cr0 = [r['cert_rate_color0'] for r in rows]; cr1 = [r['cert_rate_color1'] for r in rows]
    op_results.append({
        **op,
        'n_seeds': len(SEEDS),
        'baseline_ms_per_tok': base_mean,
        'B_alone_ms_per_tok': B_mean,
        'A_mean_ms': float(np.mean(A_ms)), 'A_sd_ms': float(np.std(A_ms, ddof=1)),
        'ABnaive_mean_ms': float(np.mean(ABn_ms)), 'ABnaive_sd_ms': float(np.std(ABn_ms, ddof=1)),
        'ABcond_mean_ms': float(np.mean(ABc_ms)), 'ABcond_sd_ms': float(np.std(ABc_ms, ddof=1)),
        'gain_A_ms': gains['A'], 'gain_B_ms': gains['B'],
        'gain_ABnaive_ms': gains['ABnaive'], 'gain_ABcond_ms': gains['ABcond'],
        'interaction_ms': interaction,
        'interaction_pct_of_baseline': interaction / base_mean * 100,
        'cond_minus_naive_ms': cond_vs_naive,
        'cond_minus_naive_pct_of_baseline': cond_vs_naive / base_mean * 100,
        'cert_rate_color0_mean': float(np.mean(cr0)), 'cert_rate_color1_mean': float(np.mean(cr1)),
        'cert_rate_pp_diff': abs(float(np.mean(cr0)) - float(np.mean(cr1))) * 100,
        'per_seed_rows': rows,
    })
    print(f"s_cert={s:.4f}: gainA={gains['A']:.4f} gainB={gains['B']:.4f} "
          f"gainABc={gains['ABcond']:.4f} inter={interaction:.4f} ms "
          f"({interaction/base_mean*100:.3f}%) cond-naive={cond_vs_naive:.4f} "
          f"({cond_vs_naive/base_mean*100:.3f}%) cert_pp_diff={abs(float(np.mean(cr0))-float(np.mean(cr1)))*100:.2f}")

res['baseline'] = {'mean_ms_per_tok': base_mean, 'p95_layerstep_ms': base_p95,
                   'arm': 'static expert-id-parity split, no certifier'}
res['B_alone'] = {'mean_ms_per_tok': B_mean, 'p95_layerstep_ms': B_p95,
                  'gain_vs_baseline_ms': base_mean - B_mean,
                  'gain_vs_baseline_pct': (base_mean - B_mean) / base_mean * 100}
res['operating_points'] = op_results

# ---------------- gate evaluation (quoted verbatim from preregistration) ----------------
ACCEPT = ("A+B(conditioned) beats BOTH A alone and B alone by >= 1.0% of baseline makespan each, "
          "AND A+B(conditioned) - A+B(naive) >= 1.0% of baseline makespan "
          "(i.e. conditioning is what pays, not either parent alone)")
REJECT = ("A+B(conditioned) - A+B(naive) < 1.0% of baseline makespan, OR per-color certification "
          "rates differ by < 2pp (certification is color-neutral, coloring needs no conditioning) "
          "-- in either case the pair is independent and REJECTED as a combination")
STOP = ("One deterministic pass over the 300-token trace; no re-fitting, no threshold search after "
        "seeing held-out numbers. If s_cert < 3% the certifier is too weak to perturb the coloring "
        "and the run is declared inconclusive rather than mined for a positive.")

gate_rows = []
for r in op_results:
    ab_beats_A = r['gain_ABcond_ms'] - r['gain_A_ms'] >= 0.01 * base_mean
    ab_beats_B = r['gain_ABcond_ms'] - r['gain_B_ms'] >= 0.01 * base_mean
    cond_pays = r['cond_minus_naive_ms'] >= 0.01 * base_mean
    accept = ab_beats_A and ab_beats_B and cond_pays
    rej_cond_vs_naive = r['cond_minus_naive_ms'] < 0.01 * base_mean
    rej_color_neutral = r['cert_rate_pp_diff'] < 2.0
    reject = rej_cond_vs_naive or rej_color_neutral
    gate_rows.append({'s_cert': r['s_cert_REAL_K3'], 'accept_gate_met': accept,
                      'reject_gate_met': reject,
                      'reject_reason': ('cond-naive<1%' if rej_cond_vs_naive else '') +
                                       ('+color-neutral<2pp' if rej_color_neutral else '')})
res['gates'] = {'accept_gate': ACCEPT, 'reject_gate': REJECT, 'stop_rule': STOP,
                'per_operating_point': gate_rows,
                'accept_gate_met_any_op': any(g['accept_gate_met'] for g in gate_rows),
                'reject_gate_met_all_ops': all(g['reject_gate_met'] for g in gate_rows)}

p = f'{OUT}/exp21_result.json'
json.dump(res, open(p, 'w'), indent=1)
print(f"\nWROTE {p}")
print(f"ACCEPT any op: {res['gates']['accept_gate_met_any_op']}")
print(f"REJECT all ops: {res['gates']['reject_gate_met_all_ops']}")
