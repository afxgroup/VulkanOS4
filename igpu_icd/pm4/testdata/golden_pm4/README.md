# Golden PM4 captures — D1–D4 self-test streams

STATUS: NOT YET CAPTURED. This directory is the drop point; capturing is a
small GCNgfx-side task (Agent C or coordinator) that must happen before
Agent D's first milestone can complete.

## What goes here

One file per D-series self-test, dumped at the point the ring/IB dwords are
final (post byte-order handling — i.e. exactly the LE dwords the CP reads):

- `d1_solid.pm4`   — 64×64 solid fill (VS+PS draw, D1)
- `d2a_sample.pm4` — textured sample (D2a)
- `d2b_blit.pm4`   — per-pixel 1:1 blit (D2b)
- `d4_scale.pm4`   — bilinear 2x scale (D4)
- `d3_srcover.pm4` — shader-side SrcOver composite (D3)

Format: raw binary, little-endian dwords, exactly the submitted stream (no
ring wrapper, no backend preamble, no EOP fence — per CONTRACTS.md §2 those
are backend-owned). Alongside each `.pm4`, a `.txt` sidecar noting: gcngfx
git rev, RT dimensions/format, shader blob used, and any GPU VAs embedded
in the stream (so the replay harness can relocate/compare with masks).

## Capture procedure (GCNgfx side)

Add a debug dump hook where the D-series tests hand their dword stream to
the ring (`src/gfx/gcn_gfx.c` submit path): write the dwords to a file via
the serial/fs harness, or `DGCN`-hex-dump and reconstruct. Do it from the
same commits whose bench-results write-ups verified the tests, or re-run
and re-verify readback first. Addresses embedded in the stream should be
noted in the sidecar so byte-diffs can mask relocation words.
