# Supported games

[Home](../README.md) · [Installation](INSTALLATION.md) · [Importing](IMPORTING.md) · [Halo: Reach](REACH.md)

HaloBridge separates the game you **import from** (the **Import game** drop-down) from the game you **prepare for** (**Export to Sapien**). You can import from any of the six games below and prepare a Halo 3 or ODST level that mixes all of them.

## At a glance

| | Halo: CE | Halo 2 | Halo 2: Anniversary | Halo 3 | Halo 3: ODST | Halo: Reach |
| --- | --- | --- | --- | --- | --- | --- |
| Index and place `.map` assets | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Import entire .map** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Import level from .scenario** | ✅ via Tool | ✅ via Tool | ➖ use the `.map` | ✅ from source | ✅ from source | ✅ placements from tags, geometry from `.map` |
| **Remastered campaign** (`.pck`) | ➖ | ➖ | ✅ levels and 3,300 assets | ➖ | ➖ | ➖ |
| **Index .scenario Assets** | ✅ | ✅ | ➖ use the `.map` | ✅ | ✅ | ✅ |
| Use its assets in a Halo 3 / ODST level | ✅ converted | ✅ converted | ✅ converted | ✅ | ✅ | ✅ converted |
| Use its sky in a Halo 3 / ODST level | ✅ converted | ✅ converted | ✅ converted | ✅ | ✅ | ✅ converted |
| Original collision reused | ➖ box / mesh | ➖ box / mesh | ➖ box / mesh | ✅ | ✅ | ✅ (models) |
| **Sapien destination** | ➖ | ➖ | ➖ | ✅ | ✅ | not yet |

## Folders

| Game | Editing Kit folder | MCC maps folder | HaloBridge storage |
| --- | --- | --- | --- |
| Halo: CE | `HCEEK` | `halo1\maps` | `HaloBridge\halo1` |
| Halo 2 | `H2EK` | `halo2\h2_maps_win64_dx11` | `HaloBridge\halo2` |
| Halo 2: Anniversary | `H2AMPEK` (multiplayer `.scenario` only; not needed) | `groundhog\maps` (campaign: `halo2\preload\paks`, found automatically) | `HaloBridge\h2a` |
| Halo 3 | `H3EK` | `halo3\maps` | `HaloBridge` |
| Halo 3: ODST | `H3ODSTEK` | `halo3odst\maps` | `HaloBridge\odst` |
| Halo: Reach | `HREK` | `haloreach\maps` | `HaloBridge\reach` |

**Detect folders** finds all of these automatically when they're in a Steam library or an Xbox app / Game Pass install. The kits are only needed for the features that use them; see [What each task needs](INSTALLATION.md#what-each-task-needs).

## Halo 3

The main game. Halo 3 `.scenario` import reads BSPs and render models from the source files stored in the H3EK tags, so you get original instance names, exact shader names, and scenery that is written back as real scenery tags when you prepare. Halo 3 is the default Sapien destination; its sky list comes from the H3EK tags (default Isolation).

## Halo 3: ODST

Works exactly like Halo 3, using H3ODSTEK. ODST is also a full Sapien destination: set **Export to Sapien** to Halo 3: ODST. ODST and Halo 3 share many tags; when an ODST shader also exists at the same path in H3EK, a Halo 3 level reuses it instead of converting it. The default ODST sky is the one from `h100` (Mombasa Streets).

## Halo: Reach

Reach's Editing Kit has scenarios and placements but no source models or BSP sources, so `.scenario` import takes placements from HREK and geometry from the `.map`. Reach assets can go into a Halo 3 level as static geometry with converted materials. Reach Sapien preparation isn't available yet, because the Halo toolset's ASS exporter only targets Halo 2 and Halo 3. See [Halo: Reach](REACH.md).

## Halo: CE and Halo 2

Both import from MCC `.map` files without any Editing Kit. Their kits have no ManagedBlam, so `.scenario` import has the kit's own Tool build a map first (about 10 seconds for a Halo: CE level, one to two minutes for Halo 2) and then imports that map. Halo 2's maps are in MCC's `halo2\h2_maps_win64_dx11` folder.

In a Halo 3 level, their materials are converted and their objects use a box or mesh-surface collision (their kits can't be read for original collision). Their skies are camera-centred in the original games, so a converted sky is enlarged to surround your level.

Halo: CE shaders that Halo 3 can't represent, such as cloud tints and animated effects, are simplified: base, normal and alpha textures carry over.

Halo 2 sky layers preview unlit in Blender, alpha-blended or additive as in the game, with their tiling, cloud masks, detail maps and tints. When you prepare an imported Halo: CE or Halo 2 map with **Sapien Sky** on "Original map / default sky", its own sky layers become the level's sky, at the size, position and rotation they have in Blender. Halo 2 layers keep their blending.

## Halo 2: Anniversary

The multiplayer maps of Halo 2: Anniversary (MCC's `groundhog\maps` folder, for example `ca_coagulation.map`) use the Halo 4 engine. HaloBridge reads them from the installed `.map` files: **Index .map Assets**, placing assets and **Import entire .map** (BSP, instances, scenery, crates, machines and the sky) work like the other games.

In a Halo 3 level, their materials are converted, their objects use box or mesh-surface collision, and an imported map's sky is converted like a Halo 2 sky. There's no `.scenario` import for Anniversary: its kit (`H2AMPEK`) uses the Halo 4 generation's ManagedBlam, and a map its Tool builds from a scenario is written uncompressed past 2 GB (Tool warns it "won't be able to ship"), which can't be read. Every Anniversary multiplayer level is already in `groundhog\maps`, so use **Import entire .map**. The kit isn't needed.

### Anniversary campaign (remastered)

The remastered campaign graphics are a different engine again: Saber Interactive's **Saber3D**, which draws the remastered picture while the original Halo 2 engine runs the game. Its levels, models and textures are `.pck` archives in MCC's `halo2\preload\paks` folder. With **Import game** set to Halo 2: Anniversary:

- **Import campaign level** imports any of the 15 campaign levels' remastered geometry and textures, at the same coordinates as the original Halo 2 level.
- **Index All Individual Assets** lists about 1,070 campaign models (with switchable variants, damage states and LODs) and 2,250 texture materials.
- **Reduce Texture Size** controls how large the stored textures are.

No Editing Kit is needed. Everything about it is in [Halo 2: Anniversary campaign](H2A-CAMPAIGN.md).

## Halo 4

Listed internally but not enabled. It needs its own extraction and conversion work first.
