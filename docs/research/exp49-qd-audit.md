# exp49 — Stage-1 achieved-QD audit of upstream warp decode expert I/O

**Experiment:** exp49 `sqe-batch-bulk-service-queue-depth` (Stage 1, offline, $0, no code changes)
**Audited source:** upstream sqliteai/warp @ `619b666a1c15` (HEAD of main, fetched 2026-08-23)
**Pinned SHA note:** preregistered SHA `33e67a9c004b` does NOT exist upstream (GitHub API 422;
not in any local branch either). Spec self-describes the pin as "current HEAD", so the audit
ran at actual HEAD. Pin drift recorded; verdict applies to `619b666a1c15` only.
**Evidence class:** RECOMPUTATION (static code trace; zero runtime measurements claimed)

## Question

Are per-layer expert preads issued serially (QD=1), via a small pool (QD~2), or fanned out by
the 64-thread compute pool (QD>=4)? Gates: ACCEPT Stage-2 if QD<=2 AND >=2 preads/layer possible;
REJECT (transfer dead) if QD>=4.

## Dispatch trace (decode, batch-1)

1. `waste_generate` (waste.c:1077) → per token `waste_model_step` (waste.c:1129).
2. Per MoE layer `moe_layer` (model.c ~2745): router picks top-K ids, then
   **`waste_ecache_hint(&m->cache, L, idx, K)` — model.c:2780 — before the first read of the
   layer.** The hint stages up to K ids (K = `num_experts_per_token`: 8 Kimi-Linear, 16 K3)
   and releases `depth` reads into flight immediately (`ec_issue_next` x depth, ecache.c:614).
3. Reader pool: **`start_readers` model.c:3058–3066: defaults `nio=2, depth=2`**
   (env `WASTE_IO_THREADS` / `WASTE_IO_DEPTH`; hard cap `EC_MAXIO = 8`, ecache.c:18;
   depth clamped to n_slots/4, ecache.c:283). NOT the 64-thread compute pool — that
   (`waste_pool_init`, vq.c:35; `waste_parallel_for`) is arithmetic-only; no pread site uses it.
4. Each reader thread runs `eio_worker` (ecache.c:242) → `bank_fetch` (model.c:1791) →
   **`waste_pread`** = true positional `pread(2)` on POSIX (platform.h:313) / overlapped
   SetFilePointer+ReadFile on Windows (platform.h:189). One pread = one whole expert record
   (12,406,784 B = 3029 pages, established).
5. Sliding window, no per-layer barrier: every `waste_ecache_get`/`hold` consumed by compute
   releases exactly ONE more read (`ec_issue_next` at ecache.c:672/705). So sustained in-flight
   ≈ min(depth, outstanding misses) = **2 by default**.
6. Synchronous fallback: an un-hinted miss is read inline on the compute thread
   (ecache.c:688–707), transiently QD=3 (2 readers + 1 inline).
7. Author's own comment (model.c:3049–3051): "internal SSD reaches 12.89 GB/s at queue depth 2
   against 10.73 at depth 1" — the QD-2 default is a deliberate, measured choice on their Mac
   SSD, not an oversight.

## Achieved QD estimate [RECOMPUTATION]

- **Default config: QD = 2** (nio=2, depth=2). Transient 3 on sync-fallback misses.
- Max without code change: **QD = 8** via `WASTE_IO_THREADS=8 WASTE_IO_DEPTH=8`.
- The "64-thread pool fans out layer experts concurrently" hypothesis (the reject-gate fear) is
  **FALSE**: I/O never touches the compute pool.

## Gate evaluation

- ACCEPT gate: "QD <= 2 AND >=2 preads per layer possible" → **MET** (default QD=2; K=8/16
  distinct expert preads per layer, each a separate 12.4 MB record).
- REJECT gate (QD>=4 via pool fan-out): not met.

**Verdict: CONFIRMED (audit) → Stage 2 promoted**, with one material design correction:

## Design correction for Stage 2 (important)

Stage 2 as written proposes SQE-batching via io_uring. But the audit reveals **the QD knob
already exists as an env var pair** (`WASTE_IO_THREADS`, `WASTE_IO_DEPTH`, cap 8) — no code
change needed to test QD 2→4→8 on Winnie's NVMe. Stage 2 should be requeued as:
(a) env-knob QD sweep at identical bytes (cheapest, zero risk, $0 code delta), THEN
(b) uring SQE-batch only if QD=8 shows B_eff still climbing toward colibri's 1M-QD8 3,232 MB/s
regime (their curve: 4M QD4 = 2,619 MB/s vs 1M QD8 = 3,232 MB/s).
Ceiling reminder from the idea's own model: at E[k]≈1.3 misses/layer the recovery is bounded
≤0.13x system — below the 19.6x need; value is only as a component stacked on exp31.

## Objective check

Optimized: I/O issue concurrency (achieved QD) during batch-1 decode. Algebraic connection:
tok/s ≈ B_eff / bytes-per-accepted-token; QD scales NVMe B_eff on the steep part of the device
curve (author's own 10.73→12.89 GB/s QD1→QD2 point), so raising QD raises B_eff at constant
bytes — the second lever of the system objective, orthogonal to byte reduction.

## Reproduction

```sh
git fetch upstream main   # sqliteai/warp
git show upstream/main:src/model.c | sed -n '3049,3066p'   # nio=2 depth=2 defaults
git show upstream/main:src/ecache.c | sed -n '16,18p'      # EC_QCAP 256, EC_MAXIO 8
git show upstream/main:src/model.c | sed -n '2777,2780p'   # pre-read hint, whole layer
git show upstream/main:src/ecache.c | sed -n '242,263p'    # eio_worker pread loop
```
