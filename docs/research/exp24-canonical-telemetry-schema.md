# Canonical telemetry: `waste-route-v2` and the four fields nobody records

**Experiment:** exp24 / idea8 — canonical telemetry schema + converter (10 fields)
**Verdict:** ACCEPT
**Lane:** offline. **Evidence class:** RECOMPUTATION (format round-trip over a PROXY trace).
**Pins:** colibri `33e67a9c004b6e608d1f19dfbdcc20793377f94f` · warp `fd0deabc62b6e2e86d245553f61e77397a48a3b8`

## The preregistered gate

> ACCEPT: a convertible canonical schema exists → write the converter spec; enables
> cross-engine validation without merging either engine.
> REJECT: structurally incompatible → document the exact gap and keep ours.

Baseline: *"our ad-hoc `tests/trace_kimi_300.jsonl` (tok + layers[][]) which captures only
3 of 10 fields."* Metric: *"schema coverage: which of the 10 canonical fields each format
captures."* Stop rule: documentation comparison; deliverable is a converter spec or an
explicit incompatibility note.

This supersedes exp18, which asked the same question over 6 fields. The four fields added
here — router weights, read start/end, device id, route/output hash — are exactly where the
answer changes, so this is not a re-run.

## Coverage census [RECOMPUTATION, N=7,800 records = 300 tok × 26 L, deterministic]

Scored `yes`=1, `partial`=0.5, `no`=0, out of 10. Every cell is cited to a line of source,
not to a README claim.

| Field | `.coli_usage` | `ROUTE_TRACE` | `WASTE_DUMP_ROUTE` | `..._ROUTE_MARGIN` | `WASTE_DUMP_PREFILL` | ecache ctrs | ours |
|---|---|---|---|---|---|---|---|
| 1 token | ✗ | ~ `call//n_layers` | ✓ `dump_pos0` | ✓ | ~ chunk coords | ✗ | ✓ |
| 2 layer | ✓ | ✓ | ✓ | ✓ | ✓ | ✗ | ✓ |
| 3 ordered ids | ✗ | ✓ | ✓ | ~ kth only | ✗ | ✗ | ✓ |
| 4 router weights | ✗ | ✓ post-norm | ✓ post-norm | ✓ **score-space** | ✗ | ✗ | ✗ |
| 5 residency | ✗ | ✗ | ✗ | ✗ | ✓ hits/misses | ✓ | ✗ |
| 6 physical bytes | ✗ | ✗ | ✗ | ✗ | ✓ | ✓ `bytes_read` | ✗ |
| 7 read start/end | ✗ | ✗ | ✗ | ✗ | ~ duration sum | ✗ | ✗ |
| 8 device id | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| 9 eviction | ✗ | ✗ | ✗ | ✗ | ✗ | ~ count only | ✗ |
| 10 route/output hash | ~ writer id | ~ writer id | ✗ | ✗ | ~ format id | ✗ | ✗ |
| **score /10** | **1.5** | **4.0** | **4.0** | **3.5** | **4.5** | **2.5** | **3.0** |

The baseline's "3 of 10" is confirmed exactly: ours scores 3.0, capturing token, layer and
ordered ids and nothing else. **The best format on either project reaches 4.5 of 10.** There
is no near-miss to adopt; every engine is instrumented for the question it happened to be
asking.

## Converter round-trip [RECOMPUTATION, deterministic, N=7,800]

`route_schema_v2.py` writes `waste-route-v2`, then serialises out to three foreign formats
and re-reads each with a reader written against that source's own parse rules:

```
roundtrip_canonical_v2_lossless          : true
roundtrip_colibri_route_trace_lossless   : true
roundtrip_waste_dump_route_lossless      : true
coli_usage_legacy_reader_agrees          : true   (5,083 distinct (layer,expert) pairs)
```

The fourth line is the one worth having. `.coli_usage` is a *lossy destination* — order is
destroyed — so it cannot be round-tripped on ids. Instead the emitted file is re-read with a
literal transcription of the pre-header reader documented in `routing-telemetry.md`
(`while(fscanf(f,"%d %d %u",&l,&e,&cnt)==3) if(l>=0 …)`), and the folded counts match the
counts computed directly from the canonical records. That tests the property that actually
matters: a v2 → usage export is still readable by a colibri binary built before the header
record existed, and the three-numeric-field rule is not violated. 5,083 distinct pairs
matches the known distinct-expert count of this trace, independently confirming the fold.

## Result: ACCEPT, with the gap named precisely

A convertible canonical schema exists and is written. But the census makes the shape of the
gap sharper than exp18 could:

**Four of the ten fields are recorded by no format on either project** — `read_start_end`,
`device_id`, `eviction` (a *count* exists at `ecache.h:82`; the evicted *key* does not), and
`route_output_hash` (three formats carry a writer/format identity, none carries an identity
of the route or the output). No conversion can supply them. They are an *engine* change.

