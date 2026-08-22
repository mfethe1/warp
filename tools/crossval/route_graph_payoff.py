#!/usr/bin/env python3
"""exp3 payoff bound: does route-transition placement touch bytes/accepted token?

Two parts:
  A) how much successor predictability is REAL (top-1 successor prob vs the
     marginal-permute null, which keeps per-layer expert popularity but kills
     cross-layer coupling);
  B) the algebraic ceiling: placement co-paging can only merge preads. It
     cannot change WHICH experts are demanded, so it cannot change bytes.
     Quantify the IOP/seek time it could recover at the K3 operating point.
"""
import json
import random
from collections import defaultdict

TRACE = "tests/trace_kimi_300.jsonl"
OUT = None

# --- established K3 constants (see ESTABLISHED FINDINGS) ---
RECORD_BYTES = 12_406_784          # exactly 3029 pages, one pread per expert
GIB = 1024 ** 3
PHYS_GIB_PER_TOK = 7.719           # measured physical
LOGICAL_GIB_PER_TOK = 17.009
TARGET_GIB_PER_TOK = 0.3946        # what 15 tok/s requires
BW_GIB_S = 5.919                   # measured streaming bandwidth
SEEK_MS = 0.080                    # optimistic NVMe random-read seek/cmd overhead


def load(path):
    out = []
    with open(path) as f:
        for line in f:
            if line.strip():
                out.append([list(x) for x in json.loads(line)["layers"]])
    return out


def top1_successor(toks):
    c = defaultdict(lambda: defaultdict(float))
    for layers in toks:
        for l in range(len(layers) - 1):
            cur, nxt = layers[l], layers[l + 1]
            w = 1.0 / (len(cur) * len(nxt))
            for u in cur:
                for v in nxt:
                    c[(l, u)][v] += w
    tot = num = 0.0
    for node, d in c.items():
        m = sum(d.values())
        num += max(d.values())
        tot += m
    return num / tot


def permute_null(toks, seed):
    rng = random.Random(seed)
    n_lay = len(toks[0])
    cols = [[toks[t][l] for t in range(len(toks))] for l in range(n_lay)]
    for c in cols:
        rng.shuffle(c)
    return [[cols[l][t] for l in range(n_lay)] for t in range(len(toks))]


def main():
    toks = load(TRACE)
    obs = top1_successor(toks)
    nulls = [top1_successor(permute_null(toks, 2000 + s)) for s in range(5)]
    mn = sum(nulls) / len(nulls)
    sd = (sum((x - mn) ** 2 for x in nulls) / len(nulls)) ** 0.5

    # --- B) byte / IOP algebra at the K3 operating point ---
    reads_per_tok = PHYS_GIB_PER_TOK * GIB / RECORD_BYTES
    stream_ms = PHYS_GIB_PER_TOK / BW_GIB_S * 1000.0
    seek_ms_total = reads_per_tok * SEEK_MS
    seek_frac = seek_ms_total / (stream_ms + seek_ms_total)

    # Perfect co-paging ceiling: every demanded successor already adjacent, so
    # every pread merges with its predecessor -> at most halve the IOP count.
    best_seek_saved_ms = seek_ms_total * 0.5
    # time budget per token to hit 15 tok/s
    budget_ms = 1000.0 / 15.0
    cur_ms = stream_ms + seek_ms_total

    res = {
        "label": "PROXY (predictability) + RECOMPUTATION (byte/IOP algebra)",
        "A_successor_predictability": {
            "n_null": len(nulls),
            "top1_successor_prob_observed": round(obs, 5),
            "top1_successor_prob_marginal_null_mean": round(mn, 5),
            "top1_successor_prob_marginal_null_sd": round(sd, 5),
            "excess_over_null": round(obs - mn, 5),
            "note": "marginal-permute null preserves per-layer expert popularity, "
                    "destroys only cross-layer coupling",
        },
        "B_byte_algebra": {
            "record_bytes": RECORD_BYTES,
            "physical_reads_per_token": round(reads_per_tok, 1),
            "stream_ms_per_token": round(stream_ms, 1),
            "seek_ms_per_token_at_80us": round(seek_ms_total, 2),
            "seek_fraction_of_read_time": round(seek_frac, 5),
            "perfect_copaging_ms_saved_per_token": round(best_seek_saved_ms, 2),
            "current_ms_per_token": round(cur_ms, 1),
            "budget_ms_per_token_for_15tps": round(budget_ms, 2),
            "ms_gap_remaining_after_perfect_copaging": round(
                cur_ms - best_seek_saved_ms - budget_ms, 1
            ),
            "bytes_per_accepted_token_delta": 0.0,
            "note": "Placement permutes WHERE records live; it does not change "
                    "WHICH experts are demanded nor the 3029-page record size. "
                    "d(bytes/accepted token)/d(layout) = 0 identically.",
        },
    }
    print(json.dumps(res, indent=2))
    import sys
    if len(sys.argv) > 1:
        with open(sys.argv[1], "w") as f:
            f.write(json.dumps(res, indent=2) + "\n")


if __name__ == "__main__":
    main()
