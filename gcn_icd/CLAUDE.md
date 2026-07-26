# gcn_vk.library — ICD core (Agent A lane)

This directory is the future `gcn_vk.library`: the hardware Vulkan ICD that
renders through gpu.library/IGpu. Multi-agent rules: this file governs the
whole `gcn_icd/` tree; `compiler/` and `pm4/` have their own CLAUDE.md and
belong to other agents. **Read `CONTRACTS.md` before writing any code.**

## Your job (Agent A)

Build the ICD skeleton — the productionised form of
`P96_Replacement/tests/igpu_vk/igpu_vk_validate.c` (15/15 checks passed
against live vgfx; that file is your proven starting point for every IGpu
call sequence):

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
3. **Sync**: VkFence over `GpuFence` (`GPU_TestFence`/`GPU_WaitFence`);
   timeline VkSemaphore over `GPU_CreateTimelineA`/`GPU_WaitTimelineA`/
   `GPU_QueryTimelineA`; binary semaphores ICD-internal.
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

## Test target

qemu-gpulib (vgfx backend). Known backend gap, not your bug: vgfx is
single-scanout, so a depth-2 exclusive swapchain gets every other Present
refused (`GPUERR_BADARGS`) — the validator write-up documents it. Windowed
path is unaffected.

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
