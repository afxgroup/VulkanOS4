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

### The real fork: which floor do they sit on

Not "native in the card driver vs on Vulkan". There are **three** candidate
tiers, and the lowest one is already settled:

1. **Native in the card driver** (GCNgfx emits its own Warp3D/GL state) —
   ruled out. Every future card would reimplement all three layers, and it is
   not what the platform does today.
2. **On `gpu.library`/IGpu** — the established floor. P96's `docs/VULKAN.md`
   is explicit that Vulkan is not IGpu's only consumer: Warp3D rides the
   identical floor (`App -> Warp3D.library -> W3D_<backend>.library ->
   gpu.library/IGpu -> backend`), and so do MiniGL, ogles2 and compute.
   **This already delivers "a new card gets the layers for free"** — one
   gpu.library backend, and every IGpu consumer works. **Warp3D** is HERE TODAY,
   not greenfield: a complete HW driver over IGpu (`vgfx/src/w3d`, exercised by
   `P96_Replacement/tests/warp3d`). **Warp3D Nova is NOT** — corrected
   2026-07-26; the cited `tests/warp3dnova` is a 26-line presence probe that
   opens the library and prints its version, not a driver. Nova over IGpu
   remains to be written, and per P96 `PLAN.md` "Anti-replication strategy" the
   intended route is over Vulkan rather than as a second direct IGpu consumer.
3. **On Vulkan** — a sibling consumer of IGpu, not the floor beneath the
   layers. Buys the same portability at a higher level of abstraction, plus a
   much richer feature set to translate against.

So the question per layer is tier 2 vs tier 3, and it plausibly answers
differently for each:

- **Warp3D** — already on IGpu and working. Immediate-mode and largely
  fixed-function, which maps badly onto Vulkan's pipeline model. Moving it
  onto Vulkan buys nothing it does not already have.
- **OpenGL / MiniGL** — on Vulkan. Zink (GL-over-Vulkan) is already named in
  VULKAN.md's list of anticipated IGpu-stack consumers; a full GL
  implementation is enormous and GL maps far better onto Vulkan than onto a
  thin device layer.
- **Warp3D Nova** — genuinely open. Shader-based, so it is the layer that maps
  *well* onto Vulkan; also the awkward one, being A-EON proprietary, so any
  implementation is a compatibility exercise against a closed API.

**Caveat on the "free" in tier 3.** `VULKAN.md` says a new GPU gets Vulkan
acceleration for free once its gpu.library backend exists, with no new ICD.
That predates CONTRACTS §2: `gcn_vk.library` emits **GCN PM4 and GCN machine
code**, so only its memory/sync/WSI half is backend-agnostic. A future
non-GCN backend gets the CPU-shade fallback for free, not hardware Vulkan —
it needs its own payload emitter and shader compiler. A layer written against
the Vulkan API still works anywhere an ICD does; it is the supply of ICDs that
is not free.

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
4. The tier question above answers per layer, not once, and two of the three
   already have a working home on IGpu. "Do these belong in this repository"
   is therefore several questions, and only the ones that land on Vulkan are
   VulkanOS4's to answer.

Do not create placeholder directories for these. An empty tree carries no
information, git will not track it, and it invites work to start in a layout
nobody has agreed to.
