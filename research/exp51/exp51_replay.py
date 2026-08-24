#!/usr/bin/env python3
"""exp51: miss-support-capped-io-depth-knee.

Offline deterministic replay of frozen trace_kimi_300.jsonl under exact LRU
key=(layer,expert) at cap=1490 plus caps {709, 2980}. For every token-layer
log K_miss (misses for that (token,layer) after LRU state from all prior
accesses, insertion order = trace order within the layer's top-8 list).

For q in {1,2,4,8}: E[min(K,q)]/E[K], E[ceil(K/q)], P(K>=q),
optimistic wave reduction q->2q = 1 - E[ceil(K/2q)]/E[ceil(K/q)].

Evidence class: PROXY (Kimi-Linear-shaped 26L x top-8 trace, NOT K3 92L x top-16).
"""
import json, math, hashlib, sys
from collections import OrderedDict

TRACE = "/Users/mfethe/warp/tests/trace_kimi_300.jsonl"
CAPS = [1490, 709, 2980]
QS = [1, 2, 4, 8]

def replay(trace, cap):
    cache = OrderedDict()  # key -> True, move_to_end on touch
    k_list = []            # K_miss per token-layer
    for row in trace:
        for L, experts in enumerate(row["layers"]):
            k = 0
            for e in experts:
                key = (L, e)
                if key in cache:
                    cache.move_to_end(key)
                else:
                    k += 1
                    cache[key] = True
                    if len(cache) > cap:
                        cache.popitem(last=False)
            k_list.append(k)
    return k_list

def stats(k_list):
    n = len(k_list)
    ek = sum(k_list) / n
    out = {"N_layers": n, "E[K]": ek}
    for q in QS:
        out[f"E[min(K,{q})]/E[K]"] = sum(min(k, q) for k in k_list) / sum(k_list)
        out[f"E[ceil(K/{q})]"] = sum(math.ceil(k / q) for k in k_list) / n
        out[f"P(K>={q})"] = sum(1 for k in k_list if k >= q) / n
    for q in (2, 4):
        hi = 2 * q
        num = sum(math.ceil(k / hi) for k in k_list)
        den = sum(math.ceil(k / q) for k in k_list)
        out[f"wave_red_{q}->{hi}"] = 1 - num / den
    return out

def main():
    with open(TRACE, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    trace = [json.loads(l) for l in open(TRACE) if l.strip()]
    assert len(trace) == 300
    print(f"trace sha256 {sha}")
    print(f"tokens {len(trace)} layers {len(trace[0]['layers'])} "
          f"topk {len(trace[0]['layers'][0])} "
          f"distinct {len({(L,e) for r in trace for L,ex in enumerate(r['layers']) for e in ex})}")
    print()
    results = {}
    for cap in CAPS:
        k = replay(trace, cap)
        s = stats(k)
        results[cap] = s
        # distribution of K for context
        dist = {}
        for x in k:
            dist[x] = dist.get(x, 0) + 1
        print(f"== cap {cap} ==")
        print(f"  N={s['N_layers']}  E[K]={s['E[K]']:.4f}  K-dist={dict(sorted(dist.items()))}")
        for q in QS:
            print(f"  q={q}: capture E[min(K,q)]/E[K]={s[f'E[min(K,{q})]/E[K]']:.4f}"
                  f"  E[ceil(K/q)]={s[f'E[ceil(K/{q})]']:.4f}"
                  f"  P(K>=q)={s[f'P(K>={q})']:.4f}")
        print(f"  wave_red q2->q4 = {s['wave_red_2->4']:.4f}   wave_red q4->q8 = {s['wave_red_4->8']:.4f}")
        print()
    json.dump({str(c): results[c] for c in CAPS}, open("exp51_results.json", "w"), indent=1)
    print("wrote exp51_results.json")

if __name__ == "__main__":
    main()
