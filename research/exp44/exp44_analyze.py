#!/usr/bin/env python3
"""exp44 analysis: grouped vs interleaved protocol comparison (wall-time metric)."""
import json, math, statistics as st

def load(fn):
    rows = [json.loads(l) for l in open(fn)]
    return rows

g1 = load("raw_grouped_arm1.jsonl")   # lru, separate process
g2 = load("raw_grouped_arm2.jsonl")   # belady, separate process
il = load("raw_interleaved.jsonl")

# determinism check (byte counts)
lru_miss = {r["misses"] for r in g1 + [r for r in il if r["arm"]=="lru"]}
bel_miss = {r["misses"] for r in g2 + [r for r in il if r["arm"]=="belady"]}
det = (len(lru_miss)==1 and len(bel_miss)==1)
print(f"byte-count deterministic: {det} (lru={lru_miss}, belady={bel_miss})")
print("=> metric switched to WALL TIME per spec\n")

def arm(rows, arm):
    return [r["wall_ms"] for r in rows if r["arm"]==arm]

# Protocol A: grouped — each arm its own process; between-arm delta = difference of means,
# sd of that delta = sqrt(sd_l^2/n + sd_b^2/n) but per-rep spread is what charges to one rep
A_lru = arm(g1,"lru"); A_bel = arm(g2,"belady")
mean_A_lru, mean_A_bel = st.mean(A_lru), st.mean(A_bel)
sd_A_lru, sd_A_bel = st.stdev(A_lru), st.stdev(A_bel)
delta_A = mean_A_bel - mean_A_lru
# per-rep between-arm comparison as done in a grouped factorial (one rep each arm):
sd_A_delta = math.sqrt(sd_A_lru**2 + sd_A_bel**2)   # single-rep difference spread
rel_A_lru = sd_A_lru/mean_A_lru*100; rel_A_bel = sd_A_bel/mean_A_bel*100

# Protocol B: interleaved, rep-major — paired differences d_i = belady_i - lru_i
lru_B = {r["rep"]: r["wall_ms"] for r in il if r["arm"]=="lru"}
bel_B = {r["rep"]: r["wall_ms"] for r in il if r["arm"]=="belady"}
d = [bel_B[i]-lru_B[i] for i in sorted(lru_B)]
mean_d, sd_d = st.mean(d), st.stdev(d)
sd_B_delta = sd_d
rel_B_lru = st.stdev(list(lru_B.values()))/st.mean(list(lru_B.values()))*100
rel_B_bel = st.stdev(list(bel_B.values()))/st.mean(list(bel_B.values()))*100

print("PROTOCOL A (grouped, two processes) — wall ms per rep")
print(f"  lru   : mean={mean_A_lru:.4f}  sd={sd_A_lru:.4f}  rel={rel_A_lru:.3f}%")
print(f"  belady: mean={mean_A_bel:.4f}  sd={sd_A_bel:.4f}  rel={rel_A_bel:.3f}%")
print(f"  between-arm delta = {delta_A:+.4f} ms; single-rep delta sd = {sd_A_delta:.4f} ms")
print(f"  delta in units of its own sd = {delta_A/sd_A_delta:+.3f} sd")
print("PROTOCOL B (interleaved, rep-major pairs) — paired delta d_i = belady_i - lru_i")
print(f"  d     : mean={mean_d:+.4f}  sd={sd_d:.4f} ms")
print(f"  lru rel sd={rel_B_lru:.3f}%  belady rel sd={rel_B_bel:.3f}%")
print(f"  |mean d| in units of sd_d = {abs(mean_d)/sd_d:.3f} sd")

# primary metric: delta_of_deltas_sd_ratio (B vs A)
ratio = sd_B_delta/sd_A_delta
print(f"\nPRIMARY METRIC delta-of-deltas sd ratio (B/A) = {ratio:.4f}")
agree_within_1sd = abs(delta_A - mean_d) < sd_A_delta or abs(delta_A-mean_d) < sd_B_delta or (abs(mean_d) < sd_d and abs(delta_A) < sd_A_delta)
print(f"protocols' point deltas: A={delta_A:+.4f} ms, B={mean_d:+.4f} ms, |A-B|={abs(delta_A-mean_d):.4f} ms")
print(f"reject_gate (agree within 1 sd): {'FIRES' if agree_within_1sd else 'not met'}")
print(f"accept_gate (sd_B < 0.5*sd_A): {'MET' if ratio<0.5 else 'not met'}")

# stop rule: per-rep sd < 0.5% both protocols?
print(f"stop_rule: all per-rep rel sds <0.5%? A_lru={rel_A_lru:.3f}% A_bel={rel_A_bel:.3f}% B_lru={rel_B_lru:.3f}% B_bel={rel_B_bel:.3f}%")

out = {
 "deterministic_bytes": det, "metric": "wall_ms",
 "A": {"lru_mean": mean_A_lru, "lru_sd": sd_A_lru, "bel_mean": mean_A_bel, "bel_sd": sd_A_bel,
        "delta": delta_A, "delta_sd_single_rep": sd_A_delta},
 "B": {"d": d, "mean_d": mean_d, "sd_d": sd_d},
 "sd_ratio_B_over_A": ratio,
 "reject_gate_fires": bool(agree_within_1sd),
 "accept_gate_met": bool(ratio < 0.5),
}
json.dump(out, open("exp44_result.json","w"), indent=1)
print("\nwrote exp44_result.json")
