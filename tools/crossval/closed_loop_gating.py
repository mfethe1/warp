#!/usr/bin/env python3
"""exp13 - closed-loop counterfactual gating.

Frozen-mask arithmetic (B_frozen) vs full stateful chronological replay (B_replay)
under two bypass semantics:
  S1 insertion-neutral : skip avoids the READ, expert is still inserted/refreshed
  S2 no-insert-on-bypass: skip avoids the read AND leaves the cache untouched

PROXY trace: tests/trace_kimi_300.jsonl (Kimi-Linear-shaped, NOT K3).
No routing margins exist in this trace; skip rules below are explicitly labelled
and NONE of them is presented as the preregistered routing-margin proxy.
"""
import json, hashlib, sys, random
from collections import OrderedDict, Counter

TRACE = '/tmp/spark/warp/tests/trace_kimi_300.jsonl'
RECORD = 12406784          # bytes per expert record (page-aligned, 3029 pages)
GIB = float(1 << 30)

raw = open(TRACE, 'rb').read()
TRACE_SHA = hashlib.sha256(raw).hexdigest()
T = [json.loads(l) for l in raw.decode().splitlines() if l.strip()]

acc = []
for r in T:
    for li, lay in enumerate(r['layers']):
        for e in lay:
            acc.append((li, e))

N = len(acc)
D = len(set(acc))
TOK = len(T)
L = len(T[0]['layers'])
K = len(T[0]['layers'][0])
WS = L * K

freq = Counter(acc)


# ---------------------------------------------------------------- cache cores
def lru_baseline_missvec(cap):
    """Unmodified LRU. Returns (miss_bool_list, n_miss)."""
    od = OrderedDict()
    mv = [False] * N
    m = 0
    for i, k in enumerate(acc):
        if k in od:
            od.move_to_end(k)
            continue
        mv[i] = True
        m += 1
        if len(od) >= cap:
            od.popitem(last=False)
        od[k] = 1
    return mv, m


def replay_S1(cap, skip):
    """Insertion-neutral: cache evolves EXACTLY as baseline; skip only suppresses
    the physical read on what would have been a miss."""
    od = OrderedDict()
    reads = 0
    for i, k in enumerate(acc):
        hit = k in od
        if hit:
            od.move_to_end(k)
        else:
            if not skip[i]:
                reads += 1
            # insertion happens regardless of skip (insertion-neutral)
            if len(od) >= cap:
                od.popitem(last=False)
            od[k] = 1
    return reads


def replay_S2(cap, skip):
    """No-insert-on-bypass: a skipped access does not touch the cache at all."""
    od = OrderedDict()
    reads = 0
    for i, k in enumerate(acc):
        if skip[i]:
            continue                      # no read, no insert, no refresh
        if k in od:
            od.move_to_end(k)
            continue
        reads += 1
        if len(od) >= cap:
            od.popitem(last=False)
        od[k] = 1
    return reads


# ---------------------------------------------------------------- skip rules
def rule_random(tau, seed=1234):
    rng = random.Random(seed)
    return [rng.random() < tau for _ in range(N)]


def _pop_ordered_skipset(tau, most_popular_first):
    keys = sorted(freq.keys(), key=lambda k: (-freq[k], k) if most_popular_first
                  else (freq[k], k))
    target = tau * N
    cum = 0
    s = set()
    for k in keys:
        if cum >= target:
            break
        s.add(k)
        cum += freq[k]
    return s


def rule_popular(tau):
    s = _pop_ordered_skipset(tau, True)
    return [k in s for k in acc]


def rule_rare(tau):
    s = _pop_ordered_skipset(tau, False)
    return [k in s for k in acc]


def rule_idorder(tau):
    """Skip the first ceil(tau*K) entries of each token-layer list.
    The lists are ID-sorted, so this is an EXPERT-ID-MAGNITUDE proxy,
    explicitly NOT a routing-margin rank."""
    cut = int(round(tau * K))
    out = []
    for _ in T:
        for _li in range(L):
            for p in range(K):
                out.append(p < cut)
    return out


