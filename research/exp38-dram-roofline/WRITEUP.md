# exp38 — dram-roofline-on-logical-demand

**Idea 36 / experiment 38.** Lane `offline`. Host: Apple M4 (4 P-core + 6 E-core, 24 GiB, macOS 15.6).
Kernel pinned to WARP `7f1fbba3cbaee0e9fdaffd940d87ff2dba9ee09b` (exp35 pin). `kern_D` body is
byte-identical to the exp35 evidence copy `lutmt2.c` (sha256 `768e690d5246dd0e...`).

## Preregistered gates (quoted verbatim, not modified)

> **ACCEPT** if kern_D achievable bandwidth is within 10% of the memcpy control (confirming the
> gather is on the DRAM roof for a good kernel) AND the recomputed M4 ceiling is <=6.6 tok/s,
> establishing that no kernel can reach 15 tok/s on M4.

> **REJECT** if kern_D exceeds the memcpy control by >10% (LUT reuse defeats the roofline
> denominator L) OR if any <=$3000 platform is shown to deliver >=315.0 GiB/s achievable on the
> 3029-page-record pattern.

## Stage 1 [SYNTHETIC, N=5 per arm, T=4, QOS_CLASS_USER_INTERACTIVE]

Per-thread independent 252.00 MB index stream (M_ROWS=196608), well beyond SLC. All numbers are
**source-read** GiB/s so the ratio is dimensionally comparable. One discarded warm-up rep per arm.

| arm | mean read GiB/s | sd (N=5) |
|---|---|---|
| **D** — VQ4P gather | **65.439** | 0.546 |
| **CPY** — memcpy control (preregistered) | 46.482 | 0.373 |
| **RDSUM** — pure streaming read-reduce | **68.159** | 0.215 |

## Gate adjudication — the preregistered control is dimensionally wrong

- **Literal arithmetic fires REJECT:** D/CPY = **1.4078**, i.e. kern_D exceeds the memcpy control
  by **+40.8%**, far beyond the >10% reject threshold.
- **But that comparison is invalid.** `memcpy` moves **2 bytes of DRAM traffic per byte of source
  read** (one read + one write); `kern_D` moves **1.003**. Comparing D's read rate against memcpy's
  read rate compares two different physical quantities. The reject clause's stated *mechanism* is
  "LUT reuse defeats the roofline denominator L" — the memcpy control cannot test that mechanism,
  because D can beat memcpy's read rate purely by not writing, with zero LUT reuse.
- **Total-DRAM-traffic normalization:** D_total = 65.634 GiB/s, CPY_total = 92.964 GiB/s,
  ratio **0.706** — D is 29.4% *below* memcpy. Neither accept nor reject as written.
- **Dimensionally matched read-only control (RDSUM):** D/RDSUM = **0.9601**. kern_D achieves
  **96.0% of the read-only streaming roof**, comfortably within 10%. The idea's actual mechanism
  claim — the gather is on the DRAM roof, LUT reuse buys nothing — is **supported**.
- Reject clause 2 (any ≤$3000 platform ≥315.0 GiB/s achievable) is **NOT DEMONSTRATED**; no such
  measurement exists.

Because the preregistered control is the wrong physical quantity and the literal reading contradicts
the correctly-controlled reading, this is filed **inconclusive**, not confirmed and not falsified.
Gates were not moved after seeing data; the corrected control is reported *alongside* the literal one.

## Stage 2 [RECOMPUTATION] — ceilings on L = 17.0085 GiB/token logical

Required achievable bandwidth for 15 tok/s: **255.128 GiB/s**.

- Achievable ratio this run: r = 65.439 / 111.759 = **0.5855** (T=4 P-cores only).
- exp35 best-ever D across all T: r = 90.659 / 111.759 = **0.8112**.
- M4 ceiling at r_measured: **3.847 tok/s** [RECOMPUTATION]
- M4 ceiling at r_exp35: **5.330 tok/s**
- M4 **absolute nameplate roof** (r = 1.0, physically unattainable): **6.571 tok/s** ≤ 6.6 →
  accept condition 2 holds.
- Remaining kernel headroom on M4 against the read roof: **1.0416x**. There is essentially none.
- L-reduction factor required on M4: **3.899x**.

## Stage 3 — platform table (every non-M4 row NAMEPLATE-UNVERIFIED)

| platform | nameplate GiB/s | DRAM GiB | ceiling @0.5855 | @0.8112 | @1.0 | holds 952 GiB WS? |
|---|---|---|---|---|---|---|
| M4 24GB (MEASURED) | 111.759 | 24 | **3.847** | 5.330 | 6.571 | no |
| DDR5-5600 dual-ch | 83.447 | 192 | 2.873 | 3.980 | 4.906 | no |
| 8-ch DDR4-3200 srv | 190.735 | 512 | 6.566 | 9.097 | 11.214 | no |
| 12-ch DDR5-4800 srv (>$3000) | 429.153 | 768 | 14.774 | 20.468 | 25.232 | no |
| RTX 5060 Ti 16GB | 417.233 | 16 | 14.364 | 19.899 | 24.531 | no |
| used M1 Ultra 128GB | 745.058 | 128 | 25.650 | 35.535 | 43.805 | no |

## Stage 4 — retro-gate, and the capacity corollary (the real result)

**Retro-gate:** every iso-rate kernel/codec idea in the register is capped at `B_achievable / L` on
its own platform. On M4 that cap is **3.847 tok/s**. No iso-rate substitution — VQ4P, rANS, any
gather kernel — can exceed it. The only remaining levers are (a) reduce L, (b) buy bandwidth.

**Capacity corollary — this is the finding worth keeping.** Not one platform in the table has DRAM
capacity ≥ the 952 GiB VQ3R working set. Every row that clears 315 GiB/s nameplate does so with
16–768 GiB of DRAM, so its DRAM roof is *unreachable* for this workload and the binding resource
reverts to SSD/PCIe. **The DRAM roofline is therefore not the binding constraint on any candidate
≤$3000 platform** — which also means the idea's own framing ("the goal becomes bandwidth-per-dollar
procurement") is under-specified. Bandwidth-per-dollar must be scored *jointly* with
capacity-per-dollar, subject to `capacity >= working set`, or the purchased bandwidth is unusable.

## Objective check

Optimized: the *denominator-independent* term of `tok/s = B_effective / bytes_per_accepted_token`.
Algebraically connected: directly. Stage 1 measures B_effective for the real VQ4P access pattern;
Stage 2 divides it by L = 17.0085 GiB/token to produce tok/s. It reduces no bytes — it establishes
the numerator's ceiling, and shows the M4 numerator is already within 4.2% of its own read roof, so
all remaining headroom must come from the denominator or from different silicon.
