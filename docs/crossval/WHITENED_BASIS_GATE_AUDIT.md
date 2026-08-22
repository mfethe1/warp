# exp1 — activation-weighted-shared-basis (whitened shared basis, preregistered revival)

**Verdict: `inconclusive` — the preregistration is internally contradictory and neither
reading is algebraically connected to the objective.**

Source SHA `cb05b14`. Working clone `/tmp/spark/warp`. Offline-only tick (Winnie CPU 100%,
aria2c + heavy python active; `E:\Projects\warp` untouched). No model was executed.
**Every number below is [RECOMPUTATION] from pinned published constants. Nothing here is a
K3 measurement.** N=1, deterministic algebra, variance n/a.

## Objective

    B_acc = M * R / a

M = physical expert-record transfers per attempted token; R = physical bytes per
transferred record; a = accepted output tokens per attempted token.

## The contradiction

The claim's own fields disagree about the bit budget:

| field | text | implication for R |
|---|---|---|
| `spec` | "compare error vs VQ3R at **MATCHED** bits/weight" | R invariant |
| `accept_gate` | ">1.5pp error improvement at **<=0.15 bits/weight**" | R additive |

FORMAT.md:259 settles which is physical: *"at rank N/128 the shared basis **costs** 0.12
bits/weight"*. The basis is an additive cost, so the gate's 0.15 b/w is **spent**, not matched.
Both readings were evaluated because the processor may not move a preregistered gate.

## Reading B — accept_gate literal (0.15 additional bits/weight)

3.00 -> 3.15 b/w scales the expert record 12,406,784 B -> 13,027,123.2 B raw. Page
quantisation is load-bearing (records are 4 KiB-aligned, baseline = exactly 3029 pages), so
the physical record is **3181 pages = 13,029,376 B**, i.e. **R +5.0182%**.

- physical demand 7.719 -> **8.1064 GiB/token**
- throughput at 5.9194836464 GiB/s: 0.76687 -> **0.73023 tok/s**, **-4.778%**
- break-even requires `a` to rise **+5.0182%**
- the **entire** measured speculative acceptance headroom is **3.69%** — it does not cover the cost

So the gate can PASS (error improves >1.5pp) while B_acc **regresses**. The gate is
sign-inverted with respect to the objective.

## Reading A — spec literal (matched bits/weight)

R and M are both unchanged by construction, so `dB_acc/d(error) = 0` **unless** error maps to
acceptance rate `a`. I searched every published artifact in `docs/gn100/` for a calibrated
error->acceptance mapping: the only `accept*` keys are scope counters
(`accepted_scope`, `accepted_cuda_vq`, `accepted_vq_group`). **No such mapping exists.**
Under this reading the gate measures a quantity with an identically-zero derivative on the
objective. Additionally, at matched budget the published deficit is
28.87% (kbvq2) vs 15.20% (INT4) = **13.67pp against** the shared basis, so passing would
require a **15.17pp** swing from whitening alone.

## The preregistered stop rule is already tripped by the prior

`stop_rule: "Stop after one layer if effect size is <0.5pp"`. Published unweighted effect is
0.3pp at 0.12 b/w; linear extrapolation to 0.15 b/w gives **0.375pp < 0.5pp**. The accept
gate needs **4.0x** the published effect. Caveat, stated plainly: the published figure is the
*unweighted* metric, and the whitened/activation-weighted number is genuinely unmeasured —
this is a prior, not a result, and it is why the verdict is `inconclusive` and not `falsified`.

## Ceiling argument

A shared basis captures 7.1% of energy vs 3.1% random and **20.0% for each expert's own**
subspace. Own-subspace capture is the unreachable ceiling for any shared basis (2.29x random).
Energy-pp does not convert to error-pp without a measurement, so this bounds plausibility only.

## What a corrected gate must say

Any revival must be stated in bytes and acceptance, not error:

    ACCEPT iff  (1 + dR_page_quantised) / (1 + da) < 1

with dR computed **after** 4 KiB page quantisation, and `da` from a *measured*
error->acceptance calibration. Absent that calibration the experiment is undecidable at any
error threshold. Recommend the research job requeue with (a) one consistent bit-budget
reading, (b) page-quantised byte accounting, (c) a measured error->acceptance mapping, or
else retire the section and the `lowrank_id` field on the existing published evidence.
