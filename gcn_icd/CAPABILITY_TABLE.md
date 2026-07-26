# Per-gfx-level capability table — specification for Lane A

What the ICD reports at enumeration, and where each number comes from.
CONTRACTS §4 mandates this table; this is its content.

**Status.** Sections 1, 5 and 6 are findings — read them as evidence.
**§2, §3 and §4 were RATIFIED into `CONTRACTS.md` §4a–4d on 2026-07-26** and are
now binding; the text here is the reasoning behind them, and the contract wins
on any discrepancy. Identification (`GPUTAG_GfxLevel`/`GfxRevision`) is settled
in CONTRACTS §4 and not repeated here.

Ratified: report `VK_API_VERSION_1_0` on every gfx level and raise by extension
(§4a); never advertise on CPU-fallback strength (§4b); the ICD supplies image
limits the backend leaves at 0 (§4c); applications must query per device,
because the loader does not select on `apiVersion` (§4d). Making the loader
`apiVersion`-aware was deliberately NOT ratified — it changes a shipped
component both other ICDs depend on and is its own decision.

---

## 1. The per-level table is SMALL

The useful headline: RADV varies **six** limit fields across GFX6→GFX9, and only
two of them matter to us. Sort every field into three kinds.

### (a) Hardware-determined — genuinely varies by level

| Field | gfx6 | gfx7 | gfx8 | gfx9 |
|---|---|---|---|---|
| `maxComputeSharedMemorySize` | 32768 | 65536 | 65536 | 65536 |
| `shaderFloat16`, `storageInputOutput16` | false | false | false | **true** |
| `filterMinmaxImageComponentMapping` | false | false | false | **true** |
| compute queue family exists | **no** | yes | yes | yes |

RADV's `lds_size_per_workgroup = gfx_level >= GFX7 ? 64K : 32K`; 16-bit packed
math is gfx9+; RADV disables the compute family on GFX6 ("may hang").

Four more vary by **device**, not level, so the table key must be
`(gfx_level, gfx_revision)` with a per-device escape — which is exactly the pair
CONTRACTS §4 now provides:

- `samplerFilterMinmax` — false on Tahiti/Verde only
- `textureCompressionETC2` — a four-chip whitelist (Stoney, Vega10, Raven,
  Raven2), *not* a level gate
- `sparse*` — `family >= CHIP_POLARIS10`, which cuts **through** gfx8
- `timestampPeriod` — per-chip crystal (40.0 on Polaris11, 37.037 on most)

### (b) Our-implementation-determined — 0/false until a lane lands it

**This is where almost everything lives.** The hardware can do it; we cannot yet.
All of `VkPhysicalDeviceFeatures` starts `VK_FALSE` except `robustBufferAccess`
(see §6). Also: all `maxTessellation*`/`maxGeometry*`/`maxClipDistances` = 0
(the blob ABI has only VS and PS, CONTRACTS §1); all sample counts =
`VK_SAMPLE_COUNT_1_BIT` (hardware does 1/2/4/8, no MSAA in the verified
recipes); `timestampPeriod = 0.0`; descriptor limits bounded by Lane A's table
design and the per-level user-SGPR cap.

**The single largest gap is `VkFormatProperties`.** The verified recipes support
one data format — `8_8_8_8` in four component orders, LINEAR only. Vulkan's
mandatory format tables are **version-independent**: they bind at 1.0.

### (c) Chosen — ours to pick, spec floors them

Allocation counts, ranges, granularities, queue family shape, IDs. Three rules,
each earned from a mistake already in this tree:

1. **Never leave a chosen limit at 0.** `ogles2_icd/src/ogles2vk_main.c:302-312`
   records VMA computing `min(blockSize, heapSize) % bufferImageGranularity` and
   dividing by zero — `vmaCreateImage` failed before `vkAllocateMemory` was ever
   called. A spec minimum is always safer than 0.
2. **`pipelineCacheUUID` must encode `(gfx_level, gfx_revision, blob ABI
   version, driver version)`** or a cache built on Polaris is replayed on
   Pitcairn. Neither existing ICD does this — `swvk_instance.c:32` is all zeros.
3. `deviceType`/`deviceName` are Vulkan's only out-of-band performance channel.
   See §3.

### Limits that do NOT vary — no table entry needed

