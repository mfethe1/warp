# Routing telemetry: one canonical schema (`waste-route-v1`)

**Experiment:** exp18 / idea8 — routing telemetry schema comparison
**Verdict:** ACCEPT (with one caveat: evictions are captured by *no* existing format)
**Lane:** offline. Evidence class: RECOMPUTATION (format round-trip over a PROXY trace).

## Question

The preregistered accept gate: *"a convertible canonical schema exists — write the
converter, avoid maintaining an incompatible format."* Reject gate: *"formats are
structurally incompatible — document the gap and keep ours."*

Six required fields: ordered `(layer, expert)`, residency state, physical bytes,
timing, evictions, route identity.

## Formats compared (pinned, read-only)

| Format | Source of truth |
|---|---|
| colibri `.coli_usage` | `c/route_trace.h:358-363`, `docs/routing-telemetry.md` @ `33e67a9c004b6e608d1f19dfbdcc20793377f94f` |
| colibri `ROUTE_TRACE` | `c/route_trace.h:142-143` (same SHA) |
| warp `WASTE_DUMP_ROUTE` | `tools/routing_stats.py:164-198` (`read_trace`) @ `0400812d0d3279ce89b6ab104a18e66cc01cfe09` |
| warp `WASTE_DUMP_PREFILL` | `tools/prefill_trace.py` `SCHEMA = waste-prefill-v1` (same SHA) |
| ours | `tests/trace_kimi_300.jsonl` sha256 `06ad026c…4965` |

## Coverage matrix

| Field | `.coli_usage` | `ROUTE_TRACE` | `WASTE_DUMP_ROUTE` | `WASTE_DUMP_PREFILL` | ours |
|---|---|---|---|---|---|
| ordered (layer,expert) | ✗ counts only | ✓ | ✓ | ~ union only | ✓ |
| residency state | ✗ | ✗ | ~ lookahead ≠ residency | ✓ hits/misses | ✗ |
| physical bytes | ✗ | ✗ | ✗ | ✓ | ✗ |
| timing | ✗ | ✗ | ✗ | ✓ | ✗ |
| evictions | ✗ | ✗ | ✗ | ✗ deltas, no key | ✗ |
| route identity | ✓ engine hash | ~ sibling file | ✗ | ✓ schema string | ✗ |

**The structural finding: the split is orthogonal, not incompatible.** Every format that
carries ordered route ids carries *no* byte/timing/residency data, and the one format that
carries bytes and timing (`waste-prefill-v1`) does not list the ids. That is exactly why a
merge works — the two halves never disagree, they only fail to overlap. Nothing needs to be
dropped to unify them.

## Converter — round-trip result [RECOMPUTATION]

`route_schema.py` converts our JSONL into `waste-route-v1` and back out into both foreign
line formats, then re-reads each with a reader written against the *source's own* parse
rules and compares the ordered `(pos, layer, ids)` sequence.

N = 7,800 records (300 tokens × 26 layers), 256 experts. Deterministic — no variance.

```
roundtrip_canonical_lossless             : true
roundtrip_colibri_route_trace_lossless   : true
roundtrip_waste_dump_route_lossless      : true
```

All three are exact on the ordered id sequence, so the gate is met.

### Two conversion hazards found, both real

1. **colibri's `call` is a flat sequence counter, not a token index.** `rt_trace` increments
   `rt_call` once per `moe()` invocation, so at batch-1 the token is `call // n_layers`, not
   `call`. A converter that reads `call` as a position silently produces a trace with
   `n_layers×` too many tokens, each one layer deep — which would look like a plausible
   trace and quietly destroy any locality measurement built on it. `WASTE_DUMP_ROUTE`
   does not have this problem: `routing_stats.py` documents that its leading field is the
   *absolute* position precisely because re-deriving token boundaries from layer-index wrap
   was got wrong three times before it moved into the engine.

2. **`.coli_usage` is not convertible in the direction that matters.** It is an aggregate —
   `(layer, expert, count)` with the order destroyed. Canonical → usage is lossy but valid
   (fold the counts). Usage → canonical is impossible. It is a *destination*, never a source.
   Its three-numeric-field rule is also absolute: a four-field record desynchronises every
   legacy reader and fabricates records rather than being skipped.

## `waste-route-v1`

Header line, then one object per (token, layer):

```json
{"schema":"waste-route-v1","record":"header","n_layers":26,"n_experts":256,
 "engine":"warp_vq3r","expert_record_bytes":12406784}
{"schema":"waste-route-v1","seq":0,"pos":0,"layer":0,"ids":[36,38,...],"gates":null,
 "resident":null,"physical_bytes_read":null,"evicted":null,"layer_ms":null}
```

The optional fields are `null` when the producing format could not supply them — an explicit
absence, not a zero. `gates: null` from a source without weights must never be silently
filled with a uniform `1/k`; the writer emits uniform gates only when serialising *out* to a
format whose parser demands the column, and the round-trip comparison is on ids alone for
that reason.

**Recommendation: do not keep a separate ad-hoc format.** Our `trace_kimi_300.jsonl` is a
strict subset of `waste-route-v1` (drop the header, keep `pos`/`layer`/`ids`), so it stays
readable and the converter is additive. `belady_sim.py` needs no change — it consumes
`(layer, expert)` pairs per token, which the canonical form yields directly.

## The gap worth naming: evictions

No format on either project records *which key was evicted*. `waste-prefill-v1` gives
`cache_hits`/`cache_misses` — enough to reconstruct byte totals, not enough to attribute a
miss to the decision that caused it. Every replacement-policy comparison we have run
(Belady vs LRU, 17.54 pp apart) reconstructs evictions by *re-simulating* the policy rather
than reading them, which means the simulation can only ever validate itself. A one-field
addition — `"evicted": [[layer, expert], ...]` — makes a recorded run auditable against a
simulated one. This is the concrete thing to propose upstream.

## Objective check

This experiment optimised **measurement plumbing, not the objective.** There is no
algebraic path from a schema change to bytes per accepted token — converting a trace moves
zero bytes at inference time.

The connection is instrumental and worth being precise about: `tok/s ≈ effective bandwidth /
physical bytes per accepted token`, and the denominator is exactly what
`waste-prefill-v1`'s `physical_bytes_read` measures while the route formats supply the
`(layer, expert)` sequence that *determines* it. Today those two live in files that cannot
be joined, so every bytes/token number we have is reconstructed from a route trace plus an
assumed cache model rather than read from one run. The canonical schema makes the numerator
and denominator observable in the same record. It buys **credibility of future
measurements, not throughput** — and per the standing objective-mismatch audit that this
idea *is*, that should be stated plainly rather than dressed up as a win.

## Reproduce

```bash
python3 route_schema.py /tmp/spark/warp/tests/trace_kimi_300.jsonl <outdir>
```

Artifacts: `canonical.jsonl` `382141e2…c398`, `as_colibri_route_trace.txt` `19a21c64…c97a`,
`as_waste_dump_route.txt` `692533e6…13a2`, `result.json`.
