#!/usr/bin/env python3
"""Reduce probe.tsv into per-generation results, flagging intra-generation splits."""
import sys, collections
GEN = [("SI/gfx6", "gfx600 gfx601 gfx602".split()),
       ("CI/gfx7", "gfx700 gfx701 gfx702 gfx703 gfx704 gfx705".split()),
       ("VI/gfx8", "gfx801 gfx802 gfx803 gfx805 gfx810".split()),
       ("GFX9",    "gfx900 gfx902 gfx904 gfx906 gfx908 gfx909 gfx90a gfx90c".split())]
rows = {}
order = []
for ln in open(sys.argv[1]):
    p = ln.rstrip("\n").split("\t")
    if len(p) < 5 or p[2] not in ("OK", "FAIL", "EMPTYTEXT"):
        continue
    if p[0] not in rows:
        rows[p[0]] = {}; order.append(p[0])
    rows[p[0]][p[1]] = (p[2], p[3], p[4])

only_splits = "--splits" in sys.argv
for probe in order:
    r = rows[probe]
    cells = []
    splits = []
    for gname, tl in GEN:
        vals = collections.OrderedDict()
        for t in tl:
            if t not in r: continue
            st, hx, err = r[t]
            key = hx if st == "OK" else "FAIL:" + err if st == "FAIL" else "EMPTY"
            vals.setdefault(key, []).append(t)
        if len(vals) == 1:
            cells.append(list(vals)[0])
        else:
            cells.append("**SPLIT**")
            splits.append((gname, {k: v for k, v in vals.items()}))
    uniq = len(set(cells))
    if only_splits and not splits:
        continue
    print("### %s   (%d distinct across gens)" % (probe, uniq))
    for (gname, _), c in zip(GEN, cells):
        print("    %-8s %s" % (gname, c))
    for gname, vals in splits:
        for k, v in vals.items():
            print("      SPLIT %s: %s -> %s" % (gname, ",".join(v), k))
