#!/usr/bin/env python3
"""exp44: grouped-vs-interleaved measurement validity.

Two protocols for a 2-arm replay comparison (LRU vs Belady, cap=1490, N=10 reps):
  A grouped: all 10 reps of arm1 in one process, then all 10 reps of arm2 in a
    separate process (what queued factorials exp31/exp41 currently do).
  B interleaved: one process, rep-major alternation (rep i: arm1, arm2).

Byte counts (misses) are checked for determinism across reps; per spec, if
deterministic, the metric switches to WALL TIME of the replay itself.
Prints one JSON line: {protocol, arm, rep, misses, wall_ms}.
"""
import json, heapq, sys, time
from collections import OrderedDict

TRACE = "/Users/mfethe/warp/tests/trace_kimi_300.jsonl"
CAP = 1490
RECORD_B = 12406784  # expert record bytes (3029 pages x 4096)

def load():
    T = [json.loads(l) for l in open(TRACE)]
    acc = []
    for r in T:
        for li, lay in enumerate(r["layers"]):
            for e in lay:
                acc.append((li, e))
    return acc

def build_nxt(acc):
    N = len(acc); INF = 10**9
    nxt = [0]*N; last = {}
    for i in range(N-1, -1, -1):
        k = acc[i]; nxt[i] = last.get(k, INF); last[k] = i
    return nxt, INF

def belady(acc, nxt, INF, cap):
    cur = {}; h = []; m = 0
    for i, k in enumerate(acc):
        if k in cur:
            cur[k] = nxt[i]; heapq.heappush(h, (-nxt[i], k)); continue
        m += 1
        if len(cur) >= cap:
            while True:
                nu, v = heapq.heappop(h)
                if v in cur and cur[v] == -nu:
                    del cur[v]; break
        cur[k] = nxt[i]; heapq.heappush(h, (-nxt[i], k))
    return m

def lru(acc, cap):
    od = OrderedDict(); m = 0
    for k in acc:
        if k in od: od.move_to_end(k); continue
        m += 1
        if len(od) >= cap: od.popitem(last=False)
        od[k] = 1
    return m

def timed(fn, *a):
    t0 = time.perf_counter_ns()
    m = fn(*a)
    t1 = time.perf_counter_ns()
    return m, (t1 - t0) / 1e6

def main():
    protocol = sys.argv[1]  # grouped_arm1 | grouped_arm2 | interleaved
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    acc = load()
    nxt, INF = build_nxt(acc)
    # warmup both code paths once (JIT-ish caches, page-in of trace already done)
    timed(lru, acc, CAP); timed(belady, acc, nxt, INF, CAP)

    if protocol.startswith("grouped_arm"):
        arm = "lru" if protocol == "grouped_arm1" else "belady"
        for rep in range(1, reps+1):
            if arm == "lru":
                m, ms = timed(lru, acc, CAP)
            else:
                m, ms = timed(belady, acc, nxt, INF, CAP)
            print(json.dumps({"protocol": protocol, "arm": arm, "rep": rep,
                              "misses": m, "wall_ms": round(ms, 4)}), flush=True)
    elif protocol == "interleaved":
        for rep in range(1, reps+1):
            for arm in ("lru", "belady"):
                if arm == "lru":
                    m, ms = timed(lru, acc, CAP)
                else:
                    m, ms = timed(belady, acc, nxt, INF, CAP)
                print(json.dumps({"protocol": protocol, "arm": arm, "rep": rep,
                                  "misses": m, "wall_ms": round(ms, 4)}), flush=True)
    else:
        raise SystemExit("unknown protocol")

if __name__ == "__main__":
    main()
