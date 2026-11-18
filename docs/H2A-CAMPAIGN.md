# Halo 2: Anniversary campaign

[Home](../README.md) · [Importing](IMPORTING.md) · [Supported games](GAMES.md) · [Sidebar reference](FEATURES.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Error reference](ERRORS.md)

HaloBridge can import the **remastered campaign** of Halo 2: Anniversary into Blender: whole levels with their remastered geometry and textures, and more than 3,000 individual props, weapons, characters, vehicles and texture materials. This page explains what the feature does, how to use it, how it works, and what to do when something goes wrong.

## Contents

1. [What this is](#what-this-is)
2. [Requirements](#requirements)
3. [Import a whole campaign level](#import-a-whole-campaign-level)
4. [Index and place individual assets](#index-and-place-individual-assets)
5. [Model parts and variants](#model-parts-and-variants)
6. [Reduce Texture Size](#reduce-texture-size)
7. [Where the data goes and how much space it takes](#where-the-data-goes-and-how-much-space-it-takes)
8. [Coordinates: lining up with original Halo 2](#coordinates-lining-up-with-original-halo-2)
9. [Using campaign content in a Halo 3 Sapien level](#using-campaign-content-in-a-halo-3-sapien-level)
10. [Saving and sharing .blend files](#saving-and-sharing-blend-files)
11. [How it works](#how-it-works)
12. [Known limits](#known-limits)
13. [Troubleshooting](#troubleshooting)
14. [Credits](#credits)

## What this is

Halo 2: Anniversary in MCC is two games in one install:

| Part | Engine | Where MCC keeps it | HaloBridge route |
| --- | --- | --- | --- |
| **Multiplayer** (Anniversary maps such as `ca_coagulation`) | Halo 4 engine, Blam `.map` files | `groundhog\maps` | **Import entire .map** and **Index .map Assets** (see [Supported games](GAMES.md#halo-2-anniversary)) |
| **Campaign, original graphics** | Halo 2 engine, Blam `.map` files | `halo2\h2_maps_win64_dx11` | Import game **Halo 2** |
| **Campaign, remastered graphics** | Saber Interactive's **Saber3D** engine, `.pck` archives | `halo2\preload\paks` | **Import Anniversary campaign level** and **Index All Individual Assets** (this page) |

The remastered campaign graphics are drawn by a separate engine, Saber3D, that runs alongside the original Halo 2 engine. When you press the graphics toggle in game, Halo 2 keeps running the gameplay and only the picture changes. Saber3D's files use a completely different format from Blam `.map` files, so HaloBridge includes its own reader for them.

## Requirements

| You need | Why |
| --- | --- |
| Halo: The Master Chief Collection with **Halo 2: Anniversary campaign** installed | The level files (`halo2\preload\paks\*.pck`, about 15 GB including the 13 GB `shared.pck`) |
| HaloBridge with its bundled extraction helper | The `.pck` reader is part of the extractor (`HaloBridge.H2ACampaign.dll`) |
| [.NET 10 Desktop Runtime (x64)](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) | Runs the extractor, as for every other game |
| The **Halo 2: Anniversary .map Files** folder set to MCC's `groundhog\maps` | HaloBridge finds the campaign from there: `groundhog` and `halo2` sit side by side in the MCC install |

You do **not** need an Editing Kit. H2AMPEK is for multiplayer only and isn't used here.

**Check that the campaign is downloaded.** In Steam: right-click MCC → Properties → Installed content (or DLC) and make sure Halo 2: Anniversary campaign content is installed. The folder `...\Halo The Master Chief Collection\halo2\preload\paks` should contain files such as `01a_tutorial.pck`, `shared.pck` and `cache.pck`, each with a `.csv` beside it.

## Import a whole campaign level

1. Set **Import game** (top of the sidebar) to **Halo 2: Anniversary**.
2. Open **Folders and Setup**. Click **Detect folders**, or set **Halo 2: Anniversary .map Files** to `...\Halo The Master Chief Collection\groundhog\maps`.
3. The **Import Anniversary campaign level** box appears above **Import entire .map**. Click the **⌄** arrow next to the level field and choose a level, or type its filename (for example `01a_tutorial.pck`).
4. Optional: set **Reduce Texture Size** (see [below](#reduce-texture-size)).
5. Click **Import campaign level**. Progress shows at the bottom of the sidebar.
6. When it finishes, the message line says how many pieces were imported and how much temporary space was freed. **Open map import report** shows the details.
7. Switch the viewport to **Material Preview** to see the textures.

### The 15 campaign levels

| File | Mission |
| --- | --- |
| `00a_introduction.pck` | The Heretic (cutscene only, has no level geometry) |
| `01a_tutorial.pck` | The Armory |
| `01b_spacestation.pck` | Cairo Station |
| `03a_oldmombasa.pck` | Outskirts |
| `03b_newmombasa.pck` | Metropolis |
| `04a_gasgiant.pck` | The Arbiter |
| `04b_floodlab.pck` | The Oracle |
| `05a_deltaapproach.pck` | Delta Halo |
| `05b_deltatowers.pck` | Regret |
| `06a_sentinelwalls.pck` | Sacred Icon |
| `06b_floodzone.pck` | Quarantine Zone |
| `07a_highcharity.pck` | Gravemind |
| `07b_forerunnership.pck` | Uprising |
| `08a_deltacliffs.pck` | High Charity |
| `08b_deltacontrol.pck` | The Great Journey |

`shared.pck` and `cache.pck` aren't levels: they hold the textures and models that every level uses, and shaders. They don't appear in the level list.

### What you get

- **The level's remastered geometry**, in one collection named after the level, split into **Level geometry**, **Decals** and **Glass**. Each piece is one Blender object named after its Saber3D object, for example `polySurface12__p0__3 #812`.
- **Materials with textures**: each material's base (color) texture and, when it has one, its normal map. Texture repeats are kept.
  - **Glass** (Saber3D shading presets containing "glass") is alpha-blended.
  - **Decals**, and surfaces with transparency switched on, are cut-outs (alpha-tested).
  - Everything else is opaque.
- **Positions in classic Halo 2 coordinates.** The level sits exactly where the original Halo 2 level is (see [Coordinates](#coordinates-lining-up-with-original-halo-2)).

Left out on purpose:

| Left out | Why |
| --- | --- |
| Lower levels of detail | Only the highest-detail version of each piece is imported, so pieces don't overlap. |
| Occluders, shadow casters, reflection-probe boxes | Engine helper geometry that is never seen in game. Imported, a 1,300-unit occluder box would hide the tutorial level. |
| Untextured "red" placeholder parts | Hidden helper parts with no UVs or lighting. |
| `sm_geom_*` pieces | Per-light shadow-casting geometry, not visible level geometry. |
| Characters, weapons, vehicles, AI, scripts | These belong to the Halo 2 gameplay engine, not to the remastered level file. Place campaign props and characters from the asset list instead. |

### How long it takes

| Level | Pieces | First import (read + build in Blender) | Again later |
| --- | --- | --- | --- |
| `07b_forerunnership` | 2,684 | about 15 s + 20 s | about 4 s to re-read, then the Blender build |
| `01a_tutorial` | 7,734 | about 25 s + 3 min | about 12 s to re-read, then the Blender build |

Most of the time is Blender creating thousands of objects. Bigger levels such as Delta Halo (`05a_deltaapproach`) have up to 12,000 pieces. Let it finish and watch the progress line. HaloBridge turns EEVEE viewport shadows off after a level import, so Material Preview stays responsive.

## Index and place individual assets

**Index All Individual Assets** (in the campaign box) lists every placeable Anniversary campaign asset in the **Indexed Asset List**:

- **About 1,070 models**: props (crates, barrels, rocks, foliage), weapons, characters and vehicles. Only templates with visible geometry are listed.
- **About 2,250 materials**: every base texture, together with its normal map. Companion textures (`_nm`, `_spec`, `_em`, `_det`, `_mask`, `_illum`) aren't listed separately.

The list shows them under the level name **H2A campaign**. Indexing reads every template in `shared.pck` once. The first time takes about a minute and a half (the 13 GB file is read from disk); later indexes take seconds.

Use them like any other indexed asset (see [Importing](IMPORTING.md#3-browse-and-place-individual-assets)):

- **Preview** with Preview Mode on and click a row. **Place asset(s)** keeps it.
- **Materials**: highlight a material row, select a mesh, and click **Selected Asset → Apply material to selected object**.
- Each asset is extracted the first time you use it (0.3 to 2 seconds) and cached afterwards.

Placed models arrive in Halo units with their objects' transforms applied, at the 3D cursor, scaled ×100 like every HaloBridge asset.

**Rigged models** (characters, weapons and vehicles with a skeleton) come in their rest pose without bones or animation. The asset's status line says "Rigged model, static rest pose: some characters' parts are out of place". Weapons, vehicles, Marines and Master Chief assemble correctly. Some Covenant characters (Elite, Grunt, Jackal) have parts that sit away from the body, because their pieces are stored relative to bones that HaloBridge doesn't apply yet.

## Model parts and variants

Campaign models carry every variant at once: the Elite's armor for each rank, energy shields, vehicle damage states and lower levels of detail. HaloBridge sorts them into **regions** you can switch in **Model Parts and Variants** while the model is selected, instead of piling them on top of each other.

| Region | What it holds | On when placed |
| --- | --- | --- |
| **body** | The model itself | Yes |
| Armor groups such as **helmet**, **lights**, **head** | Variants such as `base`, `council`, `honor`, `ultra` | The `base` / `default` variant |
| Gun groups such as **l**, **r** (Ghost) | `gun_base`, `gun_medium`, `gun_major`, `gun_destroyed` | `gun_base` |
| **shield** | Energy-shield shells around the whole character | No |
| **damage** | Damaged and destroyed pieces (`hull_destroyed`, `l_wing_destroyed`...) | No |
| **lod** | Lower-detail versions (`lod1`, `lod2`, `lod3`) | No |

Expand a region with its arrow and tick what you want visible; the mesh is rebuilt immediately. For example, switching the Elite's helmet from `base` to `council`, or turning on the Ghost's damage. **Separate enabled parts into objects** splits the visible pieces into separate objects. Models with nothing to switch, such as a crate, are plain meshes without this section.

## Reduce Texture Size

**Reduce Texture Size** (512, 1024, 2048 or 4096; default 2048) is the largest width a campaign texture is stored at. Anniversary textures are up to 4096 and 8192 pixels wide; smaller sizes save disk space and memory and load faster, at the cost of detail.

| Size | Use it for |
| --- | --- |
| **512** | The least storage and memory; visibly softer. Good for blocking out large areas. |
| **1024** | Most of Halo 3's own textures are this size. |
| **2048** (default) | Halo 3's largest textures. Good quality. |
| **4096** | The most Halo 3's Tool accepts. Much more memory. |

It's the same setting as **Texture size** under **Sapien Map Preparation**, so it also limits the textures Prepare converts for Halo 3. Changing it doesn't change levels or assets you already imported. Import the level again (or place the asset again) to get textures at the new size. Each size has its own texture folder, so you can switch back and forth without re-extracting.

## Where the data goes and how much space it takes

HaloBridge keeps as little as it can:

- **Textures** are stored **once for every level**, in `<HaloBridge storage>\h2a\map_scenes\h2a_campaign_textures_<size>`. Most of them come from `shared.pck` and are reused between levels, so each one is stored once. Each texture is kept as whichever file is smaller: the game's own GPU-compressed data as a `.dds` (an exact copy, no quality loss), or an optimized `.png`. Color textures are usually smaller as DDS; normal maps are usually half the size as PNG.
- **Level geometry files** are deleted right after a successful import. Blender already holds the meshes, and Prepare only needs the small `scene.json` that stays behind. Importing the same level again re-reads its geometry from the `.pck` in a few seconds.
- **Individual assets** go to `<storage>\h2a\assets\<id>`, with their textures in the same shared texture folder.

| Measured | Before these optimizations | Now |
| --- | --- | --- |
| `01a_tutorial`, after import | about 930 MB | about 300 MB of textures + 1.6 MB |
| `01a_tutorial` + `07b_forerunnership` | about 1.1 GB | **366 MB** |

Don't delete the texture folder while scenes use it: the imported materials load their images from it (see [Saving and sharing](#saving-and-sharing-blend-files)).

## Coordinates: lining up with original Halo 2

Saber3D stores its geometry Y-up in metres. Halo stores levels Z-up in world units (1 world unit = 10 feet = 3.048 m). HaloBridge converts every campaign position with:

```text
Halo (x, y, z) = Saber (x, −z, y) ÷ 3.048        no offset
```

This was measured, not guessed. The remastered tutorial geometry was fitted against the original Halo 2 `01a_tutorial.map` BSP extracted by HaloBridge. A scale of exactly 1/3.048 matched best, and a search for a leftover offset moved the result by less than 3 cm. The conversion is a pure rotation (no mirroring), so faces keep their winding.

What this means for you:

- A remastered campaign level imported with HaloBridge lands **exactly on top of** the same level imported from the original Halo 2 map (import game **Halo 2**, `01a_tutorial.map`). You can import both into one scene to compare, or use the original level's collision and objects with the remastered visuals.
- The remastered art has more detail than the original, so the two meshes aren't identical vertex for vertex. Floors and walls line up.
- In Sapien, the level has the size and position Halo 2 had.

## Using campaign content in a Halo 3 Sapien level

Campaign geometry and assets are prepared like other games' content (see [Importing → Use assets from any game](IMPORTING.md#use-assets-from-any-game-in-one-level)):

- Every material is converted into level-local Halo 3 bitmaps and shaders: base color, normal map, texture repeat and cut-out or blended transparency. The textures go through the same converter as Halo: Reach and Halo 2: Anniversary multiplayer materials. The converter reads the DDS and PNG files directly.
- Collision is generated from the visible mesh. Anniversary objects are tagged as `h2a`, so very dense pieces get decimated collision split into parts Tool accepts, as with Anniversary multiplayer maps.

**Whole campaign levels haven't been prepared for Sapien yet.** A campaign level has thousands of pieces (7,734 in the tutorial), while one Halo 3 BSP allows at most **1,024 instanced geometry definitions**. Preparing a whole level is likely to hit that and other Tool limits. Until this is tested, prepare a section: hide or delete the collections and pieces you don't need, or join pieces that never move into fewer objects. Individual props and textures work like any other converted asset.

## Saving and sharing .blend files

A saved `.blend` contains the geometry, objects, collections, materials and HaloBridge's metadata, but **not the texture images**. Blender stores a link to each image file in HaloBridge's storage folder. Opened on another PC, or after the texture folder is deleted, surfaces show pink (missing texture).

- To make a self-contained `.blend`, use **File → External Data → Pack Resources** before saving. Each file then carries its own copy of the textures (about 300 MB for the tutorial at 2048, on top of the geometry; expect roughly 0.5 to 1 GB per whole level).
- **Before sharing:** these files contain Halo 2: Anniversary's actual geometry and textures, which belong to Microsoft / 343 Industries / Saber Interactive. HaloBridge never distributes game content: each user extracts it from their own MCC install. The cleanest way to share work built on campaign levels is for others to install HaloBridge and import the level themselves, which takes a minute or two.

## How it works

The reader is a small .NET library (`HaloBridge.H2ACampaign.dll`, source in `source/H2ACampaign`) that the extraction helper calls. The full technical write-up, including byte layouts, is in [`source/H2ACampaign/FORMAT.md`](../source/H2ACampaign/FORMAT.md). In short:

| Layer | What HaloBridge reads |
| --- | --- |
| **`.pck` archive** | A 6 MB table of chunk offsets, then 32 KB zlib-compressed chunks. Inflated, the archive is a `1SERpak` directory (names, offsets, sizes); entries that start with `1SERpak` are nested directories. The `.csv` beside each `.pck` lists the same entries; HaloBridge matched all 1,512 tutorial entries and all 8,397 `shared.pck` entries against it. |
| **Where things live** | A level `.pck` holds the level (`.lg` geometry, `.cdt`, scripts, lighting) and lists every texture and model it uses with size 0; those bytes live in `shared.pck`. |
| **`.pct` textures** | Blocks tagged with IDs (`TCIP` magic, size, format, mip count, data). Formats: BC1, BC3, BC4, BC5 (normal maps), RGBA8, A8L8, RGBA16F and RGB9E5 (lightmaps). Cube maps store each face with its full mip chain. All 6,099 textures in `shared.pck` decode, and their sizes match exactly. |
| **`.tpl` templates and `.lg` scenes** | A `1SER` header, a property block (name, bounding box, LOD table, texture list), then an `OGM1` geometry graph: objects (names, hierarchy, 4×4 transforms, which submeshes they own), vertex/normal/UV/face buffers, meshes and submeshes with their materials. All 1,148 templates in `shared.pck` and all 15 campaign `.lg` scenes parse. |
| **Materials** | Property bags per submesh: `layer0..3` (texture name, preset, tint, tiling, UV set, blending), shading preset and lightmap. HaloBridge uses layer 0's texture and its `_nm` companion. |

Findings that are new compared with earlier community tools (and documented in FORMAT.md):

- A submesh's owner and transform come from the object whose **split range** covers it, not from its node ID (which is always 0). Using the node ID left props about 3× too large.
- Two vertex layouts earlier tools didn't decode: a separate 4-byte normal stream, and full-float normals.
- The `.lg` LOD-root layout (which objects are LOD0), the helper and placeholder objects to leave out, and that `sm_geom_*` pieces are per-light shadow casters (`sm_obj_tbl.tbl` maps lights to them).
- The exact Saber-to-Halo coordinate transform (above).
- Zero-area triangles exist in some models (the battle rifle has 10) and crash Blender's custom-normal code; HaloBridge drops them.

## Known limits

- **Gameplay isn't in these files.** AI, weapons, vehicles, scripts and triggers come from the Halo 2 engine, not the remastered level. Import the original Halo 2 map for those (it lines up exactly).
- **One texture layer per material.** About 500 tutorial surfaces blend extra texture layers by vertex color; only the first layer is used. Specular (`_spec`) and emissive (`_em`) maps aren't used.
- **Lightmaps aren't used.** The remastered lightmaps (`*_rnm0..2`, RGB9E5) are decoded by the reader but not applied; Halo 3's lighting bake replaces them.
- **Rigged models are static**, and some characters' parts sit away from the body (see [above](#index-and-place-individual-assets)).
- **Collision (`.cdt`), light probes and level scripts** aren't read.
- **Normal maps** are converted with the green channel as stored; matching Halo 3's convention in Sapien hasn't been verified yet.
- **Whole levels in Sapien** haven't been tested and will likely exceed Halo 3's instance limits (see [above](#using-campaign-content-in-a-halo-3-sapien-level)).

## Troubleshooting

| Problem | Cause and fix |
| --- | --- |
| The **Import Anniversary campaign level** box isn't there | It only appears when **Import game** is **Halo 2: Anniversary**. Open **Folders and Setup**. |
| "No campaign levels found…" when opening the level list, or "Halo 2: Anniversary campaign files not found…" | HaloBridge looks for `halo2\preload\paks\shared.pck` in the MCC install that contains your **.map Files** folder. Set **Halo 2: Anniversary .map Files** to MCC's `groundhog\maps`, and make sure the Anniversary campaign content is installed. Setting the folder directly to `...\halo2\preload\paks` also works. |
| "Choose a campaign level .pck from …" | The level filename is wrong. Use the **⌄** list, or type a name such as `01a_tutorial.pck` (with `.pck`). |
| "This .pck has no .lg level scene (only campaign level paks do)" | You chose a file that isn't a level (for example `shared.pck` or `cache.pck`). |
| `00a_introduction` stops with "The map has no decoded visual placements." | It's a cutscene level with no level geometry. Choose another level. |
| "The campaign level extractor did not create a scene manifest" or "External job failed; full log: …" | The extractor stopped. Open the log named in the message (in `<storage>\h2a\jobs`). Common causes: the .NET 10 Desktop Runtime is missing (run **Check setup**), the disk is full, or MCC is updating its files. |
| Pink or missing textures | Switch to **Material Preview**. If a `.blend` was moved to another PC or the texture folder was deleted, textures are missing: import the level again on this PC, or pack resources before moving files. |
| Some surfaces look flat or too simple | Expected for vertex-blended multi-layer materials (first layer only) and for specular/emissive detail, which isn't converted. |
| Characters' parts float away from the body | A known limit of rigged models (Elite, Grunt, Jackal). Use Marines, Master Chief, props, weapons and vehicles, or wait for bone support. |
| A placed model shows overlapping armor or damaged pieces | Turn the extra variants off in **Model Parts and Variants**. Assets extracted by an earlier development version are re-extracted automatically. |
| Indexing seems stuck | The first index reads every template in the 13 GB `shared.pck` (about 90 seconds). Wait for the message. |
| Blender is slow after importing a level | Normal with thousands of objects. Keep **Viewport Shadows** off, use Solid shading while navigating, and hide collections you aren't working on. Use a lower **Reduce Texture Size** to save memory. |
| Storage keeps growing | Each texture size has its own folder (`h2a_campaign_textures_512/1024/2048/4096`). Delete folders for sizes you no longer use, but only if no saved scene uses them. |

For any other message, see the [error reference](ERRORS.md).

## Credits

HaloBridge's Saber3D reader is original code, written for HaloBridge, but it stands on public research:

- **Haus (Wildenhaus)**: [Index](https://github.com/Wildenhaus/Index) (an H2A asset browser, 2022, MIT-licensed LibH2A) and [LibSaber](https://github.com/Wildenhaus/LibSaber). Their code was the map for the container layout, block IDs, template/scene/geometry layouts, texture formats and normal-unpacking math. Index credits **zatarita, sleepyzay and Unordinal** as well.
- **Zatarita**: [SeT](https://github.com/Zatarita/SeT), Saber editing tools for Halo CE Anniversary (a related engine).

No code from these projects is included in HaloBridge. Everything was re-implemented and checked against the game files.
