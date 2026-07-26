# Pipeline state → PM4 emission (Agent D lane)

This directory turns recorded Vulkan state (pipelines, descriptor sets,
render targets, draws) into the GFX8 PM4 stream that goes into the opaque
`GPU_SubmitA` payload. **Read `../CONTRACTS.md` §1–2 first** — you consume
the shader blob ABI and produce the submit payload; you own neither
contract.

## Your job (Agent D)

- Emit per-submit PM4 only: SET_CONTEXT_REG / SET_SH_REG / SET_UCONFIG_REG
  groups, descriptor-table writes, DRAW_INDEX_AUTO / DRAW_INDEX_2 /
  DISPATCH_DIRECT. The once-per-init preamble (CONTEXT_CONTROL, CLEAR_STATE,
  golden regs, tiling tables) and the EOP done-fence are the backend's —
  never emit them (HW-proven poison outside ring init, per the D0 notes).
- Program shader stages from `GcnShaderBlob`: place code in VRAM (256-byte
  aligned), SPI_SHADER_PGM_LO/HI = VA >> 8, RSRC1/RSRC2 from the blob,
  SPI_PS_INPUT_ENA/ADDR + SPI_PS_INPUT_CNTL_n, user-SGPR loads resolved
  from the blob's `user_sgprs[]` map against bound descriptor sets / push
  constants.
- Descriptor tables: persistent VRAM tables, T# at +0x00 / S# +0x20 style
  layout per the D5a code in `GCNgfx/src/gfx/gcn_gfx.c` — the 16-user-SGPR
  cap makes indirect tables the norm, and the mechanism is shared with
  GCNgfx's D5 compositing work (coordinate through the coordinator, don't
  fork the format).
- Render-target state: CB_COLOR0_* setup, big-endian GRPH/CB component
  order, shader-side blending (the CB blender is bypassed for Porter-Duff —
  D3 finding; `VkPipelineColorBlendState` beyond what shaders express is
  out of scope until the CB-blend RE question resolves).

## First milestone — golden captures, no hardware

`testdata/golden_pm4/` holds dword-dumps of the D1–D4 self-test PM4 streams
(see its README for the capture procedure). Reproduce each byte-for-byte
from equivalent Vulkan-level state through your emitter:

1. D1 solid fill  = 64×64 RT + solid-colour PS + fullscreen draw
2. D2a/b sample/blit = textured quad, point sampler
3. D4 scale       = bilinear sampler, src rect ≠ dst rect
4. D3 composite   = shader-side SrcOver

A byte-diff harness (host-side, plain C) is your unit test; it needs no
Amiga. After golden parity: QEMU replay via Agent A's seam, then X5000
slots **booked through the coordinator only** (Agent C owns the machine).

## References (read-only)

- `GCNgfx/src/gfx/gcn_gfx.c` + `gcn_gfx_test.c` — the register recipes.
- `GCNgfx/bench-results/d0..d4_*.md` — ground truth + poison lists +
  debug playbook. The D0 write-up's byte-order rule (SW-swap dwords LE,
  BUF_SWAP=0) governs everything you emit.
- Mesa RADV's `radv_pipeline.c`/`si_cmd_buffer.c` (upstream, not vendored)
  for structure inspiration — but the D-series recipes outrank Mesa
  whenever they disagree, because they are verified on THIS platform.

## Do not touch

`../src` (Agent A), `../compiler` (Agent B), `../CONTRACTS.md`
(coordinator), anything in `GCNgfx/` or `P96_Replacement/`. Blob-ABI or
payload-contract gaps → stop and report.
