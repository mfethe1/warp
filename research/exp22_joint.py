# exp22 supplement: JOINT entropy of (stage0,stage1,stage2) triples, gate matrix,
# layer 46, 32 experts. Marginal sum upper-bounds joint H; this measures it.
import struct
import numpy as np

BASE = r"E:\models\k3.waste"
HDR = "<IHHBBHHHIIIIIIII"
REC = 12406784
L = 46
SAMPLE = [int(round(i * 895 / 31.0)) for i in range(32)]

acc = np.zeros(1 << 24, dtype=np.int64)   # too big? 16.7M int64 = 134 MB, ok
with open(rf"{BASE}\experts-L{L}.bin", "rb") as f:
    for eid in SAMPLE:
        f.seek(eid * REC)
        h = struct.unpack(HDR, f.read(48))
        g_off, u_off = h[9], h[10]
        n = u_off - g_off
        f.seek(eid * REC + g_off)
        buf = np.frombuffer(f.read(n), dtype=np.uint8).reshape(-1, 3)
        key = buf[:, 0].astype(np.int64) << 16 | buf[:, 1].astype(np.int64) << 8 | buf[:, 2].astype(np.int64)
        acc += np.bincount(key, minlength=1 << 24)
p = acc / acc.sum()
pnz = p[p > 0]
H_joint = float(-(pnz * np.log2(pnz)).sum())
n = int(acc.sum())
distinct = int((acc > 0).sum())
# marginal sum for the same data
c0 = acc.reshape(-1, 256).sum(0)  # wrong shape; recompute properly below
print(f"n_triples={n} distinct={distinct} H_joint_bits={H_joint:.6f} H_joint_per_stage={H_joint/3:.6f}")
print(f"implied_payload_per_record_gate_B={H_joint/8*4128768/3:.0f} vs 4128768 raw")
print(f"saving_pct={(1-(H_joint/24))*100:.4f}")
