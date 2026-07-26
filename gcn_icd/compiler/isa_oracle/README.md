# GCN per-generation ISA oracle

Differential-assembly harness that measures which parts of GCN instruction
encoding change between generations. Its results are written up in
`../GCN_LEVEL_DELTAS.md`; this directory is how you re-derive or extend them.

**Why it exists.** CONTRACTS §4 commits `gcn_vk` to every GCN generation, so the
encoder must be parameterised by gfx level rather than hard-coded to gfx803. The
question "what actually differs?" is answerable by *measurement* instead of
document archaeology: assemble the same source across `-mcpu` targets and diff
the bytes. That is cheaper and far more trustworthy than reading ISA PDFs, and
it matches this project's house rule of checking the instrument.

**What it is NOT.** An assembler cannot tell you what the hardware does with a
field — only what LLVM believes. Every result is toolchain-verified and
hardware-unverified. See `../GCN_LEVEL_DELTAS.md` §"Evidence grade".

## Requirements

Docker with the `silkeh/clang` image (stock LLVM with the AMDGPU target) — the
same image GCNgfx uses to assemble its shaders. Verified with LLVM 21.1.8.

## Running

Everything runs inside the container. On Windows/MSYS use `MSYS_NO_PATHCONV=1`
and Windows-format paths for the mount:

```sh
D="C:/msys64/home/rich_/Projects/VulkanOS4/gcn_icd/compiler/isa_oracle"
MSYS_NO_PATHCONV=1 docker run --rm -v "$D:/s" -w /s silkeh/clang:latest sh /s/oracle.sh
```

Takes ~6 minutes (~2900 clang invocations). It prints, in order: the clang
version; the 22 GCN mach flags plus the bogus-target control; the shader
equivalence classes; the three pairwise delta lists and intra-generation splits;
the SMEM offset-units table; and four instrument controls.

### The real-shader matrix needs GCNgfx's shaders

`oracle.sh` step 1 assembles `/s/src/*.s`. Those sources live in **GCNgfx**
(`src/gfx/shaders/gfx8/*.s`) and are deliberately **not** duplicated here — one
copy, in the repo that owns them. Stage them first:

```sh
mkdir -p "$D/src" && cp /c/msys64/home/rich_/Projects/GCNgfx/src/gfx/shaders/gfx8/*.s "$D/src/"
```

Without `src/`, step 1 reports nothing and steps 2+ still work — the
instruction probes are self-generating and carry most of the findings.

### The single highest-value check

The SMEM offset-units result is the one finding that would silently emit wrong
descriptor addresses on gfx6/gfx7. Keep this as a regression test:

```sh
MSYS_NO_PATHCONV=1 docker run --rm -v "$D:/s" -w /s silkeh/clang:latest sh -c '
for t in gfx600 gfx700 gfx803 gfx900; do
  printf "%-8s " $t
  llc -mtriple=amdgcn-- -mcpu=$t /s/units.ll -o - \
    | sed -n "/^off128:/,/End function/p" | sed -n "s/^\t\(s_load_dword s0.*\)/\1/p"
done'
# expect: gfx600/gfx700 -> 0x20 (DWORDS) ; gfx803/gfx900 -> 0x80 (BYTES)
```

## Files

| file | role |
|---|---|
| `oracle.sh` | single entry point; runs everything and prints the report |
| `matrix.sh` | shader × target differential assembly → TSV (`$1` = source dir) |
| `probematrix.sh` | probe × target differential assembly → TSV |
| `genprobes.py` | 120 one-instruction probes (round 1) |
| `genprobes2.py` | 68 one-instruction probes (round 2) |
| `reduce.py` | collapse targets into per-generation classes; flag intra-gen splits |
| `deltas.py` | pairwise gfx6→7, gfx7→8, gfx8→9 delta lists |
| `dwdiff.py` | dword-by-dword blob diff — needed because LLVM cannot disassemble gfx6/gfx7 |
| `disasm.sh` | disassembly helper (gfx801+ only) |
| `units.ll`, `units2.ll` | SMEM offset-units codegen probes (the C-CRITICAL finding) |
| `oracle_run.txt` | **recorded baseline output, 2026-07-26** — diff against this |
| `matrix.tsv` | recorded shader × target results |

`oracle_run.txt` is the golden record, in the spirit of `pm4/testdata/golden_pm4/`:
if a future LLVM changes an encoding, the diff against this file is the finding.

## Instrument controls (do not remove them)

The harness checks itself, because three of its plausible failure modes are
silent:

1. **A bogus `-mcpu` is silently accepted.** `gfx999` exits 0 and emits bytes
   identical to gfx600 with `EF_AMDGPU_MACH = 0x0`. Every target is therefore
   cross-checked against a nonzero mach flag.
2. **An empty `.text` compares equal to anything.** Every run asserts non-empty
   output; a zero-byte extraction is reported as `EMPTYTEXT`, never as a match.
3. **A degenerate comparison would report everything identical.** A
   one-instruction source edit is confirmed to register as DIFFERENT on both
   gfx600 and gfx803.

## Extending it

Add probes to `genprobes2.py` — one instruction per probe, so a failure names
exactly one thing. Prefer probes a real VS/PS needs over exhaustive ISA
coverage; the point is to parameterise an encoder, not to document AMD's ISA.
Not yet probed: LDS/GDS beyond `ds_read_b32`/`ds_write_b32`, atomics, 64-bit
float, `s_cbranch` ranges, trap/message space, MIMG opcode numbering beyond the
sampled set.
