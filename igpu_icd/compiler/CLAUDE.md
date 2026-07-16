# SPIR-V → GCN3 compiler (Agent B lane)

This directory is the runtime shader compiler for `igpu_vk.library`.
**Read `../CONTRACTS.md` §1 first — the `GcnShaderBlob` ABI is your output
contract and you do not change it unilaterally.**

## Your job (Agent B)

A pure-function, host-testable library:

```
SPIR-V words + entry point + stage  →  GcnShaderBlob (gfx803 code + metadata)
```

- **Subset-first.** Milestone order = exactly the opcodes needed by
  VulkanOS4 examples, in this order: 01_enumerate (no shaders — blob
  plumbing only), 02_clear, 08_triangle, 09_rotating (push constants),
  12_wireframe_cube (matrix math), 11_textured (IMAGE_SAMPLE), 20_torus.
  Grow coverage example by example; reject (clean error, never miscompile)
  anything outside the implemented subset so the ICD can fall back to CPU
  shading per-pipeline.
- **Front-end**: reference `software_icd/src/swvk_spirv.c` for parsing
  (module layout, 210+ opcodes) — parse only; do NOT import its interpreter
  execution model. Target SSA form, then a simple linear-scan style
  allocation onto SGPRs/VGPRs.
- **Target**: gfx803 (GFX8/Polaris) first; keep the emitter table-driven so
  gfx6 is a second target, not a rewrite.

## Correctness oracles (no hardware needed — never touch an Amiga target)

1. **LLVM diff**: assemble equivalent `.s` via the existing flow
   (`GCNgfx/src/gfx/shaders/assemble.sh`, docker silkeh/clang,
   `clang -x assembler -target amdgcn-- -mcpu=gfx803`) and byte-diff your
   encoder's output for the same instruction sequences.
2. **Known-good blobs**: `GCNgfx/src/gfx/gcn_shaders.c` + the `.s` sources
   in `GCNgfx/src/gfx/shaders/gfx8/` are HW-verified reference outputs —
   e.g. your compiled "output solid colour" PS should be functionally
   interchangeable with `ps_solid`.
3. Unit tests run on the host (plain gcc/clang, no docker) — keep the
   compiler free of AmigaOS and IGpu includes so this stays true. Endian
   discipline: the code you emit is LE dwords; your tests must pass on both
   LE and BE hosts.

## HW findings you must honour (all readback-verified on the RX 560)

- **16 user SGPRs per stage** (GFX8 cap). Descriptor loads beyond that go
  indirect: emit `GCN_USGPR_DTAB_VA` + `s_load_dwordx8/x4` from the table.
- **Big-endian component order**: `IMAGE_SAMPLE` returns (X,Y,Z,W) =
  (A,R,G,B) — fold into swizzle lowering.
- PS screen-position input via SPI_PS_INPUT_ENA POS_X/POS_Y (the D2b
  recipe); parameter interpolation via LDS is NOT yet available — pipelines
  needing real varyings interpolation are out of subset until the contract
  gains it (coordinate via the coordinator, do not improvise).
- RSRC1 granularities: VGPRS in units of 4, SGPRS in units of 8;
  VS VGPR_COMP_CNT per input regs actually used.

## Do not touch

Anything outside `igpu_icd/compiler/`. `GCNgfx/` and `software_icd/` are
read-only references. Gaps in the blob ABI → stop and report to the
coordinator; do not extend `GcnShaderBlob` yourself.
