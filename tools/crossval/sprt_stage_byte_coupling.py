#!/usr/bin/env python3
"""exp5 whitened-basis + SPRT: does 'mean VQ stages read per expert' map to bytes?

ALL NUMBERS = [RECOMPUTATION] from pinned published constants. No K3 executed.
Deterministic algebra; N=1; variance N/A.
"""
import json, hashlib, os

# ---- pinned constants (source-of-truth citations in the writeup) ----
HIDDEN        = 7168      # docs/K3.md:41
LATENT        = 3584      # docs/K3.md:44  "expert latent dim"
MOE_INTER     = 3072      # docs/K3.md:11
LAYERS_MOE    = 92        # docs/K3.md:43
TOPK          = 16        # docs/K3.md:42
RECORD_BYTES  = 12_406_784  # docs/FORMAT.md:296 "exactly 3029 pages"
PAGE          = 4096
STAGES        = 3         # src/waste_format.h:50 WQ_VQ3R
VEC_DIM       = 8
IDX_BITS      = 8         # 256 entries/stage -> 1 byte/stage/vector
GIB           = 1024**3
BW_GIBS       = 5.9194836464   # consolidation-task3-storage-summary.json:43
PHYS_DEMAND   = 7.719          # GiB/token, established
TARGET_DEMAND = 0.3946         # GiB/token for 15 tok/s, established

out = {}

# ---- 1. reconstruct the record from first principles ----
weights = 3 * LATENT * MOE_INTER          # gate + up + down in latent space
vectors = weights // VEC_DIM
idx_payload = vectors * STAGES * (IDX_BITS // 8)
overhead = RECORD_BYTES - idx_payload
pages = RECORD_BYTES // PAGE

out['weights_per_expert'] = weights
out['vectors_per_expert'] = vectors
out['index_payload_B'] = idx_payload
out['header_plus_corrections_B'] = overhead
out['record_B'] = RECORD_BYTES
out['record_pages'] = pages
out['record_is_page_exact'] = (RECORD_BYTES % PAGE == 0)
out['bits_per_weight_check'] = idx_payload * 8 / weights
out['one_stage_plane_B'] = vectors * 1
out['stage_plane_frac_of_record'] = vectors / RECORD_BYTES

# ---- 2. the objective ----
# B_acc = M * R / a
# M = physical expert-record transfers/attempted token
# R = physical bytes per transferred record
# a = accepted tokens / attempted token
M = LAYERS_MOE * TOPK
out['M_activations_per_token'] = M

# SPRT stops reading STAGES *after the pread has already completed*.
# FORMAT.md:295 -> "One pread of record_4k_blocks*4096 bytes yields the whole expert."
# GPU_VQ_GB10.md:57-59 -> stage bytes are INTERLEAVED: "reads the three
#   adjacent stage bytes for each row". Stages are not separable planes on disk.
# Therefore for any stages-read s in [1,3]:
for s in (1, 2, 3):
    out[f'R_bytes_at_{s}_stages_read'] = RECORD_BYTES     # invariant
out['dR_dstages'] = 0
out['dM_dstages'] = 0     # routing unchanged; SPRT is post-fetch
out['da_dstages']  = 0    # exact-argmax rate held fixed BY THE SPEC's own metric
out['dBacc_dstages'] = 0

# ---- 3. most-generous counterfactual: segregate stages into 3 planes ----
# (violates one-pread + O_DIRECT fixed-length, but bounds the ceiling)
best_case_saving = 1 - (idx_payload / STAGES * 1 + overhead) / RECORD_BYTES  # skip 2 of 3
gen = {}
for mean_stages in (1.0, 1.5, 2.0, 2.5, 3.0):
    r = (vectors * mean_stages) + overhead
    # page-quantise: a real separable read is still 4KiB-granular
    r_pages = -(-int(r) // PAGE) * PAGE
    demand = PHYS_DEMAND * r_pages / RECORD_BYTES
    gen[f'mean_stages_{mean_stages}'] = {
        'R_B': r_pages,
        'R_frac_of_baseline': r_pages / RECORD_BYTES,
        'demand_GiB_per_token': round(demand, 4),
        'tok_per_s': round(BW_GIBS / demand, 4),
        'speedup_vs_baseline': round(RECORD_BYTES / r_pages, 4),
    }
out['generous_counterfactual_segregated_planes'] = gen
out['max_speedup_if_stages_were_separable'] = round(STAGES, 4)
out['speedup_needed_for_15tps'] = round(PHYS_DEMAND / TARGET_DEMAND, 4)
out['generous_ceiling_covers_target'] = (STAGES >= PHYS_DEMAND / TARGET_DEMAND)

# ---- 4. verdict inputs ----
out['baseline_tok_per_s'] = round(BW_GIBS / PHYS_DEMAND, 5)
out['interaction_measurable_offline'] = False
out['reason_not_measurable'] = (
    "gain(A), gain(B), gain(A+B) all require refitting VQ stages on real Kimi "
    "expert weights with an activation importance matrix. No such weights or "
    "activation covariance are in-repo; docs/gn100/*.json publishes no per-stage "
    "certification counts. Winnie CPU 80% -> no compute allowed this tick.")

print(json.dumps(out, indent=2))
with open('/tmp/exp5_result.json', 'w') as f:
    json.dump(out, f, indent=2)
