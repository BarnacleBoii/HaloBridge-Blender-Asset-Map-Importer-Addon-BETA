# Sidebar reference

[Home](../README.md) · [Installation](INSTALLATION.md) · [Importing](IMPORTING.md) · [First map](FIRST-MAP.md) · [Troubleshooting](TROUBLESHOOTING.md)

This page goes through the HaloBridge sidebar from top to bottom and explains every control. Open the sidebar by hovering over the 3D View and pressing **N**, then clicking the **HaloBridge** tab.

Every section can be collapsed by clicking its header. The warnings, the preparation status and the Prepare / Open in Sapien buttons at the bottom always stay visible. While a job is running, buttons that would interfere with it are greyed out.

| Section | What it's for |
| --- | --- |
| [Import game](#import-game) | Which game you're importing from |
| [Folders and Setup](#folders-and-setup) | Folders, setup check, starter template, level, campaign and map imports |
| [Indexed Asset List](#indexed-asset-list) | Search, preview and place individual assets |
| [Model Parts and Variants](#model-parts-and-variants) | Choose visible pieces of a placed model |
| [Selected Asset](#selected-asset) | Apply materials, swap objects, the object's collision, original vehicles |
| [Shaders](#shaders) | Give a material a Halo shader |
| [Editable Materials](#editable-materials-experimental) | Paint terrain, recolor models |
| [Sapien Sky](#sapien-sky-experimental) | The level's sky |
| [Sapien Map Preparation](#experimental-sapien-map-preparation) | Build settings: textures, water, decimation, portals, lighting |
| [Warnings, status and Prepare](#warnings-status-and-prepare) | Build, monitor and open in Sapien |

Every message HaloBridge can show is explained in the [error reference](ERRORS.md).

## Import game

The drop-down at the very top: **Halo: CE, Halo 2, Halo 2: Anniversary, Halo 3, Halo 3: ODST, Halo: Reach**. It picks which game's folders, maps, asset list and storage you're working with. Each game keeps its own settings, so switching back and forth is safe and doesn't touch objects already in your scene. Objects remember which game they came from.

The import game is separate from the game you export to (**Export to Sapien**, further down). You can import from Reach and prepare for Halo 3 without switching back. See [Supported games](GAMES.md).

## Folders and Setup

| Control | What it does |
| --- | --- |
| **\<Game> Editing Kit** | The Mod Tools folder for this game, the one containing `tool.exe`. Not its `tags` subfolder. |
| **\<Game> .map Files** | The MCC folder holding this game's `.map` files, e.g. `...\Halo The Master Chief Collection\halo3\maps`. |
| **Detect folders** | Fills empty folder fields automatically by searching every Steam library, `SteamLibrary` folders on local drives, Foundry's settings, and Xbox app / Game Pass installs. It never overwrites a path you entered. It also reloads this game's saved asset list. |
| **Check setup** | Checks everything HaloBridge needs and writes a report (**HaloBridge diagnostics** in the Text Editor) with what to fix. See [Installation → Check setup](INSTALLATION.md#5-check-setup). |
| **Create starter level shell template** | Adds a paintable jungle ground plane, a see-through SkyBoundary guide wall and Master Chief for scale. Neither the wall nor Master Chief is exported. Needs the Halo 3 maps folder (`010_jungle.map`). |
| **Remove Grey Blender Fog (View Distance)** | Sets every 3D View's Clip Start to 0.1 m and Clip End to 999999 m, so large levels aren't cut off or faded. On huge ranges you may see some flickering; narrow the range if so. |
| **Viewport Shadows: On / Off** | Turns EEVEE's shadows on or off for the scene (Blender 4.2 and newer). Whole Halo levels need more shadow memory than EEVEE has, which shows as "Shadow buffer full" and slows Material Preview down. Shadows start **Off** in every scene (and HaloBridge turns them off again after **Import level from .scenario**, **Import campaign level** or **Import entire .map**). Halo's own lighting is baked, so the preview looks almost the same. Click to turn them back on, for example to render. |
| **Import sky with the level: ON / OFF** | ON by default. Click it to switch to OFF to import a `.scenario` or an entire `.map` without its sky objects; preparation then uses the **Sapien Sky** setting. |

### Import level from .scenario

Shown for games with Editing Kit support.

| Control | What it does |
| --- | --- |
| Scenario field and **⌄** | The scenario tag path, relative to the kit's `tags` folder and without `.scenario`. The arrow opens a searchable list of every scenario in the kit. |
| **Import level from .scenario** | Imports the whole level from its tags. The note underneath says where the data comes from for this game. See [Importing](IMPORTING.md#1-import-a-level-from-its-scenario-recommended). |
| **Index .scenario Assets** | Adds the level's own objects, instanced meshes and shaders to the asset list instead of importing everything. |

### Import Anniversary campaign level

Shown only when **Import game** is **Halo 2: Anniversary**, above **Import entire .map**. Full guide: [Halo 2: Anniversary campaign](H2A-CAMPAIGN.md).

| Control | What it does |
| --- | --- |
| Level field and **⌄** | The campaign level file (for example `01a_tutorial.pck`). The arrow lists the 15 campaign levels found in MCC's `halo2\preload\paks` (located from your **.map Files** folder, `groundhog\maps`). Choosing a level doesn't start anything. |
| **Import campaign level** | Imports the level's remastered geometry and textures at classic Halo 2 coordinates, in **Level geometry**, **Decals** and **Glass** collections. The highest detail only; engine helpers are left out. The temporary geometry files are deleted afterwards to save space. |
| **Index All Individual Assets** | Adds about 1,070 campaign models (props, weapons, characters, vehicles) and 2,250 texture materials to the asset list, under **H2A campaign**. Each is extracted the first time you use it. |
| **Reduce Texture Size** | 512, 1024, 2048 (default) or 4096: the largest width campaign textures are stored at. The same setting as **Texture size** under Sapien Map Preparation. Re-import to apply a new size to a level you already imported. |

### Import entire .map

| Control | What it does |
| --- | --- |
| **Choose .map file** and **⌄** | The map filename (with `.map`). The arrow lists every map in the maps folder. Choosing a map doesn't start anything. |
| **Import entire .map** | Imports the map's terrain, instances, objects and skies at their original positions. See [Importing](IMPORTING.md#2-import-an-entire-map). |
| **Index .map Assets** | Adds every model, piece of scenery, instance and material the map loads to the asset list. Nothing is extracted until you use an asset. |

### Other controls

| Control | What it does |
| --- | --- |
| **Origin to Geometry - all scene meshes** | Moves every mesh's origin (pivot) to the centre of its geometry. Handy after a whole-level import, where many objects share the level's origin. Use Ctrl+Z to undo. |
| **Advanced storage** | Shows **Storage location**, where HaloBridge keeps its cache and project records. Changing it doesn't move existing files; keep the original location for a level you're still working on. |

## Indexed Asset List

| Control | What it does |
| --- | --- |
| **Reveal selected asset in Outliner** | When on, selecting a placed asset expands and scrolls the Outliner to it. |
| **Undo / Redo** | Undo or redo list actions (hide, unhide, delete from list). Separate from Blender's Ctrl+Z. |
| **Imported Assets / Hidden Assets** | Your list, or the entries you've hidden. |
| **Vegetation, Rocks, Structures, Water, Materials** | Category toggles. Categories are guessed from names, so if you can't find something, turn them all on. |
| **Level Imported** | Show one indexed level or **All Levels**. The same asset can appear under several levels. |
| **All Sources / .map Assets / .scenario Assets** | Show assets indexed from `.map` files, from `.scenario` tags, or both. A short note explains what each is best for. |
| **Search Assets** | Filters by name, source level or asset type as you type. **X** clears it. |
| The list | Click a row to highlight it (and preview it, if Preview Mode is on). Tick rows for bulk actions. The line below shows how many entries are visible out of the total. |
| **Preview Mode: ON / OFF** | When on, clicking a row shows that asset at the 3D cursor as a temporary preview. Turning it off removes the preview. |
| **Select all / Clear checks** | Tick or untick every visible row. Shows how many are ticked. |
| **Hide / Unhide** | Move ticked entries to Hidden Assets, or back. |
| **Delete checked from list** | Remove ticked entries from the list only. Placed objects and cached files are untouched. |
| **Place asset(s)** | Place the ticked assets together at the 3D cursor, or, with nothing ticked, the highlighted asset (keeping the preview's position, rotation and scale). Turns Preview Mode off. |

The first use of an asset extracts its mesh and textures, which can take a moment; later uses come from the cache.

## Model Parts and Variants

Appears when you select a placed model that has parts (vehicles, characters, crates with damage states and so on).

- Click the arrow next to a **region** (for example *hull* or *turret*) to list its choices, and tick the ones you want visible. The checkbox next to the region toggles all of its choices. Parts stay where they are, and the mesh is rebuilt immediately.
- Halo 2: Anniversary campaign models have regions for armor variants (**helmet**, **lights**, **head**...), **shield**, **damage** and **lod**; only the default look is on when placed. See [Model parts and variants](H2A-CAMPAIGN.md#model-parts-and-variants).
- **Separate enabled parts into objects** splits the visible parts into separate objects you can move individually.
- **Separate all parts and variants into objects** splits every choice, including hidden ones, so several pieces may overlap. Pick one in the Outliner before moving it.

Place a preview first; a preview can't be separated.

## Selected Asset

| Control | What it does |
| --- | --- |
| **Apply material to selected object** | With a material row highlighted in the list and a mesh selected, adds that material as a new slot and assigns it (to selected faces only in Edit Mode). |
| Asset details | The highlighted asset's status, source level and a thumbnail. |
| **Swap selected object(s) to selected index asset** | Replaces each selected object with the highlighted asset, keeping its position, rotation and collection. The asset keeps its original size. If the button is greyed out, a note below explains why. |

### Collision

**Collision: ‹object›** appears for a selected mesh (not for an original vehicle placement). It sets how that object collides in game:

| Choice | Behaviour |
| --- | --- |
| **(Default) Automatic** | Uses the object's original collision from its game's Editing Kit when HaloBridge can prove the mesh is unchanged (Halo 3, ODST, Reach models). Otherwise characters and shields get a simple box, and everything else uses its own mesh surfaces. Halo foliage shaders (including Halo 2: Anniversary foliage) are walk-through. |
| **Mesh surfaces** | The object's faces are solid. |
| **Simple box** | One solid box around the object, including any gaps inside it. |
| **No leaf collision** | For vegetation: see-through surfaces (leaf cards, cut-out or blended materials) are walked through; trunks and other solid surfaces keep their collision. |
| **No collision** | Rendered only: players, vehicles and projectiles pass through the whole object. |

To set many objects at once, select them all with the one you've set made active, then right-click the setting → **Copy to Selected**. To make a single material walk-through, tick the Halo toolset's **Render Only** flag on it in Blender's Material Properties. When Tool rejects an object's collision, HaloBridge retries with cleaned surfaces, then a box, then no collision; the preparation report lists which collision route each object used.

### Original vehicles

**Original Halo 3 Vehicle** (or ODST) appears for an imported vehicle model:

| Control | What it does |
| --- | --- |
| **Find matching original vehicles** | Looks in your Editing Kit for vehicle tags that use this model. |
| **Use original vehicle tag** | Choose one. The object becomes a placement of the real vehicle: drivable, with its own collision and physics. Mesh edits don't carry over. |
| **Use static mesh instead** | Goes back to exporting the mesh as static geometry. |

## Shaders

Every exported surface needs a Halo shader tag. This section sets one for the **active material** of the **selected object**, both shown at the top. A note warns you if the material is shared by other objects (they'll change too).

| Control | What it does |
| --- | --- |
| **Scan existing shaders** | Reads every shader in the destination Editing Kit. Do this once, and again after adding shaders to the kit. |
| **Choose an existing shader...** | Opens a search box over all scanned shaders. Type part of a name or folder. |
| **Enter shader path manually** | Instead, type a shader path relative to the kit's `tags` folder, without the extension (e.g. `levels\multi\guardian\shaders\guardian_metal`). |
| **Assign shader to active material** | Sets that shader for Sapien. It doesn't change the Blender preview; to refresh the preview use **Load Halo Shader Textures/Masks** under Editable Materials. |

Imported materials already carry their original shader, so you only need this for your own materials or to change one.

## Editable Materials (Experimental)

Turn an imported material into one you can paint or recolor; preparation bakes it into new Halo 3 textures and shaders in your level folder. Full guide: [Editable materials](EDITABLE-MATERIALS.md).

| Control | What it does |
| --- | --- |
| **Load Halo Shader Textures/Masks for Currently selected Material** | Reloads the selected material's original textures, layers and color masks from its `.map`. Also refreshes older previews. |
| **Create paintable terrain** | Converts a terrain material into numbered shader layers you can paint between. |
| **Create editable colors** | Converts a material into a base texture with four mask-driven tint colors. |
| **Texture resolution** | 512, 1024, 2048 or 4096: the size of the baked texture. |
| **Repeat settings** | Shows X/Y/Z tiling for each texture. |
| **Shader 1–4** sections | Each terrain layer, with its texture images and a **Paint** button. |
| **Paint original blend** | Paint back the level's original mix of layers. |
| **Pack texture edits into blend** | Saves painted images inside your `.blend`. Do this before saving. |

## Sapien Sky (Experimental)

| Control | What it does |
| --- | --- |
| **Game** | Which game the sky comes from. Defaults to the Sapien destination game. |
| **Scan for map skies** (destination game) | Reads every scenario in the destination kit and lists the levels that have a sky. |
| **Sky** (destination game) | Choose a level; its sky tags are used as they are, lighting included. **Original map / default sky** uses the imported level's sky, or Isolation. |
| **Sky** (other games) | Lists sky models in that game's asset list (index one of its levels first). Choosing one places it in a **Sapien Sky** collection; preparation converts it into a Halo 3 sky. |
| **Remove sky object** | Deletes the placed converted sky. |

If you've chosen another game but no sky, a warning says preparation will stop. Details: [Use a sky from another game](IMPORTING.md#use-a-sky-from-another-game).

## (Experimental) Sapien Map Preparation

| Control | What it does |
| --- | --- |
The controls in the order they appear:

| Control | What it does |
| --- | --- |
| **Export to Sapien** | **Halo 3** or **Halo 3: ODST**. Reach is listed but not available yet. Assets from any other game are converted ("Mixed-game meshes convert to the destination"). |
| **Output Level Name (without .map)** | Your level's name: 3–32 lowercase letters, digits or underscores, starting with a letter. Starts as `levelname123`; give each level its own name. The level is written to `levels\multi\<name>` in the Editing Kit. HaloBridge only overwrites a level it created itself. |
| **Texture size** | 512, 1024, 2048 (default) or 4096: textures converted from other games are scaled down to at most this width. Halo 3's own textures are mostly 512–1024, a few 2048; Reach and Halo 2: Anniversary textures reach 4K and 8K. Larger means sharper but more memory, disk and compile time. Tool accepts at most 4096. (Also shown as **Reduce Texture Size** for the Anniversary campaign.) |
| **Water** | The Halo 3 water shader used for Halo 2 and Halo CE water: **Pool (Reactor)** (default), **Pond (The Covenant)**, **River (Sierra 117)**, **Ocean (Zanzibar)**, **Rough (Rat's Nest)**, or HaloBridge's own conversion (dark still water with the original waves as its bump map). Halo 2 water takes its color from a reflection cube map that can't be converted, so a real Halo 3 water looks much better. Water surfaces have no collision (you wade through them). |
| **Halo 3 energy and glass** | On by default. Halo 2 plasma fields (teleporters, grav lifts) and reflective glass, and Halo CE plasma and glass, use Halo 3 shaders that draw the same animated or see-through effect. Off: they're converted from their textures and come out white or grey. |
| **Decimate very dense objects** | Off by default. When on, preparing adds a **HaloBridge Decimate** modifier to every exported object with more triangles than **Over** (30,000 by default), using **Ratio** (0.5 keeps about half). The modifier stays on the object, so you can change its Ratio per object in Modifier Properties (for example 0.4 on Halo 2: Anniversary's EMP device), and removing it restores the full mesh. **Add Decimate to dense objects now** adds the modifiers without preparing, so you can check them first. Objects that already have the modifier keep their own ratio. |
| **Add portal grid** and **Every** | Adds vertical `+portal` planes across the level, spaced **Every** world units apart (40 by default; Halo 3 multiplayer maps are about 50–200 units across), as one **HaloBridge Portals** object in a **Portals** collection. Running it again replaces the grid. Halo Tool cuts the level structure into clusters at portals, so big or dense levels stay within Halo 3's per-section limits and draw faster. Move or delete planes freely; any object made only of `+portal` faces counts. When a structure is too big for one cluster and has no portals, preparation adds portals itself. |
| **Skip objects with export problems** | When on, whole objects are left out instead of stopping the build: objects with mesh or material problems found before compiling (listed in the review popup), objects that fail while being converted, and objects Halo Tool rejects (preparation starts again without them automatically). They stay in Blender and are listed in the preparation report. Errors that aren't about one object (for example the level's own structure) still stop the build. |
| **Retry ‹n› object(s) Tool rejected** | Appears after Tool rejected objects. Includes them again in the next preparation. A rejected object is also retried automatically once you change it (for example its Decimate ratio). |
| **Quick test compile first** | On by default. Before the full compile, Tool compiles only the level's riskiest objects (the densest, and objects placed more than once that have separate collision, with all their placements) in a temporary test level (`hb_quick_test`, removed afterwards), so an object Tool rejects is found in minutes instead of near the end of the full compile. |
| **Show Tool warning markers in Sapien** | Off by default. Tool's geometry warnings (red "overlapping surfaces" text and lines) are cleared from the level so they don't cover the view in Sapien; the preparation report still lists every warning. Turn on to see them in Sapien. |
| **Generate Test Lighting for Sapien Level** | On by default. Bakes lighting after the geometry compile. Turn off for quick geometry tests. |
| **Copy Halo 2's original lighting** | Shown while lighting is on; on by default. For a Halo 2 map imported from a Halo 2 Editing Kit `.scenario`, and for Halo CE maps, puts the original game's own baked light, shadows and color on the level instead of baking new lighting. Halo 2 needs the Halo 2 Editing Kit the level was built from; Halo CE's lighting is read straight from the `.map`. |
| **Brightness**, **Sun**, **Shade** | Shown while original lighting is on. **Brightness** scales the copied lighting (1 = Halo 2's sunlit ground at the brightness of Bungie's Halo 3 multiplayer maps). **Sun** and **Shade** scale a converted Halo 2 sky's sun and the sky light that fills shadows and interiors (1 = default; raise **Shade** for lighter shadows, as in Halo 2). They take effect when you prepare again. |
| **Lighting bake** | **Tool** (default): Tool's quick draft lighting on the processor, 16 stages, no bounced light, so shaded areas come out very dark. **H3LM**: the [H3LM Lightmapper](https://github.com/Zoephie/H3LM) by Zoephie bakes Halo 3 lightmaps on a DirectX 12 graphics card, with bounced light. Download H3LM separately and unzip it. |
| **H3LM folder** | The folder with `h3lm-lm.exe`. A red line appears until it's set correctly. |
| **Quality** and **Ambient occlusion** | H3LM quality: **Low** (fast preview), **Medium**, **High** (Bungie's Tool settings), **Optimized** (H3LM's recommendation, default), **Ultra** (Bungie's Super doubled, much slower). Ambient occlusion darkens corners and interiors. |
| **Per-pixel lighting for large pieces** | On by default (H3LM only). Large pieces (terrain, buildings) are lit per pixel, which keeps sun shadows and avoids steps between pieces. Off: every piece keeps per-vertex lighting (light only at triangle corners), as Tool's own bake does. |
| **Open Sapien when ready** | Starts Sapien with the level when preparation succeeds. |

### What preparation does with the original game's gameplay

When the source is an original Halo 2 or Halo CE map, preparation also converts its gameplay where Halo 3 has an equivalent:

- **Player starting locations** replace the single test spawn (68 on Ascension, 72 on Blood Gulch).
- **Kill volumes** (Halo 2, from the Halo 2 Editing Kit scenario) become Halo 3 trigger volumes marked as kill volumes.
- **Netgame flags** become Halo 3 multiplayer objects: CTF flag spawns and returns, assault bomb spawns and goals, oddball spawns, territories, King of the Hill hills and teleporter pairs. Race checkpoints and headhunter bins have no Halo 3 counterpart.
- **Vehicles** become the Halo 3 vehicle of the same name when the Halo 3 Editing Kit has one (Banshee, Ghost, Warthog, Scorpion, Wraith...). Weapons and grenades are left for you to place.
- **Halo 2 water definitions** (the sea on Zanzibar, Needle, Headlong, Dune, Grotto and Beaver Creek, which is a height set in the BSP, not geometry) are read from the Halo 2 Editing Kit and become a flat Halo 3 water plane, drawn with the **Water** choice and without collision. The plane exists only while preparing; your Blender scene is unchanged.
- **Halo CE** gameplay (player starts, netgame flags, teleporters paired by team index, hills, vehicles) is read straight from the `.map`, so no Editing Kit is needed.
- **Converted shaders** keep Halo 2's surface material (footsteps and impact effects).

Placed objects are named `hb_ng_<n>` and updated when you prepare again.

## Warnings, status and Prepare

| Control | What it does |
| --- | --- |
| **HaloBridge Warnings and Messages** | The latest result or problem. **ACTION REQUIRED** means something needs your attention. Buttons here open the full diagnostic report, the map or scenario import report, or select the objects involved. |
| **Map Preparation Status** | Current stage, total elapsed time, the stages still to run and recent activity. Blender stays usable while it runs (look around, but don't edit the scene until stage 2 starts). During stage 3, Halo Tool compiles many objects at once and names one only when it has a problem with it; those messages show your Blender object's name. Stages differ a lot in length; there's no reliable time-remaining estimate. |
| **Open live activity log / Open live compiler output** | Open the step-by-step log or Tool's raw output in Blender's Text Editor. They update while preparation runs. |
| **Cancel preparation** | Stops the build and restores the previous successful version of the level. Converted textures, and the Halo 3 bitmaps Tool compiled from them, are kept outside the level, so the next preparation reuses whatever didn't change. |
| **Review preparation warnings** | Appears when preparation found something to confirm; choose to continue or stop. |
| **Prepare current scene for sapien** | Builds the level. See [First map](FIRST-MAP.md). |
| **Open in Sapien** | Opens the prepared level in Sapien. |
