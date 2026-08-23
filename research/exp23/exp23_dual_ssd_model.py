#!/usr/bin/env python3
"""
exp23 -- DUAL/MULTI-SSD STRIPING ECONOMIC MODEL  [RECOMPUTATION]

Extends exp17 (2-drive duplicate vs shard) to the full preregistered ladder:
  required bytes/accepted token at aggregate 5.919 / 9 / 12 / 18 GiB/s,
  duplicate-container vs sharded-container,
  capacity for 952 GiB VQ3R, SSD cost under a $3,000 rig budget,
  queue-depth and imbalance penalties,
  byte amplification from retries or duplicate reads.

ALL numbers are RECOMPUTATION from established WARP findings + published
drive spec sheets. NOTHING here is a K3 measurement.
"""
import itertools, json, math, hashlib, sys
from collections import Counter

# ---------------------------------------------------------------- constants
# ESTABLISHED FINDINGS (do not re-derive)
LOGICAL_GIB_PER_TOKEN  = 17.009      # GiB/token logical demand
PHYSICAL_GIB_PER_TOKEN = 7.719       # GiB/token physical (VQ3R, post-residency)
TARGET_TOKS            = 15.0        # goal: >= 15 tok/s batch-1
BW_MEASURED            = 5.919       # GiB/s, measured single Samsung 990 Pro
VQ3R_FOOTPRINT_GIB     = 952.0       # full K3 in VQ3R 3.00 bits/weight
EXPERT_RECORD_BYTES    = 12_406_784  # exactly 3029 pages x 4096
PAGE                   = 4096
K3_LAYERS              = 92
K3_TOPK                = 16
BUDGET_USD             = 3000.0

# derating measured on our own hardware (exp17): 5.919 measured / 6.938 spec
DERATE = BW_MEASURED / 6.938

GIB = 1024**3
GB  = 1000**3

# published spec sheets (seq read, MB/s) + street price, 2TB class
DRIVES = {
    "samsung_990_pro_2tb":  dict(spec_mbs=7450,  usd=150, gen=4, measured=True),
    "samsung_9100_pro_2tb": dict(spec_mbs=14800, usd=230, gen=5, measured=False),
    "crucial_t705_2tb":     dict(spec_mbs=14500, usd=250, gen=5, measured=False),
}
for d in DRIVES.values():
    d["spec_gibs"] = d["spec_mbs"] * GB / GIB / 1000  # MB/s -> GiB/s
    d["eff_gibs"]  = d["spec_gibs"] * DERATE
    d["usable_gib"] = 2000 * GB / GIB   # 2 TB marketed -> GiB usable

# ------------------------------------------------------- core objective math
def required_bytes_per_token(bw_gibs):
    """tok/s = BW / bytes_per_token  ->  bytes_per_token = BW / target"""
    return bw_gibs / TARGET_TOKS

def gap(bw_gibs):
    return PHYSICAL_GIB_PER_TOKEN / required_bytes_per_token(bw_gibs)

def ms_per_token(bw_gibs, bytes_per_token=PHYSICAL_GIB_PER_TOKEN):
    return bytes_per_token / bw_gibs * 1000.0

# ------------------------------------------------- imbalance / makespan math
def exact_expected_max_load(n_balls, n_bins):
    """E[max bin load] for n_balls thrown uniformly into n_bins (exact,
    enumerated over compositions).  This is the per-layer barrier makespan
    for a SHARDED container at batch-1: the layer cannot proceed until the
    slowest device has delivered its share."""
    total = 0.0
    denom = float(n_bins) ** n_balls
    # enumerate compositions of n_balls into n_bins
    def comps(n, k):
        if k == 1:
            yield (n,); return
        for i in range(n + 1):
            for rest in comps(n - i, k - 1):
                yield (i,) + rest
    for c in comps(n_balls, n_bins):
        # multinomial coefficient
        coef = math.factorial(n_balls)
        for x in c:
            coef //= math.factorial(x)
        total += coef * max(c)
    return total / denom

def shard_makespan(n_balls, n_bins):
    return exact_expected_max_load(n_balls, n_bins)

def duplicate_makespan(n_balls, n_bins):
    """Full duplication -> dispatcher is free to place any expert on any
    device, so makespan is the perfectly balanced ceiling."""
    return math.ceil(n_balls / n_bins)

def ideal_makespan(n_balls, n_bins):
    return n_balls / n_bins

