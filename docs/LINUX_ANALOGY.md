# Linux stack analogy — what VulkanOS4 owns

**Status: ANALYSIS + RECOMMENDATIONS, nothing ratified.** Written 2026-07-26.
Each item carries its Linux precedent and the local evidence that prompted it;
acting on one is this project's call, and the ones touching `gcn_icd/` are
coordinator work. Sibling documents split the same analysis by owner:
`P96_Replacement/docs/LINUX_ANALOGY.md` (DRM core + uAPI) and
`GCNgfx/docs/LINUX_ANALOGY.md` (the KMD).

## The mapping

| Component | Linux equivalent |
|---|---|
| **vulkan.library** | **vulkan-loader** — ICD discovery, ranking, device aggregation |
| **gcn_vk.library** | **RADV** |
| **software_vk.library** | **lavapipe** |
| **ogles2_vk.library** | **MoltenVK** — Vulkan on a foreign higher-level API (an Apple analogy; Linux has no equivalent) |
| gpu.library / IGpu | DRM core / libdrm uAPI (see its own doc) |
| GCNgfx backend | amdgpu (see its own doc) |

**This project is Mesa's half of the stack.** Everything below follows from
that.

---

## 1. Express a barrier-only submit as a verb, not as an empty payload

**Local evidence.** `gcn_icd/CONTRACTS.md` §2 currently tells the ICD to spell a
fence-only or barrier-only `vkQueueSubmit` as a **draw-less PM4 payload**, which
the backend recognises and skips. P96 has since ratified the explicit form:
`GPU_SubmitA(queue, NULL, 0, tags)` (`dd3a6fe`).

**Linux precedent — AMENDED 2026-07-26, the absolute form was wrong.** This
said "amdgpu does not parse indirect buffers; the kernel never recognises
payload content". Checked against `refs/linux-4.14`: true for GFX/compute/SDMA,
which only kmap an IB when a parser exists, but **false as an absolute** — six
UVD/VCE rings bind a real `parse_cs` that walks the stream, patches addresses
into it, and rejects an IB lacking a required packet type. Linux's `radeon`
driver also parses every packet on SI/CIK's VM path, so GCN-class hardware plus
a GPU VM did not make parsing unnecessary in Linux either. The argument survives
on its own merits — an explicit uAPI verb beats content introspection, and it is
what keeps the two sides' obligations separable — but not by appeal to authority.

**Suggestion.** CONTRACTS **v0.3** should make fence-only submit the sanctioned
spelling and retire the draw-less-payload contract. Note the ordering
constraint: gcngfx **rejects** the ratified form today, so the ICD needs either
the backend fix first or a documented interim per-backend no-op. This is already
one of the four v0.3 items.

## 2. Put a small IR between SPIR-V and GCN encodings — before the second gfx level

**Local evidence.** CONTRACTS §4 commits `gcn_vk` to **all** GCN generations,
and §1's blob carries a `gfx_level` field. Lane B is a subset compiler targeting
gfx803 first. Nothing yet forces the gfx level to be a *parameter* rather than a
set of constants scattered through the emitter.

**Linux precedent.** Mesa became tractable because of **NIR**: one shared IR,
per-target backends. ACO replaced LLVM for RADV only *after* that existed. Every
Mesa driver that grew ISA-specific code paths without an IR ended up rewritten.

**Suggestion.** A deliberately small IR — enough to carry the subset Lane B
implements — with GCN encoding as a backend keyed on `gfx_level`. The cost of
adding it later is a fork per generation; the cost now is modest because the
compiler has no code yet. Same argument for Lane D's register/descriptor
tables (§4 already mandates table-driven emission).

## 3. Per-gfx-level capability tables are the RADV shape — keep them literal

**Local evidence.** CONTRACTS §4 requires one per-level table driving
`apiVersion`, limits, features and extensions, consulted at enumeration.

**Linux precedent.** RADV does exactly this: `radv_physical_device` populated
from `radeon_info` supplied *by the kernel driver*, with per-generation
conditionals concentrated in table initialisation rather than sprinkled through
entry points.

**Suggestion.** Two refinements. First, the gfx level should come **from the
backend**, not be sniffed by the ICD — a `GPUTAG_GfxLevel` is owed by
gpu.library (its doc, item 3), and §4's `GPUATTR_BackendPCIDevice` stopgap is a
client re-deriving what the driver already knows. Second, the reported
`apiVersion` must be a *floor over our own implementation*, not the hardware's
theoretical capability: RADV runs Vulkan 1.3 on GFX6, so "what can this card
do" answers 1.3 for every GCN part and tells us nothing. §4 already states the
formula; the risk is that it gets treated as aspirational.

## 4. The test suites are Mesa-shaped; the missing piece is CTS

**Local evidence.** Across the three projects: `gpu_selftest` 241/241,
`igpu_vk_validate` 39/39, `w3d_suite` 16/16, gpu.chip compconform 32/32, plus
22 example programs and `examples/24_proc_addr` as an ABI regression test. That
is a real conformance culture and it is what has made aggressive refactoring
survivable at this scale.

**Linux precedent.** Mesa's leverage comes from **dEQP/VK-GL-CTS** — an
externally authored suite that finds what the authors did not think to test.
Piglit and crucible complement it; they do not replace it.