RULES = {
    'random-iid':   rule_random,
    'skip-popular': rule_popular,
    'skip-rare':    rule_rare,
    'id-order':     rule_idorder,
}


def kendall_tau(a, b):
    n = len(a)
    con = dis = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (a[i] - a[j]) * (b[i] - b[j])
            if s > 0:
                con += 1
            elif s < 0:
                dis += 1
    return (con - dis) / (con + dis) if (con + dis) else float('nan')


def gib_per_tok(reads):
    return reads * RECORD / GIB / TOK


# ---------------------------------------------------------------- main sweep
CAPS = [('0.5x', int(round(0.5 * WS))), ('1x', WS),
        ('3.41x', 709), ('8x', int(round(8 * WS)))]
TAUS = [round(0.1 * i, 1) for i in range(1, 10)]

print(f"# exp13 closed-loop counterfactual gating  [PROXY trace]")
print(f"trace sha256 = {TRACE_SHA}")
print(f"{TOK} tok x {L} lay x top-{K} -> N={N} accesses, D={D} distinct, WS={WS}")
print(f"RECORD={RECORD} B   deterministic replay: no sampling variance "
      f"(random-iid uses one pinned seed=1234)")
print()

rows = []
s1_max_abs = 0.0
s2_max_abs = 0.0

for cname, cap in CAPS:
    mv, base_miss = lru_baseline_missvec(cap)
    print(f"== capacity {cname} (cap={cap}) baseline LRU misses = {base_miss} "
          f"({gib_per_tok(base_miss):.4f} GiB/tok PROXY) ==")
    print(f"{'rule':<13}{'tau':>5}{'B_frozen':>10}{'B_S1':>9}{'epsS1':>9}"
          f"{'B_S2':>9}{'epsS2':>10}{'GiB/tok_S2':>12}")
    for rname, rfn in RULES.items():
        froz_list, s2_list = [], []
        for tau in TAUS:
            skip = rfn(tau)
            b_frozen = sum(1 for i in range(N) if mv[i] and not skip[i])
            b_s1 = replay_S1(cap, skip)
            b_s2 = replay_S2(cap, skip)
            e1 = (b_frozen - b_s1) / b_s1 if b_s1 else float('nan')
            e2 = (b_frozen - b_s2) / b_s2 if b_s2 else float('nan')
            s1_max_abs = max(s1_max_abs, abs(e1))
            s2_max_abs = max(s2_max_abs, abs(e2))
            froz_list.append(b_frozen)
            s2_list.append(b_s2)
            rows.append(dict(cap=cname, cap_n=cap, rule=rname, tau=tau,
                             b_frozen=b_frozen, b_s1=b_s1, b_s2=b_s2,
                             eps_s1=e1, eps_s2=e2,
                             gib_tok_frozen=gib_per_tok(b_frozen),
                             gib_tok_s2=gib_per_tok(b_s2)))
            print(f"{rname:<13}{tau:>5}{b_frozen:>10}{b_s1:>9}{e1:>9.5f}"
                  f"{b_s2:>9}{e2:>10.4f}{gib_per_tok(b_s2):>12.4f}")
        kt = kendall_tau(froz_list, s2_list)
        print(f"{'  kendall tau (frozen vs S2 ranking over tau)':<50}{kt:>8.4f}")
    print()

print(f"MAX |eps_B| under S1 (insertion-neutral) = {s1_max_abs:.3e}")
print(f"MAX |eps_B| under S2 (no-insert-on-bypass) = {s2_max_abs:.4f} "
      f"({100*s2_max_abs:.2f}%)")

out = dict(trace_sha256=TRACE_SHA, N=N, D=D, TOK=TOK, L=L, K=K, WS=WS,
           RECORD=RECORD, seed=1234,
           max_abs_eps_s1=s1_max_abs, max_abs_eps_s2=s2_max_abs,
           rows=rows)
with open('/tmp/spark/warp/docs/gn100/exp13-closed-loop-gating.json', 'w') as f:
    json.dump(out, f, indent=1)
print("wrote docs/gn100/exp13-closed-loop-gating.json")