# ----------------------------------------------------------------- configs
def eff_bw(devices, mode):
    """devices: list of per-device effective GiB/s.
    mode 'duplicate': dispatcher balances -> aggregate is bandwidth-additive
                      up to the discrete makespan penalty.
    mode 'shard_uniform': uniform hash forces the assignment; the per-layer
                      barrier runs at the SLOWEST device's finish time."""
    d = len(devices)
    agg = sum(devices)
    if mode == "duplicate":
        ms = duplicate_makespan(K3_TOPK, d)
        tax = ms / ideal_makespan(K3_TOPK, d)
        # heterogeneous duplicate: work is assigned proportional to speed,
        # so the additive aggregate is attainable modulo the discrete tax
        return agg / tax, tax
    if mode == "shard_uniform":
        ms = shard_makespan(K3_TOPK, d)
        tax = ms / ideal_makespan(K3_TOPK, d)
        if len(set(devices)) == 1:
            return agg / tax, tax
        # ASYMMETRIC uniform hash: each device gets ~n/d records regardless of
        # its speed. Barrier = max over devices of (share / speed).
        share = K3_TOPK / d
        t_slow = max(share / s for s in devices)
        # exact-ish: use expected max load on the slowest device
        return (K3_TOPK / (ms / min(devices) if False else t_slow * tax), tax)
    raise ValueError(mode)

# ----------------------------------------------------------------- report
out = {"labels": "ALL FIGURES RECOMPUTATION or PROJECTION -- NO K3 MEASUREMENT",
       "derate": DERATE, "established": {
           "physical_gib_per_token": PHYSICAL_GIB_PER_TOKEN,
           "bw_measured_gibs": BW_MEASURED,
           "expert_record_bytes": EXPERT_RECORD_BYTES}}

print("="*74)
print("A. PREREGISTERED BANDWIDTH LADDER  [RECOMPUTATION]")
print("="*74)
print(f"{'agg BW GiB/s':>13} {'req B/tok GiB':>14} {'gap x':>9} {'ms/token':>10} {'tok/s @7.719':>13}")
ladder = []
for bw in (BW_MEASURED, 9.0, 12.0, 18.0):
    req = required_bytes_per_token(bw)
    g   = gap(bw)
    ms  = ms_per_token(bw)
    tps = bw / PHYSICAL_GIB_PER_TOKEN
    ladder.append(dict(bw=bw, req_gib=req, gap=g, ms=ms, toks=tps))
    print(f"{bw:13.3f} {req:14.4f} {g:9.3f} {ms:10.1f} {tps:13.4f}")
out["ladder"] = ladder

print()
print("="*74)
print("B. IMBALANCE / QUEUE-DEPTH PENALTY  (batch-1, top-16, per-layer barrier)")
print("="*74)
print(f"{'devices':>8} {'ideal':>7} {'shard E[max]':>13} {'shard tax':>10} "
      f"{'dup makespan':>13} {'dup tax':>8}")
imb = []
for d in (2, 3, 4):
    idl = ideal_makespan(K3_TOPK, d)
    sm  = shard_makespan(K3_TOPK, d)
    dm  = duplicate_makespan(K3_TOPK, d)
    row = dict(devices=d, ideal=idl, shard_emax=sm, shard_tax=sm/idl,
               dup_makespan=dm, dup_tax=dm/idl)
    imb.append(row)
    print(f"{d:8d} {idl:7.3f} {sm:13.4f} {sm/idl:9.4f}x {dm:13d} {dm/idl:7.4f}x")
out["imbalance"] = imb

print()
print("="*74)
print("C. BYTE AMPLIFICATION  [RECOMPUTATION -- the decisive audit point]")
print("="*74)
# duplication: every selected expert is read ONCE, from whichever replica the
# dispatcher picks. Replicas are not both read.
reads_per_expert_duplicate = 1
reads_per_expert_shard     = 1
amp_read_dup   = (reads_per_expert_duplicate - 1) * 100.0
amp_read_shard = (reads_per_expert_shard - 1) * 100.0
# stored amplification is a CAPACITY cost, not a bandwidth/bytes cost
print(f"READ  amplification, duplicate container : {amp_read_dup:.3f}%")
print(f"READ  amplification, sharded  container : {amp_read_shard:.3f}%")
for d in (2, 3, 4):
    print(f"STORE amplification, {d}x duplicate      : {(d-1)*100.0:.1f}%"
          f"  ({d*VQ3R_FOOTPRINT_GIB:.0f} GiB stored)")
