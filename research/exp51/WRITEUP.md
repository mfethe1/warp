# exp51: miss-support-capped-io-depth-knee

**Claimed:** 2026-08-24 00:45 EDT (job 8998beee8f3a). Lane: offline. Priority 0.613. Source SHA 619b666a1c15404a947f92cf0f684d7c2f4c3dcd (upstream main HEAD; exp49 audit pin).

**Verdict: CONFIRMED — the preregistered QD4 knee prediction holds exactly; QD8 promotion is objective-mismatched.**

## Preregistered gates (unmodified)

- accept: "q=4 captures >=90% of useful requests AND q4->q8 optimistic wave reduction <=15% at cap=1490 with same sign at >=2/3 caps; preserve q2->q4 hardware validation if its wave reduction >=25%."
- reject: "q4 captures <90% OR q4->q8 wave reduction >15%."

## Method

Deterministic offline replay of the frozen in-repo PROXY trace `tests/trace_kimi_300.jsonl`
(sha256 06ad026c928d1c05eb59f0b1db55e1317c1899b1d3a687741ab5c49fdc014965;
300 tokens x 26 layers x top-8 = 7,800 token-layers, 5,083 distinct (layer,expert) keys)
under exact LRU, key=(layer,expert), insertion order = trace order within each layer's list.
K_miss logged per token-layer at cap=1490 plus cap sweep {709, 2980}.
No kernels, no hardware, no code changes. Fully deterministic (single pass, no RNG).

## Result [PROXY — Kimi-Linear-shaped trace, NOT K3 92L x 896E x top-16]

cap=1490 (N=7800 token-layers; E[K]=2.4085; K-dist 0:713 1:1638 2:2035 3:1676 4:981 5:514 6:172 7:44 8:27):

| q | capture E[min(K,q)]/E[K] | E[ceil(K/q)] | P(K>=q) |
|---|---------------------------|--------------|---------|
| 1 | 0.3772 | 2.4085 | 0.9086 |
| 2 | 0.6673 | 1.4524 | 0.6986 |
| 4 | **0.9416** | 1.0056 | 0.2228 |
| 8 | 1.0000 | 0.9086 | 0.0035 |

- Optimistic wave reduction q2->q4 = **30.76%**  (>=25% gate: MET → q2->q4 hardware validation PRESERVED)
- Optimistic wave reduction q4->q8 = **9.65%**  (<=15% gate: MET)

Cap sensitivity (same-sign check):

| cap | E[K] | q4 capture | wave q2->q4 | wave q4->q8 |
|-----|------|-----------|-------------|-------------|
| 709  | 3.5871 | 0.8572 | 37.81% | 23.46% |
| 1490 | 2.4085 | 0.9416 | 30.76% | 9.65% |
| 2980 | 1.2146 | 0.9683 | 17.98% | 3.31% |

Sign stability: q2->q4 reduction positive at 3/3 caps. q4->q8 reduction <=15% at 2/3 caps
(1490: 9.65%, 2980: 3.31%; 709: 23.46% exceeds). The preregistered knee needs "<=15% at
cap=1490 with same sign at >=2/3 caps" — sign is positive (reduction exists) everywhere and
the <=15% magnitude holds at 2/3 caps → gate satisfied as written. Note honestly: at the
undersized cap=709 (LRU starved, E[K]=3.59) QD8 does retain >15% wave value; the knee is
workload-conditioned, as the title predicted ("miss-support-capped").

## Gate evaluation

- ACCEPT gate: q4 captures 94.16% >= 90% ✓ AND q4->q8 wave reduction 9.65% <= 15% ✓ at cap=1490,
  magnitude condition holds at 2/3 caps ✓ → **ACCEPT the knee**.
- REJECT gate: not fired (94.16% > 90%, 9.65% <= 15%).
- Prediction vs outcome: predicted q4 capture >=94% → measured 94.16%; predicted q4->q8 <=10% →
  measured 9.65%; predicted q2->q4 >=25% → measured 30.76%. All three landed inside the
  preregistered ranges.

## Stage-2 ceiling recompute [RECOMPUTATION from PROXY capture x measured device curve]

Per the spec, only the workload-supported fraction may be multiplied by the measured
target-device large-block QD curve — raw fio QD8 gain must NOT be credited wholesale.

- QD4->QD8 workload-supported capture gain: 5.84pp (1.0000-0.9416).
- Only measured target-device curve = exp42 Mac internal SSD (12.2MB O_DIRECT, fio posixaio,
  N=3 interleaved): QD4 3.178 -> QD8 3.171 GiB/s = **-0.22%**. Ceiling = 0.0584 x -0.0022
  ≈ **-0.01%** (a hardware-conditional null).
- Rig-NVMe curve remains OPEN (no rig measurement yet). Even under the most generous imported
  curve (colibri-hypothetical 4M-QD4 2,619 -> 1M-QD8 3,232 MB/s = +23.4%): ceiling =
  0.0584 x 0.234 ≈ **+1.37% aggregate read bandwidth** — below the noise floor of any honest
  measurement and ~1/14th of the 19.6x system need. Cross-project caveat: colibri's curve is
  MXFP4-native 1.6TB media, not WARP's VQ3R layout; treated strictly as an upper-bound import.
- QD2->QD4: capture gain 27.4pp; wave reduction 30.8% (up to 37.8% at cap 709) — this is the
  one arm with a live objective-connected path, worth at most ~2.7% bandwidth per 10pp of rig
  device gain, and only if the rig device actually scales QD2->QD4 (Mac: 0.0%).

Configured vs achieved QD: with the ecache sliding window, achieved_QD = min(configured,
outstanding misses). At cap=1490, only 22.28% of token-layers can even present 4 outstanding
misses (P(K>=4)) and 0.35% can present 8 — configured QD8 would be achieved in 1 layer per
~286 token-layers even if issued perfectly. Separation is now measured, not assumed.

## Objective check

Optimized: useful-concurrency capture of decode expert misses as a function of configured I/O
queue depth. Connection: tok/s ~= B_eff / bytes-per-accepted-token; QD scales B_eff only on
workload-supported requests, so the legitimate ceiling is capture(q) x device_curve(q). This
experiment measured capture(q) exactly and bounded the QD8 product at ~0% (Mac measured) to
+1.37% (rig-hypothetical), retargeting Stage 2 from QD8 to a QD2->QD4 env-knob sweep
(WASTE_IO_THREADS/WASTE_IO_DEPTH=4) on the rig NVMe only, with QD8 dropped unless the rig
curve shows steep QD4->QD8 scaling under real trace-shaped issue patterns.

## Prediction for the requeued Stage 2 (falsifiable)

Env-knob QD2->QD4 on rig NVMe: wave reduction >=25% (PROXY), so decode layer-service time
falls materially IF the rig device scales QD2->QD4 on 12.4MB O_DIRECT reads; expected system
effect <= ~3% aggregate bandwidth (bounded by device gain), NOT a path to 19.6x. QD8 arm
expected null-or-noise; predicted capture-bounded ceiling +1.4% even on colibri's curve.

## Artifacts

- exp51_replay.py — deterministic replay (this dir)
- exp51_output.txt — full raw output, all caps
- exp51_results.json — machine-readable results
- SHA256SUMS.txt — integrity record
- Branch: research/exp51 on mfethe1/warp

## Reproduction

```sh
python3 exp51_replay.py   # deterministic; ~2s; prints all three caps
```
