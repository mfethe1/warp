#!/usr/bin/env python3
"""
exp29 -- LATENCY-BOUND LAYER BARRIER: RAID0 vs DUPLICATION vs SHARD  [RECOMPUTATION]

Three-arm placement comparison at swept operating points. Zero hardware.

INPUT  : exp24 canonical_v2.jsonl  (provenance src=tests/trace_kimi_300.jsonl
         src_sha256=06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965)
         PROXY: 300 tok x 26 layers x top-8, 256 experts.  NOT K3 (92L x top-16).

METHOD : replay through an LRU cache sim at swept capacities -> EMPIRICAL
         per-layer miss-count distribution (no Bin(16,p) assumption).
         Map PROXY top-8 -> K3-equivalent top-16 by self-convolution of the
         empirical per-layer miss pmf (a K3 layer = 2 independent proxy layers,
         preserving E[k]*2 exactly).
         Then evaluate per-layer I/O critical path under three placements.

ALL NUMBERS ARE RECOMPUTATION OVER A PROXY TRACE. NO K3 MEASUREMENT.
"""
import json, math, hashlib, os, sys
from collections import OrderedDict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
TRACE = os.path.join(HERE, "evidence/exp24-canonical-schema/canonical_v2.jsonl")

# ------------------------------------------------- ESTABLISHED CONSTANTS
EXPERT_RECORD_BYTES = 12_406_784          # exactly 3029 pages x 4096
GIB                 = 1024**3
REC_GIB             = EXPERT_RECORD_BYTES / GIB      # 0.0115547 GiB
BW_SINGLE           = 5.919               # GiB/s measured Samsung 990 Pro
DERATE              = 5.919 / 6.938       # exp17/exp23 derating, 0.8531
T_REC               = REC_GIB / BW_SINGLE            # s per whole record, 1 device
K3_LAYERS           = 92
K3_TOPK             = 16
STRIPE_UNIT         = 128 * 1024
TARGET_TOKS         = 15.0
LAYER_BUDGET_S      = 1.0 / TARGET_TOKS / K3_LAYERS   # 0.72464 ms

PHYS_TODAY_GIB_TOK  = 7.719
PHYS_TARGET_GIB_TOK = 5.919 / TARGET_TOKS             # 0.3946

def k3_misses_per_layer(gib_per_token):
    return gib_per_token / (K3_LAYERS * REC_GIB)

E_K_TODAY  = k3_misses_per_layer(PHYS_TODAY_GIB_TOK)    # 7.262
E_K_TARGET = k3_misses_per_layer(PHYS_TARGET_GIB_TOK)   # 0.3713

# ------------------------------------------------- load PROXY trace
def load_trace(path):
    hdr, rows = None, []
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("record") == "header":
                hdr = r; continue
            rows.append((r["seq"], r["layer"], tuple(r["ids"])))
    rows.sort(key=lambda x: x[0])
    return hdr, rows

# ------------------------------------------------- LRU sim -> per-layer miss counts
def lru_replay(rows, capacity):
    """Cache keyed on (layer, expert_id). Returns list of miss counts, one per
    trace layer-visit (i.e. per (token,layer) pair)."""
    cache = OrderedDict()
    per_layer_misses = []
    for _seq, layer, ids in rows:
        m = 0
        for e in ids:
            key = (layer, e)
            if key in cache:
                cache.move_to_end(key)
            else:
                m += 1
                cache[key] = True
                if len(cache) > capacity:
                    cache.popitem(last=False)
        per_layer_misses.append(m)
    return per_layer_misses

def pmf_from_counts(counts):
    n = len(counts)
    c = Counter(counts)
    return {k: v / n for k, v in sorted(c.items())}

def convolve(p, q):
    out = {}
    for a, pa in p.items():
        for b, pb in q.items():
            out[a + b] = out.get(a + b, 0.0) + pa * pb
    return out

def mean(p):
    return sum(k * v for k, v in p.items())

