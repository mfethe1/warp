# exp6 — Protected admission × EV-gated prefetch (FACTORIAL): FALSIFIED

**Source SHA:** `cb05b14` · **Evidence class:** PROXY replay + RECOMPUTATION · **Lane:** offline

## Preregistered gates (verbatim from claim id=6, idea=10)

- **ACCEPT:** A+B reduces verifier bytes >=2.13% vs baseline AND beats both A and B alone
- **REJECT:** A+B fails to beat lookahead-off, or one parent alone matches A+B (no added value)
- **STOP:** Offline replay only. Abort if segmented policy cannot reproduce the baseline miss count as a validity check.

## Arms

| Arm | Cache | Prefetch |
|---|---|---|
| baseline | LRU | off |
| A | SLRU (protected/probationary) | off |
| B | LRU | EV-gated |
| A+B | SLRU | EV-gated into probationary |

SLRU: demand miss → probationary; demand hit on probationary → promote to protected
(protected LRU line demoted to probationary MRU); eviction always from probationary
LRU end; prefetches enter probationary only. `prot_frac=0.0` degenerates to plain LRU.

## Validity check (stop rule) — PASS

SLRU(prot_frac=0.0) = **27,979** reads == LRU baseline **27,979** reads at cap 709. Exact.

## Result at the K3-EQUIVALENT operating point (cap=709, 3.41× working set)

| quantity | value |
|---|---|
| baseline reads | 27,979 |
| A saving | **+1.719%** |
| B saving | **+0.000%** |
| A+B saving | **+1.719%** |
| interaction | **0 bytes** |
| A+B beats A | **False** |
| A+B ≥ 2.13% | **False** |
| physical prefetches issued by B | **0** |

**REJECT gate fires:** A alone exactly matches A+B — no added value — and A+B is below the
2.13% speculative break-even.

## Why the headline factorial looked like a pass (selection bias)

The naive sweep reports `confirmed` because each arm's best cell is drawn from a
different-sized grid (A: 5 cells, B: 9 cells, A+B: 45 cells). A best-of-45 arm beats a
best-of-5 arm on a finite trace even when the policies are equal in expectation.
Matched-pair analysis (same `prot_frac`, so the prefetcher is the only difference)
collapses the effect:

- cells where B helps given A: **12/25**
- marginal effect of B: mean **+0.173%**, max **+1.094%**, stdev **0.320%**
- total physical prefetches issued across all 25 cells: **0**

## The decisive diagnostic: arm B never fetches anything

In every cell `prefetch_fetch == 0`. The EV candidate set — the previous token's experts
at the next layer — is *already resident*, so `prefetch(k)` degenerates to a bare
`move_to_end()`. Arm B has **no byte-moving mechanism on this trace**; it is a pure LRU
recency perturbation, and every A+B vs A delta is cache-order noise, not prefetching.

### Sham control (N=20 seeds/cell)

Replacing EV candidates with random *resident* keys, matched touch-for-touch:

| cap | pf | A_rd | EV_rd | EV fetches | EV Δ | sham Δ mean | sham SD | z |
|---|---|---|---|---|---|---|---|---|
| 709 | 0.5 | 27,847 | 27,541 | 0 | +306 | −391.4 | 46.9 | +14.89 |
| 762 | 0.5 | 26,776 | 26,585 | 0 | +191 | −559.2 | 53.4 | +14.06 |
| 1270 | 0.8 | 21,039 | 20,839 | 0 | +200 | −391.2 | 53.9 | +10.97 |
| 3049 | 0.4 | 8,992 | 8,984 | 0 | +8 | −235.4 | 46.1 | +5.28 |

Random touches *hurt* (negative deltas); EV touches help slightly. So the EV signal is
real as a **recency-ordering hint**, but it is categorically not the preregistered
mechanism (prefetch admission), and it is far too small to matter — see below.

## Magnitude check against the actual goal

Best A+B anywhere in the sweep is +5.721% (cap 1270, not a K3-reachable configuration),
which scales to **7.2774 GiB/token** against the **0.3946 GiB/token** needed for 15 tok/s.
Off by **18.4×**. Consistent with the established finding that cache policy is dead for
this target: Belady itself is 16.84pp short.

## Objective check

Metric: `B_acc = (m_demand + f_prefetch) * RECORD_B / a`, RECORD_B = 12,406,784 B.

Arm A moves only `m_demand` (which lines survive eviction). Arm B adds `f_prefetch`,
which is strictly additive, and can reduce `m_demand` by at most the number of prefetches
later demanded: `dB_acc/d(prefetch) = (1 - P(useful)) * RECORD_B / a >= 0`. Acceptance
rate `a` is untouched by both arms — neither changes routing nor the verifier — so this is
a pure numerator experiment, algebraically identical to bytes per accepted token.

Empirically `f_prefetch = 0`, so B's term vanishes identically and
`gain(A+B) ≡ gain(A)`, forcing `interaction ≡ 0`. This reproduces the exp10 structural
result by a different route: **prefetch changes when a page is read, never whether.**

## Artifacts

- `tools/crossval/exp6_chaperone_ev_factorial.py` — factorial + SLRU + validity check
- `tools/crossval/exp6_debias.py` — matched-pair de-biasing, K3-equivalent gate
- `tools/crossval/exp6_sham_control.py` — random-touch null distribution
- `evidence/exp6/exp6_result.json`, `exp6_debias.json`, `exp6_sham_control.json`

Trace: `tests/trace_kimi_300.jsonl` (300 tok × 26 layers × top-8, 62,400 accesses,
5,083 distinct) — **PROXY, Kimi-Linear-shaped, NOT K3 (92L × 896E × top-16)**.

## Recommendation for the queue

Any future prefetch idea must first pass a **fetch-count precondition**: if the candidate
set is already cache-resident, the arm cannot move bytes and the experiment is void
before it starts. Two mechanisms (exp10 certified-skip, exp6 chaperone) have now died on
the same structural fact. Prefetch variants should be retired as a family on the
bytes/accepted-token objective; only ideas that change *whether* a page is read
(skip, compress, restructure the record) can reach 0.3946 GiB/token.

Secondary observation, offered as raw material only: EV-ordered recency touches beat
random touches at z = +5 to +15, so next-layer route prediction carries a usable
reuse signal. It is worth ~0.2% and cannot approach the target alone.
