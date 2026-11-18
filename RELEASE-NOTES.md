# HaloBridge v0.10.1 — Halo 2: Anniversary campaign, scenario import and test lighting fixes

Import levels and assets from Halo: CE, Halo 2, Halo 2: Anniversary (multiplayer **and now the remastered campaign**), Halo 3, Halo 3: ODST and Halo: Reach in Blender 4.0 to 5.2, straight from Editing Kit `.scenario` tags, MCC `.map` files or Anniversary's campaign `.pck` archives, and prepare a Halo 3 or ODST Sapien test level that mixes assets (and skies) from all of them.

## Downloads

- **HaloBridge-0.10.1.zip** is the Blender installer, including compiled helpers.
- **HaloBridge-0.10.1-source.zip** contains the matching source for developers.

Expand Assets below to download the installer. GitHub's automatic source archives omit compiled helpers. If you downloaded 0.10.1 before this update, download it again: the installer now includes the Anniversary campaign reader (`HaloBridge.H2ACampaign.dll`).

## New in this update: the Halo 2: Anniversary campaign

- **Import campaign level.** Set **Import game** to Halo 2: Anniversary; the new **Import Anniversary campaign level** box (above Import entire .map) imports any of the 15 campaign levels' **remastered** geometry and textures from MCC's `halo2\preload\paks`. These are Saber3D `.pck` archives; HaloBridge includes its own reader for them. You get the highest-detail geometry with base textures and normal maps (glass blended, decals cut out), without the engine's helper geometry. No Editing Kit needed.
- **Lines up with original Halo 2.** Remastered levels are placed in classic Halo 2 coordinates (measured: Saber3D metres ÷ 3.048, Y-up to Z-up, no offset), so they sit exactly on top of the same level imported from the original Halo 2 map.
- **Index All Individual Assets.** About 1,070 remastered campaign models (props, weapons, characters, vehicles) and 2,250 texture materials in the asset list, extracted on first use. Armor variants, energy shields, damage states and LODs are switchable in **Model Parts and Variants**.
- **Reduce Texture Size** (512 / 1024 / 2048 / 4096) for campaign textures; also the new 512 option for Prepare's **Texture size**.
- **Small storage.** Textures are stored once for all levels (as the game's own DDS data or an optimized PNG, whichever is smaller), and level geometry files are deleted after import. Two levels: 366 MB instead of about 1.1 GB.
- **Default sky is now Isolation** instead of Deadlock.
- **New guides:** [Halo 2: Anniversary campaign](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/H2A-CAMPAIGN.md) and an [error reference](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/ERRORS.md) that explains every message HaloBridge shows and how to fix it.

Known limits of the campaign import: visual geometry and textures only (no AI, weapons, scripts or campaign collision); one texture layer per material; rigged models are static, and some Covenant characters' parts sit away from the body; whole campaign levels haven't been prepared for Sapien yet and will likely exceed Halo 3's 1,024-instance limit, so prepare a section.

## Fixed in 0.10.1

- **`.scenario` imports no longer stop with "JMS triangle uses a missing material".** Some original source files contain faces that were never given a material (070_waste's cinematic sky has 1,498 of them). These faces are now skipped and listed in the import report, and the rest of the level imports. 070_waste now imports with 13/13 BSPs, 4,609 placements and all 5 skies.
- **BSP pieces are no longer dropped for a few unassigned faces.** Only those faces are left out, so geometry missing from earlier imports comes back. Cached scenario imports rebuild once.
- **No more white surfaces in `.scenario` imports** when two shaders share a name (the level's own shader is used, as Tool does), and **detail-mapped surfaces are no longer too dark**: the preview now matches Halo 3's detail brightness.
- **Faster viewport on whole levels.** Level imports now turn off EEVEE's viewport shadows, which removes the "Shadow buffer full" message and speeds up Material Preview on big levels. **Folders and Setup → Viewport Shadows** turns them back on.
- **Preparation no longer fails with "ASSERTION FAILED … faux_material.cpp … parameter_success".** Halo Tool's test lighting cannot process some animated shaders (for example 070_waste's sky waterfall, `waterfall.shader_custom`). The level is now kept without test lighting, and the preparation report names the shader and the objects using it.

Updating from 0.10.0: remove the old add-on, restart Blender, then install the new ZIP.

## What's new in 0.10

- **Import level from .scenario (Halo 3).** HaloBridge now reads a level from your extracted H3EK tags instead of reconstructing it from compiled `.map` data. BSP geometry comes from the source files stored in the BSP tags, with original instance names and transforms; every scenery, crate, machine, control and vehicle placement comes from the scenario with its variant; each surface gets its real shader tag and source flags. The matching `.map` only supplies preview textures, looked up by exact shader path.
- **Original scenery stays scenery.** When you prepare a scenario import for Sapien, unedited scenery is written as placements of its own scenery tag, keeping its collision and physics. Vehicles keep their vehicle tags. Edited objects export as static geometry.
- **Halo 3: ODST** is a full game: index and import its `.map` files, import levels from the H3ODSTEK `.scenario`, and prepare ODST Sapien levels.
- **Halo: CE and Halo 2** import from MCC `.map` files, and from their Editing Kit `.scenario` tags (HCEEK / H2EK; the kit's own Tool builds the map first).
- **Halo: Reach `.scenario` import** places objects from the HREK scenario (geometry comes from the matching `.map`).
- **Every game in one level.** Assets from any import game can be prepared together in a Halo 3 Sapien level; their shaders are converted automatically.
- **Skies from any game.** **Sapien Sky** has a **Game** choice: use a Halo 3 kit sky, or convert a Halo: CE, Halo 2, ODST or Reach sky into your level.
- **Index .scenario Assets** and a source filter (All / .map / .scenario) in the asset list.
- **Blender 5.2 support.** Runs on Blender 4.0 through 5.2. On 4.1 and newer, use the current Halo Asset Blender Development Toolset release.
- **Detect folders** finds Editing Kits and MCC in every Steam library and Xbox app / PC Game Pass installs, and storage follows a Documents folder moved by OneDrive.
- **Sidebar:** collapsible sections, **(Default) Automatic** object collision (the per-material Collision control is gone), output level name starts as `levelname123`, and **Remove Grey Blender Fog** sets 0.1 m / 999999 m.
- **Fixes:** vehicles and invisible blocks with pitch or roll were rotated incorrectly on export; Halo: CE / Halo 2 textures that imported white; Tool collision rejections are retried automatically.

See the [changelog](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/CHANGELOG.md) for every change.

## Requirements

| Component | Required version / purpose |
| --- | --- |
| [Windows](https://www.microsoft.com/windows/) | 64-bit Windows |
| [Blender](https://www.blender.org/download/) | **4.0 to 5.2** (5.2 recommended) |
| [Halo 3 Mod Tools / H3EK](https://store.steampowered.com/app/1695791/Halo_3_Mod_Tools__MCC/) | Extract the supplied tag archives. Required for Halo 3 scenario import and Halo 3 Sapien preparation. Other games' kits (H3ODSTEK, HREK, HCEEK, H2EK) are needed only for their own `.scenario` import / ODST preparation |
| [Halo: The Master Chief Collection](https://store.steampowered.com/app/976730/Halo_The_Master_Chief_Collection/) | Steam or Xbox app / PC Game Pass, with the games you import from installed. Supplies preview textures, the asset browser and `.map` imports |
| [Halo Asset Blender Development Toolset](https://github.com/General-101/Halo-Asset-Blender-Development-Toolset) | Blender 4.1–5.2: v432 or newer. Blender 4.0: v364 or v432. Provides Halo Blender properties and ASS export |
| [.NET Desktop Runtime](https://dotnet.microsoft.com/en-us/download/dotnet/10.0) | **10, Windows x64 Desktop Runtime**, for map extraction |
| [.NET Framework](https://dotnet.microsoft.com/en-us/download/dotnet-framework/net48) | **4.8+**, for the Editing Kit tag helper |

## How to Install

1. Install Blender and the runtimes above.
2. Install and enable the **Halo Asset Blender Development Toolset** (v432 or newer; v364 also works on Blender 4.0).
3. Download **HaloBridge-0.10.1.zip** from this release's Assets.
4. In Blender, open **Edit → Preferences → Add-ons**, use the drop-down at the top right → **Install from Disk…** (on 4.0/4.1: **Install**), select the ZIP without extracting it, and enable **HaloBridge - Halo Level Importing**.
5. In the 3D View, press **N** and open **HaloBridge**.
6. Choose an **Import game**, then use **Folders and Setup → Detect folders** (it finds Steam libraries on any drive and Xbox app / Game Pass installs) or enter the Editing Kit and maps paths, then run **Check setup**.
7. **A whole level:** choose a scenario and click **Import level from .scenario**, or choose a `.map` and click **Import entire .map**, or (Halo 2: Anniversary) choose a campaign level and click **Import campaign level**. **Individual assets:** click **Index .map Assets**, **Index .scenario Assets** or **Index All Individual Assets**, then preview and place from the **Indexed Asset List**. Use Material Preview to view textures.

**Updating:** save your work, finish or cancel jobs, remove/disable the old add-on in Preferences, restart Blender, and install the new ZIP. Keep your cache, project manifests and backups.

[Full installation guide](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/INSTALLATION.md) · [Importing guide](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/IMPORTING.md) · [First Sapien test map](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/FIRST-MAP.md)

## Known limits

Halo 3 / ODST scenario import needs the source files stored in kit tags; a BSP without them is reported and skipped. Reach Sapien preparation is not available. Converted skies from other games carry no sky lighting (test lighting uses the destination kit's sky), and Halo: CE cloud tints are not converted. Weapons and equipment are reference-only; AI, scripts, decals, lighting and zone sets are not imported. Sapien preparation remains experimental and builds a new level from current meshes plus original scenery and vehicle placements. Preview shaders approximate engine rendering. See [limits](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/LIMITATIONS.md).

[Feature index](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/FEATURES.md) · [Troubleshooting](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/TROUBLESHOOTING.md) · [Error reference](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/ERRORS.md) · [Halo 2: Anniversary campaign](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/blob/main/docs/H2A-CAMPAIGN.md) · [Report a problem](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/issues/new/choose)
