# exp40 — SPRT stages × row-norm certification: preregistration audit

**Verdict: INCONCLUSIVE (wrong/underdetermined spec; no factorial run).**

This is a successful methodology result, not a negative mechanism result. The
preregistered first-stage overlap gate cannot be evaluated from the frozen spec
or pinned sources. Running a synthetic factorial would require inventing the
joint correlation that the experiment is supposed to measure.

## Preregistered gates (quoted)

- **Stop:** “Stop at the overlap statistic if it is >=80% (falsified before the
  factorial runs). Otherwise run all 5 arms on the full 300-token trace…”
- **Accept:** combined gain must beat each solo arm; both conditional marginals
  must retain at least 0.25× solo gain; combined gain at least 0.386 GiB/token;
  KL at most 0.01 nats; zero SPRT argmax flips; compute inside budget.
- **Reject:** either conditional marginal below 0.10× solo gain, overlap at least
  80%, KL above 0.01, any SPRT flip, compute over budget, or any non-page read.

## Cheapest decisive audit

Ran `tools/crossval/exp40_prereg_audit.py` against source SHA
`cb05b1424eaefd5f777f62215c31d4af760e6e86`.

### Available evidence

- **PROXY, N=62,400 accesses:** the 300-token, 26-layer, top-8
  Kimi-Linear-shaped trace has 5,083 distinct `(layer, expert)` keys. At the
  established 3.41× working-set ratio, LRU capacity is 1,490 and produces
  18,786 misses (30.106%). This trace is **not K3** and contains routing IDs
  only—no margins, hidden states, row norms, VQ residuals, or stage decisions.
- **REAL-K3, N=6,348 aggregate rows / 69 positions / 92 layers:** the pinned
  sprint11 margin summary provides an aggregate certifier CDF at five error
  bounds. It does not provide per-access identities and cannot be joined to the
  PROXY trace.
- **RECOMPUTATION, deterministic N=1:** VQ3R is 12,406,784 B = exactly 3,029
  pages. Index payload is 12,386,304 B and header/corrections are 20,480 B.
  A hypothetical segregated stage plane is 4,128,768 B = 1,008 pages, so page
  boundaries 1,008 / 2,016 / 3,029 are feasible. However, WARP as shipped uses
  one whole-record pread and interleaves the three stage bytes per vector;
  `R(1)=R(2)=R(3)=12,406,784 B`, so shipped SPRT byte gain is exactly 0 B.

### Why the overlap is not identifiable

The stop gate needs the joint statistic
`q = P(certifier_suppressed AND SPRT_stage1)`. For marginal rates
`c=P(certifier_suppressed)` and `p=P(SPRT_stage1)`, aggregate sources constrain
only the Fréchet interval:

`max(0, c+p-1) <= q <= min(c,p)`.

The spec omits both the frozen certifier tolerance and the exact SPRT stopping
inequality; the pinned sources provide neither `p` nor aligned joint labels.
Even `c` is a five-point curve rather than one preregistered operating point.
Consequently, the overlap can legally range from disjoint to nested under the
same available marginals. Choosing a correlation in a simulator would directly
manufacture the verdict.

The KL and accepted-token gates are likewise not computable because no arm has
aligned logits or continuations.

## Objective check

The requested objective is physical bytes per accepted token:

`B_acc = Σ(page-rounded bytes of non-suppressed physical misses) / accepted_tokens`.

That is algebraically direct **only** if stages are physically separable and
certifier/SPRT decisions are observed jointly. In the shipped layout, SPRT only
changes post-fetch decode work and `dB_acc/d(stop_stage)=0`. Thus the current
spec cannot establish a byte-objective interaction.

## Corrected requeue requirements

A corrected experiment should freeze before execution:

1. one certifier tolerance/bound;
2. the exact SPRT stopping inequality;
3. an explicit stage-segregated, page-rounded record layout (or accept shipped
   layout and record zero SPRT byte gain);
4. aligned per-access certifier verdicts and SPRT stop stages from the same
   experts and hidden states;
5. exact-arm logits/continuations for KL and acceptance accounting.

Until those exist, no kernel or factorial should be written.
