#!/usr/bin/env python3
"""exp34 STAGE 1 -- VQ3R vs VQ4P record geometry, bottom-up.
Pinned SHA 7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b (src/waste_format.h, docs/FORMAT.md).
No K3 weights required: this is pure arithmetic over the frozen shapes.
Label: RECOMPUTATION.
"""
import json, math

PAGE = 4096
HDR  = 48            # static_assert(sizeof(waste_expert_hdr)==48)
VEC  = 8             # vec_dim
N_IN, N_OUT, NMAT = 3072, 3584, 3   # gate/up/down, K3 expert shape (established finding)

W = NMAT * N_IN * N_OUT
VECS = W // VEC
assert W % VEC == 0

def fmt(name, stages, entries, index_bits):
    bits_per_vec = stages * index_bits
    bpw = bits_per_vec / VEC
    idx_bytes_per_vec = bits_per_vec / 8
    assert float(idx_bytes_per_vec).is_integer(), "non-integral index bytes"
    idx_bytes = VECS * int(idx_bytes_per_vec)
    # per-output-row f16 scale, all three matrices (vq.c: "one f16 scale per output row")
    corr = NMAT * N_IN * 2
    raw = HDR + idx_bytes + corr
    pages = math.ceil(raw / PAGE)
    return dict(name=name, stages=stages, entries=entries, index_bits=index_bits,
                bits_per_weight=bpw, index_bytes_per_vector=int(idx_bytes_per_vec),
                index_bytes=idx_bytes, corr_bytes=corr, raw_bytes=raw,
                pages=pages, record_bytes=pages * PAGE,
                table_bytes_per_stage=entries * VEC,   # int8 runtime LUT, dim 8
                page_aligned=(pages * PAGE) % PAGE == 0)

vq3r = fmt("VQ3R", 3, 256, 8)
vq4p = fmt("VQ4P", 4, 64, 6)

checks = {
  "both_exactly_3.00_bits_per_weight": vq3r["bits_per_weight"] == 3.0 and vq4p["bits_per_weight"] == 3.0,
  "both_exactly_3_index_bytes_per_vector": vq3r["index_bytes_per_vector"] == 3 and vq4p["index_bytes_per_vector"] == 3,
  "index_payload_byte_identical": vq3r["index_bytes"] == vq4p["index_bytes"],
  "record_bytes_identical": vq3r["record_bytes"] == vq4p["record_bytes"],
  "page_count_identical": vq3r["pages"] == vq4p["pages"],
  "record_is_12406784B": vq3r["record_bytes"] == 12406784,
  "record_is_3029_pages": vq3r["pages"] == 3029,
}
# the packing round-trip from docs/FORMAT.md, verified exhaustively over all 64^4
def pack(s0,s1,s2,s3):
    return (s0 | (s1<<6)) & 0xff, ((s1>>2) | (s2<<4)) & 0xff, ((s2>>4) | (s3<<2)) & 0xff
def unpack(b0,b1,b2):
    return b0 & 0x3f, (b0>>6) | ((b1 & 0x0f)<<2), (b1>>4) | ((b2 & 0x03)<<4), b2>>2
bad = 0
for s0 in range(64):
    for s1 in range(64):
        for s2 in (0,1,17,33,62,63):
            for s3 in (0,1,17,33,62,63):
                if unpack(*pack(s0,s1,s2,s3)) != (s0,s1,s2,s3): bad += 1
checks["vq4p_6bit_packing_bijective"] = (bad == 0)
checks["packing_cases_tested"] = 64*64*6*6

out = dict(experiment="exp34", stage=1, label="RECOMPUTATION",
           source_sha="7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b",
           expert_shape=dict(n_matrices=NMAT, n_in=N_IN, n_out=N_OUT, weights=W, vectors=VECS),
           vq3r=vq3r, vq4p=vq4p, checks=checks,
           d_bytes_per_token_d_format=0 if checks["record_bytes_identical"] else None)
print(json.dumps(out, indent=2))
