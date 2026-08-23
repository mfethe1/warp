# exp48 — falsified-corpus reindex under exp45 kernel lane

Date: 2026-08-23
Evidence class: RECOMPUTATION (database audit + algebra only; no K3 measurement)
Source anchors: exp33 result (kern_A 5.065 GiB/s/core, B*(4)=4.9691 GiB/token); exp45 result-41 / experiment 45 (kern_D 22.705 GiB/s/core; nominal 4.9x lane, exact pinned-rate ratio 4.4827x); research.db snapshot queried 2026-08-23.

## Frozen gate

> ACCEPT if classification is complete (17/17 assigned, none “other” without justification) AND arithmetic shown for every category-(i) item. The audit's value is the classification itself.

Stop rule: one database pass; no falsified experiment rerun.

## Method

The database has 17 ideas with `ideas.status='falsified'` and 20 experiment-result rows with `results.verdict='falsified'`. The primary corpus is the 17 falsified ideas. Duplicate/supplemental falsified result rows are audited separately so no row is silently discarded.

Categories:
1. kernel/unpack/dequant cost was the binding kill;
2. quality/entropy floor;
3. zero byte derivative or objective mismatch;
4. other/voided, with explicit reason.

## Primary corpus: all 17 falsified ideas

| idea | representative result | class | binding reject mechanism | exp45 repricing |
|---|---:|:---:|---|---|
| kinetic-proofreading-certified-skip | exp27 | ii | Quality contract: 0.03% expert reduction at KL 0.0232 versus >=15% gate. | No effect. |
| metabolic-channeling-route-graph | exp3/exp25 | iii | Placement does not change O_DIRECT bytes; even perfect co-paging can address only seek time (3.94% of read time). exp25 was additionally voided. | No effect on byte derivative. |
| option-value-prefetch | exp4 | iii | At the frozen operating point best policy prefetches nothing and changes physical reads by exactly 0; maximum off-design gain 0.606% is below 2.13% break-even. | No effect: no kernel term was binding. |
| chaperone-plus-ev-prefetch | exp6 | iii | EV arm adds exactly zero bytes saved at the operating point; combined 1.719% stays below 2.13%. | No category-(i) kill to reprice. |
| route-graph-plus-fragment-placement | exp7 | iv | Auto-falsified dependency: route-graph parent died and combination did not remove that falsifier. | Parent mechanism unchanged. |
| coarse-resident-plus-certified-skip | exp8 | iv | Auto-falsified dependency on dead certified-skip parent. | Parent quality gate unchanged. |
| certified-skip-whitened-basis | exp9 | iv | Auto-falsified dependency on dead certified-skip parent. | Parent quality gate unchanged. |
| certified-skip-option-prefetch | exp10 | iii | Factorial interaction is exactly zero across the whole score-error curve; prefetch cannot reduce certified-skip bytes. | No kernel-cost kill. |
| asymmetric-replica-dispatch-gate | exp19 | iv | Indivisible 3029-page records + per-layer barrier; even clairvoyant split reaches only 1.0224x versus 1.10x gate. | Dispatch law/hardware asymmetry unchanged. |
| certified-skip-conditioned-makespan-coloring | exp21 | iv | Certification thins misses color-neutrally; interaction is negative at all five points. | Independence/negative interaction unchanged. |
| latency-bound-layer-barrier-raid0 | exp29 | iv | Preregistered crossover law was wrong because `ceil(k/D)` creates a divisibility artifact; gate 3 failed. | Queueing-law falsification unchanged. |
| certifier-bypass-starvation-chaperone-hedge | exp32 | iv | Mechanisms compete for the same one-shot bytes; interaction -0.020 pp and parent dominance fired. | Mechanism overlap unchanged. |
| vq4p-isobyte-kernel-substitution | exp34 | iv | REAL-K3/in-engine scheduling transfer failed: 4.48x single-core microkernel became 1.07x threaded/in-engine and 1.086x end-to-end; VQ4P also had an undefined distortion sub-gate. This is a fork-join/E-core transfer failure, not a raw kernel-cost kill. | exp45 validates the raw kernel lane but does not erase exp34's measured engine transfer failure; no flip. |
| certified-suppression-under-vq4p-gather | exp36 | iv | Combination voided by exp34 premise; recomputed ceiling only 4.880 tok/s at evidence-backed suppression. | Parent transfer failure remains; no rerun authorized. |
| vq4p-collapses-flowshop-serialization-penalty | exp37 | iv | The alleged flow-shop penalty did not exist at target E[k], and VQ4P widened rather than collapsed spread. | Wrong interaction sign remains. |
| qd-saturation-transfer-target-ssd | exp42 | iv | Mac SSD QD8/QD1=1.001; hardware transfer null, rig-NVMe remains open. | Kernel lane cannot manufacture storage QD scaling. |
| grouped-vs-interleaved-measurement-validity | exp44 | iv | Measurement hazard did not transfer to deterministic replay; grouped/interleaved deltas differed by only 0.083 ms. | Methodology result unchanged. |