`maxImageDimension1D/2D/Cube = 16384`, `3D = 2048`, `maxImageArrayLayers = 2048`,
`maxFramebufferWidth/Height = 16384`, `maxColorAttachments = 8`,
`maxVertexInputAttributes/Bindings = 32`, `maxViewports = 16`,
**`subgroupSize = 64`** (wave64 is universal on GCN; wave32 arrives at GFX10)
with the full `subgroupSupportedOperations` set *including on gfx6*, buffer
offset alignments = 4, `nonCoherentAtomSize = 64`, and `geometryShader`,
`tessellationShader`, `textureCompressionBC`, `shaderFloat64`, `shaderInt64`,
`multiview` — all true on every GCN generation.

### ⚠ But our own descriptor fields cap two of them below RADV's numbers

Measured in-tree on gfx803, HW-verified via the D-series readback oracles:

- T# WIDTH/HEIGHT are 14 bits each ⇒ 16384, agreeing with RADV. **But T# PITCH
  is 13 bits** (`GCNgfx/src/gfx/gcn_gfx.c:753`) ⇒ a **linear** image is capped
  at **8192** texels wide. Tiled images should escape this (tiling index
  replaces pitch) but that is UNVERIFIED. **Until Lane A implements tiled
  layouts, report `maxImageDimension2D = 8192`, not 16384.**
- V# STRIDE is 14 bits ⇒ `maxVertexInputBindingStride` ≤ 16383. RADV's 2048 is
  a choice, not a hardware limit.

## 2. PROPOSED: report `VK_API_VERSION_1_0` on every gfx level

**The gfx level does not enter into this**, which is the surprise.

**Hardware blockers are empty.** RADV reports **1.3 on GFX6/GFX7** and 1.4 on
GFX8+, and the sole reason for that split is stated in the commit that made it:
GFX6-7 cannot do `indexTypeUint8`, which is a **1.4** requirement. Every
1.3-mandatory feature is `true` on gfx6 in RADV. So "what can this card do"
answers 1.3 for every GCN part and tells us nothing — exactly as CONTRACTS §4
says.

**Our lanes are the whole story**, and there is a **third bound CONTRACTS §4's
formula is missing**:

> `apiVersion = min(compiler+PM4, backend, **what our headers and loader can
> express**)`

`include/vulkan/vulkan_core.h` is a hand-trimmed 2578-line subset with 146
`PFN_vk` declarations against a real 1.3's ~400, and it contains **none** of
`VkPhysicalDeviceVulkan11Features`/`12Features`/`13Features` or
`VkPhysicalDeviceSubgroupProperties`. A 1.1+ device must answer
`vkGetPhysicalDeviceFeatures2` for those structs; there is no struct and no
sType to match. The header alone forecloses 1.1.

What each version would force on us: **1.0** — `robustBufferAccess = TRUE`, the
mandatory format tables, and at least one *complete* compressed family. **1.1** —
~50 promoted entry points, `multiview`, SPIR-V 1.3. **1.2** — seven
unconditional `TRUE` features incl. `timelineSemaphore`, SPIR-V 1.5. **1.3** —
sixteen unconditional `TRUE` incl. `dynamicRendering`, `synchronization2`,
`bufferDeviceAddress`, plus all of `VK_EXT_extended_dynamic_state`, SPIR-V 1.6.

**Raise by extension, not by version.** Almost every promoted feature ships on a
1.0 driver given `VK_KHR_get_physical_device_properties2` —
`VK_KHR_{timeline_semaphore, synchronization2, dynamic_rendering,
buffer_device_address, multiview, create_renderpass2, …}` all have no
core-version dependency. Only `shader_subgroup_extended_types`, `maintenance4`
and `spirv_1_4` hard-require 1.1.

**Two things make the conservative claim more strongly indicated, not less.**
First, there is no external oracle and never will be — dEQP-VK cannot be ported
(`docs/LINUX_ANALOGY.md` §4), so
`dEQP-VK.api.info.device_mandatory_features`, the test that mechanically
enforces the mandatory-feature rules against whatever version you advertise,
will never run here. **This document is the only thing between an inflated
version claim and a shipped lie.** Second, the in-repo precedent is to
over-claim and should be broken: `software_vk` reports 1.3 while reporting
`robustBufferAccess = VK_FALSE` (mandatory at 1.0) and four formats;
`ogles2_vk` reports 1.3 with zero feature bits true. Both are non-conformant
even as 1.0 implementations. Reporting 1.0 makes `gcn_vk` the only honest device
in the stack.

