#!/usr/bin/env python3
"""exp26: prefill expert-dedup sweep + objective-mismatch audit.

PROXY evidence on in-repo trace_kimi_300.jsonl (Kimi-Linear-shaped:
300 tok x 26 layers x top-8 = 62,400 accesses, 5,083 distinct experts).
Expert record = 12,406,784 B (verified bottom-up in prior work).

For each chunk size C we process the 300-token prompt in order, and for
each (chunk, layer) count DISTINCT experts routed to by the chunk's
tokens at that layer. Layer-major chunked prefill (warp ENGINE.md /
colibri kimi_k3.md) reads each distinct (layer, expert) exactly once per
chunk. Physical bytes = distinct_records * RECORD_BYTES.

Prints: dedup factor vs C=1, physical GiB per prompt token, and the
audit arithmetic comparing logical vs physical demand.
"""
import json, sys

TRACE = "/Users/mfethe/e3-policy/trace_kimi_300.jsonl"
RECORD_BYTES = 12_406_784  # exact 3029 x 4096-byte pages
GiB = 1024**3

toks = []
with open(TRACE) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        toks.append(d["layers"])  # list[list[int]] experts per layer

N = len(toks)
L = len(toks[0])
K = len(toks[0][0])
print(f"# PROXY trace: N={N} tokens, L={L} layers, top-{K} "
      f"-> {N*L*K} raw accesses")

results = {}
for C in (1, 8, 16, 32, 64):
    reads = 0  # distinct (chunk, layer, expert) records
    raw = 0
    for c0 in range(0, N, C):
        chunk = toks[c0:c0 + C]
        for li in range(L):
            distinct = set()
            for t in chunk:
                distinct.update(t[li])
            reads += len(distinct)
            raw += len(chunk) * K
    bytes_total = reads * RECORD_BYTES
    bytes_per_tok = bytes_total / N
    raw_per_tok = raw * RECORD_BYTES / N
    results[C] = (reads, raw, bytes_per_tok, raw_per_tok)
    print(f"C={C:3d}  distinct_records={reads:6d}  raw={raw:6d}  "
          f"dedup={raw/reads:5.3f}x  "
          f"phys={bytes_per_tok/GiB:7.4f} GiB/prompt-tok  "
          f"(raw={raw_per_tok/GiB:7.4f})")

# audit arithmetic: the earlier apples-to-oranges comparison
c1 = results[1][2]
c32 = results[32][2]
print()
print("# AUDIT: earlier 'batching dead' claim compared LOGICAL batched")
print("# demand (GiB/token, counting every routed expert) against PHYSICAL")
print("# unbatched reads with a warm cache. Correct comparisons:")
print(f"#   raw logical demand (no dedup):  {results[1][3]/GiB:.4f} GiB/token [PROXY trace]")
print(f"#   physical @ C=1 (dedup within token, none across): {c1/GiB:.4f} GiB/token")
print(f"#   physical @ C=32 (chunk dedup):                    {c32/GiB:.4f} GiB/token")
print(f"#   reduction C=1 -> C=32: {100*(1-c32/c1):.2f}%")
for C in (8, 16, 32, 64):
    print(f"#   reduction C=1 -> C={C}: {100*(1-results[C][2]/c1):.2f}%  (gate: >=20%)")

# K3-shape note: expected dedup sensitivity to top-k / n_experts
# (analytic, not measured): overlap probability rises with k/E; trace is
# top-8/256 Kimi-Linear shape; K3 is top-16/896 per routing telemetry.
print()
print("# SHAPE CAVEAT: trace is Kimi-Linear-shaped (top-8, 256E), NOT K3")
print("# (92L x 896E x top-16). K3 chunk overlap must be re-measured on a")
print("# real K3 routing dump before any REAL-K3 number is quoted.")
