# gcn_vk contracts — single source of truth

These are the interfaces between the parallel work lanes (ICD core, compiler,
PM4 emission, GCNgfx backend). **Changes go ONLY through the coordinator.**
If your lane discovers a contract is wrong or incomplete: STOP, write up the
gap (what you needed, why the contract can't express it), and report. Do not
edit this file or work around it by reaching into another lane's directory.

Naming: this library was called `igpu_vk` / `igpu_icd/` until 2026-07-26.
Dated documents in GCNgfx and P96_Replacement still use the old path; it is the
same component. (`igpu` was read from the `IGpu` interface, but everywhere else
in the industry it means *integrated* GPU — which is the opposite of the
discrete cards this drives.) The P96 seam validator `tests/igpu_vk` KEEPS its
name: it validates the IGpu API surface, not this ICD.

Status: **v0.3 (2026-07-26)**. Three of the four items scoped for v0.3 have
landed:

1. **§2's draw-less rationale RETRACTED** — the "armed CE deadlocks" mechanism
   is false (GCNgfx `docs/GFX_HANDOFF_25Jul2026.md` §1) and the defect it
   guarded is cleared by a 10-boot soak.
2. **§2 now spells a barrier-only submit as the ratified FENCE-ONLY SUBMIT**,
   with an interim note because gcngfx does not accept it yet.
3. **§4 all-GCN support and the feature level we may report** — binds every
   lane from first commit; read it before choosing where a gfx8 constant lives.
   §1's constants are now explicitly level-scoped.

**v0.4 sync→async render submission — THE BLOCKING DECISION IS IN (2026-07-26).**
This section used to defer v0.4 pending "a decision in another repo": whether
gpu.library adopts per-engine fence contexts (`(backend, context, seq)`, the
`dma_fence` shape) or keeps one seq space per backend. That decision was itself
waiting on async submit — **a circular deferral, with each side blocked on the
other.** It is broken, in favour of the status quo:

> **gpu.library KEEPS ONE SEQUENCE SPACE PER BACKEND.** Fence identity stays
> `(backendId, seq)`. Per-engine contexts were investigated and **deferred**;
> the ruling is published as a negative decision precisely so this repo is not
> left waiting. See `P96_Replacement/docs/API_DESIGN.md` "One sequence space per
> backend" and `docs/LINUX_ANALOGY_VERDICTS.md` §1.

So GCNgfx `docs/ASYNC_SUBMIT_PROPOSAL.md` §8's min-over-busy-engines is the
**permanent** shape, not a fallback — and it is already implemented and soaked
(`fc1c84d`). v0.4 can now be written once.

What the ICD must know about it, none of which is new API:

- The backend's retirement watermark is contractually *"truthful retired-up-to
  across all engines"*. `GpuFence` stays an opaque `int64`; nothing about
  engines is visible above IGpu, so **the ICD needs no change** for this.
- **Over-reporting corrupts silently** — a watermark ahead of the truth advances
  a timeline early, so `vkWaitSemaphores` / `vkWaitForFences` return while the
  GPU is still writing. There is no error path. If a backend ever looks like it
  is retiring early, that is the shape of the bug.
- Reopen triggers are listed in the P96 section above; the nearest is this
  driver gaining a second, independent retirement producer — which is exactly
  what v0.4's ISR-side retirement would be. If v0.4 adds one, re-read that
  section before designing the fence handling.

Lanes may assume synchronous submit until v0.4 says otherwise.

(Old §4, shared logistics, became §5 on 2026-07-26; nothing referenced it by
number.)

§2's transport is IMPLEMENTED and deployed:
gcngfx executes `GPU_QUEUE_RENDER` payloads on the CP gfx ring
(`gcn_gfx_submit_payload`, backend EOP fence, synchronous v1) and the
device-address query is live (ratified surface below). Golden captures for
Lane D are committed under `pm4/testdata/golden_pm4/`. Field layouts are
grounded in the HW-verified D0–D4 register recipes but have not yet carried
a COMPILED shader end-to-end — expect a v0.3 after the first Lane B+D
integration. **Lane A HW caveat LIFTED (2026-07-19)**: exclusive-fullscreen WSI
(`GPU_AcquireDisplayA`) now works on real hardware — the "DisplayHook
kills the first SDMA fence" finding was refuted by an interleaved re-test
(7/7 boots pass both arms) and gcngfx registers its hook by default;
validator stage 3 ran ACQUIRE → 30/30 flip-rotated presents → RELEASE on
the X5000 (GCNgfx `bench-results/displayhook_exonerated_x5000_19Jul2026.md`).
Submit-path HW caveats CLEARED (2026-07-19, GCNgfx
`bench-results/drawless_submit_and_timeline_fix_x5000_19Jul2026.md`,
`igpu_vk_validate` 15/15 ALL PASS): draw-less render submits are now a
no-op that retires on the fence (see §2), and timeline signals advance
correctly on gcngfx's synchronous submit.

---

## 1. Shader blob ABI (compiler → ICD core / PM4 emission)

The compiler is a pure function: SPIR-V module + entry point + stage in,
one `GcnShaderBlob` out. No I/O, no OS calls, host-buildable.

```c
#define GCN_BLOB_ABI_VERSION  1

typedef enum { GCN_STAGE_VS = 0, GCN_STAGE_PS = 1 } GcnStage;

/* What each user SGPR group is loaded with (the ICD resolves these against
 * descriptor sets / push constants at draw time and emits SET_SH_REG). */
typedef enum {
    GCN_USGPR_TDESC8,      /* 8-dword T# image descriptor (set/binding below) */
    GCN_USGPR_SDESC4,      /* 4-dword S# sampler descriptor */
    GCN_USGPR_VDESC4,      /* 4-dword V# buffer descriptor (vertex/storage)   */
    GCN_USGPR_PUSHCONST,   /* N dwords of push-constant data (offset below)   */
    GCN_USGPR_DTAB_VA,     /* 2 dwords: GPU VA of an indirect descriptor table
                              (the 16-user-SGPR/stage cap forces this for
                              anything beyond trivial binding layouts)         */
} GcnUserSgprKind;

typedef struct {
    uint8_t  first_sgpr;   /* s[first_sgpr] .. s[first_sgpr+count-1] */
    uint8_t  count;        /* dwords */
    uint8_t  kind;         /* GcnUserSgprKind */
    uint8_t  set;          /* descriptor set (or 0)      */
    uint16_t binding;      /* binding index (or push-constant byte offset) */
} GcnUserSgprSlot;

typedef struct {
    uint32_t abi_version;      /* GCN_BLOB_ABI_VERSION */
    uint32_t stage;            /* GcnStage */
    uint32_t gfx_level;        /* 8 = GFX8/gfx803 (first target), 6 = GFX6 */
    uint32_t code_size;        /* bytes, multiple of 4 */
    const void *code;          /* GCN machine code, stored LITTLE-ENDIAN
                                  (same convention as gcn_shaders.c blobs);
                                  ICD places it in VRAM 256-byte aligned and
                                  programs SPI_SHADER_PGM_LO/HI = VA >> 8 */
    uint32_t rsrc1;            /* full SPI_SHADER_PGM_RSRC1_{VS,PS} value:
                                  VGPRS = (max_vgpr/4), SGPRS = (max_sgpr/8),
                                  VS: VGPR_COMP_CNT per input regs used */
    uint32_t rsrc2;            /* full RSRC2 value incl. USER_SGPR count */
    uint32_t num_user_sgprs;   /* redundant with rsrc2, for validation */
    /* PS only (0 for VS): */
    uint32_t spi_ps_input_ena; /* also written to SPI_PS_INPUT_ADDR */
    uint32_t num_interp;       /* SPI_PS_INPUT_CNTL_n entries required */
    /* VS only: */
    uint32_t num_params;       /* SPI_VS_OUT_CONFIG / PARAM_GEN exports */
    uint32_t user_sgpr_count;  /* entries in user_sgprs[] */
    GcnUserSgprSlot user_sgprs[16];
} GcnShaderBlob;
```

Hard constraints the compiler must honour (HW-verified findings). **Every
constant here was measured on gfx803 and is therefore LEVEL-SCOPED** — see §4;
none may be applied to another GCN generation without re-verification.
- **16 user SGPRs per stage max** — a **GFX8** cap (D3 finding), not a
  universal one. Beyond that, emit `GCN_USGPR_DTAB_VA` + `s_load_dwordx8/x4`
  from the table. The limit itself must come from the per-level table, not a
  `#define`.
- **Big-endian sampled component order**: `IMAGE_SAMPLE` returns
  (X,Y,Z,W) = (A,R,G,B) on this platform (D3 finding). The compiler's
  swizzle lowering must account for it.
- PS reading its own screen position uses SPI_PS_INPUT_ENA POS_X/POS_Y
  (POS_FIXED at bit 10 in INPUT_CNTL_0 per the D2b recipe) — LDS texcoord
  interpolation is not yet part of the contract.
- Code bytes little-endian; the host is big-endian; never memcpy dwords
  without going through the gcn_endian helpers on the ICD side.

## 2. Submit payload (ICD → gcngfx via GPU_SubmitA, opaque)

- The payload is a **PM4 dword stream for the GFX CP ring**, stored
  **little-endian** (the D0 contract: SW-swap dwords, ring BUF_SWAP=0).
  The backend copies/chains it as an IB; it does not parse or patch it.
- The backend owns the **once-per-ring-init full preamble**
  (CONTEXT_CONTROL / SET_BASE(CE) / CLEAR_STATE / golden registers /
  tiling tables — D0). The ICD payload contains ONLY per-submit state:
  SET_CONTEXT_REG / SET_SH_REG / SET_UCONFIG_REG groups, descriptor
  writes, and DRAW_* / DISPATCH_* packets.
- **Fencing is the backend's job**: gcngfx appends the
  EVENT_WRITE_EOP + CACHE_FLUSH_AND_INV_TS done-fence (D1 finding) and
  maps it to the returned GpuFence. The ICD never emits EOP packets.
- **A barrier-only or fence-only `vkQueueSubmit` is spelled as a FENCE-ONLY
  SUBMIT — not as an empty payload.** `GPU_SubmitA(queue, NULL, 0, tags)`
  means "no work, just this backend's next fence"; it is ratified in the core
  (P96 `dd3a6fe`) and is the portable form. The ICD must NOT express this by
  handing the backend a payload it has to recognise as work-free: an API with
  deliberately opaque payloads should not require the other side to introspect
  them. (An earlier draft justified this as "the same reason amdgpu never parses
  indirect buffers". **That absolute is false** — checked against
  `refs/linux-4.14`: amdgpu's GFX/compute/SDMA rings genuinely do not parse, but
  six UVD/VCE rings bind a real `parse_cs` that walks the stream and rejects an
  IB lacking a required packet type, and Linux's `radeon` driver parses every
  packet on SI/CIK's VM path. The argument here stands on its own terms — an
  explicit verb beats introspection — not on an appeal to amdgpu.)
  The core also rejects `payload == NULL` with `length != 0` as
  `GPUERR_BADARGS` on every backend's behalf.
- **INTERIM (2026-07-26), and it WILL bite Lane A on hardware — but only on ONE
  queue.** gcngfx rejects the ratified form on `GPU_QUEUE_RENDER` only:
  `gcn_gfx_submit_payload` bails on `payload_le == NULL` (and on `ndw == 0`)
  *before* the draw-less classifier runs, and `gcn_Submit` returns
  **`GPUERR_BADARGS`** (it returned `GPUERR_TIMEOUT` before GCNgfx `fc1c84d`).
  **Every other queue there already conforms** — the SDMA path has implemented
  exactly the core's rule since 2026-07-13 — so transfer and present submits
  need no workaround at all. vgfx and null accept it everywhere.
  Until the render queue is fixed, the ICD needs a per-backend fallback on that
  queue: a draw-less PM4 payload. **Do not rely on the old explanation of why
  that works** — "gcngfx skips such payloads off the gfx ring" is only true when
  the engine is idle; when it is busy the draw-less path deliberately falls back
  to a real ring submit. Both arms return a valid seq, so the workaround
  functions, but anyone debugging it against the old sentence would be chasing a
  mechanism that is not running. Treat it as a workaround with an expiry date,
  isolated behind one helper, not as the contract.
- **Enforcement, decided in P96 2026-07-26.** "Every backend MUST accept it" was
  always the rule; what was open is where non-compliance is CAUGHT. Answer:
  `gpu_conform`, gated behind the trigger "gcngfx accepts NULL/0 on RENDER,
  hardware-verified". Registration cannot test it (it is deliberately call-free,
  and `GPU_SubmitA` returns `GPUERR_BUSY` while a backend's server is starting).
  So this stays an ICD-visible gap until that lands, not a build break.
- **Retracted rationale, recorded because it was load-bearing for weeks.**
  This section previously justified the draw-less skip as "an armed CE
  deadlocks on a draw-less stream — CE_WAITING_ON_DE, HW-proven". **That
  mechanism is false.** `CP_STAT` after the preamble is `0x00000000` (the CE
  is not armed; our own "= CE armed" log text was a hardcoded string, not a
  decode), `CP_STAT=0x94008200` is a BUSY reading and does not encode the CE
  wait at all, and bit 12 `CE_WAITING_ON_DE_COUNTER` has been observed clear
  while bit 13 `…_UNDERFLOW` was set. See GCNgfx
  `docs/GFX_HANDOFF_25Jul2026.md` §1. The underflow that did occur traced to
  a zero-filled ring plus unpadded commits and to a boot scratch probe, all
  fixed by other means; a 10-boot cold soak
  (`bench-results/drawless_gate_soak_x5000_26Jul2026.md`) shows draw-less
  payloads execute and retire harmlessly. Retiring gcngfx's gate is expected
  and would make the interim above unnecessary.
- Corollary that survives regardless: never rely on a side-effecting
  non-render packet (WRITE_DATA/COPY_DATA/EVENT) in a draw-less render
  payload — route copies and events through the transfer queue.
- All GPU addresses inside the stream (RT surfaces, shader PGM_LO,
  descriptor tables, vertex/index V#s) are **GPU VAs of IGpu buffers**,
  obtained via the **RATIFIED v6 surface** (accepted + implemented
  2026-07-17): `GPU_GetAttrsA` with `GPUATTR_Buffer` (GPU_TAGBASE+17,
  INPUT: the `GpuBuffer *` itself) + `GPUATTR_DeviceAddress`
  (GPU_TAGBASE+18, `uint64 *` out). Owning backend resolves from
  `buf->BackendId`. Gate on `GPUCAP_DEVICEADDRESS` (0x00004000) — a
  capless backend (vgfx) answers 0, and the ICD then enumerates no HW
  device there. Backend side: `BufferAddress` op at
  `GPU_BACKEND_API_VERSION 6`; gcngfx implements it (VRAM + GART).
  Design rationale: `P96_Replacement/docs/DEVICE_ADDRESS_PROPOSAL.md`.
- Queue: `GPU_QUEUE_RENDER`. Compute later via the same contract on
  DISPATCH packets.

## 3. IGpu v1 (ICD ↔ gpu.library) — already verified

The governing documents are `P96_Replacement/docs/VULKAN.md` and
`docs/VULKAN_V1_VERIFICATION.md` (verdict: v1 SUFFICIENT). The division of
labour is RADV's, and it is binding on all lanes:
- **ICD owns**: sub-allocation (`VkDeviceMemory` = one `GPU_CreateBufferA`
  chunk; `VkBuffer`/`VkImage` = (chunk, offset) views), image tiling and
  `vkGetImageMemoryRequirements` math, binary semaphores (WSI-internal).
- **IGpu owns**: memory domains + map contract, `GpuFence` + timelines,
  swapchain (`GPU_AcquireDisplayA` / `GPU_NextDisplayBufferA` /
  `GPU_PresentA`), queues, `GPU_Transfer`.
- `GPU_CreateImageA` is used ONLY for scanout / cross-component shared
  images; ICD-internal textures and render targets are plain buffers with
  ICD-computed layouts.
- Memory-type convention: WRITECOMBINE ⇒ HOST_COHERENT (write-only),
  CACHED ⇒ non-coherent (needs vkFlushMappedMemoryRanges).

## 4. Multi-generation GCN support and reported feature level

**Requirement (admitted 2026-07-26, v0.3 item).** `gcn_vk` targets **all GCN
parts**, not just the gfx803 first target. At device enumeration it must
establish which ASIC it is on and report a Vulkan `apiVersion`, limits, features
and extension list it can actually honour **on that ASIC**. No lane may emit a
command it cannot lower for the running gfx level.

**The constraint is OURS, not the hardware's.** RADV runs Vulkan 1.3 on GFX6, so
"what is this card capable of" answers 1.3 for every GCN part and tells us
nothing. What we may advertise is

```
apiVersion = min( what compiler + PM4 emission implement for this gfx_level,
                  what the backend implements for this ASIC,
                  what OUR OWN HEADERS AND LOADER CAN EXPRESS )    <- RATIFIED 2026-07-26
```

Advertise low and raise it as lanes land. **Never advertise a version or feature
bit the emitter cannot honour for the running level** — an application acts on
those. A pipeline dropping to the CPU-shade fallback is a performance outcome
and is fine; a false capability is not.

**The third term, ratified 2026-07-26.** `include/vulkan/vulkan_core.h` is a
hand-trimmed 2578-line subset carrying 146 `PFN_vk` declarations against a real
1.3's ~400, and it contains **none** of `VkPhysicalDeviceVulkan11Features` /
`12Features` / `13Features` / `VkPhysicalDeviceSubgroupProperties`. A 1.1+
device must answer `vkGetPhysicalDeviceFeatures2` for those structs; there is no
struct and no sType to match. So the header alone forecloses 1.1, independently
of any lane. A version claim must clear all three bounds, not two.

### 4a. RATIFIED 2026-07-26 — report `VK_API_VERSION_1_0` on every gfx level

The gfx level does not enter into it. Hardware blockers are **empty**: RADV
reports 1.3 on GFX6/GFX7, and the only reason it caps them below 1.4 is
`indexTypeUint8`, a 1.4 requirement. Every 1.3-mandatory feature is `true` on
gfx6 in RADV. The blockers are our unimplemented lanes plus the header bound
above.

**Raise by extension, not by version.** Nearly every promoted feature ships on a
1.0 driver given `VK_KHR_get_physical_device_properties2` —
`VK_KHR_{timeline_semaphore, synchronization2, dynamic_rendering,
buffer_device_address, multiview, create_renderpass2, …}` carry no core-version
dependency. Implement timeline semaphores ⇒ advertise
`VK_KHR_timeline_semaphore` on a 1.0 device; do **not** claim 1.2. Only
`shader_subgroup_extended_types`, `maintenance4` and `spirv_1_4` hard-require
1.1.

Two facts that make the conservative claim more strongly indicated, not less:

- **There is no external oracle and never will be.** dEQP-VK cannot be ported
  (`docs/LINUX_ANALOGY.md` §4 — `#error "Big-endian not supported"` inside
  `mapVkFormat()`), so `dEQP-VK.api.info.device_mandatory_features`, the test
  that mechanically enforces the mandatory-feature rules against whatever
  version you advertise, will never run here. **This contract is the only thing
  between an inflated claim and a shipped lie.**
- **The in-repo precedent is to over-claim, and it stops here.**
  `software_vk.library` reports 1.3 while reporting `robustBufferAccess = FALSE`
  (mandatory at 1.0) and supporting four formats; `ogles2_vk.library` reports
  1.3 with zero feature bits true. Both are non-conformant even as 1.0
  implementations. `gcn_vk` reporting 1.0 makes it the only honest device in the
  stack — that is the intended outcome, not a regression.

It costs nothing: all 24 examples set `VkApplicationInfo.apiVersion` to 1.3, and
**none** compares `props.apiVersion` against anything.

### 4b. RATIFIED 2026-07-26 — never advertise on the strength of the CPU fallback

Advertise strictly what the PM4 + compiler path can honour for the running
level. The fallback is a **reliability** mechanism for pipelines already inside
the advertised set — never a capability-widening one.

Reasons, in order of force:

1. **The fallback is the software ICD's interpreter**, which advertises every
   feature bit false, `maxImageDimension2D = 4096`, one sample count and four
   formats. It is a *narrower* set of a different shape, not a superset. Any
   feature the PM4 path cannot do, it cannot do either — so the interesting
   version of this trade-off is not currently reachable.
2. **A feature bit is a promise with no escape hatch.**
   `vkCreateGraphicsPipelines` has no legal return meaning "I cannot do this",
   so advertising commits us to succeeding at *every* pipeline using it,
   forever.
3. **Mixed-path composition is an unproven correctness question**, not merely a
   speed one: a per-pipeline fallback puts GPU draws and CPU draws into the same
   render target, requiring it to be CPU-mappable and correctly de-tiled and
   re-tiled, decided at pipeline-creation time and possibly after the image was
   created tiled.
4. **No conformance suite will ever check an emulation here** (see 4a).

Signal cost through the three channels Vulkan actually has:
`deviceType = DISCRETE_GPU` only while PM4 is the normal path (report `CPU` if
everything routes to the interpreter, which is lavapipe's whole honesty story);
`deviceName` carrying the state Mesa-style; one debug line per fallback naming
the pipeline and the compiler's refusal reason; plus a tunable whose `off`
setting refuses the fallback outright so CI can answer "did this actually run on
the GPU". Default: fallback **on but loud**.

**The bar for ever revisiting this**, so it is a decision and not a drift: (i)
the feature is shader-behaviour, not fixed-function or format state; (ii) a test
exercises it *through* the fallback; (iii) mixed GPU/CPU output into one render
target is proven byte-correct.

### 4c. RATIFIED 2026-07-26 — the ICD supplies image limits the backend leaves at 0

`0` from a declaration tag means **undeclared**, never "none" — and for
*capabilities* the rule is to under-report and enumerate nothing
(`GPUCAP_DEVICEADDRESS`, `GfxLevel`). **Image limits are the one exception**,
because §3 already gives image tiling, layout and
`vkGetImageMemoryRequirements` maths to the ICD: the limit is the ICD's fact to
know, and the backend's declaration is a cross-check, not the source.

Three tiers:

1. Backend declares non-zero → use it, and clamp our own value **down** to it,
   never up.
2. Backend declares 0 → use the ICD's own per-level value **and log that we
   did**. (gcngfx deliberately declares no `GPUTAG_MaxTextureDim`: its image
   path cannot yet enforce a limit, and declaring one would advertise a
   guarantee nothing upholds.)
3. Neither knows → report the Vulkan **spec floor**, never 0. A zero limit is
   not conservative: `ogles2_icd/src/ogles2vk_main.c:302-312` records VMA
   computing `min(blockSize, heapSize) % bufferImageGranularity` and dividing by
   zero, so `vmaCreateImage` failed before `vkAllocateMemory` was ever called.

### 4d. The loader does NOT select on `apiVersion` — accepted, not fixed

This section previously asked that someone confirm it. **Confirmed, negative.**
`loader/src/loader_icd.c:408-444` sorts by prefs priority and then "software
goes last" via `strstr(libraryPath, "software")` — `gcn_vk.library` does not
match that string, so it sorts **ahead** of `software_vk`.
`loader/src/loader_dispatch.c:66-90` then takes the first ICD whose
`vkCreateInstance` succeeds, sets `activeICD`, and overwrites `VulkanIFace`
wholesale. `apiVersion` appears nowhere in selection, and physical devices are
**not** aggregated across ICDs.

**Ratified consequence: applications must query per device.** An honest 1.0
claim from `gcn_vk` therefore gets no automatic fallback to `software_vk`, and
that is accepted. The honesty argument stands on its own: an application that
queries and adapts is served correctly, and one that assumes fails fast rather
than rendering corrupt output.

**NOT ratified, and deliberately left open:** making the loader `apiVersion`-
aware. It changes a shipped component that both existing ICDs depend on, and its
selection heuristic is entangled with the VulkanPrefs priority mechanism. That
is its own decision with its own testing, not a rider on this one. Until it is
taken, no lane may assume the loader will route around a low claim.

**Identification — LANDED 2026-07-26, the stopgap is retired.** The backend
declares its generation at registration and the ICD reads it back. **Two tags,
not one**, because a bare level does not name an ISA: GFX8 spans
gfx800/801/802/803, and §1's blob takes the sub-target as a compiler *input*.

| Registration tag (backend) | Read back as (ICD) | Meaning |
|---|---|---|
| `GPUTAG_GfxLevel` | `GPUATTR_OutGfxLevel` | AMD: 6/7/8/9 |
| `GPUTAG_GfxRevision` | `GPUATTR_OutGfxRevision` | ISA sub-target: 803 = Polaris, 601 = Pitcairn |

Both are `uint32`, selected by `GPUATTR_BackendIndex`, and **vendor-scoped** —
meaningless without the vendor, which the ICD already has from
`GPUATTR_BackendPCIDevice`. There is no cross-vendor scale. Absent = 0 =
undeclared, and the ICD then enumerates no HW device there (the same honest
under-report rule as `GPUCAP_DEVICEADDRESS`). gcngfx declares both (803/Polaris,
601/Pitcairn, from the one ASIC table in `gcn_pci.c`); vgfx declares 0/0
explicitly, since virtio-gpu is not a GCN part.

**Delete any ICD-side PCI-ID table.** That stopgap is withdrawn: gcngfx
registers only for the device ids it supports, so a client-side copy is a mirror
that goes stale the moment a card is added to the driver — silently, answering
wrongly rather than not at all.

**What these do NOT answer, so nobody plans around them.** Surface tiling and
the addrlib inputs behind `vkGetImageMemoryRequirements` — `GB_ADDR_CONFIG`
(computed live from per-*board* memory config), the per-*chip* tile/macrotile
tables, and the SE/RB geometry read from AtomBIOS at boot. None of that is
derivable from a generation number **or** from a PCI id, so §"image layout"
still owns it, and when it is needed it wants a backend-owned struct behind an
op rather than more scalar tags.

**Caveat, stated rather than discovered later:** these cannot be exercised
distinguishingly yet. gcngfx is Polaris-only in gmc/gfx/dce, so it reports a
constant 8/803 on all reachable hardware — behaviourally identical to the ICD
hardcoding it. The value arrives with the second generation; the test that
proves it is a Pitcairn reporting 6/601, which needs GFX6 IP modules that do not
exist. Treat this as plumbing verified as plumbing.

Consequences per lane:

- **Lane B**: `gfx_level` in §1's blob is an **input**, not an annotation. The
  compiler must **refuse** a level it does not implement — cleanly, so the ICD
  falls back to CPU shading for that pipeline — and never silently emit gfx8
  encodings for another generation. The per-pipeline fallback is also the
  multi-generation safety net.
- **Lane D**: register offsets, T#/S#/V# descriptor layouts and tiling all move
  between generations. The emitter must be **table-driven by gfx level from the
  start**; do not inline gfx8 constants at call sites. `testdata/golden_pm4/` is
  gfx803-only — other levels need their own captures from real cards, and byte
  parity is claimed per level, never across.

**MEASURED 2026-07-26** (`compiler/GCN_LEVEL_DELTAS.md`, harness in
`compiler/isa_oracle/`, ~2900 differential assemblies; toolchain-verified and
**hardware-unverified** — the fleet has only gfx803):

- There are **THREE encoding levels, not four**: gfx6 and gfx7 are
  byte-identical for all 13 reference shaders and ~190 instruction probes, so
  they share one table; the level flag between them gates only FLAT addressing
  and the SMEM literal-offset escape. gfx8 and gfx9 are then separate.
- **All image/MIMG encoding, and the descriptor operand form (T# = 8 SGPRs,
  S# = 4 SGPRs), are identical across gfx6→gfx9** — including every modifier
  bit position. The most portable area of the ISA is the one the textured-quad
  subset needs most.
- **gfx90a (CDNA2) is EXCLUDED from this contract.** It rejects every `exp`
  form and requires 64-bit-aligned VGPR tuples, so it cannot run a graphics
  pipeline. Being a gfx9 target is not sufficient grounds to enumerate a device.
- The level table must therefore be keyed on more than generation: image `d16`
  is gfx810-only *within* gfx8, and `v_fmac_f32` is gfx906/908-only within
  gfx9. §7 of `GCN_LEVEL_DELTAS.md` lists the minimum table contents.
- **Lane A**: one **per-gfx-level capability table** drives
  `VkPhysicalDeviceProperties.apiVersion`, limits, features and the extension
  list, consulted at enumeration. No ad-hoc per-ASIC conditionals scattered
  through the ICD.
- **§1's "16 user SGPRs per stage" is a GFX8 fact** (D3 finding), not a
  universal one. Every such HW constant in this document is implicitly
  level-scoped and must be re-verified before it is applied to another
  generation.

Note for the loader: the software ICD reports `VK_API_VERSION_1_3` per physical
device, so a GCN part on which `gcn_vk` reports less is a legitimate reason for
the loader to prefer another ICD for an application that demands more. Confirm
the loader actually selects on `apiVersion` before relying on that.

## 5. Shared logistics

- **Hardware**: the X5000 is a single shared resource; Agent C owns it by
  default, Agent D books slots through the coordinator. QEMU targets
  (vgfx) are freely parallel. Follow the TEST:/Kicklayout safety rules in
  `GCNgfx/docs/DESIGN.md` without exception.
- **Repos**: no lane commits outside its declared directories. Cross-repo
  needs (e.g. an IGpu tag) are coordinator work.
- **Verification culture**: every milestone gets a readback-verified test
  and a short write-up in the owning repo's `bench-results/` — the D-series
  format is the model.
