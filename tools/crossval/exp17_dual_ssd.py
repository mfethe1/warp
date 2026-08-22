#!/usr/bin/env python3
"""exp17 / idea8: DUAL-SSD BANDWIDTH ECONOMICS.
Pure RECOMPUTATION from WARP established constants + published spec sheets.
No purchase, no device access, no K3 measurement.
"""
import math, json
from math import comb

GiB = 1.0
# ---- ESTABLISHED WARP CONSTANTS (do not re-derive) ----
LOGICAL   = 17.009      # GiB/token logical demand
PHYSICAL  = 7.719       # GiB/token physical (VQ3R 3.00 bpw)
BW_MEAS   = 5.919       # GiB/s measured single-drive effective (O_DIRECT, 3029-page records)
TARGET    = 15.0        # tok/s batch-1
CONTAINER = 952.0       # GiB VQ3R container
REC_BYTES = 12_406_784  # expert record = 3029 pages
LAYERS_K3 = 92
TOPK_K3   = 16

def required_bpt(bw):        # GiB/accepted token needed to hit 15 tok/s
    return bw / TARGET

def gap_factor(bw):          # how much byte reduction still needed
    return PHYSICAL / required_bpt(bw)

# ---- 1. bandwidth -> required bytes/accepted token ----
rows = []
for bw in (5.919, 9.0, 11.838, 12.0, 18.0):
    rows.append((bw, required_bpt(bw), gap_factor(bw)))

# ---- 2. static placement theory ----
# time per byte-set: with fraction f of bytes on drive A(bw a), 1-f on B(bw b)
# t = max(f/a, (1-f)/b);  optimal f* = a/(a+b) -> aggregate = a+b
# uniform hash f=0.5      -> aggregate = 2*min(a,b)
def agg_uniform(a, b): return 2 * min(a, b)
def agg_optimal(a, b): return a + b

COLIBRI_PAIR = (9.0, 3.0)   # colibri's claimed 9+3 GB/s pair

# ---- 3. batch-1 per-layer barrier imbalance under SHARDED uniform hash ----
# Each layer step issues n=TOPK independent record reads. Next layer's expert set
# is not known until this layer completes (sequential dependency at batch-1),
# so the step ends at max(load_A, load_B), not at the mean.
def expected_max_split(n, p=0.5):
    """E[max(X, n-X)] for X~Bin(n,p) -- records landing on drive A.
    log-space pmf so large n does not overflow."""
    lg = math.lgamma
    tot = 0.0
    for k in range(n + 1):
        lpmf = (lg(n+1) - lg(k+1) - lg(n-k+1)
                + k*math.log(p) + (n-k)*math.log(1-p))
        tot += math.exp(lpmf) * max(k, n-k)
    return tot

def imbalance_loss(n):
    em = expected_max_split(n)
    return em, em / (n/2.0) - 1.0

per_layer = imbalance_loss(TOPK_K3)                 # batch-1, per-layer barrier
per_token = imbalance_loss(TOPK_K3 * LAYERS_K3)     # hypothetical full read-ahead

# ---- 4. economics ----
# Published spec sheets (seq read), derated by measured efficiency of our O_DIRECT path.
EFF = BW_MEAS / (7450e6 / 2**30)   # measured / Samsung 990 Pro 2TB spec 7450 MB/s
SPECS = [
    # name, spec seq-read MB/s, 2TB street $, interface
    ("Samsung 990 Pro 2TB",      7450,  150, "PCIe 4.0 x4"),
    ("WD SN850X 2TB",            7300,  140, "PCIe 4.0 x4"),
    ("Crucial T705 2TB",        14100,  250, "PCIe 5.0 x4"),
    ("Samsung 9100 Pro 2TB",    14800,  260, "PCIe 5.0 x4"),
]
def derate(mbs): return (mbs * 1e6 / 2**30) * EFF

