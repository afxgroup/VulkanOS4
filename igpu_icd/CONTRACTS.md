# igpu_vk contracts — single source of truth

These are the interfaces between the parallel work lanes (ICD core, compiler,
PM4 emission, GCNgfx backend). **Changes go ONLY through the coordinator.**
If your lane discovers a contract is wrong or incomplete: STOP, write up the
gap (what you needed, why the contract can't express it), and report. Do not
edit this file or work around it by reaching into another lane's directory.

Status: v0.2 (2026-07-17), plus one requirement admitted 2026-07-26: **§4,
all-GCN support and the feature level we may report**. It binds every lane from
first commit — read it before choosing where a gfx8 constant lives. (Old §4,
shared logistics, is now §5; nothing referenced it by number.)

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

Hard constraints the compiler must honour (HW-verified findings):
- **16 user SGPRs per stage max** (GFX8 cap, D3 finding). Beyond that,
  emit `GCN_USGPR_DTAB_VA` + `s_load_dwordx8/x4` from the table.
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
- **A draw-less render submit is a NO-OP that still retires its fence.**
  A payload containing no DRAW_*/DISPATCH_* packet renders nothing, and
  because state is per-submit (above), a state-only or empty/NOP payload
  has no persistent effect either. gcngfx does NOT execute it on the gfx
  ring (an armed CE deadlocks on a draw-less stream — CE_WAITING_ON_DE,
  HW-proven) and simply retires it on the shared fence: the returned
  GpuFence/timeline signals normally. So a Vulkan fence-only or
  barrier-only `vkQueueSubmit` is safe and correct. Corollary: never rely
  on a side-effecting non-render packet (WRITE_DATA/COPY_DATA/EVENT) in a
  draw-less render payload — it will be skipped; route copies and events
  through the transfer queue.
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

**Requirement (admitted 2026-07-26, v0.3 item).** `igpu_vk` targets **all GCN
parts**, not just the gfx803 first target. At device enumeration it must
establish which ASIC it is on and report a Vulkan `apiVersion`, limits, features
and extension list it can actually honour **on that ASIC**. No lane may emit a
command it cannot lower for the running gfx level.

**The constraint is OURS, not the hardware's.** RADV runs Vulkan 1.3 on GFX6, so
"what is this card capable of" answers 1.3 for every GCN part and tells us
nothing. What we may advertise is

```
apiVersion = min( what compiler + PM4 emission implement for this gfx_level,
                  what the backend implements for this ASIC )
```

Advertise low and raise it as lanes land. **Never advertise a version or feature
bit the emitter cannot honour for the running level** — an application acts on
those. A pipeline dropping to the CPU-shade fallback is a performance outcome
and is fine; a false capability is not.

**Identification.** Preferred surface: the backend declares its generation at
registration, `GPUTAG_GfxLevel` (uint32: 6/7/8/9), one tag per fact per the
ratified 10.5 pattern — the backend is the component that must know. Absent =
0 = undeclared, and the ICD then enumerates no HW device there (the same honest
under-report rule as `GPUCAP_DEVICEADDRESS`). **This is a gpu.library change and
therefore coordinator work — not yet proposed.** Until it exists, lanes may
derive the level from `GPUATTR_BackendPCIDevice` (gcngfx registers
`GPUTAG_PCIDevice`) via an ICD-side PCI-ID table; that is a stopgap, not the
contract.

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
- **Lane A**: one **per-gfx-level capability table** drives
  `VkPhysicalDeviceProperties.apiVersion`, limits, features and the extension
  list, consulted at enumeration. No ad-hoc per-ASIC conditionals scattered
  through the ICD.
- **§1's "16 user SGPRs per stage" is a GFX8 fact** (D3 finding), not a
  universal one. Every such HW constant in this document is implicitly
  level-scoped and must be re-verified before it is applied to another
  generation.

Note for the loader: the software ICD reports `VK_API_VERSION_1_3` per physical
device, so a GCN part on which `igpu_vk` reports less is a legitimate reason for
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
