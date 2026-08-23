# exp42: QD-saturation transfer test — Mac internal SSD (protocol shakeout)

**Claimed:** 2026-08-23 12:45 EDT. Lane: offline. Priority 0.702. Source SHA d13493a7508144dc9723a2d62c50cbcf165179b9.

**Verdict: FALSIFIED (on Mac-class Apple AP0512Z SSD) — reject gate fired cleanly.**

## Preregistered gates (unmodified)
- accept: QD8/QD1 >= 1.30 on 12.2MB O_DIRECT blocks, non-overlapping spreads
- reject: QD8/QD1 <= 1.10 OR spread-within-setting > between-setting delta
- stop: any setting relsd > 15% (never fired — max relsd 0.7%)

## Result [HARDWARE MEASUREMENT on Mac internal SSD — NOT a K3 measurement, NOT rig NVMe]
fio 3.42 (homebrew), ioengine=posixaio, --direct=1 (F_NOCACHE). Note: fio-3.42 on macOS/APFS has
no io_uring; QD>1 requires an async engine and posixaio is the only one available — recorded as a
protocol deviation (spec said "fio or minimal io_uring harness"; fio+posixaio is the macOS-valid form).
16 independent lane files, each 40 x 12,406,784B (= 3029 x 4KiB) blocks; sequential-within-lane;
interleaved design (rep-major, QD arms alternated within rep); N=3 reps x 5 QD arms = 15 runs.

| QD | mean GiB/s | sd | relsd | per-rep |
|----|-----------|-----|------|---------|
| 1  | 3.167 | 0.009 | 0.3% | 3.163 / 3.159 / 3.177 |
| 2  | 3.178 | 0.002 | 0.1% | 3.180 / 3.179 / 3.176 |
| 4  | 3.178 | 0.006 | 0.2% | 3.184 / 3.177 / 3.172 |
| 8  | 3.171 | 0.023 | 0.7% | 3.145 / 3.179 / 3.188 |
| 16 | 3.179 | 0.005 | 0.2% | 3.183 / 3.173 / 3.181 |

**QD8/QD1 = 1.001** (QD2 1.004, QD4 1.004, QD16 1.004). Between-setting delta (QD8−QD1 = 0.004 GiB/s)
is below the within-setting noise (spreads 0.004–0.043 GiB/s) — exactly upstream's own failure
signature (their S29 null), reproduced deliberately.

## Confounders ruled out (single-stream discriminator runs)
- single-stream: QD1 = 2.931, QD4 = 3.134, QD16 = 3.113 GiB/s → one stream alone delivers ~93%
  of the 16-stream aggregate; per-stream QD scaling exists but is tiny (~1.07x).
- 4-stream QD1 = 3.173 GiB/s ≈ full aggregate.
- ⇒ Mac internal SSD saturates from ~4 parallel 12.2MB streams regardless of per-stream QD.
  Parallel-stream COUNT, not queue depth, is the binding constraint on Mac-class hardware.

## Interpretation for the rig decision
On Mac-class SSDs, QD>2 is a hardware-conditional null — consistent with upstream's S22/S29 nulls
on their Mac. This does NOT transfer-test the actual $250-class rig NVMe (990PRO/SN850X); the
prediction for rig NVMe remains OPEN per the spec ("candidate rig NVMe ... BEFORE building the
rig"). Protocol, scripts, and parse tooling are now validated end-to-end and portable to the rig
drive (Linux io_uring form ready in sweep.zsh).

## Objective check
Optimizes: aggregate effective read bandwidth (GiB/s) vs queue depth on 3029-page O_DIRECT blocks —
the "aggregate effective bandwidth" term of tok/s ≈ aggregate BW / physical bytes per accepted
token. Directly algebraically connected; no K3 inference was run, no bytes/accepted-token number
claimed or implied.

## Artifacts
- arm_r{1,2,3}_qd{1,2,4,8,16}.csv — raw fio terse v3 (15 runs), SHA256SUMS.txt alongside
- sweep.zsh / prep.zsh — exact protocol, reproducible
- Single-stream/4-stream discriminator outputs quoted inline above (raw in shell history of run)