print("NOTE: the ACCEPT gate says 'physical-byte amplification <=1%'. Read and")
print("      stored amplification are DIFFERENT quantities; only READ bytes")
print("      appear in bytes/accepted token. Recorded as an audit finding.")
out["amplification"] = dict(read_duplicate_pct=amp_read_dup,
                            read_shard_pct=amp_read_shard,
                            store_pct={d: (d-1)*100.0 for d in (2,3,4)})
# page-rounding waste is the only true read amplification present
waste = (math.ceil(EXPERT_RECORD_BYTES/PAGE)*PAGE - EXPERT_RECORD_BYTES)
print(f"Page-rounding read waste: {waste} B on {EXPERT_RECORD_BYTES} B "
      f"= {waste/EXPERT_RECORD_BYTES*100:.4f}%  (record is exactly "
      f"{EXPERT_RECORD_BYTES//PAGE} pages)")
out["amplification"]["page_round_waste_pct"] = waste/EXPERT_RECORD_BYTES*100

print()
print("="*74)
print("D. CAPACITY  (952 GiB VQ3R)")
print("="*74)
usable = DRIVES["samsung_990_pro_2tb"]["usable_gib"]
print(f"2TB-class usable: {usable:.1f} GiB")
for d in (2, 3, 4):
    need_dup   = VQ3R_FOOTPRINT_GIB          # per device, full replica
    need_shard = VQ3R_FOOTPRINT_GIB / d
    print(f"  {d}x  duplicate: {need_dup:7.1f} GiB/dev "
          f"({'FITS' if need_dup<=usable else 'NO FIT'}, "
          f"{need_dup/usable*100:.1f}% full)   "
          f"sharded: {need_shard:7.1f} GiB/dev "
          f"({'FITS' if need_shard<=usable else 'NO FIT'})")

print()
print("="*74)
print("E. PLATFORM PCIe LANE CONSTRAINT  [PROJECTION -- decisive for >12 GiB/s]")
print("="*74)
print("Consumer AM5: CPU-direct = 1x Gen5 x4 M.2 + 1x Gen4 x4 M.2.")
print("Extra M.2 slots hang off the chipset, which shares ONE Gen4 x4 uplink")
print(f"= {4*1.969*DERATE:.3f} GiB/s derated TOTAL for all chipset devices.")
print("=> naive '4 drives on the motherboard' does NOT give 4x bandwidth.")
print("WARP runs CPU-only streaming inference: the x16 GPU link is UNUSED.")
print("Bifurcating x16 -> 4x x4 via a passive carrier gives 4 CPU-direct NVMe.")
out["platform_note"] = ("chipset M.2 share one Gen4 x4 uplink; x16 GPU link is "
                        "unused under CPU-only streaming and bifurcates to 4x x4")

print()
print("="*74)
print("F. BUILD CONFIGURATIONS  [PROJECTION, derated spec sheets]")
print("="*74)
BIFURC_CARD = 70.0
REST_OF_RIG = 2010.0   # CPU + mobo + 128GB DDR5, stated assumption

configs = []
def add(name, drivekey, n, mode, extra_usd=0.0, note=""):
    dv = DRIVES[drivekey]
    devs = [dv["eff_gibs"]] * n
    bw, tax = eff_bw(devs, mode)
    usd = dv["usd"] * n + extra_usd
    per_dev_need = VQ3R_FOOTPRINT_GIB if mode == "duplicate" else VQ3R_FOOTPRINT_GIB/n
    fits = per_dev_need <= dv["usable_gib"]
    configs.append(dict(name=name, n=n, mode=mode, per_dev_gibs=dv["eff_gibs"],
                        agg_gibs=bw, tax=tax, usd=usd,
                        gain_vs_measured=bw/BW_MEASURED - 1.0,
                        gap=gap(bw), ms=ms_per_token(bw),
                        capacity_fits=fits, total_rig=usd+REST_OF_RIG, note=note))

