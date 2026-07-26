# SPIR-V → GCN3 compiler (Agent B lane)

This directory is the runtime shader compiler for `gcn_vk.library`.
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
- **Front-end: WRITE YOUR OWN, in C. Decided 2026-07-26 after investigation.**
  Do NOT try to reuse the software ICD's front end, and do NOT take SPIRV-Cross
  as a dependency. What you may lift from `software_icd/include/swvk_spirv.h` is
  genuinely useful and genuinely small: the **opcode enum** (`:33-178`), the
  **37-entry GLSL.std.450 table** (`:183-219`), the decoration/builtin/
  storage-class constants (`:222-244`), and `spv_TypeComponentCount` /
  `spv_StructMemberOffset` (both non-static, pure type-table walks).
  Why not more, in one line each:
  - `SpvCompiledInstr` is not IR. It stores an interpreter *handler pointer*, no
    opcode field and no result-type id, with `componentCount`/`extra`
    overloaded to mean different things per opcode, ids truncated to `uint16`,
    and a hard cap of 1024 instructions. (The information is not *destroyed* —
    `module->code` is retained and four handlers already re-read it — but you
    should walk that lossless source directly, not this projection.)
  - `spv_ParseModule` is a **reference sketch, not a liftable component**: it
    silently drops ids ≥ 512, clamps a 12-member UBO to 8 *and writes the
    clamped count back*, truncates 64-bit constants, discards `OpTypeImage`'s
    `Dim`/`Arrayed`/`MS`/`Format` (which is exactly what `IMAGE_SAMPLE` needs),
    and records no layout decorations at all — no `ArrayStride`,
    `MatrixStride`, `RowMajor`. Every one of those is a silent wrong answer,
    and your contract is to **reject, never miscompile**.
  - SPIRV-Cross exists at `external/spirv-cross` and `ogles2_icd` already
    cross-compiles it, but `external/` is gitignored (it holds the proprietary
    Enhancer SDK), so a fresh clone could not build this lane. It is still
    valuable as a **host-side oracle** — diff your parser's understanding of a
    module against it — just not as a build dependency.
  Target SSA form, then simple linear-scan allocation onto SGPRs/VGPRs.
- **Endianness — do NOT copy `swvk_pipeline.c:62-96` verbatim.** That code
  matches the magic word's *byte pattern* with the host hard-wired big-endian.
  Correct on AmigaOS, and **exactly inverted on a little-endian host** — it
  would byte-swap already-correct words and then reject the module. This lane is
  host-buildable by contract, so it runs on an LE dev machine. Use the
  host-agnostic form: compare the **word**, not the bytes —
  `if (w[0] == SPV_MAGIC) no swap; else if (bswap32(w[0]) == SPV_MAGIC) swap;
  else reject`.
- **Target**: gfx803 (GFX8/Polaris) first, but the emitter is **table-driven by
  gfx level from the first commit** — CONTRACTS §4. Read
  **`GCN_LEVEL_DELTAS.md`** before writing any encoder: it has the measured
  per-generation deltas and §7 lists the minimum contents of the level table.
  Three headlines: there are **three** encoding classes not four (gfx6 and gfx7
  are byte-identical); **all image/MIMG encoding is identical across gfx6→gfx9**,
  which is excellent news for the textured-quad ladder above; and the SMEM
  immediate offset is in **DWORDS on gfx6/7 but BYTES on gfx8+**, which will
  emit wrong descriptor addresses with no diagnostic if you hard-code it.

## Correctness oracles (no hardware needed — never touch an Amiga target)

1. **LLVM diff**: assemble equivalent `.s` via the existing flow
   (`GCNgfx/src/gfx/shaders/gfx8/assemble.sh`, docker silkeh/clang,
   `clang -x assembler -target amdgcn-- -mcpu=gfx803`) and byte-diff your
   encoder's output for the same instruction sequences.
   **`isa_oracle/` already automates this across every GCN target** — use it
   rather than rebuilding it, and diff against its recorded baseline
   `isa_oracle/oracle_run.txt`. Two assembler traps it documents will bite you
   if you trust clang blindly: a bogus `-mcpu` is silently accepted (and yields
   gfx600 encodings), and MUBUF `offset:` overflow is silently truncated, so
   **range-check immediates in your encoder** rather than relying on the
   assembler to reject them.
2. **Known-good blobs**: `GCNgfx/src/gfx/gcn_shaders.c` + the `.s` sources
   in `GCNgfx/src/gfx/shaders/gfx8/` are HW-verified reference outputs —
   e.g. your compiled "output solid colour" PS should be functionally
   interchangeable with `ps_solid`.
3. Unit tests run on the host (plain gcc/clang, no docker) — keep the
   compiler free of AmigaOS and IGpu includes so this stays true. Endian
   discipline: the code you emit is LE dwords; your tests must pass on both
   LE and BE hosts.

## HW findings you must honour (all readback-verified on the RX 560)

- **16 user SGPRs per stage** — a **GFX8** cap, not universal. Take it from the
  level table, never a `#define` (CONTRACTS §1/§4). Descriptor loads beyond it
  go indirect: emit `GCN_USGPR_DTAB_VA` + `s_load_dwordx8/x4` from the table.
- The **constant-bus rule is NOT a gfx8 quirk**: at most one unique SGPR per
  vector op is rejected identically on *every* generation (measured). The
  mul-then-add workaround in GCNgfx's `ps_blit_rect.s` / `ps_comp2_rect.s` is
  required everywhere — do not treat it as a gfx8 concession you can drop.
- **Big-endian component order**: `IMAGE_SAMPLE` returns (X,Y,Z,W) =
  (A,R,G,B) — fold into swizzle lowering.
- PS screen-position input via SPI_PS_INPUT_ENA POS_X/POS_Y (the D2b
  recipe); parameter interpolation via LDS is NOT yet available — pipelines
  needing real varyings interpolation are out of subset until the contract
  gains it (coordinate via the coordinator, do not improvise).
- RSRC1 granularities: VGPRS in units of 4, SGPRS in units of 8;
  VS VGPR_COMP_CNT per input regs actually used.

## Do not touch

Anything outside `gcn_icd/compiler/`. `GCNgfx/` and `software_icd/` are
read-only references. Gaps in the blob ABI → stop and report to the
coordinator; do not extend `GcnShaderBlob` yourself.