def var(p):
    m = mean(p)
    return sum(v * (k - m) ** 2 for k, v in p.items())

# ------------------------------------------------- placement arms
def exact_expected_max_load(n_balls, n_bins, _memo={}):
    """E[max bin load], n balls uniform into n bins. Exact enumeration."""
    if n_balls == 0:
        return 0.0
    key = (n_balls, n_bins)
    if key in _memo:
        return _memo[key]
    total = 0.0
    denom = float(n_bins) ** n_balls
    def comps(n, k):
        if k == 1:
            yield (n,); return
        for i in range(n + 1):
            for rest in comps(n - i, k - 1):
                yield (i,) + rest
    for c in comps(n_balls, n_bins):
        coef = math.factorial(n_balls)
        for x in c:
            coef //= math.factorial(x)
        total += coef * max(c)
    r = total / denom
    _memo[key] = r
    return r

def raid0_max_device_bytes(D):
    """One 12,406,784 B record striped in 128 KiB units round-robin over D
    devices. Returns bytes landing on the MOST loaded device (the critical
    path), which captures the tail-stripe imbalance exactly."""
    full = EXPERT_RECORD_BYTES // STRIPE_UNIT          # 94
    tail = EXPERT_RECORD_BYTES - full * STRIPE_UNIT    # 85,248 B
    load = [0] * D
    for u in range(full):
        load[u % D] += STRIPE_UNIT
    if tail:
        load[full % D] += tail
    return max(load), load

# per-layer critical path (seconds) for each arm, given the miss pmf
def cost_shard(pmf, D):
    return sum(p * exact_expected_max_load(k, D) for k, p in pmf.items()) * T_REC

def cost_duplicate(pmf, D):
    return sum(p * math.ceil(k / D) for k, p in pmf.items()) * T_REC

def cost_raid0(pmf, D):
    mx, _ = raid0_max_device_bytes(D)
    t_one = (mx / GIB) / BW_SINGLE        # all D devices work the SAME record
    return mean(pmf) * t_one

def b_eff(pmf, seconds):
    """B_eff = physical expert bytes on the layer critical path / critical-path s"""
    if seconds <= 0:
        return float("inf")
    return REC_GIB * mean(pmf) / seconds