**INVESTIGATED 2026-07-26 — the verdict is: do NOT attempt a dEQP-VK port.**
This item originally recommended it as "the highest-leverage investment
available". That was wrong, and the reason is not cost — it is that **Khronos
has explicitly declared big-endian unsupported and enforced it with
preprocessor errors**:

- `vkImageUtil.cpp:3592-3608` — inside **`mapVkFormat()`**, the function that
  translates every `VkFormat` and on which essentially the whole suite depends:
  `#else` / `#error "Big-endian not supported"`. Cause is exactly the predicted
  class: `A8B8G8R8_*_PACK32` is a *packed* format shortcut to a *byte-order*
  `tcu` format, equivalent only on LE.
- `vkImageUtil.cpp:1156-1158` — same in `getCorePlanarFormatDescription()`.
- `vkPrograms.cpp:150-158` — `createProgramBinaryFromSpirV`, the single funnel
  for all shader creation, does `TCU_THROW(InternalError, "SPIR-V endianness
  translation not supported")` on a non-native-endianness binary. So on BE,
  every test that compiles or assembles a shader throws.

Both `#error`s have been in the tree since ~2016 and remain on `main`. Corroboration
that nobody has ever done this: 2 issues in project history matching "big
endian" (one OpenGL file), **0** matching `s390x`/`powerpc`/`ppc64`/`sparc`, and
a global code search for `DE_ENDIANNESS=DE_BIG_ENDIAN` returns **0** results —
no maintained BE fork exists to inherit.

**The trap that would have cost weeks.** `framework/delibs/cmake/Defs.cmake`
never consults `CMAKE_SYSTEM_PROCESSOR`; it infers CPU from pointer size alone,
so 32-bit PowerPC sets `DE_CPU_X86`. The endianness cascade then tests
`DE_CPU == DE_CPU_X86` *before* the `__BYTE_ORDER__` fallback, and unlike the
MIPS branch it has no sanity check. So the default build **compiles, declares
itself little-endian x86, bypasses both `#error`s and the `TCU_THROW`, and
silently generates wrong reference data** wherever packed formats appear. A
suite that appears to work and lies is the worst available outcome. The honest
build (`-DDE_ENDIANNESS=DE_BIG_ENDIAN`) does not compile.

**Recommended instead: Amber** (google/amber). It survives because it never
links `vkImageUtil.cpp` or `vkPrograms.cpp`: expectations are declared as typed
values in the script rather than composed by LE bit-packing, there is no
`#error` and no `TCU_THROW`, and the risk surface is ~4 MB of readable code
instead of 115 MB. **Caveat: Amber has no endianness handling either** — the
word appears once in the whole project, in a doc asserting little-endian scalar
layout — so treat its packed-format and image-dump paths as suspect from day
one. It is triageable; dEQP is not.

Also viable, and cheaper: use the CTS **case list as a specification** and write
tests against it, and use the software ICD as a same-machine differential
reference. Note the wider hazard this uncovered — **glslang and SPIRV-Tools have
open big-endian bugs too** (glslang #4145, #2797; SPIRV-Tools #5595; Debian
#1137720 shows Mesa FTBFS on ppc64 with `nepOs.LC` = byte-reversed `"OpenCL.s"`).
Those are build dependencies, not just test tools. The graphics suite that does
have real BE coverage is **piglit**, which Debian builds on s390x/powerpc/ppc64.

**Before any porting work at all**, run the 30-line experiment: confirm C++
exception unwinding works on real AmigaOS 4 hardware. Everything above is moot
if it does not.

## 5. Where the future API layers sit — the Gallium question

`docs/ROADMAP.md` defers naming and placement of Warp3D / Warp3D Nova /
OpenGL-on-Vulkan until `gcn_vk` is complete. The Linux analogy sharpens *why*
the deferral is right and what to watch for:

- **Zink only became the right answer once Vulkan drivers were universal and
  good.** GL-on-Vulkan on an immature ICD means debugging two layers at once.
  Build `gcn_vk` first and GL-over-Vulkan is nearly free.
- **IGpu is this stack's libdrm, not its Gallium.** Mesa's answer to "many APIs,
  one device" was a userspace device abstraction (`pipe_context`) with state
  trackers above it — not each API talking to the kernel. Warp3D-on-IGpu today
  is a state tracker talking raw ioctls: fine for one API, triplicated for
  three. If all three layers are wanted, the missing tier is a shared userspace
  layer above IGpu and below the APIs.
- A consequence for **this** project: if those layers land on Vulkan, `gcn_vk`
  becomes infrastructure for other implementations, not just a driver for
  applications. Pipeline-creation cost and cache behaviour then matter far more
  than they do for a hand-written Vulkan app, because a GL translation layer
  creates pipelines at a rate no application would.

## Not this project's items

- Fence-handle encoding, registration-time cap honesty, `GPUTAG_GfxLevel`,
  whether fence-only submit becomes mandatory —
  `P96_Replacement/docs/LINUX_ANALOGY.md`.
- The `payload_has_draw()` gate, per-engine fence contexts, generated register
  decoders, KMD scope — `GCNgfx/docs/LINUX_ANALOGY.md`.
