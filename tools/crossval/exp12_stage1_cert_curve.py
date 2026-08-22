"""
exp12 stage-1: convert the PREREGISTERED s_eff gates into required bound magnitudes,
using the REAL-K3 sprint11 route-margin certification curve.

Certification rule (idea16): an access is certified (pread skipped) iff
    bound <= gap/2          i.e. required_margin = 2*bound
so   s_cert(bound) = P(margin >= 2*bound)
which is exactly the published score_error_risk curve.

Source: docs/gn100/sprint11-route-margin-summary.json  [REAL-K3, 92L, 6348 rows]
"""
import json, math

P = '/tmp/spark/warp/docs/gn100/sprint11-route-margin-summary.json'
d = json.load(open(P))

pts = [(r['required_margin'], 1.0 - r['fraction_not_certified'])
       for r in d['score_error_risk']]
pts = [(m, s) for (m, s) in pts if 0.0 < s < 1.0]
pts.sort()

print(f"REAL-K3 certification curve  (layers={d['layers']}, rows={d['rows']}, "
      f"exact_boundary_ties={d['exact_boundary_ties']}, "
      f"nonfinite={d['rows_with_nonfinite_scores']})")
print(f"{'required_margin':>16} {'bound=m/2':>14} {'s_cert':>12}")
for m, s in pts:
    print(f"{m:>16g} {m/2:>14.6g} {s:>12.8f}")


def bound_for_s(target):
    """log10(required_margin) linear in s_cert between bracketing published points."""
    for (m0, s0), (m1, s1) in zip(pts, pts[1:]):
        hi, lo = max(s0, s1), min(s0, s1)
        if lo <= target <= hi:
            l0, l1 = math.log10(m0), math.log10(m1)
            t = (target - s0) / (s1 - s0)
            lm = l0 + t * (l1 - l0)
            return 10 ** lm
    return None


print("\n=== PREREGISTERED GATES -> required bound magnitude (score units) ===")
for label, s in [("accept gate (1): arm A must FAIL, s_eff < 0.10", 0.10),
                 ("accept gate (2): arm A+B must reach s_eff >= 0.40", 0.40),
                 ("reject gate (1): A+B dies if s_eff < 0.25", 0.25)]:
    m = bound_for_s(s)
    print(f"{label}\n    s_cert={s:.2f} -> required_margin={m:.6g}  "
          f"=> bound <= {m/2:.6g}")

bA = bound_for_s(0.10) / 2
bAB = bound_for_s(0.40) / 2
print(f"\n=== THE TIGHTENING WHITENING MUST BUY ===")
print(f"arm A  (isotropic, at its DEAD line s=0.10): bound  > {bA:.6g}")
print(f"arm A+B (whitened, to pass gate 2, s=0.40) : bound <= {bAB:.6g}")
print(f"REQUIRED TIGHTENING FACTOR = {bA/bAB:.4f}x")
print("\nInterpretation: for the ENABLING signature to exist at all, activation")
print("whitening must shrink the Cauchy-Schwarz residual bound by this factor")
print("in score units. This is a NECESSARY condition, derived from REAL-K3")
print("margins, and is independent of any replay.")

print("\n=== WHY STAGE 1 IS NOT DECIDABLE ===")
print("Computing the ACHIEVED bound under either metric requires:")
print("  (a) one real K3 expert's row norms   -> max_row ||W_row||_2")
print("  (b) one batch of real hidden states  -> ||x||_2 and Sigma_x")
print("Neither is derivable from the published margin summary, which contains")
print("only order statistics of the routing gap. Substituting synthetic or")
print("iid activations would make the answer a tautology of the assumption --")
print("the exact failure the stop_rule forbids and that sank exp11.")
print("\nAdditionally: sprint11 margins are UNCONDITIONAL over all 6348 rows.")
print("The gates are written on s_eff = P(certified AND miss)/P(miss).")
print("exp11 established sprint11 carries NO margin<->expert-identity coupling,")
print("so the miss-conditioning cannot be recovered from this artifact either.")