# ------------------------------------------------- run
def main():
    hdr, rows = load_trace(TRACE)
    src_sha = hdr["provenance"]["src_sha256"]
    n_layers = hdr["n_layers"]; n_experts = hdr["n_experts"]
    assert hdr["expert_record_bytes"] == EXPERT_RECORD_BYTES

    out = {
        "label": "RECOMPUTATION over PROXY trace -- NOT a K3 measurement",
        "trace": {"path": TRACE, "src": hdr["provenance"]["src"],
                  "src_sha256": src_sha, "n_layer_visits": len(rows),
                  "n_layers": n_layers, "n_experts": n_experts,
                  "topk_proxy": len(rows[0][2]), "accesses": len(rows)*len(rows[0][2])},
        "constants": {"expert_record_bytes": EXPERT_RECORD_BYTES,
                      "rec_gib": REC_GIB, "bw_single_gibs": BW_SINGLE,
                      "t_rec_ms": T_REC*1e3, "derate": DERATE,
                      "layer_budget_ms": LAYER_BUDGET_S*1e3,
                      "E_k_today": E_K_TODAY, "E_k_target": E_K_TARGET},
    }

    print("="*78)
    print("exp29  LATENCY-BOUND LAYER BARRIER: RAID0 vs DUPLICATE vs SHARD")
    print("="*78)
    print(f"trace           : {hdr['provenance']['src']}  sha256={src_sha[:16]}...")
    print(f"                  PROXY {n_layers}L x {n_experts}E x top-{len(rows[0][2])}"
          f" = {len(rows)*len(rows[0][2])} accesses  (NOT K3)")
    print(f"record          : {EXPERT_RECORD_BYTES} B = {REC_GIB:.7f} GiB"
          f" = {EXPERT_RECORD_BYTES//4096} pages")
    print(f"t_rec (1 device): {T_REC*1e3:.4f} ms   layer budget @15tok/s/92L:"
          f" {LAYER_BUDGET_S*1e3:.5f} ms  -> t_rec = {T_REC/LAYER_BUDGET_S:.3f} budgets")
    print(f"K3-equiv E[k]   : today {E_K_TODAY:.4f}   target {E_K_TARGET:.4f}")

    # ---------------- cross-check gate 1: reproduce exp23 at k=16 deterministic
    print()
    print("="*78)
    print("GATE 1 CROSS-CHECK -- arms A,B must reproduce exp23 barrier taxes at k=16")
    print("="*78)
    exp23_shard = {2: 1.1964, 3: 1.3750, 4: 1.5348}
    g1_rows, g1_ok = [], True
    print(f"{'D':>3} {'ideal':>7} {'shardE[max]':>12} {'shard tax':>10} {'exp23':>8}"
          f" {'delta%':>8} {'dup tax':>8}")
    for D in (2, 3, 4):
        idl = K3_TOPK / D
        sm  = exact_expected_max_load(K3_TOPK, D)
        st  = sm / idl
        dt  = math.ceil(K3_TOPK / D) / idl
        dl  = abs(st - exp23_shard[D]) / exp23_shard[D] * 100
        ok  = dl <= 1.0
        g1_ok &= ok
        g1_rows.append(dict(D=D, shard_tax=st, exp23=exp23_shard[D],
                            delta_pct=dl, dup_tax=dt, within_1pct=ok))
        print(f"{D:3d} {idl:7.3f} {sm:12.4f} {st:10.4f} {exp23_shard[D]:8.4f}"
              f" {dl:8.4f} {dt:8.4f}")
    print(f"GATE 1 (arms A,B reproduce exp23 within 1%): "
          f"{'PASS' if g1_ok else 'FAIL -- HARNESS INVALID'}")
    out["gate1_reproduce_exp23"] = {"rows": g1_rows, "pass": g1_ok}
    if not g1_ok:
        print("Harness invalid per stop rule -- aborting."); sys.exit(2)

    # ---------------- RAID0 stripe geometry
    print()
    print("="*78)
    print("RAID0 STRIPE GEOMETRY (128 KiB unit, tail-stripe imbalance, EXACT)")
    print("="*78)
    full = EXPERT_RECORD_BYTES // STRIPE_UNIT
    tail = EXPERT_RECORD_BYTES - full * STRIPE_UNIT
    print(f"record / stripe = {EXPERT_RECORD_BYTES/STRIPE_UNIT:.4f} units"
          f"  -> {full} full + tail {tail} B")
    geo = []
    for D in (2, 3, 4):
        mx, load = raid0_max_device_bytes(D)
        ideal = EXPERT_RECORD_BYTES / D
        t_one = (mx/GIB)/BW_SINGLE
        geo.append(dict(D=D, max_dev_bytes=mx, ideal_bytes=ideal,
                        tail_tax=mx/ideal, t_one_ms=t_one*1e3, load=load))
        print(f"  D={D}  max-device {mx:>9} B  ideal {ideal:>11.1f} B"
              f"  tail tax {mx/ideal:.5f}x  t_record {t_one*1e3:.4f} ms")
    out["raid0_geometry"] = geo

    # ---------------- capacity sweep -> empirical miss pmf
    print()
    print("="*78)
    print("CAPACITY SWEEP -- EMPIRICAL per-layer miss pmf  [PROXY, N=%d layer-visits]"
          % len(rows))
    print("="*78)
    caps = [64,128,192,256,384,512,768,1024,1536,2048,2560,3072,3584,4096,4608,5120,
            5632,6144,6400,6656]
    sweep = []
    print(f"{'cap':>6} {'proxy E[k]':>11} {'var':>8} {'K3eq E[k]':>10} {'K3eq var':>9}"
          f" {'phys GiB/tok':>13} {'missrate':>9}")
    for cap in caps:
        mc = lru_replay(rows, cap)
        p8 = pmf_from_counts(mc)
        p16 = convolve(p8, p8)             # K3-equivalent top-16 layer
        ek16, vk16 = mean(p16), var(p16)
        phys = ek16 * K3_LAYERS * REC_GIB
        mr = mean(p8) / len(rows[0][2])
        sweep.append(dict(cap=cap, proxy_Ek=mean(p8), proxy_var=var(p8),
                          k3_Ek=ek16, k3_var=vk16, phys_gib_tok=phys,
                          miss_rate=mr, pmf16={str(k): v for k, v in p16.items()}))
        print(f"{cap:6d} {mean(p8):11.5f} {var(p8):8.4f} {ek16:10.5f} {vk16:9.4f}"
              f" {phys:13.4f} {mr:9.5f}")
    out["sweep"] = sweep

    reach_lo = min(s["k3_Ek"] for s in sweep)
    reach_hi = max(s["k3_Ek"] for s in sweep)
    print(f"\nK3-equivalent E[k] reachable by LRU on this trace: "
          f"[{reach_lo:.5f}, {reach_hi:.5f}]")
    print(f"  today  E[k]={E_K_TODAY:.4f} -> "
          f"{'IN RANGE' if reach_lo<=E_K_TODAY<=reach_hi else 'OUT OF RANGE'}")
    print(f"  target E[k]={E_K_TARGET:.4f} -> "
          f"{'IN RANGE' if reach_lo<=E_K_TARGET<=reach_hi else 'OUT OF RANGE'}")
    out["reachable_k3_Ek"] = [reach_lo, reach_hi]

    # ---------------- pick operating points: nearest empirical pmf to today/target
    def nearest(ek):
        return min(sweep, key=lambda s: abs(s["k3_Ek"] - ek))
    op_today  = nearest(E_K_TODAY)
    op_target = nearest(E_K_TARGET)

    # ---------------- three-arm evaluation at every swept point
    print()
    print("="*78)
    print("THREE-ARM PER-LAYER CRITICAL PATH  [RECOMPUTATION, empirical pmf]")
    print("="*78)
    arms = []
    for s in sweep:
        pmf = {int(k): v for k, v in s["pmf16"].items()}
        row = {"cap": s["cap"], "k3_Ek": s["k3_Ek"], "phys_gib_tok": s["phys_gib_tok"]}
        for D in (2, 3, 4):
            cs, cd, cr = cost_shard(pmf, D), cost_duplicate(pmf, D), cost_raid0(pmf, D)
            row[f"D{D}"] = {
                "shard_ms": cs*1e3, "dup_ms": cd*1e3, "raid0_ms": cr*1e3,
                "shard_Beff": b_eff(pmf, cs), "dup_Beff": b_eff(pmf, cd),
                "raid0_Beff": b_eff(pmf, cr),
                "raid0_vs_dup_pct": (cd/cr - 1.0)*100 if cr > 0 else float("inf"),
                "dup_frac_of_budget": cd/LAYER_BUDGET_S,
                "raid0_frac_of_budget": cr/LAYER_BUDGET_S,
            }
        arms.append(row)
    out["arms"] = arms

    for label, op in (("TODAY", op_today), ("TARGET", op_target)):
        r = next(a for a in arms if a["cap"] == op["cap"])
        print(f"\n--- {label} operating point: cap={op['cap']}  "
              f"K3-equiv E[k]={op['k3_Ek']:.5f}  physical {op['phys_gib_tok']:.4f} GiB/tok")
        print(f"{'D':>3} {'shard ms':>10} {'dup ms':>9} {'RAID0 ms':>10}"
              f" {'dup B_eff':>10} {'R0 B_eff':>10} {'R0 vs dup':>10}"
              f" {'dup %budget':>12} {'R0 %budget':>11}")
        for D in (2, 3, 4):
            x = r[f"D{D}"]
            print(f"{D:3d} {x['shard_ms']:10.4f} {x['dup_ms']:9.4f} {x['raid0_ms']:10.4f}"
                  f" {x['dup_Beff']:10.3f} {x['raid0_Beff']:10.3f}"
                  f" {x['raid0_vs_dup_pct']:9.2f}% {x['dup_frac_of_budget']*100:11.1f}%"
                  f" {x['raid0_frac_of_budget']*100:10.1f}%")
    out["op_today"] = {"cap": op_today["cap"], "k3_Ek": op_today["k3_Ek"]}
    out["op_target"] = {"cap": op_target["cap"], "k3_Ek": op_target["k3_Ek"]}

    # ---------------- GATE 2: RAID0 advantage at TARGET >= 10% for D>=2
    print()
    print("="*78)
    print("GATE 2 -- at TARGET miss rate, RAID0 B_eff exceeds duplication by >=10%, D>=2")
    print("="*78)
    rt = next(a for a in arms if a["cap"] == op_target["cap"])
    g2_rows, g2_ok = [], True
    for D in (2, 3, 4):
        adv = rt[f"D{D}"]["raid0_vs_dup_pct"]
        ok = adv >= 10.0
        g2_ok &= ok
        g2_rows.append(dict(D=D, advantage_pct=adv, pass_=ok))
        print(f"  D={D}: RAID0 B_eff advantage over duplication = {adv:7.2f}%"
              f"  -> {'PASS' if ok else 'FAIL'}")
    print(f"GATE 2: {'PASS' if g2_ok else 'FAIL'}")
    out["gate2_raid0_advantage"] = {"rows": g2_rows, "pass": g2_ok,
                                    "at_cap": op_target["cap"],
                                    "at_k3_Ek": op_target["k3_Ek"]}

    # ---------------- GATE 3: empirical crossover within +-25% of E[k]=D
    print()
    print("="*78)
    print("GATE 3 -- empirical RAID0/duplication crossover within +-25% of E[k]=D")
    print("="*78)
    g3_rows, g3_ok = [], True
    srt = sorted(arms, key=lambda a: a["k3_Ek"])
    for D in (2, 3, 4):
        # advantage decreases as E[k] grows; crossover where raid0_vs_dup_pct == 0
        xs = [(a["k3_Ek"], a[f"D{D}"]["raid0_vs_dup_pct"]) for a in srt]
        cross = None
        for i in range(len(xs)-1):
            (e0, a0), (e1, a1) = xs[i], xs[i+1]
            if (a0 > 0 >= a1) or (a0 >= 0 > a1) or (a0 < 0 <= a1):
                if a0 != a1:
                    cross = e0 + (e1-e0) * (a0-0)/(a0-a1)
                else:
                    cross = e0
                break
        if cross is None:
            lo, hi = xs[0][1], xs[-1][1]
            note = ("RAID0 wins across the ENTIRE reachable range "
                    f"(advantage {min(lo,hi):.2f}%..{max(lo,hi):.2f}%) -- "
                    "no crossover observed")
            ok = False
            g3_rows.append(dict(D=D, crossover=None, predicted=D,
                                within_25pct=False, note=note))
            print(f"  D={D}: NO CROSSOVER in reachable E[k] range. {note}")
        else:
            lo_b, hi_b = D*0.75, D*1.25
            ok = lo_b <= cross <= hi_b
            g3_rows.append(dict(D=D, crossover=cross, predicted=D,
                                band=[lo_b, hi_b], within_25pct=ok))
            print(f"  D={D}: crossover at E[k]={cross:.4f}, predicted {D}"
                  f" (band {lo_b:.2f}..{hi_b:.2f}) -> {'PASS' if ok else 'FAIL'}")
        g3_ok &= ok
    print(f"GATE 3: {'PASS' if g3_ok else 'FAIL'}")
    out["gate3_crossover"] = {"rows": g3_rows, "pass": g3_ok}

    # ---------------- advantage curve (for the record)
    print()
    print("="*78)
    print("RAID0-vs-DUPLICATION ADVANTAGE CURVE  B_eff(miss rate)  [answers mismatch #9]")
    print("="*78)
    print(f"{'K3eq E[k]':>10} {'physGiB/tok':>12} {'D2 adv%':>9} {'D3 adv%':>9}"
          f" {'D4 adv%':>9} {'D4 dupBeff':>11} {'D4 R0Beff':>10}")
    for a in srt:
        print(f"{a['k3_Ek']:10.5f} {a['phys_gib_tok']:12.4f}"
              f" {a['D2']['raid0_vs_dup_pct']:9.2f} {a['D3']['raid0_vs_dup_pct']:9.2f}"
              f" {a['D4']['raid0_vs_dup_pct']:9.2f} {a['D4']['dup_Beff']:11.3f}"
              f" {a['D4']['raid0_Beff']:10.3f}")

    # ---------------- PROJECTION at the exact preregistered target E[k]
    print()
    print("="*78)
    print("PROJECTION at EXACT preregistered E[k]=0.3713 (spec's Bin(16,p) form)")
    print("="*78)
    p = E_K_TARGET / K3_TOPK
    binom = {k: math.comb(K3_TOPK, k) * p**k * (1-p)**(K3_TOPK-k)
             for k in range(K3_TOPK+1)}
    print(f"Bin(16,{p:.6f}): E[k]={mean(binom):.5f}  P(k>=1)={1-binom[0]:.5f}")
    proj = {}
    for D in (2, 3, 4):
        cs, cd, cr = cost_shard(binom, D), cost_duplicate(binom, D), cost_raid0(binom, D)
        proj[D] = dict(shard_ms=cs*1e3, dup_ms=cd*1e3, raid0_ms=cr*1e3,
                       dup_Beff=b_eff(binom, cd), raid0_Beff=b_eff(binom, cr),
                       adv_pct=(cd/cr-1)*100,
                       dup_pct_budget=cd/LAYER_BUDGET_S*100,
                       raid0_pct_budget=cr/LAYER_BUDGET_S*100)
        x = proj[D]
        print(f"  D={D}: shard {x['shard_ms']:.4f} ms  dup {x['dup_ms']:.4f} ms"
              f"  RAID0 {x['raid0_ms']:.4f} ms  adv {x['adv_pct']:.2f}%"
              f"  | dup uses {x['dup_pct_budget']:.1f}% of layer budget,"
              f" RAID0 {x['raid0_pct_budget']:.1f}%")
    out["projection_binomial_target"] = {str(k): v for k, v in proj.items()}
    out["projection_note"] = ("PROJECTION -- binomial form taken verbatim from the "
                              "preregistered prediction, NOT from the trace")

    # ---------------- verdict
    print()
    print("="*78)
    print("PREREGISTERED VERDICT")
    print("="*78)
    accept = g1_ok and g2_ok and g3_ok
    print(f"  ACCEPT requires gate1 AND gate2 AND gate3")
    print(f"    gate1 reproduce exp23 : {'PASS' if g1_ok else 'FAIL'}")
    print(f"    gate2 RAID0 >=10% adv : {'PASS' if g2_ok else 'FAIL'}")
    print(f"    gate3 crossover +-25% : {'PASS' if g3_ok else 'FAIL'}")
    print(f"  => {'ACCEPT (confirmed)' if accept else 'REJECT (falsified as specified)'}")
    out["verdict"] = {"gate1": g1_ok, "gate2": g2_ok, "gate3": g3_ok,
                      "accept": accept}

    dest = os.path.join(HERE, "evidence/exp29-raid0-layer-barrier")
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "result.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwrote {dest}/result.json")

if __name__ == "__main__":
    main()