**Two more are captured but not joinable to a route**: `resident_before_demand` and
`physical_bytes` exist only in `waste-prefill-v1` and the ecache counters, and *neither of
those lists expert ids*. So today, no artifact on either project can answer "which expert
read cost these bytes" — the join key does not exist in the data.

That is the same orthogonality exp18 found, but it now has teeth: the split is not merely
inconvenient, it means **every bytes/token figure we hold is a route trace plus an assumed
cache model**, never a measurement of one run.

### Two conversion hazards, both still live

1. **`call` is a flat moe counter, not a token index** (`c/route_trace.h` `rt_trace_end`).
   At batch-1 the token is `call // n_layers`. Misreading it yields `n_layers×` too many
   one-layer tokens — a plausible-looking trace that silently destroys any locality result.
2. **Gate spaces are not interchangeable.** `ROUTE_TRACE` and `WASTE_DUMP_ROUTE` record
   *post-normalisation* gates; `WASTE_DUMP_ROUTE_MARGIN` records *score-space* `prob+bias`,
   the boundary the router actually selected on (`src/model.c:3268` says so explicitly, and
   is why it is a separate CSV rather than an extension). v2 therefore carries a mandatory
   `gate_space` discriminator. Folding these two into one `gates` column would produce a
   file that is arithmetically wrong in a way no reader can detect.

## `waste-route-v2`

```json
{"schema":"waste-route-v2","record":"header","n_layers":26,"n_experts":256,
 "engine":"warp_vq3r","expert_record_bytes":12406784,"provenance":{...},
 "n_devices":null,"device_map":null}
{"schema":"waste-route-v2","seq":0,"pos":0,"layer":0,"ids":[36,38,...],
 "gates":null,"gate_space":null,"resident":null,"physical_bytes_read":null,
 "read_ns":null,"dev":null,"evicted":null,"route_hash":null,"layer_ms":null}
```

`null` means *the producing format could not supply this* — an explicit absence, never a
zero. A source without weights must never have `gates` filled with a uniform `1/k`; the
writer synthesises uniform gates only when serialising *out* to a parser that demands the
column, which is why every round-trip comparison above is on ids alone.

`trace_kimi_300.jsonl` is a strict subset of v2. `belady_sim.py` needs no change.

## Two things to propose upstream

- **`"evicted": [[layer, expert], …]`** — every replacement-policy result we have (Belady vs
  LRU, 17.54 pp) reconstructs evictions by re-simulating the policy, so the simulation can
  only validate itself.
- **`"dev"` per read** — field 8 is recorded by nobody, and exp23 just concluded that the
  duplicate-vs-shard decision turns on per-device load balance (shard tax 1.1964× / 1.3750× /
  1.5348× at 2/3/4 devices). That model is currently unfalsifiable from telemetry: there is
  no artifact in which a read is attributed to a device.

## Objective check

This optimised **measurement plumbing, not the objective**, and per the standing
objective-mismatch audit that idea8 *is*, that is stated plainly rather than dressed as a
win. There is no algebraic path from a schema to bytes per accepted token — converting a
trace moves zero bytes at inference time.

The connection is instrumental and now quantified. `tok/s ≈ effective_bandwidth /
physical_bytes_per_accepted_token`. The denominator is measured only by
`physical_bytes_read`; the route ids that *determine* it live in files that cannot be
joined to it (`fields_captured_but_not_joinable_to_route`). The numerator, effective
bandwidth, requires fields 7 and 8 — per-read start/end and device id — which **no format on
either project records at all**. So exp23's central quantity, effective bandwidth under a
batch-1 per-layer barrier, cannot today be measured, only modelled. The canonical schema
does not raise tok/s by one token; it makes both terms observable in one record, which is
the precondition for any future number being a measurement rather than a reconstruction.

## Reproduce

```bash
python3 route_schema_v2.py /tmp/spark/warp/tests/trace_kimi_300.jsonl <outdir>
```

Input `trace_kimi_300.jsonl` sha256 `06ad026c…4965` — **PROXY**: Kimi-Linear-shaped
(26 L × 256 E, top-8), *not* K3 (92 L × 896 E, top-16). No K3 measurement was taken.

| Artifact | sha256 |
|---|---|
| `canonical_v2.jsonl` | `c86d0c2ef99e2451c8f1402befe16bd64965c639e787d6f9794fa861856d5a77` |
| `as_colibri_route_trace.txt` | `19a21c64c5df4bc23c8e2e481fab1a10b91d34f4a665df1652b5683e8315c97a` |
| `as_waste_dump_route.txt` | `f8be533197c92864aec2566b8566ce5ea15bc2bcec25d823cd041a87ee2d2c78` |
| `as_coli_usage.txt` | `ee0620c0107765379748bbe9d420996748e68fe833a10d1ba6a7fdde985357a1` |
