# Roadmap — direction, not schedule

High-level intent only. Nothing here is a commitment, and nothing here binds
an implementation: the binding documents are `gcn_icd/CONTRACTS.md` for the
hardware ICD and the per-directory `CLAUDE.md` lane briefs.

## Current

Three Vulkan ICDs, all of which **implement** Vulkan and render through
something beneath them:

| ICD | Renders through | State |
|---|---|---|
| `software_vk.library` | CPU (SPIR-V interpreter) | shipped, v1.3 |
| `ogles2_vk.library` | ogles2.library / Warp3D Nova | shipped, v1.3 |
| `gcn_vk.library` | gpu.library/IGpu → GCN hardware | in progress (`gcn_icd/`) |

## Future — legacy 3D APIs ON TOP OF Vulkan

A long-term goal is to run the platform's existing 3D APIs on this stack:

- **Warp3D** on Vulkan
- **Warp3D Nova** on Vulkan
- **OpenGL / MiniGL** on Vulkan

These are the **opposite direction of translation** from everything above.
An ICD implements Vulkan; these would *consume* it — the shape of DXVK, vkd3d
or Zink, not of a driver. They are therefore not `*_icd` components, whatever
they end up being called.

Two facts worth having on record before that discussion happens:

- On AmigaOS each would ship as a **drop-in replacement** and keep the name of
  the library it replaces (`Warp3D.library`, `Warp3DNova.library`, …). The
  directory name is the only naming freedom there is.
- They plausibly share a substantial core — fixed-function or GLSL state to
  SPIR-V, pipeline caching, descriptor management. Whether that shared core
  exists, and what it contains, decides the layout.

### Decision deliberately DEFERRED

**No decision is to be made on naming, directory layout, or whether these live
in this repository, until `gcn_vk.library` is complete.**

This is a deferral, not an omission. The reasons:

1. The shared-core question above cannot be answered from where we stand, and
   choosing a layout first would prejudge it.
2. These layers are only worth having once there is hardware Vulkan underneath
   them. A Warp3D implementation over a CPU rasteriser is slower than the
   Warp3D it replaces.
3. Building the hardware ICD will teach us what the translation layers
   actually need from a Vulkan implementation — which is exactly the input
   this decision wants and does not yet have.

Do not create placeholder directories for these. An empty tree carries no
information, git will not track it, and it invites work to start in a layout
nobody has agreed to.
