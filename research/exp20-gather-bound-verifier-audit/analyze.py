import statistics as st, json

runs = {
 3072:  [(1.883,0.273),(0.907,0.283),(0.944,0.232),(0.873,0.202),(0.790,0.185)],
 9216:  [(2.551,0.647),(2.209,0.515),(1.995,0.469),(1.999,0.460),(2.014,0.470)],
 196608:[(49.596,11.091),(49.190,13.533),(48.028,9.938),(47.357,10.095),(48.831,10.249)],
}
NV, TILE = 448, 64
out = {}
for M, rs in runs.items():
    nidx = (M//TILE)*NV*TILE*3
    gib = nidx/1073741824
    A = [gib/(a/1e3) for a, _ in rs]
    D = [gib/(d/1e3) for _, d in rs]
    out[M] = {"idx_bytes": nidx, "gib": gib,
              "A_mean": st.mean(A), "A_sd": st.pstdev(A), "A_min": min(A), "A_max": max(A),
              "D_mean": st.mean(D), "D_sd": st.pstdev(D), "N": 5}
    print("M_ROWS=%d idx_bytes=%d (%.6f GiB)" % (M, nidx, gib))
    print("  VQ3R kern_A: mean %.3f GiB/s/core  sd %.3f  N=5  [%.3f,%.3f]" % (st.mean(A), st.pstdev(A), min(A), max(A)))
    print("  VQ4P kern_D: mean %.3f GiB/s/core  sd %.3f  N=5" % (st.mean(D), st.pstdev(D)))
    for bw, tag in ((5.919,'single-SSD'), (11.838,'dual-SSD')):
        print("    cores_required @%.3f GiB/s (%s) = %.3f" % (bw, tag, bw/st.mean(A)))
    print()

r = out[196608]["A_mean"]; rsd = out[196608]["A_sd"]
print("=== DECISIVE CONFIG: M_ROWS=196608, 252 MB index stream (DRAM-resident, out of cache) ===")
print("VQ3R gather rate = %.3f GiB/s/core (sd %.3f, N=5)" % (r, rsd))
print("ACCEPT gate (rate >= 2.0 GiB/s/core): %s" % ("PASS" if r >= 2.0 else "FAIL"))
print("REJECT gate (rate <  0.75 GiB/s/core): %s" % ("TRIGGERED" if r < 0.75 else "not triggered"))
print()
phys = 7.719
print("Per-token physical demand %.3f GiB" % phys)
print("  disk time @5.919 GiB/s = %.1f ms (established 1304.1 ms)" % (phys/5.919*1e3))
print("  single-core gather time = %.1f ms" % (phys/r*1e3))
print()
rows = []
for n in (1, 2, 3, 4, 10):
    for bw, tag in ((5.919,'1xSSD'), (11.838,'2xSSD')):
        io = phys/bw*1e3
        cp = phys/(r*n)*1e3
        t = max(io, cp)
        rows.append({"cores": n, "regime": tag, "io_ms": io, "compute_ms": cp,
                     "t_ms": t, "bound": "COMPUTE" if cp > io else "I/O"})
        print("  cores=%2d %s: io=%7.1f  compute=%7.1f  ->  t=%7.1f ms  bound=%s"
              % (n, tag, io, cp, t, "COMPUTE" if cp > io else "I/O"))
print()
res = {}
for n in (4, 10):
    c = min(1.0, (5.919/r)/n)
    ach = 1304.1*(c + (1-c)/2)
    res[n] = {"c": c, "achieved_ms": ach, "speedup": 1304.1/ach}
    print("c (avail=%d cores) = %.4f -> exp17 dual-SSD achieved %.1f ms = %.3fx (vs claimed 2.000x)" % (n, c, ach, 1304.1/ach))

json.dump({"per_config": out, "decisive_rate_gib_s_core": r, "decisive_sd": rsd,
           "scaling": rows, "exp17_erosion": res}, open("exp20_result.json", "w"), indent=2)
print("\nwrote exp20_result.json")
