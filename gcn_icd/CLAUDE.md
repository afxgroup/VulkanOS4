# gcn_vk.library — ICD core (Agent A lane)

This directory is the future `gcn_vk.library`: the hardware Vulkan ICD that
renders through gpu.library/IGpu. Multi-agent rules: this file governs the
whole `gcn_icd/` tree; `compiler/` and `pm4/` have their own CLAUDE.md and
belong to other agents. **Read `CONTRACTS.md` before writing any code.**

## Your job (Agent A)

Build the ICD skeleton — the productionised form of
`P96_Replacement/tests/igpu_vk/igpu_vk_validate.c`. That file is your proven
starting point for every IGpu call sequence.

**Its status, corrected 2026-07-26** (this brief previously said "15/15 checks
passed against live vgfx", which is now wrong twice over): the validator was
rewritten on 2026-07-25 into five stages and currently reports **39/39 on
QEMU against vgfx**. The old 15-check version is what passed on the **X5000**
on 2026-07-19. **The expanded validator has never been run on hardware.** Treat
its QEMU-only checks as unproven on gcngfx until someone runs them there.

1. **Entry points / dispatch**: the loader contract is the same as the other
   two ICDs. Keep the `DISPATCH` and `RAW` tables in lockstep — the v1.3
   changelog documents the ABI bug that results if they drift, and
   `examples/24_proc_addr` is the regression test. `vkGetDeviceProcAddr`
   returns raw (non-APICALL) pointers.
2. **Memory**: `VkDeviceMemory` = one `GPU_CreateBufferA` chunk (domain from
   `GPUTAG_MemoryDomain`/`HostVisible`/`MapCaching`); sub-allocate
   `VkBuffer`/`VkImage` as (chunk, offset) views. TEST the map result, never
   assume unified vs discrete (validator finding #1).
   `VkPhysicalDeviceMemoryProperties` from `GpuBackendCaps.MemoryDomains` +
   `GPU_QueryMemoryA`; coherence per the CONTRACTS.md §3 convention.
   **NB (2026-07-26)**: `MemoryDomains` only became real on 2026-07-25 (P96
   `8547b7f`) — backends now declare it via `GPUTAG_MemoryDomains` at
   registration, and it read 0 for everyone before that. vgfx declares
   `VRAM|SYSTEM` (0xa); **gcngfx declares NOTHING yet**, so on the actual
   target hardware you will read 0. Handle 0 as "undeclared" rather than
   "no domains", and report the gap rather than inventing a memory type.
3. **Sync**: VkFence over `GpuFence` (`GPU_TestFence`/`GPU_WaitFence`);
   timeline VkSemaphore over `GPU_CreateTimelineA`/`GPU_WaitTimelineA`/
   `GPU_QueryTimelineA`; binary semaphores ICD-internal.
   **Timeout semantics matter here and were broken until 2026-07-25** (P96
   `b842d52`, found by validator stage 2): `GPU_WaitTimelineA` ignored its
   timeout entirely and slept forever. Now explicit — `0` = poll,
   `1..0xFFFFFFFE` = real microsecond bound, `GPU_TIMEOUT_INFINITE` = block.
   `vkWaitSemaphores`/`vkWaitForFences` MUST return `VK_TIMEOUT`, so rely on
   this. **Caveat**: `GPU_WaitFence` delegates its timeout to the backend and
   that path is still UNTESTED — both in-tree backends retire synchronously,
   so nothing ever stays pending. Assume nothing about it; test it.
4. **WSI**: windowed present like the software ICD; fullscreen/exclusive via
   `GPU_AcquireDisplayA(GPUTAG_SwapchainDepth)` + `GPU_NextDisplayBufferA` +
   `GPU_PresentA` + `GPU_ReleaseDisplay`. NB (2026-07-19): the X5000 block
   is LIFTED — the DisplayHook was exonerated (interleaved re-test 7/7;
   CONTRACTS.md status note) and registers by default, and validator
   stage 3 verified acquire→present→release on HW. Fullscreen now works on
   both vgfx/QEMU and the X5000.
5. **Shading fallback**: CPU-shade via the software ICD's SPIR-V interpreter
   until the compiler + pm4 lanes integrate. Structure command-buffer
   recording so the execution backend (CPU interpret vs PM4 emit) is a
   pluggable seam — pm4/ plugs in behind it later.
6. Manifest (`gcn_vk.json`) + Makefile.cross following `software_icd/`'s
   pattern-rule style; wire into the top-level Makefile as `make gcn-icd`.
7. **Enumeration + capability reporting**: **read `CAPABILITY_TABLE.md` before
   writing `vkGetPhysicalDevice*`.** It specifies what the per-level table
   holds, and its findings are not what you would guess. Three that will bite:
   - **`QueueMask` is structurally useless** — `P96 src/lib/gpu_api.c:466-469`
     hardcodes `PRESENT|RENDER|COMPUTE` for *every* backend regardless of what
     it registered. Never derive `VkQueueFamilyProperties` from it. Report one
     graphics+transfer family and grow on tested evidence only.
   - **`maxImageDimension2D` is 8192, not 16384**, until tiled layouts exist:
     T# WIDTH/HEIGHT are 14 bits (so 16384) but **T# PITCH is 13 bits**
     (`GCNgfx/src/gfx/gcn_gfx.c:753`), which caps a *linear* image at 8192.
   - **Gate enumeration on CAPABILITY, never on gfx level.** gcngfx binds the
     Pitcairn PCI ids and will report `GfxLevel = 6`, but `gfx_v8.c:1247` is
     `if (family != POLARIS) return FALSE` and GMC/SDMA/DCE6 are the same. A
     gfx6 board answers 6 while being undriveable.
   The proposed answer on reported version is **`VK_API_VERSION_1_0` on every
   level**, raised by extension rather than by version — hardware is not the
   blocker (RADV does 1.3 on GFX6); our lanes and our trimmed
   `vulkan_core.h` are. Not yet ratified into CONTRACTS §4.
   NB the loader does **not** select on `apiVersion`
   (`loader/src/loader_icd.c:408-444` sorts by prefs then "software goes last"
   by `strstr`), so a low claim gets no automatic fallback to `software_vk`.
8. **Barrier-only / fence-only submits**: use the ratified fence-only submit,
   `GPU_SubmitA(queue, NULL, 0, tags)` — NOT an empty PM4 payload the backend
   has to recognise as work-free. Read CONTRACTS.md §2 first: gcngfx does not
   accept the ratified form yet (`GPUERR_BADARGS`), so you need a per-backend
   fallback behind ONE helper, with an expiry date. Numbered last because it
   was added on 2026-07-26; items 1–6 keep their numbers, which other documents
   cite (§4 = WSI).

## Test target

qemu-gpulib (vgfx backend).

**The single-scanout limitation this brief used to warn about is FIXED** (vgfx
`5229440`, 2026-07-25): vgfx now does a real depth-N swapchain with per-image
resources and a per-image flip, and the validator reports 2/2 swapchain images
and 30/30 presents. Do not design around every-other-Present refusals. Per
P96 `dd3a6fe` the flip *mechanism* is now proven on both backends — gcngfx
address-only vblank-latched on hardware, vgfx `SET_SCANOUT` on QEMU — so what
remains hardware-gated is real vsync *timing*, not the flip.

Historical note worth knowing before you trust a green run: between 11-Jul and
25-Jul a stage-3 swapchain acquire on vgfx silently **corrupted the live
desktop** (it freed the P96 board pool out from under the shim, and afterwards
`vgb_Present` returned `GPUERR_OK` forever while displaying nothing). The
validator's own "display released (desktop restored)" line was believed twice
and proved nothing — it printed once the RELEASE hook returned. A moving
present counter proves presents happen, not that pixels are visible.

## Do not touch

- `compiler/` (Agent B), `pm4/` (Agent D), `CONTRACTS.md` (coordinator).
- Anything in `GCNgfx/` or `P96_Replacement/` (read-only references).
- The loader, software_icd, ogles2_icd — except reading them as references.
  If the loader needs a change, stop and report.

## Style / platform notes

- Mirror `software_icd/src/` file layout (`gcnvk_instance.c`, `gcnvk_memory.c`,
  …); `swvk_internal.h` is the object-model reference.
- Userspace disk-loaded library: clib4/newlib allowed (the CRT-free
  discipline applies to gcngfx, NOT here).
- Big-endian host: SPIR-V endianness from the magic word (v1.3 behaviour);
  all IGpu-visible dword streams little-endian per CONTRACTS.md.
- Debug via the `D(...)` macro convention (no-op unless DEBUG).
- Vendor gpulib SDK headers the way `GCNgfx/include/gpulib/` does (note the
  provenance in a VENDORED.md); do not #include across repos.
