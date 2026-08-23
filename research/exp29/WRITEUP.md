# exp29 — Latency-bound layer barrier: RAID0 vs duplication vs shard

**Verdict: FALSIFIED (as preregistered).** Mechanism direction CONFIRMED, quantitative law REFUTED.

**Evidence class:** RECOMPUTATION over a PROXY trace. **No K3 measurement appears anywhere in this experiment.**

## Inputs

- Trace: `tests/trace_kimi_300.jsonl`, `src_sha256=06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965`
  (via exp24 `canonical_v2.jsonl`, sha256 `c86d0c2e...5a77`).
- **PROXY** shape: 26 layers × 256 experts × top-8 = 62,400 accesses, N=7,800 layer-visits. **NOT K3** (92L × 896E × top-16).
- K3-equivalent top-16 miss pmf obtained by self-convolution of the empirical top-8 per-layer miss pmf (preserves E[k]×2 exactly). Empirical throughout — no Bin(16,p) assumption in the trace arms.
- Constants: record 12,406,784 B = 3029 pages = 0.0115547 GiB; single-device 5.919 GiB/s; t_rec = 1.9521 ms; layer budget @15 tok/s over 92L = 0.72464 ms.

## Gate 1 — arms A,B reproduce exp23 (harness validity)

| D | shard E[max] | shard tax | exp23 | delta |
|---|---|---|---|---|
| 2 | 9.5710 | 1.1964 | 1.1964 | 0.0016% |
| 3 | 7.3334 | 1.3750 | 1.3750 | 0.0005% |
| 4 | 6.1390 | 1.5348 | 1.5348 | 0.0030% |

**PASS** — max deviation 0.003%, far inside the 1% tolerance. Harness is valid.

## Gate 2 — RAID0 B_eff advantage ≥10% at the target miss rate

At the lowest reachable LRU point (cap=5120, K3-equiv E[k]=1.30333, physical 1.3855 GiB/tok):

| D | dup ms | RAID0 ms | dup B_eff | RAID0 B_eff | advantage |
|---|---|---|---|---|---|
| 2 | 1.6500 | 1.2810 | 9.127 | 11.756 | **+28.81%** |
| 3 | 1.3879 | 0.8601 | 10.850 | 17.508 | **+61.36%** |
| 4 | 1.2738 | 0.6451 | 11.823 | 23.345 | **+97.46%** |

**PASS** at every device count.

## Gate 3 — empirical crossover within ±25% of E[k]=D

**FAIL.** Predicted crossovers at E[k]=2, 3, 4. Observed:

- D=2: crossover at **E[k]=15.209** (band 1.50–2.50) — off by 7.6×
- D=3: **no crossover anywhere** in the reachable range; RAID0 wins by 10.93%–61.36% throughout
- D=4: crossover at **E[k]=15.461** (band 3.00–5.00) — off by 3.9×

## Preregistered verdict

ACCEPT required gate1 ∧ gate2 ∧ gate3. Gate 3 failed ⇒ **REJECT / falsified**. Gates were not moved after seeing data.

## What is actually true

The *sign* of the effect is confirmed and strengthens monotonically as the miss rate falls — RAID0 beats duplication across the entire reachable range for D=3, and by ~2× at D=4 at the lowest reachable miss rate. But the queueing story that motivated it is **wrong**. The crossover is not at E[k]=D; it sits near E[k]≈15–16, i.e. essentially at *saturation* (top-16, every expert missing). RAID0's advantage decays smoothly with rising E[k] rather than inverting at D.

Root cause: `duplicate` costs `E[ceil(k/D)]·t_rec`, and the ceiling only stops hurting when k is a large multiple of D. At k=16, D=2 and D=4 divide 16 exactly, so duplication finally ties RAID0 (−0.69% and −1.40%); D=3 does not divide 16, so RAID0 still wins by 10.93%. **The crossover is a divisibility artifact of the ceiling, not a queueing threshold.** The prediction's "bank of tellers" analogy mislocated the mechanism.

## Corollary (holds, and is the decisive number)

t_rec = 1.9521 ms = **2.694 layer budgets**. Any layer with even one miss served whole-record by a single device has already overrun the 15 tok/s budget, regardless of device count. Under duplication the whole-record read is irreducible; only sub-record parallelism (RAID0) can shorten it.

At the exact preregistered target E[k]=0.3713 — **PROJECTION**, binomial form taken verbatim from the spec, not from the trace, because LRU on this trace bottoms out at E[k]=1.303 and cannot reach 0.371:

| D | dup ms | RAID0 ms | adv | dup %budget | RAID0 %budget |
|---|---|---|---|---|---|
| 2 | 0.6222 | 0.3648 | +70.5% | 85.9% | 50.3% |
| 3 | 0.6120 | 0.2450 | +149.8% | 84.5% | 33.8% |
| 4 | 0.6113 | 0.1837 | +232.7% | 84.4% | **25.4%** |

Duplication consumes ~84–86% of the layer budget on I/O alone at *every* device count — it is flat in D, which is exactly mismatch #9's claim. RAID0 scales.

## Objective check

Optimizes **effective bandwidth (B_eff)**, not bytes. Physical bytes per accepted token are **exactly invariant** across all three arms: each selected expert is read exactly once; page-rounding waste is 0 B (record is exactly 3029 pages); RAID0 read amplification is 0 because the stripe set covers the record exactly once. Confirmed: the tail-stripe tax is a *time* imbalance (1.0069× at D=2, 1.0142× at D=3,4), not extra bytes.

Algebraic connection: tok/s = B_eff / (bytes per accepted token). This experiment moves only the numerator, and the trace arms show B_eff is a **function of the miss rate**, not a constant — D=4 duplication delivers 11.82 GiB/s at E[k]=1.30 but 23.68 GiB/s at E[k]=16, while RAID0 holds 23.345 GiB/s flat at all miss rates. This is direct empirical support for **mismatch #9**: any B_eff figure quoted without its miss rate is meaningless, and exp23's 23.677 GiB/s was an E[k]=16 number that does not transfer to the target regime.

## Honest limits

- PROXY trace is Kimi-Linear-shaped (26L/256E/top-8), not K3 (92L/896E/top-16). The top-16 pmf is a convolution construct, not measured.
- LRU bottoms out at K3-equiv E[k]=1.303 (physical 1.3855 GiB/tok) on this trace; the target 0.3713 is unreachable, so the target-point table is a PROJECTION under the spec's own binomial form, per the stop rule.
- Linear service model at 12 MB granularity. If per-command overhead dominates at ~3.1 MB/device (D=4), RAID0 is overstated. Untested — needs real fio.
