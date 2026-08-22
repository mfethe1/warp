import json,heapq
from collections import OrderedDict
T=[json.loads(l) for l in open('/tmp/spark/warp/tests/trace_kimi_300.jsonl')]
acc=[]
for r in T:
    for li,lay in enumerate(r['layers']):
        for e in lay: acc.append((li,e))
N=len(acc); D=len(set(acc)); L=len(T[0]['layers']); K=len(T[0]['layers'][0]); TOK=len(T)
INF=10**9
nxt=[0]*N; last={}
for i in range(N-1,-1,-1):
    k=acc[i]; nxt[i]=last.get(k,INF); last[k]=i

def belady(cap):
    cur={}; h=[]; m=0
    for i,k in enumerate(acc):
        if k in cur:
            cur[k]=nxt[i]; heapq.heappush(h,(-nxt[i],k)); continue
        m+=1
        if len(cur)>=cap:
            while True:
                nu,v=heapq.heappop(h)
                if v in cur and cur[v]==-nu: del cur[v]; break
        cur[k]=nxt[i]; heapq.heappush(h,(-nxt[i],k))
    return m

def lru(cap):
    od=OrderedDict(); m=0
    for k in acc:
        if k in od: od.move_to_end(k); continue
        m+=1
        if len(od)>=cap: od.popitem(last=False)
        od[k]=1
    return m

WS=L*K; K3_WS=92*16; K3_CACHE=5015
ratio=K3_CACHE/K3_WS
cap_eq=int(round(ratio*WS))
print(f"PROXY trace (Kimi-Linear-like, NOT K3): {TOK} tok x {L} layers x top-{K}")
print(f"  {N} accesses, {D} distinct (layer,expert), per-token WS={WS}")
print(f"  compulsory floor: {D} cold misses -> max hit {(1-D/N)*100:.2f}% on this short trace")
print(f"K3: WS={K3_WS}, cache~{K3_CACHE} experts -> cache/WS = {ratio:.2f}x")
print(f"K3-EQUIVALENT proxy cap = {cap_eq} slots ({cap_eq/D*100:.1f}% of distinct)\n")
print(f"{'cap':>6} {'xWS':>6} {'%dist':>7} | {'LRU':>8} {'BELADY':>8} | {'LRUhit':>8} {'BELhit':>8} {'gap':>6} | {'BELsteady':>9}")
for cap in sorted(set([152,309,cap_eq,508,762,1270,2033,3049,4066,5083])):
    b=belady(cap); l=lru(cap)
    lh=(1-l/N)*100; bh=(1-b/N)*100
    capmiss=b-D
    steady=(1-capmiss/N)*100
    tag=" <== K3-EQUIV" if cap==cap_eq else ""
    print(f"{cap:6} {cap/WS:6.2f} {cap/D*100:6.1f}% | {l:8} {b:8} | {lh:7.2f}% {bh:7.2f}% {bh-lh:5.2f} | {steady:8.2f}%{tag}")

TARGET=97.68
print(f"\n=== Can Belady reach {TARGET}% (the 15 tok/s bandwidth-equivalent bar)? ===")
lo,hi=1,D; found=None
b_full=belady(D)
print(f"  at 100% residency ({D} slots): Belady hit = {(1-b_full/N)*100:.2f}%  <- compulsory-limited")
for cap in [cap_eq,1270,2033,3049,4066,5083]:
    b=belady(cap); h=(1-b/N)*100
    st=(1-(b-D)/N)*100
    print(f"  cap={cap:5} ({cap/WS:5.2f}x WS): raw {h:6.2f}%  steady-state {st:6.2f}%  shortfall(steady) {TARGET-st:+6.2f} pp")