add("1x 990 Pro (BASELINE, measured)", "samsung_990_pro_2tb", 1, "duplicate")
add("2x 990 Pro duplicate",            "samsung_990_pro_2tb", 2, "duplicate")
add("2x 990 Pro sharded (uniform hash)","samsung_990_pro_2tb",2, "shard_uniform")
add("3x 990 Pro duplicate",            "samsung_990_pro_2tb", 3, "duplicate", BIFURC_CARD)
add("3x 990 Pro sharded",              "samsung_990_pro_2tb", 3, "shard_uniform", BIFURC_CARD)
add("4x 990 Pro duplicate (bifurc)",   "samsung_990_pro_2tb", 4, "duplicate", BIFURC_CARD)
add("4x 990 Pro sharded (bifurc)",     "samsung_990_pro_2tb", 4, "shard_uniform", BIFURC_CARD)
add("2x 9100 Pro Gen5 duplicate",      "samsung_9100_pro_2tb",2, "duplicate")
add("4x 9100 Pro Gen5 duplicate",      "samsung_9100_pro_2tb",4, "duplicate", BIFURC_CARD)
add("4x 9100 Pro Gen5 sharded",        "samsung_9100_pro_2tb",4, "shard_uniform", BIFURC_CARD)

hdr = (f"{'config':<34}{'aggGiB/s':>9}{'gain':>8}{'gap x':>8}"
       f"{'ms/tok':>8}{'$SSD':>7}{'$rig':>7}{'cap':>5}")
print(hdr); print("-"*len(hdr))
for c in configs:
    print(f"{c['name']:<34}{c['agg_gibs']:9.3f}{c['gain_vs_measured']*100:7.1f}%"
          f"{c['gap']:8.3f}{c['ms']:8.1f}{c['usd']:7.0f}{c['total_rig']:7.0f}"
          f"{'  ok' if c['capacity_fits'] else '  NO':>5}")
out["configs"] = configs

print()
print("="*74)
print("G. DOLLARS PER UNIT OF GAP CLOSED  [RECOMPUTATION]")
print("="*74)
base = configs[0]
print(f"{'config':<34}{'d$ SSD':>8}{'+GiB/s':>9}{'$/GiB/s':>10}{'gap closed':>12}{'$/gapx':>9}")
econ = []
for c in configs[1:]:
    dusd = c["usd"] - base["usd"]
    dbw  = c["agg_gibs"] - base["agg_gibs"]
    dgap = base["gap"] - c["gap"]
    e = dict(name=c["name"], d_usd=dusd, d_bw=dbw,
             usd_per_gibs=dusd/dbw if dbw > 0 else float("inf"),
             gap_closed=dgap, usd_per_gapx=dusd/dgap if dgap > 0 else float("inf"))
    econ.append(e)
    print(f"{c['name']:<34}{dusd:8.0f}{dbw:9.3f}{e['usd_per_gibs']:10.2f}"
          f"{dgap:12.3f}{e['usd_per_gapx']:9.0f}")
out["economics"] = econ

print()
print("="*74)
print("H. PREREGISTERED GATE EVALUATION")
print("="*74)
gate_rows = []
for c in configs[1:]:
    g1 = c["gain_vs_measured"] >= 0.20
    g2 = amp_read_dup <= 1.0 if c["mode"] == "duplicate" else amp_read_shard <= 1.0
    g3 = c["total_rig"] < BUDGET_USD
    g4 = c["capacity_fits"]
    ok = g1 and g2 and g3 and g4
    gate_rows.append(dict(name=c["name"], bw20=g1, amp=g2, budget=g3,
                          capacity=g4, ACCEPT=ok))
    print(f"{c['name']:<34} BW>=20%:{'Y' if g1 else 'N'} "
          f"amp<=1%:{'Y' if g2 else 'N'} rig<$3k:{'Y' if g3 else 'N'} "
          f"cap:{'Y' if g4 else 'N'}  -> {'ACCEPT' if ok else 'reject'}")
out["gates"] = gate_rows

print()
print("="*74)
print("I. COUPLING TO CPU-SIDE DEQUANT (exp20 dependency)")
print("="*74)
print("Raising aggregate BW only helps while VQ3R dequant keeps up. At")
print("aggregate B GiB/s the dequant loop must sustain B GiB/s of 3-bit-index")
print("-> dim-8 codeword expansion. exp20 is measuring exactly that ceiling.")
print("If dequant sustains D GiB/s aggregate, usable BW = min(B, D).")
for c in configs:
    print(f"  {c['name']:<34} needs dequant >= {c['agg_gibs']:6.2f} GiB/s")

print()
print(json.dumps({"summary_keys": list(out.keys())}))
with open("evidence/exp23_dual_ssd_model.json", "w") as f:
    json.dump(out, f, indent=2, default=str)
print("wrote evidence/exp23_dual_ssd_model.json")
