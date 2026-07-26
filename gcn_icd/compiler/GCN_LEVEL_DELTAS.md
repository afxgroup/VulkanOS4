# GCN per-generation encoding deltas — what the encoder must parameterise

**Measured 2026-07-26** with the oracle in `isa_oracle/` (LLVM 21.1.8 via the
`silkeh/clang` image, ~2900 assembly runs). This is the input CONTRACTS §4 asks
for: which parts of GCN encoding are level-dependent, so the encoder takes them
from a table instead of hard-coding gfx8.

**Evidence grade — read this before trusting any row.** Everything here is
**toolchain-verified, hardware-unverified**. It is what LLVM believes about the
ISA, established by assembling and diffing bytes, not by executing them. The
fleet has exactly one GCN part (gfx803, the X5000's RX 560), so no gfx6/gfx7/gfx9
claim below can currently be checked against silicon at all — and the gfx803
column is the one place where the existing golden PM4 captures already provide
independent hardware confirmation. Treat rows marked MEASURED as strong
evidence and rows marked INFERRED as leads.

## The headline: THREE encoding levels, not four

| class | targets | relationship |
|---|---|---|
| **gfx6+gfx7** | gfx600/601/602, gfx700–705 | **byte-identical to each other** for all 13 project shaders and ~190 instruction probes |
| **gfx8** | gfx801/802/803/805/810 | differs from gfx6/7 in *every one* of the 13 shaders |
| **gfx9** | gfx900/902/904/906/908/909/90c | byte-identical to gfx8 for 10 of 13 shaders |

gfx6 and gfx7 can **share one encoding table**. The level flag needs only to
gate two things between them: FLAT addressing (gfx7+) and the SMEM 32-bit
literal offset escape (gfx7+).

**gfx90a (CDNA2) must be excluded from a graphics ICD.** Every `exp` form is
rejected (`instruction not supported on this GPU`) and it requires 64-bit-aligned
VGPR tuples. It is a real target with a real mach flag (0x33F), so "it is in the
gfx9 list" is not grounds to accept it. gfx908 *does* accept `exp`.

---

## 1. Do this one first — it silently corrupts shaders

**The SMEM immediate offset is in DWORDS on gfx6/gfx7 and BYTES on gfx8+.**
(MEASURED, through LLVM's code generator, so the *units* are pinned and not just
the field.) Same IR, `getelementptr i32, ptr addrspace(4) %p, i64 32` = byte 128:

| byte offset in IR | gfx600 | gfx700 | gfx803 | gfx900 |
|---|---|---|---|---|
| 128 | `0x20` | `0x20` | `0x80` | `0x80` |
| 1020 | `0xff` | `0xff` | `0x3fc` | `0x3fc` |
| 1024 | *SGPR fallback* | `0x100` | `0x400` | `0x400` |
| 4096 | *SGPR fallback* | `0x400` | `0x1000` | `0x1000` |

**The project's own sources are live ammunition.** GCNgfx's `ps_comp2.s` and
friends encode a descriptor table as
`s_buffer_load_dwordx8 s[16:23], s[0:3], 0x00 / 0x20 / 0x30 / 0x50`. Re-emitted
for gfx6/gfx7 with those same literals they would read byte offsets
0 / 0x80 / 0xC0 / 0x140 — **wrong descriptors, no diagnostic, no crash**.

Same area, also per-level: offset **field width** and escape form — gfx6 = 8-bit
(`0x100` rejected), gfx7 = 8-bit plus a 32-bit-literal escape (literal *also in
dwords*), gfx8+ = 20-bit. The table needs
`(offset_units, offset_width, has_literal_escape)`.

## 2. gfx7 → gfx8: the major break

| # | Requirement | Evidence | Grade |
|---|---|---|---|
| C1 | **SMEM instruction size: 4 bytes (SMRD) on gfx6/7, 8 bytes on gfx8+.** Affects instruction-size and all code-offset accounting. | `s_load_dword s8,s[0:1],0x0`: `c0040100` → `c0020200 00000000`. Same for x2/x4/x8/x16 and every `s_buffer_load_*`. | MEASURED |
| C2 | **EXP prefix is a per-level constant**; everything else in EXP is shared. | `exp mrt0 v0,v1,v2,v3 done vm`: `f800180f 03020100` → `c400180f 03020100` — only bits [31:26] move. Target/en/done/compr/vm verified bit-identical (mrt0=0, mrt7=7, mrtz=8, null=9, pos0=12, param0=32, param31=63). | MEASURED |
| C3 | **Per-level VOP3 opcode table AND per-level CLAMP bit.** | `v_mad_f32`: `d2820000 040e0501` → `d1c10000 040e0501` (dword1 identical). `clamp` = dword0 **bit 11** on gfx6/7 vs **bit 15** on gfx8+. abs (bit 8), neg (dword1 bit 29), omod (dword1 [28:27]) identical. | MEASURED |
| C3b | The VOP3 op field is [25:17] (9 bits) on gfx6/7 and [25:16] (10 bits) on gfx8+. Supporting: gfx6/7 never set dword0 bit 16 across every probe; gfx8 does. | — | **INFERRED** |
| C4 | **Per-level opcode tables for VOP1/VOP2/VOPC/SOP1/SOP2/DS.** Renumbering is *partial*, so this is per-instruction data, not a blanket offset. | Changed: VOP2 `v_mul_f32` `10`→`0a`, `v_add_f32` `06`→`02`, `v_sub_f32` `08`→`04`, `v_mac_f32` `3e`→`2c`, `v_and_b32` `36`→`26`, `v_lshlrev_b32` `34`→`24`, `v_min/max_f32`; VOP1 `v_rcp/rsq/sqrt/log/exp/fract/trunc/floor`; DS `ds_read_b32` `d8d8`→`d86c`. **Unchanged**: `v_mov_b32`, `v_cvt_f16_f32`, `v_cvt_f32_u32`, `v_cvt_u32_f32`, `v_readfirstlane_b32`, `s_add_u32`, `s_branch`, `s_nop`, `s_barrier`, `s_endpgm`, `s_sendmsg`, `s_waitcnt`. | MEASURED |
| C5 | **MUBUF: opcode partially renumbered, and the SLC bit relocates.** | `buffer_load_dword` `e0302000`→`e0502000`; `dwordx4` `e0382000`→`e05c2000`. But `buffer_store_dword` and `buffer_load_format_xyzw` are identical on all gens. **`slc` moves** dword1 bit 22 → dword0 bit 17. `glc` (dword0 bit 14) and `tfe` (dword1 bit 23) are stable on all gens. | MEASURED |
| C6 | **ADDR64 buffer addressing is gfx6/gfx7-only** — must be lowered differently on gfx8+. | `buffer_load_dword v1, v[2:3], s[0:3], 0 addr64` = `e0308000 80000102`; gfx8/9 → `invalid operand for instruction`. | MEASURED |
| C7 | **MTBUF opcode field width differs; dfmt/nfmt do NOT.** | Sweeping dfmt×nfmt: dfmt = [22:19], nfmt = [25:23] on both gfx600 and gfx803. Delta localises to op: `3<<16` (gfx6/7) vs `3<<15` (gfx8+) ⇒ field [18:16] → [18:15]. | MEASURED |
| C8 | **`v_cvt_pkrtz_f16_f32` / `v_cvt_pknorm_i16_f32` change instruction CLASS and SIZE** — the encoder picks VOP2 vs VOP3 by level. | `5e000501` (VOP2, 4 B) → `d2960000 00020501` (VOP3, 8 B). **This alone explains the corpus size deltas**: ps_sample_fp16 40→48, ps_comp_sw 96→104. | MEASURED |
| C9 | **`v_interp_*` prefix is per-level.** `ps_vtx` depends on this. | `v_interp_p1_f32 v2, v0, attr0.x`: `c8080000` → `d4080000`. Same for p2 and `v_interp_mov_f32`. | MEASURED |
| C10 | **The inline-constant table is per-level.** | 1/2π is inline `0xf8` on gfx8+ (4 B) but needs a 32-bit literal on gfx6/7 (8 B). −1.0 and 4.0 are inline on all gens. | MEASURED |
| C11 | **SGPR file: s102/s103 exist on gfx6/7, NOT on gfx8/9.** The register allocator takes the cap from the table. | `s_mov_b32 s102, 0` OK on gfx600/700, rejected on gfx803/900. s104+ rejected everywhere; v255 max. | MEASURED |
| C12 | **gfx8+ only — never emit for gfx6/7**: SDWA, DPP, all `v_*_f16`, `s_load … glc`, `s_store_dword`, `s_memrealtime`, `s_set_gpr_idx_on`, image `d16`. | `v_add_f16` → `instruction not supported on this GPU` on gfx6/7. | MEASURED |

## 3. gfx8 → gfx9: a short list

| # | Requirement | Evidence | Grade |
|---|---|---|---|
| G1 | **`s_waitcnt` packing is per-level: vmcnt widens 4→6 bits on gfx9, as a SPLIT field at simm16[15:14]+[3:0].** A gfx8-shaped wait word is an *under-specified* wait on gfx9 — a correctness bug, not a size bug. | gfx8 max vmcnt=15 (`vmcnt(16)` rejected); gfx9 accepts 63. `s_waitcnt lgkmcnt(0)`: `bf8c007f` → `bf8cc07f`. `lgkmcnt` stays 4 bits on **all** gens. **Sole cause of the three gfx8≠gfx9 shaders.** | MEASURED |
| G2 | **VOP3 f16 opcodes renumbered.** | `v_mad_f16` `d1ea0000`→`d2030000`; `v_fma_f16` `d1ee0000`→`d2060000`. `v_mad_f32`/`v_fma_f32`/`v_med3_f32`/`v_cndmask_b32_e64` unchanged. | MEASURED |
| G3 | **gfx9-only, usable only at level ≥ gfx9**: `global_load/store_*`, `scratch_load_*`, the **FLAT `offset:` modifier** (rejected on gfx7 *and* gfx8), `v_pk_add_f16`/`v_pk_mul_f16`, `v_lshl_add_u32`, image `a16`/`d16`, and the SMEM combined imm+SGPR-soffset form. | as listed | MEASURED |
| G4 | **Removed on gfx9**: `v_movrels_b32` (works gfx6/7/8). | `7e008701` → `instruction not supported on this GPU` | MEASURED |
| G5 | EXP, MIMG, MUBUF, VOP1/VOP2/VOPC/SOP are **identical** gfx8↔gfx9 — no work. | all probes "1 distinct" | MEASURED |

## 4. Stable across gfx6→gfx9 — safe to hard-code

**MEASURED identical on all four generations:**

- **Every image/MIMG operation** — `image_sample`, `_l`, `_lz`, `_c`,
  `image_load`, `image_load_mip`, `image_store`, `image_get_resinfo` — *and*
  every modifier bit position: `unorm` 12, `glc` 13, `da` 14, `tfe` 16,
  `lwe` 17, `slc` 25, dmask [11:8]. **This is the most portable area of the ISA
  for a textured-quad workload**, which is exactly the subset ladder Lane B
  targets. Genuinely good news.
- **The descriptor operand form** — T# = 8 SGPRs, S# = 4 SGPRs — identical.
- `s_endpgm`, `s_nop`, `s_barrier`, `s_branch`, `s_cbranch_scc0`, `s_sendmsg`,
  `s_add_u32`, `v_mov_b32`, `v_readfirstlane_b32`, `v_cvt_f16_f32`,
  `v_cvt_f32_u32`, `v_cvt_u32_f32`.
- EXP target/en/done/compr/vm layout (only the prefix moves — C2).
- VOP3 abs/neg/omod bit positions; VOP2/VOP3 32-bit-literal operand support.
- **The 1-unique-SGPR-per-vector-op constant-bus rule is NOT a gfx8 quirk.**
  `v_mul_f32 v0, s1, s2` is rejected identically on **every** generation. The
  mul-then-add workaround documented in GCNgfx's `ps_blit_rect.s` and
  `ps_comp2_rect.s` is required everywhere, not a gfx8 concession.
- `v_mac_f32`/`v_mad_f32`/`v_fma_f32` exist on every generation. `v_fmac_f32`
  exists **only** on gfx906/908/90a.

## 5. Sub-level feature flags the table also needs

The table cannot be keyed on generation alone (MEASURED):

- **image `d16` within gfx8: gfx810 ONLY.** gfx801/802/803/805 reject it.
- **`v_fmac_f32` within gfx9: gfx906/gfx908 only.**
- **gfx90a: exclude from graphics entirely** (see above).

## 6. Two assembler traps to defend against

Both MEASURED, both silent:

1. **A bogus `-mcpu` is accepted.** `-mcpu=gfx999` exits 0, emits 28 bytes
   **byte-identical to gfx600**, with `EF_AMDGPU_MACH = 0x0`. A typo'd level
   name in a build script yields SI encodings with no warning. Always
   cross-check the mach flag.
2. **MUBUF `offset:` is 12 bits on every generation and LLVM silently truncates
   overflow.** `offset:4096` exits 0 and produces bytes identical to `offset:0`.
   **The encoder must range-check immediates itself** — do not rely on the
   assembler to reject them.

## 7. Minimum contents of the level table

```
smem       : offset_units {DWORDS|BYTES}, offset_width, has_literal_escape,
             instruction_size
exp        : prefix
vop3       : opcode_table, clamp_bit
vop1/2/c   : opcode_table        sop1/2 : opcode_table      ds : opcode_table
mubuf      : opcode_table, slc_bit_pos
mtbuf      : opcode_field_width
inline_consts : table
waitcnt    : field_map (vmcnt width + split position)
sgpr_max   : 101 (gfx8/9) | 103 (gfx6/7)
class_sel  : v_cvt_pk* -> VOP2 (gfx6/7) | VOP3 (gfx8+)
features   : flat, smem_literal, sdwa, dpp, f16, addr64, global_scratch,
             flat_offset, d16, fmac_f32
```

Image/MIMG and the descriptor operand form need no entries.

## 8. What could not be determined

1. **LLVM 21 cannot disassemble gfx6/gfx7 at all** (`disassembly not yet
   supported for subtarget`, including the `tahiti`/`bonaire`/`hawaii` aliases;
   gfx801 is the earliest that disassembles). Every gfx6/gfx7 claim rests on
   assembler output plus dword diffing, never a round-trip. C3b and C7's
   field-boundary attributions are the weakest results here.
2. **An assembler cannot say what the hardware does with a field.** The SMEM
   units result is LLVM's belief, strongly held and consistent, but not silicon.
3. **No gfx6/gfx7/gfx9 hardware exists in the fleet.** If any of those becomes
   testable, §1 is the first thing to re-verify.
4. Not probed: LDS/GDS beyond `ds_read_b32`/`ds_write_b32`, atomics, 64-bit
   float, `s_cbranch` offset ranges, trap/message space, MIMG opcode numbering
   beyond the sampled set, `r128`, tbuffer symbolic `format:`.

## Re-running

See `isa_oracle/README.md`. The single highest-value regression check is the
SMEM offset-units probe — it is the finding most likely to cause a silent
miscompile, and it is four lines.
