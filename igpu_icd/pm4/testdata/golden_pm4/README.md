# Golden PM4 captures — D1–D4 self-test streams

STATUS: **CAPTURED 2026-07-17** on the X5000 RX 560 (gcn-wb boot, gcngfx
`956f0ab` + `EXTRA_CFLAGS=-DGCN_PM4_CAPTURE`). All five streams landed in
one boot with every readback oracle PASSED on the same run; each capture
has its `.txt` sidecar (embedded MC addresses, masking rules). Dword
counts: d1_solid=127, d2a_sample=141, d2b_blit=141, d3_srcover=144,
d4_scale=144. Each stream opens with SET_SH_REG (VS program) and closes
with the 6-dword EOP fence (masked per below).

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

## Capture procedure (GCNgfx side — IMPLEMENTED)

The hook exists in GCNgfx: `gfx_cap_begin(name)`/`gfx_cap_end()` record
every dword passing through `gfx_ring_write1` and hex-dump over serial.
The five D-series self-tests are already instrumented with the exact names
listed above. To capture:

1. Build with the lab flag: `make clean all EXTRA_CFLAGS=-DGCN_PM4_CAPTURE`
   (the flag is compiled out of shipping builds; both configs link green).
2. Deploy to the X5000 and boot with COM7 serial captured
   (`serial_start uboot`, no rotation — NOT `sys_debug_ring`, which the
   present spam overflows). **Deploy needs the user's go-ahead** (TEST:
   safety rules in GCNgfx `docs/DESIGN.md`).
3. The self-tests run one-shot at init; each capture appears as:
   ```
   PM4CAP begin name=d1_solid dwords=NNN
   PM4CAP 0000: c0016900 000000a1 ...   (8 dwords per line)
   PM4CAP end name=d1_solid
   ```
4. Reconstruct on the PC: parse the hex values (they are HOST-order, i.e.
   the pre-swap dwords) and write each as a **little-endian uint32** — that
   byte-for-byte reproduces the ring memory the CP read. Confirm the run's
   self-tests PASSED (readback oracles) before blessing the capture.

Two deviations from the original spec, both deliberate:
- **The trailing EOP fence packet (6 dwords, EVENT_WRITE_EOP +
  CACHE_FLUSH_AND_INV_TS) IS included** in each capture — the self-tests
  emit it inline. Under the CONTRACTS.md §2 payload split it is
  backend-owned, so Agent D's diff harness must treat the final 6 dwords
  as reference-only (mask or strip), not as emitter output.
- Captures are the full test emission (state + descriptors + draw + EOP),
  not a trimmed payload; the sidecar records the boundaries.

Sidecar `.txt` per capture: gcngfx git rev, dword count, RT/tex dimensions
+ formats, shader blobs used, and every GPU (MC) address embedded in the
stream (RT base >>8 in CB_COLOR0_BASE, shader PGM_LO/HI, T# base, EOP
writeback address) so the diff harness can mask relocation words.
