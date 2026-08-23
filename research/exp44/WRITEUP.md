# exp44 — grouped-vs-interleaved measurement validity (falsified)

**Claimed:** 2026-08-23 ~13:20 EDT, lane `offline`, priority 0.459.
**Verdict:** falsified — the upstream grouped-drift hazard does NOT transfer to our pure-replay lane.

## Preregistered spec (unchanged)
- PROXY on this Mac; LRU vs Belady on `tests/trace_kimi_300.jsonl`, cap=1490, N=10 reps.
- Protocol A grouped (all reps arm1 then arm2, separate processes) vs B interleaved (rep-major alternation).
- Metric: per-rep physical GiB/token → **switched to wall time** (spec-mandated: byte counts proved deterministic).
- Accept: sd_B < 0.5·sd_A. Reject: protocols agree within 1 sd. Stop: per-rep sd < 0.5%.

## Result [PROXY, N=10 reps/arm/protocol]
- Byte counts fully deterministic: LRU misses = 18,786 / 62,400 accesses; Belady = 10,261 — every rep, both protocols. (Matches exp40's 18,786.)
- Wall time, protocol A (grouped, two processes): LRU 4.006 ± 0.142 ms, Belady 15.305 ± 0.392 ms; between-arm delta +11.299 ms (27.1 sd from 0).
- Wall time, protocol B (interleaved pairs): paired d̄ = +11.382 ms, sd_d = 0.303 ms (37.6 sd from 0).
- **Primary metric sd ratio B/A = 0.727** — interleaving does cut single-rep delta noise ~27%, but not < 0.5×.
- **Reject gate FIRES:** |A − B| = 0.083 ms, far inside 1 sd (0.42 / 0.30). Protocols agree in sign and magnitude.

## Interpretation
Upstream's §32/§33 grouped-sweep failures (39% drift on sync runs) arise from fio/page-cache/engine state charging drift to the last arm. In pure in-memory Python replay there is no engine state; the only noise is scheduler jitter on a 4–15 ms computation. The effect under test (Belady 3.8× slower than LRU at cap 1490 — heap maintenance dominates) is ~27 sd away from zero, so grouped measurement cannot flip any such conclusion here.

**Operational consequence:** exp31/exp41 factorials may keep the grouped protocol; replay byte metrics are exact. If a future pair of arms lands within ~2 sd of each other, rerun interleaved — it is strictly cheaper in variance per rep.

## Objective check
Optimizes measurement validity (noise floor of 2-arm wall-time deltas in the replay harness), not bytes/accepted token. It is a methods guard for factorials whose metric is physical GiB/token; since replay byte counts are deterministic, protocol choice cannot alter any byte-derived result.

## Artifacts
- `exp44_run.py`, `exp44_analyze.py`, `raw_grouped_arm1.jsonl`, `raw_grouped_arm2.jsonl`, `raw_interleaved.jsonl`, `exp44_result.json`, `sha256.txt` in this directory.
- Trace: `warp@ba3f394` (collab/belady-oracle) `tests/trace_kimi_300.jsonl`; harness adapted from `tools/crossval/belady_sim.py`.
