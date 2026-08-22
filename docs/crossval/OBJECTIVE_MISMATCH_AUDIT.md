# Objective-Mismatch Audit — exp2 (WARP research queue)

**Evidence class: RECOMPUTATION.** No K3 execution, no machine contention
(Winnie was at `CPU_LOAD_PCT=100`; this tick was offline-only on the Mac).

Repo SHA `ba3f394` (branch `collab/belady-oracle`); spec source SHA `cb05b14`.

## The model every gate is checked against

Physical expert bytes per **accepted** output token:

    B_acc = (M * RECORD_BYTES) / a

  * `M` — expert-record **misses** per proposed token (set by cache policy)
  * `a` — accepted output tokens per proposed token (set by speculation)
  * `RECORD_BYTES` — 12,406,784 B, fixed, exactly 3029 pages, one pread per expert

A lever that moves none of `M`, `a`, `RECORD_BYTES` has coupling `dB_acc/dx = 0`
and is **not connected** to the objective. That is the whole test.

Invariants recomputed from pinned constants (92 layers x top-16 = 1472
activations/token): logical 17.0090 GiB/token, measured physical 7.719,
budget at 15 tok/s = 5.9194836464/15 = 0.39463 GiB/token, required speedup
19.56x vs measured physical, required hit on logical demand 97.68%,
current hit on logical demand 54.62%.

## Result: 3 new mismatches in 5 active gates

### 1. exp3 `metabolic-channeling-route-graph` — coupling is *exactly zero*

Gate: *"ACCEPT: modularity >0.15 AND entropy materially below uniform ->
placement work justified"*.

Placement is a permutation `pi` of record offsets. `M` is fixed by the demand
sequence and cache policy; `RECORD_BYTES` is fixed by FORMAT.md; `a` is
untouched. So `dB_acc/dpi = 0` **identically, for all pi, at every modularity
value**. The gate can PASS at modularity 1.0 with physical bytes bit-for-bit
unchanged.

The idea's own `conserved` clause — *"Bytes are conserved; only PLACEMENT
changes"* — is itself the proof that its accept gate measures a quantity the
objective is invariant to.

The only channel to bytes would be readahead merging two co-demanded records
into one transfer: a 128 KiB window covers 1.06% of one 11.83 MiB record, and
under O_DIRECT readahead is bypassed entirely — coverage 0.

**Corrected gate:** placement can only pay in *latency*, never bytes, so the
decisive gate is wall-clock GiB/s at fixed byte count, not a byte gate. The
engine is already 100% I/O-bound at 5.919 GiB/s and sequential-vs-random is
within noise for 11.83 MiB transfers. **Recommend DEAD before implementation,
on the algebra — the graph analysis need not be run.**

### 2. exp1 `activation-weighted-shared-basis` — gate accepts a byte *regression*

Gate: *"ACCEPT: >1.5pp error improvement at <=0.15 bits/weight"*.

The 0.15 bits/weight is **spent**. On a 3.00 bits/weight baseline that is a
+5.00% enlargement of `RECORD_BYTES`:

| quantity | before | after |
|---|---|---|
| physical GiB/token | 7.719 | 8.105 |
| tok/s at 5.9195 GiB/s | 0.7669 | 0.7304 |

A 4.76% throughput loss. Error is a distortion in logit space; it reaches
`B_acc` **only** through the acceptance rate `a`, and the gate supplies no
error->acceptance conversion — so the *sign* of `dB_acc` is undetermined by the
gate as written. This is the Frobenius mismatch in new clothing: the **metric**
was corrected from Frobenius to activation-weighted, but the **gate** was never
re-derived against bytes per accepted token.

**Corrected gate:** fit at matched *error* and gate on *bits saved*, not at
matched bits gating on error. ACCEPT iff the whitened basis reaches VQ3R's
activation-weighted error at <= 2.85 bits/weight (>=5% byte reduction, ~223 ms
of arithmetic budget at the established 44.7 ms-per-1% conversion). If the fit
only exists at +0.15 bits/weight, ACCEPT requires a *measured* relative
acceptance gain >= 5.00%; otherwise it is a byte regression and must be rejected.

### 3. idea 1 `kinetic-proofreading-certified-skip` — gate is 2.79pp too harsh

Its stated prediction is a de-facto preregistered gate: *"bytes/token =
17.009*(1-s); 15 tok/s needs s >= 97.7%"*.

A certified skip avoids a read **only when that read would have been a physical
miss**. 54.62% of logical demands are already cache hits costing zero bytes, so
the saving is `s * PHYSICAL`, not `s * LOGICAL`:

    against logical  17.009:  s >= 97.680%   (as written)
    against physical  7.719:  s >= 94.887%   (correct)

The preregistered bar is **2.79pp too harsh** — a false-negative risk on the
project's highest-expected-gain idea (0.95).

**Corrected gate:** preregister `s >= 94.89%` against physical misses, and state
explicitly whether the resident coarse basis `B_e` is counted inside or outside
the 7.719 GiB/token figure, since it changes the denominator.

### Connected (no change)

* **exp4 `option-value-prefetch`** — stated metric *is* the objective;
  `dB_acc/dM = RECORD_BYTES/a > 0`, correct sign. One note: the premium term
  must count speculatively-read bytes in the numerator, not only demand reads.
* **exp2** — meta-gate, exempt by construction.

## Reproduce

    python3 tools/crossval/objective_audit.py out.json

N = 5 gates audited. Deterministic recomputation from pinned constants;
variance not applicable.
