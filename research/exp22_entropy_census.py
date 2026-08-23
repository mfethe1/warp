# exp22: VQ3R index-entropy census on real K3 experts (E:\models\k3.waste)
# Read-only. Samples 32 experts/layer x 3 layers (1, 46, 92).
# Per record: 48B header -> blocked indices [gate|up|down] -> scales -> pad.
# Within each segment, stage = byte_offset_in_segment % 3 (blocked layout
# [nb, nvr, 64, 3]); blocking is a permutation, so marginal entropy is exact.
import struct, json, sys
import numpy as np

BASE = r"E:\models\k3.waste"
ALIGN = 4096
HDR = "<IHHBBHHHIIIIIIII"
REC = 12406784
SAMPLE_EIDS = [int(round(i * 895 / 31.0)) for i in range(32)]  # 0..895, even

def H(counts):
    p = counts / counts.sum()
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())

out = {"layers": {}, "sample_experts": SAMPLE_EIDS}
for L in (1, 46, 92):
    path = rf"{BASE}\experts-L{L}.bin"
    # acc[matrix][stage] -> counts[256]
    acc = [[np.zeros(256, dtype=np.int64) for _ in range(3)] for _ in range(3)]
    seg_lens = [0, 0, 0]
    nrec = 0
    with open(path, "rb") as f:
        for eid in SAMPLE_EIDS:
            f.seek(eid * REC)
            (magic, layer, _eid, fmt, flags, cb, lowrank, r0, blocks,
             g_off, u_off, d_off, corr_off, crc, r1, r2) = struct.unpack(HDR, f.read(48))
            assert magic == 0x50584557, hex(magic)
            assert layer == L and _eid == eid, (layer, _eid)
            assert fmt == 4, fmt  # WQ_VQ3R
            segs = [(g_off, u_off), (u_off, d_off), (d_off, corr_off)]
            for mi, (a, b) in enumerate(segs):
                n = b - a
                assert n % 3 == 0, (mi, n)
                seg_lens[mi] = n
                f.seek(eid * REC + a)
                buf = np.frombuffer(f.read(n), dtype=np.uint8).reshape(-1, 3)
                for st in range(3):
                    acc[mi][st] += np.bincount(buf[:, st], minlength=256)
            nrec += 1
    layer_res = {"n_experts": nrec, "segments": {}}
    for mi, mname in enumerate(("gate", "up", "down")):
        mres = {}
        for st in range(3):
            c = acc[mi][st]
            mres[f"stage{st}"] = {"H_bits": H(c), "n": int(c.sum()),
                                  "top5": [[int(s), int(c[s])] for s in np.argsort(-c)[:5]]}
        # marginal over all stages of this matrix
        c = acc[mi][0] + acc[mi][1] + acc[mi][2]
        mres["combined"] = {"H_bits": H(c), "n": int(c.sum())}
        layer_res["segments"][mname] = mres
    # whole-record marginal (all 9 stage-matrix cells)
    ctot = np.zeros(256, dtype=np.int64)
    for mi in range(3):
        for st in range(3):
            ctot += acc[mi][st]
    layer_res["record_marginal_H_bits"] = H(ctot)
    layer_res["seg_bytes"] = {"gate": seg_lens[0], "up": seg_lens[1],
                              "down": seg_lens[2]}
    out["layers"][str(L)] = layer_res

# Net-reduction model (per record): index bytes = 12,386,304; scales 20,480 B;
# rANS payload uses the WORST (highest-entropy) layer/matrix/stage estimate
# on the conservative side: use actual per-layer combined entropies.
IDX = 12386304
SCALES = 20480
REC_TOTAL = IDX + SCALES + 48  # 12406784
out["model"] = {"idx_bytes": IDX, "scales_bytes": SCALES, "rec_total": REC_TOTAL}
for L in (1, 46, 92):
    r = out["layers"][str(L)]
    tot_bits = 0.0
    for mname in ("gate", "up", "down"):
        n = r["segments"][mname]["combined"]["n"]
        tot_bits += r["segments"][mname]["combined"]["H_bits"] * n
    payload = tot_bits / 8.0
    # overhead: per-record rANS state + 3 segment tables (256 u16 freqs each,
    # entropy-coded tables would be smaller; use raw 1.5 KB worst case) 
    overhead = 1536 + 3 * 512
    new_total = payload + SCALES + 48 + overhead
    old_pages = REC_TOTAL // ALIGN
    new_pages = int(np.ceil(new_total / ALIGN))
    r["rans_payload_bytes"] = payload
    r["net_page_rounded_reduction_pct"] = 100.0 * (old_pages - new_pages) / old_pages
    r["symbol_level_reduction_pct"] = 100.0 * (1.0 - (tot_bits / 8.0) / IDX)
print(json.dumps(out, indent=1))