Primary counts: **i=0, ii=1, iii=4, iv=12; total=17/17**. Every class-(iv) assignment has a stated mechanism.

## Supplemental falsified experiment rows

The 20-row result query exceeds the 17-idea corpus because some ideas have duplicate or diagnostic experiments:

- exp25 duplicates the route-graph idea and is class iii/iv (zero byte derivative; administratively voided).
- exp29 is the representative row already used for the latency-bound RAID idea.
- exp22 and exp28 belong to the objective-mismatch-audit idea, whose idea status is not falsified. exp22 is class ii: near-uniform VQ3R entropy limits theoretical savings to 4.906%, below the 5% gate.
- exp28 is the **only falsified result row** whose immediate rejection is category i: measured rANS NEON decode rate 0.399 GiB/s is slower than the 5.919 GiB/s read path. It is not one of the 17 falsified ideas because the parent audit idea successfully established non-transferability.

## Required category-(i) arithmetic: exp28 diagnostic row

Original [RECOMPUTATION from measured rates]:

- expert read time = 1.9521 ms at 5.919 GiB/s;
- mode-0 decode time = 28.9592 ms at 0.399 GiB/s;
- even ratio→0 saves at most 1.9521 ms, so decode/max-save = 14.835x; verdict falsified/non-transferable.

Counterfactual nominal exp45 4.9x repricing [RECOMPUTATION]:

- decode rate = 0.399 × 4.9 = **1.9551 GiB/s**;
- decode time = 28.9592 / 4.9 = **5.9100 ms**;
- decode/max-save = 5.9100 / 1.9521 = **3.0275x**;
- still below required 5.919 GiB/s by **3.0275x**; verdict does **not** flip.

This is generous: exp45 measures a VQ gather-kernel lane, not an rANS decoder acceleration. Therefore even granting the whole 4.9x counterfactually cannot revive exp28.

## Q3G cross-check (established negative, absent from the 17-idea DB corpus)

Pinned peer report `spark-docs/e77536fd_LEARNED.md` records Q3G trunk at 0.16 tok/s versus Q4G 0.23 tok/s, with kda bucket 3.70→10.39 s over five steps. But the binding final kill is category ii: logits land 36% off Q4G and generation collapses because the non-expert trunk lacks 3-bit QAT tolerance. Thus vectorizing unpack cannot flip the verdict; the quality wall sits before the speed wall.

## Break-even repricing for the corpus

Using `B*=B_log*BW/(rate*C)`, `B_log=17.0085 GiB/token`, `BW=5.919 GiB/s`:

| cores C | B* at kern_A=5.065 | B* at kern_D=22.705 |
|---:|---:|---:|
| 1 | 19.8763 | 4.4340 |
| 4 | 4.9691 | 1.1085 |
| 10 | 1.9876 | 0.4434 |
| 16 | 1.2423 | 0.2771 |

All values are RECOMPUTATION. Exact pinned-rate improvement is 22.705/5.065 = 4.4827x (the experiment's “4.9x” is the broader measured range/nominal lane). This substantially reopens future byte-saving work, but none of the 17 falsified ideas was killed solely by the old `B*`; therefore **zero verdicts flip**.

## Verdict and objective check

**CONFIRMED negative audit:** the falsified-idea corpus is exp45-robust. No primary-corpus idea is category i, and no verdict flips. The one category-i diagnostic result (exp28) remains 3.03x too slow even under an intentionally generous 4.9x repricing.

Objective optimized: re-price whether past ideas can lower `max(B_phys/BW_eff, B_log/(rate*C))`. The audit is algebraically connected through the compute/I/O crossover `B*`; it does not itself reduce physical bytes or increase effective bandwidth. Its value is preventing stale kernel economics from hiding a revival candidate. Result: no revival candidate; future queue work should proceed rather than rerun the dead corpus.