out = {
  "constants": {"logical_gib_tok": LOGICAL, "physical_gib_tok": PHYSICAL,
                "bw_measured_gib_s": BW_MEAS, "target_tok_s": TARGET,
                "container_gib": CONTAINER, "record_bytes": REC_BYTES,
                "k3_layers": LAYERS_K3, "k3_topk": TOPK_K3,
                "measured_efficiency_vs_spec": round(EFF, 4)},
  "bw_table": [{"agg_bw_gib_s": b, "required_gib_per_accepted_token": round(r, 4),
                "byte_reduction_factor_still_needed": round(g, 3)} for b, r, g in rows],
  "placement": {
     "colibri_pair_9_plus_3": {
        "uniform_hash_aggregate_gib_s": agg_uniform(*COLIBRI_PAIR),
        "bw_proportional_aggregate_gib_s": agg_optimal(*COLIBRI_PAIR),
        "fast_drive_alone_gib_s": max(COLIBRI_PAIR),
        "uniform_hash_vs_fast_alone": round(agg_uniform(*COLIBRI_PAIR)/max(COLIBRI_PAIR), 4),
        "claimed_speedup_1.33_matches_proportional": round(agg_optimal(*COLIBRI_PAIR)/max(COLIBRI_PAIR), 4),
     },
     "matched_pair_5.919x2": {"uniform_hash_aggregate_gib_s": agg_uniform(BW_MEAS, BW_MEAS)},
  },
  "batch1_imbalance": {
     "sharded_per_layer_barrier": {"n": TOPK_K3, "E_max_records": round(per_layer[0], 4),
                                   "slowdown_vs_ideal": round(per_layer[1], 4)},
     "full_readahead_per_token":  {"n": TOPK_K3*LAYERS_K3, "E_max_records": round(per_token[0], 2),
                                   "slowdown_vs_ideal": round(per_token[1], 4)},
  },
  "capacity": {
     "container_gib": CONTAINER,
     "sharded_per_drive_gib": CONTAINER/2,
     "duplicated_per_drive_gib": CONTAINER,
     "usable_1TB_gib": 1000e9/2**30, "usable_2TB_gib": 2000e9/2**30,
     "note_1TB_too_small_for_duplication": (1000e9/2**30) < CONTAINER,
  },
  "cost": [],
}
for name, spec, price, iface in SPECS:
    d = derate(spec)
    out["cost"].append({
        "drive": name, "iface": iface, "spec_seq_read_MB_s": spec,
        "derated_effective_gib_s": round(d, 3), "street_2TB_usd": price,
        "usd_per_effective_gib_s": round(price / d, 2),
    })

# marginal economics of adding a matched 990 Pro (duplicated container)
d0 = BW_MEAS
d1 = derate(7450)
agg = d0 + d1   # duplication -> perfectly splittable -> additive
out["marginal"] = {
   "single_drive_gib_s": d0,
   "dual_duplicated_agg_gib_s": round(agg, 3),
   "gap_before": round(gap_factor(d0), 3),
   "gap_after": round(gap_factor(agg), 3),
   "gap_factor_reduction": round(gap_factor(d0)/gap_factor(agg), 4),
   "added_cost_usd": 150,
   "usd_per_GiB_s_added": round(150/d1, 2),
   "ms_per_token_before": round(1000*PHYSICAL/d0, 1),
   "ms_per_token_after": round(1000*PHYSICAL/agg, 1),
   "tok_s_before_no_algo_change": round(d0/PHYSICAL, 4),
   "tok_s_after_no_algo_change": round(agg/PHYSICAL, 4),
}
# sharded variant pays the per-layer barrier tax
sh = agg / (1 + per_layer[1])
out["marginal"]["dual_sharded_effective_gib_s"] = round(sh, 3)
out["marginal"]["sharded_gap_after"] = round(gap_factor(sh), 3)
out["marginal"]["duplication_capacity_cost_gib"] = CONTAINER  # extra copy

print(json.dumps(out, indent=2))
