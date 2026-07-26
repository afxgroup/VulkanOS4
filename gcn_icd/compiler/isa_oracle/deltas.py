#!/usr/bin/env python3
"""Pairwise generation deltas across all probe TSVs."""
import sys
REP = [("gfx6", "gfx600"), ("gfx7", "gfx700"), ("gfx8", "gfx803"), ("gfx9", "gfx900")]
GENS = {"gfx6": "gfx600 gfx601 gfx602".split(),
        "gfx7": "gfx700 gfx701 gfx702 gfx703 gfx704 gfx705".split(),
        "gfx8": "gfx801 gfx802 gfx803 gfx805 gfx810".split(),
        "gfx9": "gfx900 gfx902 gfx904 gfx906 gfx908 gfx909 gfx90c".split()}  # gfx90a = CDNA2, no graphics
d = {}
for path in sys.argv[1:]:
    for ln in open(path):
        p = ln.rstrip("\n").split("\t")
        if len(p) < 5 or p[2] not in ("OK", "FAIL", "EMPTYTEXT"):
            continue
        d.setdefault(p[0], {})[p[1]] = p[3] if p[2] == "OK" else "FAIL(" + p[4] + ")"

def cell(pr, t):
    return d[pr].get(t, "?")

for a, b in (("gfx6", "gfx7"), ("gfx7", "gfx8"), ("gfx8", "gfx9")):
    ra, rb = dict(REP)[a], dict(REP)[b]
    print("\n" + "=" * 78)
    print("DELTA  %s (%s)  ->  %s (%s)" % (a, ra, b, rb))
    print("=" * 78)
    for pr in sorted(d):
        x, y = cell(pr, ra), cell(pr, rb)
        if x != y:
            print("  %-26s %-34s %s" % (pr, x, y))

print("\n" + "=" * 78)
print("INTRA-GENERATION SPLITS (a difference *within* one generation)")
print("=" * 78)
for pr in sorted(d):
    for g, tl in GENS.items():
        vals = {}
        for t in tl:
            vals.setdefault(cell(pr, t), []).append(t)
        if len(vals) > 1:
            print("  %-26s %s:" % (pr, g))
            for k, v in vals.items():
                print("      %-38s %s" % (",".join(v), k))
