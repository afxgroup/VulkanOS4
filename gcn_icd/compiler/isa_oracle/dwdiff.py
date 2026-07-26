#!/usr/bin/env python3
"""Dword-by-dword diff of two raw .text blobs (little-endian)."""
import sys, struct
def dw(p):
    d = open(p, 'rb').read()
    return [struct.unpack_from('<I', d, i)[0] for i in range(0, len(d) - 3, 4)]
a, b = sys.argv[1], sys.argv[2]
A, B = dw(a), dw(b)
print("%-10s len=%d dwords   |  %-10s len=%d dwords" % (a.split('/')[-1], len(A), b.split('/')[-1], len(B)))
for i in range(max(len(A), len(B))):
    x = "%08X" % A[i] if i < len(A) else "--------"
    y = "%08X" % B[i] if i < len(B) else "--------"
    print("  [%2d] %s  %s  %s" % (i, x, y, "" if x == y else "  <<< DIFF"))