**It costs nothing.** All 24 examples set `VkApplicationInfo.apiVersion` to 1.3
but **none** compares `props.apiVersion` against anything.

### ⚠ CONTRACTS §4 asked a question; here is the answer

§4 says *"Confirm the loader actually selects on `apiVersion`."* **It does not.**
`loader/src/loader_icd.c:408-444` sorts by prefs priority, then "software goes
last" via `strstr(libraryPath, "software")`. `gcn_vk.library` does not contain
"software", so it sorts **ahead** of `software_vk`.
`loader/src/loader_dispatch.c:66-90` then takes the first ICD whose
`vkCreateInstance` succeeds, sets `activeICD`, and overwrites `VulkanIFace`
wholesale. `apiVersion` appears nowhere in selection, and physical devices are
**not** aggregated across ICDs.

Consequence: an honest low claim gives an application **no automatic fallback**
to the software ICD. Either the loader gains apiVersion-aware selection (a
loader change — Lane A's brief says stop and report) or we accept that apps must
query per-device. The honesty argument stands either way — an app that queries
is served correctly, and one that assumes fails fast rather than corrupting —
but this should be decided knowingly.

## 3. PROPOSED: do NOT advertise anything on the strength of the CPU fallback

Advertise strictly what the PM4 + compiler path can honour for the running
level. The fallback is a **reliability** mechanism for pipelines inside the
already-advertised set, never a capability-widening one.

**In this codebase the trade-off does not even exist yet.** The fallback is the
software ICD's interpreter, and that ICD advertises *every* feature bit false,
`maxImageDimension2D = 4096`, one sample count, four formats, no geometry or
tessellation. It is not a superset of the hardware path — it is a *narrower* set
of a different shape. Any feature the PM4 path cannot do, it cannot do either.

**Feature bits are a promise with no escape hatch.** `vkCreateGraphicsPipelines`
has no legal return meaning "I cannot do this" — advertising a feature commits
you to succeeding at *every* pipeline using it, forever.

**Mixed-path composition is a correctness risk, not just a speed one.** A
per-pipeline fallback means a single command buffer can contain GPU draws and
CPU draws into the same render target — requiring that target to be CPU-mappable
and correctly de-tiled/re-tiled, with the decision forced at pipeline-creation
time, possibly after the image was created tiled. Advertising on that basis
would be advertising something not known to be correct.

**What the comparable implementations do.** MoltenVK defines a third category —
"no practical, or *reasonably performant*, mechanism" — and puts those in a
documented known-limitations list, i.e. **not advertised**. Lavapipe advertises
broadly but is genuinely conformant, and signals cost through
`VK_PHYSICAL_DEVICE_TYPE_CPU` and its device name, not a feature bit. RADV is
*not* a precedent for flag-gated advertisement: `RADV_PERFTEST`/`RADV_DEBUG`
toggle optimisations and never change what is claimed; RADV's answer to "we
don't want to do this on old hardware" is to **not advertise**. And Khronos
considered adding an emulated-vs-native query (Vulkan-Docs #519) and **closed it
without one** — the absence is deliberate.

**Build this instead:** `deviceType = DISCRETE_GPU` only while PM4 is the normal
path (report `CPU` if everything routes to the interpreter); `deviceName`
carries the state Mesa-style; one `DebugPrintF` per fallback naming the pipeline
and the compiler's refusal reason; and a `RADV_DEBUG`-style tunable whose `off`
setting refuses the fallback outright, so CI and benchmarks can answer "did this
actually run on the GPU". Default: fallback **on but loud**.

If the fallback ever *does* become the sole implementation of a feature, the bar
for advertising it is: (i) shader-behaviour feature, not fixed-function or
format state; (ii) a test exercises it *through the fallback*; (iii) mixed
GPU/CPU output into one target is proven byte-correct.

## 4. Facts the backend does not declare

`MaxTextureDim` reads 0 from gcngfx **by deliberate decision**, recorded at its
registration site: GFX8's real limit is 16384, but its image path does not yet
enforce or test any limit, so declaring one would advertise a guarantee nothing
upholds. P96's rule is normative: **absent is not zero** — 0 means *not
declared*, never "the backend has none".

Three-tier rule, already the in-repo pattern
(`ogles2_icd/src/ogles2vk_main.c:288-350` sets a conservative constant, queries,
and overrides only if non-zero):

1. **Declared non-zero** → use it, and clamp your own value **down** to it,
   never up.
2. **Declared 0** → substitute the ICD's own per-level value and log that you
   did. Legitimate for image limits *specifically* because CONTRACTS §3 gives
   image tiling, layout and `vkGetImageMemoryRequirements` maths to the ICD —
   so the limit is the ICD's fact to know and the backend's declaration is a
   cross-check, not the source. **This needs ratifying**: it is the one place
   where "0 = undeclared ⇒ under-report" is answered by the ICD supplying a
   number instead.
3. **Neither knows** → report the Vulkan spec floor, never 0 (see §1(c) rule 1).

For **capabilities** the rule inverts: undeclared ⇒ enumerate nothing, per
`GPUCAP_DEVICEADDRESS` and `GfxLevel`. A missing *limit* can be answered from
the ICD's own knowledge; a missing *capability* cannot.

## 5. ⚠ `QueueMask` is structurally useless — do not derive queue families from it

`P96_Replacement/src/lib/gpu_api.c:466-469` hardcodes
`(1<<PRESENT)|(1<<RENDER)|(1<<COMPUTE)` for **every** backend regardless of what
it registered. Report one graphics+transfer family and grow only on tested
evidence. Note RADV disables the compute family entirely on GFX6.

## 6. Two hazards worth carrying into Lane A

**Gate on capability, never on level.** gcngfx *binds* the two Pitcairn PCI ids
and will report `GfxLevel = 6`, but nothing behind it works: gfx ring init is
`if (family != POLARIS) return FALSE` (`GCNgfx/src/gfx/gfx_v8.c:1247`), and GMC,
SDMA and DCE6 are the same or explicit SEAM_TODOs. So a gfx6 board answers 6
while being undriveable. Enumerate on `GPUCAP_DEVICEADDRESS` plus a successful
render submit — not on the level number.

**A live cross-lane hazard for the eventual gfx6 port.** RADV sets
`has_clear_state = gfx_level >= GFX7` with the comment *"The mere presence of
CLEAR_STATE in the IB causes random GPU hangs on GFX6"* — and CONTRACTS §2 puts
CLEAR_STATE in the **backend-owned preamble**. Whoever ports gfx6 needs this
before they start.

**`robustBufferAccess` is achievable now**, which matters because it is the one
bit Vulkan 1.0 requires unconditionally: GCN's V# `NUM_RECORDS` bounds-checks
buffer fetches in hardware, and this project has HW-proven it — an out-of-range
vertex fetch returned 0 rather than faulting.

## 7. Open items before Lane A codes this

1. **Ratify §2** (1.0 on every level, raised by extension) and the third term in
   §4's `min()`.
2. **Ratify §3** (no advertising on fallback strength) and the bar for ever
   changing that.
3. **Ratify §4 tier 2** — the ICD supplying image limits when the backend
   declares 0.
4. **Decide the loader question** (apiVersion-aware selection, or documented
   query-per-device).
5. **T#/S#/V# field layouts per level are UNVERIFIED.** `GCN_LEVEL_DELTAS.md`
   proves *instruction* encoding and the descriptor *operand form* identical
   gfx6→gfx9 — it does **not** prove the bit layout inside the descriptor, and
   GFX9 is understood to have changed the T# base-address width. Lane D's first
   non-gfx8 task. The reported *limit* is settled independently.
6. **Is the fallback per-pipeline or per-command-buffer, and is mixed-path
   output into one render target sound?** Blocks §3's implementation and the
   tiling decision. Both briefs use both phrasings.
7. **Which compressed family, and does a decoder exist?** 1.0 needs one
   *complete* family; BC is the only candidate (native on all GCN). Nothing
   in-tree decodes or samples BC today.
8. **The mandatory format tables are the real 1.0 gate.** Scope the
   format → (`DATA_FORMAT`, `NUM_FORMAT`, `DST_SEL`, `CB_FORMAT`, `COMP_SWAP`)
   mapping and decide whether to ship a documented, MoltenVK-style *declared*
   non-compliance in the interim. Recommendation: yes, declared and tracked —
   an undeclared gap is the thing to avoid.

## Testing this before hardware exists

The table is pure data in → `VkPhysicalDeviceProperties` out, so a **host-side
unit test over the table itself** needs no Amiga and no backend. That matters
because vgfx declares no `GPUCAP_DEVICEADDRESS`, so per CONTRACTS §2 the ICD
enumerates no hardware device on QEMU — meaning this table is only ever
consulted on gcngfx and is otherwise untestable. The host test is the only
pre-hardware verification available; write it first.
