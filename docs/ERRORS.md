# Error and message reference

[Home](../README.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Sidebar reference](FEATURES.md) · [Known limits](LIMITATIONS.md)

This page lists the messages HaloBridge can show, grouped by what you were doing, with what each one means and how to fix it. Messages are quoted as HaloBridge writes them. Parts in *‹angle quotes›* are filled in with your object, file or tag names.

**Where messages appear**

- **HaloBridge Warnings and Messages** (near the bottom of the sidebar, and as a popover in the 3D View header) shows the latest result or problem. **ACTION REQUIRED** means something needs your attention.
- **Open diagnostic report** opens the full text in Blender's Text Editor (**HaloBridge diagnostics**). It lists *every* issue found so far, numbered.
- **Open map import report** / **HaloBridge scenario import report** list what a level import couldn't bring in.
- **Open live activity log** / **Open live compiler output** (in **Map Preparation Status**) show what preparation is doing, and Halo Tool's own output.
- Every helper run keeps a log in your storage folder's `jobs` folder. A message ending in "full log: ‹path›" names it.

Search this page with **Ctrl+F** for a few words of your message.

## Contents

- [Setup and Check setup](#setup-and-check-setup)
- [Folders, maps and the asset list](#folders-maps-and-the-asset-list)
- [Importing a .scenario](#importing-a-scenario)
- [Importing an entire .map](#importing-an-entire-map)
- [Halo 2: Anniversary campaign](#halo-2-anniversary-campaign)
- [Placing assets, model parts and vehicles](#placing-assets-model-parts-and-vehicles)
- [Shaders and materials](#shaders-and-materials)
- [Editable materials](#editable-materials)
- [Sky](#sky)
- [Preparing for Sapien: before compiling](#preparing-for-sapien-before-compiling)
- [Preparing for Sapien: level name and ownership](#preparing-for-sapien-level-name-and-ownership)
- [Halo Tool compiler errors](#halo-tool-compiler-errors)
- [Lighting](#lighting)
- [Jobs, cancelling and timing](#jobs-cancelling-and-timing)
- [Blender and Sapien messages](#blender-and-sapien-messages)

## Setup and Check setup

| Message | What it means | How to fix it |
| --- | --- | --- |
| HaloBridge needs Blender 4.0 or newer (4.0 and 5.2 are the tested targets). | Your Blender is too old. | Install Blender 4.0 to 5.2 (5.2 recommended). |
| This alpha requires 64-bit Windows. | The helpers and Editing Kits are 64-bit Windows programs. | Use 64-bit Windows 10 or 11. |
| Install and enable the Halo Asset Blender Development Toolset (General-101). Use v432 or newer (Blender 4.0 can also use v364). | The second add-on HaloBridge exports level geometry with is missing or disabled. HaloBridge also checks for it before placing assets. | Install the [toolset](https://github.com/General-101/Halo-Asset-Blender-Development-Toolset/releases) and tick it in **Edit → Preferences → Add-ons**. |
| On Blender 4.0, use Halo Asset Blender Development Toolset v364 (2.364.0) or v432 (2.432.0). | Blender 4.0 only works with those two toolset versions. | Install v432 (or v364). |
| … cannot export on Blender ‹version› (Python 3.13). Install the current General-101 toolset release (v432 or newer) … | Toolset v364 uses a trick Python 3.13 (Blender 5.x) no longer allows; its export fails. | Install toolset v432 or newer and prepare again. |
| The installed Halo toolset does not provide the ASS export options HaloBridge uses (‹options›). … | The toolset is a different or modified version. | Install the current General-101 release. |
| Select the ‹game› Editing Kit folder (‹kit›); missing ‹file›. | The Editing Kit path is wrong, points at a subfolder, or the kit isn't installed. `tool.exe`, `sapien.exe` and `bin\ManagedBlam.dll` must be inside. | Use the kit folder that contains `tool.exe` (e.g. `...\H3EK`, not `...\H3EK\tags`). |
| Optional: select the ‹game› Editing Kit folder … to import its .scenario tags; tool.exe was not found. | Only `.scenario` import for that game needs its kit. | Ignore it if you only import `.map` files. |
| Extract the Editing Kit tag archives; ‹sky›.scenario is required for starter sky settings. | The kit's tag archives aren't extracted, so the default sky scenario (`levels\multi\isolation\isolation`) is missing. | Extract the archives the kit ships with, keeping their folders (see [Installation](INSTALLATION.md#1-install-the-games-and-mod-tools)). |
| Select the installed MCC maps folder for the chosen game containing .map files. | The **.map Files** path is empty, wrong, or has no `.map` files. | Click **Detect folders**, or choose the game's maps folder (table in [Supported games](GAMES.md#folders)). |
| Install Microsoft .NET 10 Desktop Runtime for Windows x64, then restart Blender. | The extraction helper can't run. The plain ".NET Runtime" isn't enough. | Install **.NET Desktop Runtime 10, x64**, then restart Blender. |
| Install .NET Framework 4.8 or newer for the scenario helper. | The Editing Kit helper can't run. | Install .NET Framework 4.8. |
| Helper missing: ‹name›. … / HaloBridge helper is missing. Install the release add-on ZIP, or build helpers from source. … | The `bin` folder of the add-on is incomplete: GitHub's "Source code" ZIP was installed, or security software quarantined a file. | Install **HaloBridge-‹version›.zip** from the release Assets. Restore quarantined files. |
| The installed tag helper is older than this add-on. … | The add-on and its helpers come from different versions. | Reinstall the release ZIP (remove the old add-on and restart Blender first). |

## Folders, maps and the asset list

| Message | What it means | How to fix it |
| --- | --- | --- |
| Choose the selected game .map Files folder first, or type a filename manually. | The map picker needs the maps folder. | Set **.map Files** (or click **Detect folders**). |
| No .map files found in ‹folder›. … | The folder exists but has no maps. | Choose the right folder; for Halo 2 it's `halo2\h2_maps_win64_dx11`, for Anniversary multiplayer `groundhog\maps`. |
| Choose an existing .map file for the selected game. / Choose an existing MCC .map filename for the selected game. | The map name doesn't exist in the maps folder. | Use the **⌄** picker, or type the name with `.map`. |
| The map belongs to a different game (‹game›). Change the Halo game selector or maps folder. | The chosen map is from another game than **Import game**. | Switch **Import game**, or choose that game's maps folder. |
| Select an MCC PC Halo: CE, Halo 2, Halo 2: Anniversary, Halo 3, Halo 3: ODST or Halo: Reach map. | The file isn't an MCC PC map HaloBridge reads (Xbox 360 or original-Xbox maps, or a damaged file). | Use maps from your MCC PC install. |
| The saved asset catalogue is missing. Click Detect folders, then Index map. … | The asset list file in storage was deleted or the storage folder changed. | **Detect folders**, then index again. |
| This asset is no longer in the catalogue. Click Detect folders to reload the list, then select the asset again. | The list changed (deleted or re-indexed). | Reload with **Detect folders**. |
| Select an asset first. / Select an asset in the current list first. | Nothing is highlighted. | Click a row in **Indexed Asset List**. |
| Choose an asset indexed for the selected Halo game. | The highlighted asset belongs to another game than **Import game**. | Switch **Import game** to the asset's game. |
| Check at least one asset in this tab first. | Bulk actions need ticked rows. | Tick rows or **Select all**. |
| Uncheck assets from a different or unverified game. | Ticked rows mix games. | Clear the other game's ticks. |
| No matching asset-list history is available. / The catalogue changed outside this list. Reload it … | Undo/Redo has nothing to undo, or the list was changed elsewhere. | Reload with **Detect folders**. |
| No .scenario tags found under ‹kit›\tags. … | The kit's tags aren't extracted, or the kit path is wrong. | Extract the tag archives; check the kit path. |

## Importing a .scenario

| Message | What it means | How to fix it |
| --- | --- | --- |
| Enter a scenario path relative to the Editing Kit tags folder, for example levels\multi\guardian\guardian. | The scenario field is empty or absolute. | Use the **⌄** list, or type the path without `.scenario`. |
| Scenario not found in the Editing Kit tags: ‹path›.scenario. … | No such tag in the kit. | Check the path; extract the kit's tag archives. |
| The Editing Kit could not open ‹path›.scenario. Its tags may be unfinished or damaged or saved by a different kit version. … | ManagedBlam refused the tag. | Open it in Sapien to check, or choose another scenario. |
| Editing Kit scenario import is not available for ‹game›. | That game has no `.scenario` route (Halo 2: Anniversary). | Use **Import entire .map**, or the Anniversary campaign import. |
| Choose the ‹game› Editing Kit folder (‹kit›, it contains tool.exe and tags) first. | The kit path is empty. | Set it in **Folders and Setup**. |
| BSP ‹tag›: no embedded source geometry in its Editing Kit tag. Use Import entire .map for this level. | That BSP tag doesn't contain the source file HaloBridge rebuilds geometry from. | Use **Import entire .map** for that level. |
| BSP ‹tag›: ‹n› face(s) have no material in the original source file and were skipped. | Bungie's source had faces without a material (070_waste's cinematic sky has 1,498). | Nothing to do; the rest imports. |
| ‹tag›: skipped ‹n› degenerate source triangle(s). | Zero-area triangles in the source. | Nothing to do. |
| ‹render model›: no embedded source in its tag; used the map mesh with its default variant. | The render model has no stored source; geometry comes from the `.map`. | Set the game's **.map Files** folder so this fallback works. |
| ‹render model›: fallback mesh failed: … | Neither source nor map mesh could be read. | Check the maps folder is complete; report it if it persists. |
| Material "‹name›" has no unique shader reference in ‹folders›. Assign a Halo shader before preparing. | The source material name matches no shader, or several. | Assign one under **Shaders** before preparing. |
| Material "‹name›" in ‹folders› has no shader in the original tag either … | Bungie left it on `shaders\invalid`. | Assign a shader under **Shaders**. |
| ‹n› shader(s) were not found in ‹map›; they have no preview texture. | Preview textures come from the matching map, which doesn't contain those shaders. | Normal for some shaders. Set the right maps folder. |
| Halo: Reach Editing Kit tags carry no source models, so ‹n› object model(s) use the mesh from ‹map› with their default variant. … | Reach geometry comes from the `.map`. | Expected; set the Reach maps folder. |
| Nothing could be imported from ‹scenario›. … | Every part failed. The message lists the first warnings. | Read the warnings; usually the kit or maps path. |
| Building a map from a .scenario is only used for Halo: CE and Halo 2. / Tool did not produce ‹map›. See ‹log› | The Halo CE / Halo 2 kit's Tool couldn't build the scenario. | Read the Tool log; check the kit folder and that its tags are intact. |
| ‹name› is no longer in ‹scenario›. Index the scenario again. | The asset list is older than the scenario. | **Index .scenario Assets** again. |
| Embedded geometry failed its checksum. … / … incomplete or its stored size is incorrect. / Source BSP changed during recovery. … | A source file stored in a tag is damaged, or the tag changed while it was read. | Close tag editors and retry. If it persists, use **Import entire .map**. |
| JMS version ‹n› is not supported (Halo 3 uses 8205-8213). / ASS version ‹n› is not supported. | A source file is from another toolchain. | Use **Import entire .map** for that level. |

## Importing an entire .map

| Message | What it means | How to fix it |
| --- | --- | --- |
| Map extractor did not create a scene manifest. | The extractor stopped. | Open the log in `jobs`; check .NET 10, disk space and that the maps folder is complete. |
| The map has no decoded visual placements. | Nothing in the map could be read as geometry. | Check the map isn't damaged; for a cutscene-only level this is expected. |
| Incomplete import: ‹n›/‹m› terrain BSPs. This scene is not ready for Sapien preparation. | Some BSPs didn't decode (they're listed). | Keep shared maps next to level maps, make sure storage is writable, then import again. Some developer-only BSPs never decode. |
| Unsupported original-map scene manifest. | A cache from a much older version. | Import the map again. |

## Halo 2: Anniversary campaign

See also [Halo 2: Anniversary campaign → Troubleshooting](H2A-CAMPAIGN.md#troubleshooting).

| Message | What it means | How to fix it |
| --- | --- | --- |
| Halo 2: Anniversary campaign files not found. Select MCC's groundhog maps folder (the campaign … is in halo2\preload\paks of the same MCC install). | HaloBridge couldn't find `halo2\preload\paks\shared.pck` from your **.map Files** folder. | Set **.map Files** to MCC's `groundhog\maps` (or directly to `halo2\preload\paks`) and install the Anniversary campaign content. |
| No campaign levels found. … | Same cause, from the level picker. | As above. |
| Choose a campaign level .pck from ‹folder›. | The level filename doesn't exist. | Use the **⌄** picker; include `.pck`. |
| This .pck has no .lg level scene (only campaign level paks do). | `shared.pck` / `cache.pck` aren't levels. | Choose a level such as `01a_tutorial.pck`. |
| The campaign level extractor did not create a scene manifest. | The extractor stopped. | Read the log in `jobs` (named in the message). |
| The map has no decoded visual placements. (on `00a_introduction`) | That level is a cutscene with no geometry. | Choose another level. |
| shared.pck not found next to the level … | The level `.pck` was copied away from MCC's paks folder. | Use the files in place in MCC. |
| Asset not found in shared.pck: ‹tag› | The asset list is older than the installed game files (MCC updated). | **Index All Individual Assets** again. |
| This template has no visible geometry. | The template only has helpers or volumes. | Choose another asset. |
| Status: Rigged model, static rest pose: some characters' parts are out of place | Not an error; a note on characters with skeletons. | See [rigged models](H2A-CAMPAIGN.md#index-and-place-individual-assets). |

## Placing assets, model parts and vehicles

| Message | What it means | How to fix it |
| --- | --- | --- |
| Select a mesh to apply this material to, or click Preview. | **Apply material** needs a target. | Select a mesh in the 3D View. |
| Select the level object that should receive this material; the preview sphere is not exported. | The preview sphere is selected. | Select your level object. |
| No mesh imported from ‹file› | A legacy AMF/JMS file was empty or unreadable. | Re-export the file; prefer indexing the `.map`. |
| Select a model with part metadata. / Select a placed model with part metadata. | The selected object has no switchable parts. | Select a placed model that shows **Model Parts and Variants**. |
| This model mesh was edited. Place a fresh copy to change variants without losing your edits. | Switching parts rebuilds the mesh, which would throw away your edits. | Place a new copy, switch its parts, then edit. |
| The part selection is no longer available. Reimport the model. | The cached parts changed (newer version). | Place the asset again. |
| Place the model first, then separate its parts. / Enable at least one part first. / Unparent attached child objects before separating this model. | **Separate** needs a placed model with visible parts and no children. | Do as the message says. |
| Use static mesh instead before changing parts; an original vehicle tag controls its own variants. | The object is an original vehicle placement. | **Use static mesh instead** first. |
| Select the imported vehicle model in the 3D View first. / Find matching vehicles for this model first. | Vehicle steps out of order. | Select the model, **Find matching original vehicles**, then **Use original vehicle tag**. |
| No installed Halo 3 vehicle tag references this model. Check that the Editing Kit tags are extracted. | No vehicle tag uses this model. | Extract the kit's tags; otherwise keep it static. |
| This object has no verified original model identity. Place its model from the Indexed Asset List first. | Only placed (not hand-made) models can become original vehicles. | Place the model from the list. |
| Remove modifiers before using an original vehicle tag … / This preview mesh was edited. … | Original vehicles use the game's model, so edits can't carry over. | Remove modifiers / reimport, or keep it static. |
| Original vehicle placement requires assets from the Sapien destination game; use the static mesh instead. | Only Halo 3 (or ODST) vehicles can be original placements in their own game. | Keep it static. |
| Original vehicles require positive uniform scale. / Remove transform shear before placing this vehicle. | Vehicles can't be stretched. | Apply uniform scale; clear shear (unparent or apply transforms). |
| The starter template uses Halo 3 assets … / The starter template needs 010_jungle.map … | **Create starter level shell template** needs Halo 3. | Set **Export to Sapien** to Halo 3 and the Halo 3 maps folder. |
| Switch to Object Mode first. | **Origin to Geometry** needs Object Mode. | Press Tab. |
| Make linked library meshes local before centering all scene origins. | Linked meshes can't be changed. | **Object → Relations → Make Local**. |

## Shaders and materials

| Message | What it means | How to fix it |
| --- | --- | --- |
| Choose an Editing Kit with extracted tags first. | The shader scan needs the destination kit's tags. | Set the kit; extract its tags. |
| Select an object with an active material. / Scan existing shaders and choose one first. | **Assign shader** steps out of order. | Select the object and material slot, **Scan existing shaders**, choose one. |
| The Editing Kit changed. Open the shader picker again. | The kit path changed after scanning. | Scan again. |
| Missing or ambiguous Halo shader: ‹tag› / Missing or ambiguous shader: ‹tag› | The material's shader tag doesn't exist in the destination kit, or exists twice. | Assign an existing shader under **Shaders**. |
| No unique shader collection mapping for ‹tag›. Choose a shader with an existing collection prefix. | Halo's `shader_collections.txt` has no prefix for that folder. | Choose a shader from a standard folder. |
| No existing Halo shader is assigned. Apply a HaloBridge material to the object, not just select it in the Asset List. | A material has no shader. | Apply a material from the list, or assign a shader. |
| Unsupported material nodes. Use the imported image textures or assign a Halo 3 shader. | A converted material's node tree was changed into something the converter can't read (only image textures, Normal Map and Separate Color nodes are read). | Restore the imported nodes, make it an editable material, or assign a Halo 3 shader. |
| Unsupported texture mapping; use imported UV mapping. / Texture tiling must be positive. | The texture's mapping isn't a UV multiply. | Use UV coordinates with a positive tiling. |
| No Principled preview material found. / No supported Principled preview material. | The material has no Principled BSDF. | Use an imported material or assign a shader. |
| Missing texture: ‹path› | The image file is gone (cache deleted, `.blend` moved). | Reimport the asset or level, or pack resources before moving files. |
| Material conversion: ‹material›: ‹reason› | A material from another game couldn't be converted (reasons above). | Fix that material, or enable **Skip objects with export problems**. |

## Editable materials

| Message | What it means | How to fix it |
| --- | --- | --- |
| Select a mesh with a UV map first. / Editable materials require a UV map. | Painting needs UVs. | Add a UV map (**UV → Unwrap**). |
| Place the asset first before creating editable materials. | A preview can't be edited. | Place it. |
| Apply an imported material first. / Select a material with a Principled shader. / The current material needs a base-color image. … | The material isn't one HaloBridge imported. | Apply an imported material, then convert it. |
| Select Create editable colors for vehicle paint. | Vehicles can't have terrain paint. | Use **Create editable colors**. |
| This terrain material was changed by hand. Create the paintable terrain again. | Its nodes no longer match. | Create it again. |
| Halo 3 terrain shaders have at most four layers, and this terrain already has four. | Halo 3's limit. | Reuse a layer. |
| Editable paint textures need UVs inside 0-1. … | Baking uses one UV tile. | Unwrap into 0-1; use layer tiling for repeats. |
| Texture resolution must be 512, 1024, 2048 or 4096. | An invalid size was stored. | Choose one of the sizes. |
| Choose an image for ‹layer›. / Use a Normal Map node for editable normal textures. / Unsupported editable-material node: ‹node›. … | A layer is incomplete or uses unsupported nodes. | Load an image, or restore the material. |
| Texture bake did not finish. | Blender's bake failed (often out of memory). | Lower **Texture resolution** and try again. |
| ‹object›: select an original vehicle material and create editable colors from it. / … two paint materials replace the same original shader … / original vehicle paint requires repeating images and whole-number UV tiling. | Vehicle paint rules. | Paint the vehicle's own material once, with whole-number tiling. |

## Sky

| Message | What it means | How to fix it |
| --- | --- | --- |
| No sky chosen: preparation will stop. (sidebar) | **Sapien Sky → Game** is another game but no sky is placed. | Choose a sky, or set **Game** back to the destination. |
| Sapien Sky is set to a sky from another game, but its sky object (Sapien Sky collection) is missing. … | The placed sky was deleted. | Choose the sky again. |
| That sky is no longer in the ‹game› asset list. Index its map again. | The sky's list entry is gone. | Index the map again. |
| Sky source scenario must name an existing Editing Kit scenario without its extension, for example levels\multi\shrine\shrine. | The sky scenario path is wrong. | **Scan for map skies** and choose one. |
| ‹object›: the sky has no materials. / The sky JMS was not written. … | A converted sky couldn't be exported. | Choose the sky again; check the Halo toolset. |
| Enable the Halo Asset Blender Development Toolset to export the sky. | The toolset is off. | Enable it. |

## Preparing for Sapien: before compiling

Preparation checks the whole scene first and lists every problem at once (numbered). Messages starting with an object name (‹object›: …) are about that Blender object. With **Skip objects with export problems** on, those objects are left out instead (they stay in Blender and are listed in the report).

| Message | What it means | How to fix it |
| --- | --- | --- |
| There are no meshes to export. / The scene has no level geometry. | Nothing visible to export (hidden, previews and sky objects don't count). | Add or unhide geometry. |
| No exportable objects remain. … | Every object was skipped or invalid. | Fix at least one object. |
| No renderable surfaces remain. Add solid geometry with a Halo material before preparing. / The scene contains only sky faces; add solid geometry. | Only collision-only or sky faces remain. | Add solid geometry with a Halo material. |
| ‹object›: Faces use an empty material slot. Assign a HaloBridge material. / ‹object›: empty material slot. | Some faces have no material. | Assign one to those faces, or remove the empty slot. |
| ‹object›: assign a Halo shader before exporting. | Your own material has no Halo shader. | Assign one under **Shaders**. |
| ‹object›: Extends ‹n› world units from the origin; Halo 3 geometry must stay within ‹limit› units. … | The object is too far from the centre. Halo 3 levels must fit in a limited box. | Move it closer, scale it down, or delete it. Sky domes come from the **Sapien Sky** setting, not geometry. |
| ‹object›: Object has zero scale. / Object transform contains non-finite values. / Mesh contains non-finite coordinates. / Working scale must be finite and positive. | Broken transforms or vertices (NaN or infinite). | Apply or reset the transform; clean the mesh (**Mesh → Clean Up**). |
| ‹object›: No mesh faces remain after modifiers. | Modifiers delete everything. | Fix or remove the modifiers. |
| ‹object›: use positive uniform scale. / parent transforms introduce shear … | Original scenery, vehicles and blockers can't be stretched or sheared. | Use uniform scale; apply transforms; clear the parent. |
| ‹object›: Halo Tool rejected this object in an earlier preparation (‹reason›). Change it … or use Retry objects Tool rejected to try it again. | Tool refused this object last time, so it's left out. | Fix it (e.g. lower its Decimate ratio), or click **Retry objects Tool rejected**. |
| Original scenery tag is missing: ‹tag› / Original scenery requires positive uniform scale. … | An unedited scenario scenery object can't be written as its original tag. | Extract the kit's tags; use uniform scale. |
| Invisible block: original scenery/model/collision tags are missing. … / … could not be verified. … / Blocker geometry was edited … | Halo 3 invisible blockers reuse their original tags. | Extract the kit's tags; restore the blocker's mesh. |
| This scene mixes older 1x imports with new 100x imports. … | Scenes from very old versions used a different scale. | Keep them in separate scenes. |
| Halo 3 allows at most 1024 instanced geometry definitions in one BSP, and this level has more … / This level has ‹n› different instanced meshes; one Halo 3 BSP allows at most 1024 … | A Halo 3 limit: each distinct instanced mesh counts once (copies of one mesh count once). Whole imported levels can exceed it. | Delete or hide pieces you don't need (small scenery, crates, decorations), or join pieces that never move. |
| The exported level is ‹n› GB; Halo 3's Tool cannot import a level file this large … | Tool can't read level files over about 2 GB (it crashes with `MAXIMUM_MEMSET_SIZE`). Very detailed levels (Anniversary) can exceed it. | Remove parts you don't need, use simpler pieces, or turn on **Decimate very dense objects**. |
| An object was deleted or changed while preparation was reading the scene … | You edited the scene during stage 1. | Prepare again and leave the scene alone until stage 2 starts. |
| This confirmation expired. Prepare again. / The scene or setup changed. Prepare again … / The detected issues changed. … | The warning review is out of date. | Click Prepare again. |
| Review preparation warnings (box) | Preparation found things to confirm (objects that won't export, original scenery, vehicles, converted materials). | Read them; **Continue with warnings** or cancel. |

## Preparing for Sapien: level name and ownership

| Message | What it means | How to fix it |
| --- | --- | --- |
| Name your level first: replace Level_Name_Here … | The placeholder name from older versions. | Type a real name. |
| Output level name … is ‹name›. Enter a name such as shrine20, without .map, folders, spaces or capitals. … | Names must be 3–32 lowercase letters, digits or underscores, starting with a letter. | e.g. `my_first_map`. |
| Reserved Windows filename. | Names such as `con`, `aux`, `nul` can't be folder names. | Choose another name. |
| This level already exists and is not owned by HaloBridge. Choose a new level name. | A level of that name exists in the kit, and HaloBridge didn't create it (or its record is gone). HaloBridge never overwrites other levels. | Choose a new name. Don't delete project records to force it. |
| Manifest belongs to a different editing kit. / This output belongs to another map or Editing Kit. … | The level's record is from another kit. | Choose a new name. |
| This output was created using the older original-map mode. … / This level is an original-map copy. … | An old-style copy owns that name. | Choose a new name. |
| CONFLICT: Sapien changed Blender-owned placements. Restore those edits or explicitly choose Resolve conflict: use Blender. | Since your last build, the level was edited in Sapien on objects HaloBridge placed. | Click **Resolve conflict: use Blender** to overwrite those placements (content you added yourself in Sapien is kept), or undo them in Sapien. |
| Save and close Sapien before preparing the level. … / Cannot check whether Sapien is running. … | Tool can't write a level Sapien has open. | Save and close Sapien. |
| Prepare this level successfully before opening Sapien. / No previously successful export for this level. | **Open in Sapien** needs a successful build. | Prepare first. |
| Sapien export for ‹game› is not implemented. … / Reach Sapien export is not available yet. | Only Halo 3 and ODST are destinations. | Set **Export to Sapien** to Halo 3. |

## Halo Tool compiler errors

These come from Halo's own compiler (**Tool**). HaloBridge reads Tool's output, translates object names back to your Blender object names, and retries automatically where it can. The **live compiler output** shows Tool's raw text.

| Tool says | What it means | What HaloBridge does / how to fix it |
| --- | --- | --- |
| `degenerate collision edge` / `bad connections - N ambiguous` | An object's collision has edges too short, or edges shared by three or more faces. | HaloBridge recompiles that object with cleaned surfaces (near-duplicate vertices merged, zero-length edges and slivers removed), welds harder, then uses a box, then no collision, and reports which. Clean the mesh to keep detailed collision. |
| `ASSERTION FAILED … connected_geometry_plane_builder.cpp` | Tool crashed building collision, often for an object placed more than once with separate collision. | Treated like rejected collision (cleaned, box, none). With **Skip objects with export problems**, an object Tool still crashes on is left out. |
| `collision geometry is too large` | More than 32,767 collision surfaces in one object. | HaloBridge collides it with a simplified copy (Anniversary pieces: decimated and cut into parts of up to 10,000 triangles). |
| `section 'global' has too many vertices` | More than 32,767 render vertices in one part. | HaloBridge splits dense objects by vertex count before Tool runs. If it still happens, decimate the object. |
| `cluster N has too many parts (count=…)` | Too many separately sorted see-through pieces in one structure cluster (limit 255). | HaloBridge compiles see-through faces as separate pieces. Add portals (**Add portal grid**) for big levels. |
| `tool overflowed indices_word_block` | One cluster's mesh has more than 65,535 indices. | HaloBridge adds portal planes automatically for oversized structures; you can add your own with **Add portal grid**. |
| `couldn't build leaf map` (during portalization) | Portals don't meet the level's sealed boundary correctly, or faces lie exactly on a portal plane. | HaloBridge retries with instanced pieces, slabs and moved grids automatically. Move portals off symmetric centre lines; make sure portals reach the walls. |
| `cluster … has too many vertices` | A cluster passes Halo 3's per-section vertex limit. | HaloBridge compiles again with smaller clusters (up to 3 times). |
| `instanced geometry definitions` | More than 1,024 distinct instanced meshes. | See the instance-limit message above. |
| `MAXIMUM_MEMSET_SIZE` | Level file over about 2 GB. | See the file-size message above. |
| `unable to find shader` | A material's shader tag doesn't exist. | Assign an existing shader under **Shaders**. |
| `failed to add import info` | Tool couldn't embed a copy of a very large source file in the tag. | Harmless: the level still compiles, and HaloBridge ignores it. |
| `overlapping surfaces`, `duplicate triangle`, `degenerate triangle`, `open edge` (warnings) | Geometry quality warnings. Tool draws them in Sapien as red text and lines. | Listed by object in the preparation report. HaloBridge clears the red markers from the level unless **Show Tool warning markers in Sapien** is on. |
| `vertex shader entry point doesn't exist` (in Sapien, on water) | A Halo 3 water shader on faces Tool didn't build as water. | Fixed: HaloBridge marks water materials so Tool builds them as water. Prepare again. |
| `-1 is not a valid sky_lights_block index` | A converted sky had a sun but no sky light. | Fixed: such skies get a dim sky fill. |
| Halo did not confirm the level structure import or produce its scenario and BSP tags. | Tool finished without the expected tags. | Open the compiler output; usually an earlier error explains it. |
| Process exited with code ‹n› … (External job failed; full log: ‹path›) | A helper or Tool stopped. The message includes the end of its output. | Read the log. |

A failed compile restores the previous successful version of the level. Stage 3 (geometry) can't resume, but converted textures, compiled bitmaps and unchanged meshes are reused, so the next attempt is faster.

## Lighting

| Message | What it means | How to fix it |
| --- | --- | --- |
| `ASSERTION FAILED … faux_material.cpp … parameter_success` | Tool's test lighting can't evaluate some animated shaders (for example 070_waste's sky waterfall). | HaloBridge keeps the level without test lighting and names the shader and objects. Give them another shader, delete them, or turn off **Generate Test Lighting**. |
| `faux_rasterizer.cpp` crash with per-pixel pieces | Tool's draft lighting can't light per-pixel instanced pieces. | HaloBridge keeps pieces per-vertex with Tool's bake. Use the **H3LM** bake for per-pixel lighting. |
| Lighting bake is set to H3LM, but h3lm-lm.exe was not found in "‹folder›". … | The H3LM folder is wrong or not set. | Download the [H3LM Lightmapper](https://github.com/Zoephie/H3LM), unzip it, and choose its folder; or set **Lighting bake** to Tool. |
| Cancelled; H3LM installs nothing from a cancelled bake. | You cancelled the H3LM bake. | Nothing to do. |
| Halo 2 Editing Kit Tool not found: ‹path› / No Halo 2 lightmap found for ‹scenario› … / The Halo 2 Editing Kit did not export ‹file› | **Copy Halo 2's original lighting** needs the Halo 2 kit the level was built from, with the level lit. | Set the Halo 2 kit; light the level in H2EK first; or turn the option off. |
| Halo 2 scenario tag not found: ‹tag› / The Halo 2 Editing Kit did not export ‹scenario› | Halo 2 spawns and gameplay couldn't be read. | Check the H2EK path and scenario. |

## Jobs, cancelling and timing

| Message | What it means | How to fix it |
| --- | --- | --- |
| A HaloBridge job is running. Wait or cancel it first. / Wait for the current job or cancel it. | One job at a time. | Wait, or click **Cancel**. |
| Cancelled; the previous successful level is retained. | You cancelled preparation; the old level was restored. | Nothing to do. |
| Import cancelled. / Scenario import cancelled. / Job cancelled; no new placements were applied. / Batch placement cancelled … | You cancelled; nothing was changed. | Nothing to do. |
| The active scene changed during the job. Its result was not applied to this scene. | You switched scenes while a job ran. | Run it again in the scene you want. |
| Preparation seems stuck | Not a message, but common. Tool compiles many objects at once and can be silent for minutes. | Open the live logs: CPU use and "time since last output" show it's working. See [Troubleshooting](TROUBLESHOOTING.md#preparation-seems-stuck). |

## Blender and Sapien messages

| Message | What it means | How to fix it |
| --- | --- | --- |
| `Error: Shadow buffer full, may result in missing shadows and lower performance` (3D View) | EEVEE (Blender 4.2+) ran out of shadow memory on a whole level. | **Viewport Shadows: Off**. HaloBridge turns shadows off after level imports. |
| `Failed to create GPU texture from Blender image` (console) | Blender couldn't upload a texture to the graphics card (very large image, or out of video memory). | Use a smaller **Reduce Texture Size** / **Texture size**; close other GPU-heavy programs. |
| Pink surfaces | Blender can't find a texture file. | See **Missing texture** above. |
| `overflowed working portal stack during visibility traversal` (Sapien) | Too many portal clusters for Sapien's visibility. | Use fewer portals (larger **Every** spacing); HaloBridge's automatic portals already limit clusters to about 9,000 triangles each. |
| "Assertion Failed" pop-ups during `.scenario` import (older versions) | ManagedBlam raised a .NET assertion on some render models. | Fixed: written to the job log, and the model uses its map mesh. Update HaloBridge. |

---

Didn't find your message? See [Troubleshooting](TROUBLESHOOTING.md), then [report it](https://github.com/BarnacleBoii/HaloBridge-Blender-4.0-Asset-Map-Importer-Addon-BETA/issues/new/choose) with the diagnostic report (remove personal folder names first).
