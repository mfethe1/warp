# exp12 — activation-whitened bound geometry for the resident row-norm certifier

**Verdict: `inconclusive` — NOT DECIDABLE, per the preregistered `stop_rule`'s own escape clause.**

Source SHA `cb05b14`. Working clone `/tmp/spark/warp`. Offline-only tick
(Winnie CPU **88.8%**, python active → no compute contention permitted;
`E:\Projects\warp` untouched, no model executed).

All numbers below are **[RECOMPUTATION] over a [REAL-K3] artifact**
(`docs/gn100/sprint11-route-margin-summary.json`: 92 layers, 6348 rows,
0 exact boundary ties, 0 non-finite scores). N=1, deterministic algebra, variance n/a.
**Nothing here is a K3 throughput or byte measurement.**

## What stage 1 established

Under idea16's certification rule an access is certified (pread skipped) iff
`bound <= gap/2`, so

    s_cert(bound) = P(margin >= 2*bound)

which is *exactly* the published `score_error_risk` table:

| bound | required_margin | s_cert |
|---|---|---|
| 1e-6 | 2e-6 | 0.99779458 |
| 1e-5 | 2e-5 | 0.98015123 |
| 1e-4 | 2e-4 | 0.82325142 |
| 1e-3 | 2e-3 | 0.24196597 |
| 1e-2 | 2e-2 | 0.00488343 |

Inverting the **preregistered** gates into required bound magnitudes
(log-linear interpolation between published points):

| gate | s_eff | required bound |
|---|---|---|
| accept (1) — arm A must FAIL its own DEAD line | < 0.10 | isotropic bound **> 3.97012e-3** |
| accept (2) — arm A+B must certify | >= 0.40 | whitened bound **<= 5.34724e-4** |
| reject (1) — A+B dies | < 0.25 | 9.68677e-4 |

### Necessary condition (new, gate-independent)

    REQUIRED TIGHTENING = 3.97012e-3 / 5.34724e-4 = 7.4246x

Activation whitening must shrink the Cauchy–Schwarz residual bound by
**≥7.4246x in score units** for the ENABLING signature to exist at all.
This is derived from real-K3 margins and holds independently of any replay.

## Why it is NOT DECIDABLE

Computing the **achieved** bound under either metric requires
(a) one real K3 expert's row norms (`max_row ||W_row||_2`) and
(b) one batch of real hidden states (`||x||_2`, `Sigma_x`).

Exhaustive search found **neither**:

- repo contains zero `.npz` / `.npy` / `.pt` / `.safetensors`
- Winnie `E:\` and `C:\` scans for `*.safetensors`, `*.gguf`, and any file >100 MB returned **empty**
- `E:\KimiK3` holds only `.claude_context_tree` (0 MB)

The `stop_rule` explicitly forbids substituting synthetic or iid-imputed
activations, and requires naming the missing artifact instead — this is the
exact tautology that rendered exp11 inconclusive.

**Second, independent blocker.** sprint11 margins are *unconditional* over all
6348 rows, while every gate is written on the miss-conditioned
`s_eff = P(certified AND miss)/P(miss)`. exp11 already established that
sprint11 carries **no margin↔expert-identity coupling**, so miss-conditioning
cannot be recovered from this artifact. The unconditional `s_cert` recomputed
here is therefore an **upper bound** on `s_eff` — exp10 showed skips land
preferentially on hits — and may not be read as a byte saving.

Stage 2 (four-arm replay at fixed RAM budget) was correctly **not run**: the
`stop_rule` gates it behind stage 1 clearing. Gates were frozen and not moved.

## Objective check

    B_acc = M * R / a

`M` = physical expert-record transfers per attempted token; `R` = 12,406,784 B
= 3029 pages (exp5-verified: one pread, no independently addressable stage);
`a` = accepted tokens per attempted token.

idea16 acts **only** on `M`, multiplying the physical-miss term by `(1 - s_eff)`
at zero added read bytes and no change to `R` or `a`. Whitening (idea2 as a
*resident sidecar*, not a basis re-encoding — which structurally removes the
+5.018% byte regression exp1/exp2 found) does not itself remove bytes; it sets
how far below 1 that multiplier can be driven, reaching the objective strictly
through `s_eff`. So `dB_acc/ds_eff = -M_miss * R / a < 0` — a real algebraic
connection.

**Scope, stated plainly:** even a full pass lands near 5.403 GiB/token against
the 0.3946 GiB/token needed for 15 tok/s — still ~13.7x short. Necessary,
not sufficient.
