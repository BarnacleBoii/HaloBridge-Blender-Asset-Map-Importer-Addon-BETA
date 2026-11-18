## 0.10.1 — scenario import and test lighting fixes

- **New: Halo 2: Anniversary campaign (remastered).** With **Import game** set to Halo 2: Anniversary, a new **Import Anniversary campaign level** box (above Import entire .map) imports any of the 15 campaign levels' remastered geometry and textures straight from MCC's `halo2\preload\paks` (Saber Interactive's Saber3D `.pck` archives, which nothing in HaloBridge or Reclaimer read before). HaloBridge's own reader (`source/H2ACampaign`) inflates the archives, reads the level scenes, templates and textures (BC1/BC3/BC4/BC5, RGBA8, A8L8, RGBA16F, RGB9E5), keeps the highest detail, leaves out occluders, shadow casters, reflection boxes and placeholder parts, and gives each material its base texture and normal map (glass alpha-blended, decals cut out). Tested on all 15 levels (`00a_introduction` is a cutscene without geometry); The Armory imports as 7,734 pieces, 173 materials and 254 textures.
- **Remastered levels line up with original Halo 2.** Saber3D stores levels Y-up in metres; HaloBridge converts them with Halo = (x, −z, y) ÷ 3.048, measured against the original `01a_tutorial.map` BSP (best fit exactly 1/3.048, leftover offset under 3 cm). A remastered level lands exactly on top of the same level imported from Halo 2.
- **New: Index All Individual Assets** (Halo 2: Anniversary campaign) lists about 1,070 campaign models (props, weapons, characters, vehicles) and 2,250 texture materials in the asset list. Each is extracted on first use (0.3–2 s). Model variants become switchable parts in **Model Parts and Variants**: armor variants per rank (helmet, lights, head), energy shields, damage states (Ghost guns, destroyed hulls) and lower LODs, with the default look on.
- **New: Reduce Texture Size**, in the campaign box: 512, 1024, 2048 (default) or 4096. It's the same setting as Prepare's **Texture size**, which gains the 512 option. Saved scenes keep their choice.
- **Small campaign storage.** Textures are stored once for every level, each as whichever is smaller: the game's own block-compressed data as DDS (no re-encoding; Blender 4.4 and 5.2 load it) or an optimized PNG. A level's geometry files are deleted right after a successful import (Blender keeps the meshes, Prepare only reads `scene.json`); importing it again re-reads them in seconds. The Armory plus Uprising: 366 MB, down from about 1.1 GB.
- **Changed: the default Halo 3 sky is Isolation** instead of Deadlock, for levels without a sky of their own and when no sky is chosen.
- **Fixed: Blender crash placing some models.** Zero-area triangles (a repeated vertex; the Anniversary battle rifle has 10) crashed Blender's custom-normals code (`EXCEPTION_ACCESS_VIOLATION`). They're dropped.
- **Docs:** new [Halo 2: Anniversary campaign](docs/H2A-CAMPAIGN.md) guide and [error reference](docs/ERRORS.md) explaining every message HaloBridge shows; the sidebar reference now covers every current control (Selected Asset collision choices, Water, Halo 3 energy and glass, portals, Quick test compile, Tool warning markers, Halo 2 lighting, H3LM bake options).

- **New: walk-through objects.** The selected object's collision is now set in the **Selected Asset** box (it replaces the separate Collision box), with two more choices. **No collision**: the object is rendered only; players, vehicles and projectiles pass through it. **No leaf collision** (vegetation): its see-through surfaces (leaf cards and other cut-out or blended materials) are walked through, while trunks and other solid surfaces keep their collision. Use Copy to Selected to set many objects at once.
- **Changed: Halo 2 lighting settings appear only when used.** Brightness and the Halo 2 sun and shade strengths now show under **Copy Halo 2's original lighting** only while it is turned on.

- **New: Halo CE maps keep their original lighting and gameplay.** For a Halo CE map, **Copy the original lighting** puts Halo CE's own baked light on the level the same way as Halo 2's: the extractor reads each BSP's lightmap blocks (positions, lightmap texcoords, incident light directions) and pages straight from the .map, so no editing kit is needed (Halo CE fills unused lightmap texels with a red/yellow checker; those count as unlit). Its player starting locations (Blood Gulch: 72) and netgame flags become Halo 3 player starts and multiplayer objects: CTF flags, oddball spawns, teleporters (paired by their team index, as in Halo CE) and King of the Hill hills; its vehicles (Blood Gulch: 28 warthogs, ghosts, scorpions and banshees) become the Halo 3 vehicles of the same kind.
- **New: portals (Add portal grid).** Prepare for Sapien has **Add portal grid** with a spacing (default 40 world units): vertical `+portal` planes across the level, in a Portals collection (run again to replace the grid; move or delete planes freely; any object made only of `+portal` faces is used). Halo Tool cuts the level structure into clusters at them, so big or dense levels stay within Halo 3's limits and draw faster. Portal planes are compiled into the structure and stretched exactly to the walls of the generated sealed boundary: a portal that stops short of the walls only "leaks", and one that pokes past them left Tool unable to build its leaf map (Burial Mounds, Ivory Tower and others failed until their portals ended on the walls). When the structure is too big for one Halo 3 cluster (over 14,000 triangles: Chiron TL34 passed Halo 3's 32,767 vertices per section before its index limit) and the scene has no portals, preparation adds portal planes itself, placed by where the triangles are (cuts at quantiles of the triangles' positions, added one at a time on the axis that helps most until no cluster holds more than about 9,000 triangles (cutting both axes each time gave Gemini about 120 clusters and Sapien "overflowed working portal stack during visibility traversal"), since an even grid left Gemini's densest cell over Halo 3's 32,767 vertices per section; cuts never fall exactly on a symmetric map's centre line, where faces lie in their plane and Tool "couldn't build leaf map"; when Tool still can't build its leaf map from them, preparation compiles again with the BSP instances and machines that portals cross as instanced pieces (they overlap the terrain; Gemini compiled this way), then with parallel slabs across the long side, then the short side (slabs never cross), then a moved grid, and as a last resort compiles one cluster with the biggest pieces instanced; when Tool finds a cluster with too many vertices (Warlock and Derelict as one cluster: 34,208 and 38,648), it compiles again with smaller clusters, up to 3 times; a new Prepare for Sapien starts over from the usual portals): Halo 2's Backwash (23,936 triangles) failed with "tool overflowed indices_word_block" (one cluster's mesh holds at most 65,535 indices) and now prepares.
- **New: instanced pieces get the original lighting too.** Halo 2 and Halo CE lighting was copied onto the level structure only; pieces compiled as instances (BSP pieces and objects moved out of the structure, rocks, crates) kept Tool's draft lighting, which is nearly black indoors (Gemini's pillars, Warlock's tower). Preparation now also writes Halo 2's light into each instance's per-vertex lighting (the lightmap BSP's "bsp per-vertex data": a dominant light and linear SH terms per vertex, encoded for Halo 3's static per-vertex shader so each vertex gets Halo 2's light on its own normal). An instance's vertices are stored compressed to 0..1 inside its definition's compression bounds; they are decompressed before Halo 2's light is looked up. Light that only skims a vertex is turned toward its normal, so the vertex keeps its full value and bump-mapped faces never flare. Checked in Sapien on Warlock (48,861 instance vertices; the central tower is no longer black) and Derelict (40,834).
- **New: Halo 2 energy fields, glass and water use Halo 3 shaders.** Halo 2's plasma (teleporter fields, grav lifts: `transparent\plasma_alpha`) gets its color and motion from the shader template, not a texture, so converted it showed solid white; reflective glass (`transparent\*_alpha_env*`) picked up its reflection map and showed flat grey; water draws its color from a reflection cube map. These now use a Halo 3 shader with the same role, copied into the level: animated green energy (Descent's grav lifts), clear glass (Lockout) and a Halo 3 water chosen under **Water** in Prepare for Sapien (pool, pond, river, ocean, rough, or the old dark conversion). **Halo 3 energy and glass** turns the first two off. Halo 3 water draws only on faces Tool builds as water: preparation marks those materials with the water-surface symbol (`'`) in the level's ASS (its BM_FLAGS have no water flag, and the Blender toolset drops symbols from ASS material names), keeps water pieces in the structure, and gives Halo 2 water no collision (it is waded through). Unmarked, the water had no shader in Sapien ("vertex shader entry point doesn't exist") and vanished.
- **New: Halo 2 water definitions become Halo 3 water.** Zanzibar, Needle, Headlong, Dune, Grotto and Beaver Creek draw their sea with the BSP's "water definitions" (an infinite plane at a fixed height, set in Guerilla, not geometry), so their converted levels had no sea. Preparation now reads them from the Halo 2 Editing Kit BSP and adds one flat quad at that height across the level's terrain (kept 2 units inside its outer bounds; a dense grid moved the automatic portal cuts), drawn with the Halo 3 water chosen under **Water** (without collision). The grid exists only while preparing; the Blender scene is unchanged.
- **Fixed: Halo CE see-through shaders drawn black or with holes.** Reclaimer reads one map of Halo CE's transparent shaders and calls them all "multiply", or reads nothing (plasma, generic), so Chill Out's lights and energy drew black and its glass showed pink holes. The extractor now records each Halo CE shader's class: plasma (teleporter shields) uses the Halo 3 energy shader, glass the clear glass, water the chosen Halo 3 water (without collision), and chicago, generic and meter layers (lights and glows) are drawn additively.
- **Fixed: a shader of an earlier Prepare used instead of the new one.** When a material's shader changed type between Prepares (a converted `.shader` becoming a Halo 3 `.shader_water`), the old tag stayed in the level's shaders folder and Tool kept using it. Prepare now removes shaders of another type under the same name.
- **Fixed: no footstep sounds on converted Halo 2 levels.** Converted shaders had Halo 3's `default_material`, which has no footstep or impact effects. They now take the global material Halo 2's shader names (`tough_terrain_dirt`, `hard_metal_thick_for`, `liquid_thin_water` ...), or its nearest Halo 3 parent.
- **Fixed: Halo 3 teleporters on top of Halo 2's.** Halo 2's netgame teleporter flags are invisible; the level's own teleporter scenery shows them. They became Halo 3's teleporter crates, model and glow included, standing inside Halo 2's. Teleporters from Halo 2 and Halo CE now use a level copy of the crate without its model or effects, which still teleports and keeps its sound.
- **Less disk space.** Every Prepare saved a full backup of the level's Editing Kit folders and a new exported `.ASS` file (often over 1 GB), and never removed either, so the HaloBridge folder grew by gigabytes per Prepare. Now each level keeps only the backup from its latest finished Prepare. Backups already copied back after a failed Prepare are removed, while a backup left by an interrupted Prepare is never touched. Each Prepare also removes the level's earlier exported `.ASS` files, which are never read again.
- **New: Texture size setting (default 2048).** Prepare for Sapien has **Texture size** (1024, 2048 or 4096): textures converted from other games are scaled down to at most that size. Halo 3's own textures are mostly 512–1024 wide and a few 2048, while Reach and Halo 2: Anniversary textures reach 4K and 8K; before, converted textures were only capped at Tool's 4096 limit.
- **Fixed: Halo 2 levels Tool couldn't compile as one structure.** Collision problems inside the merged Halo 2 structure, which Tool reports without naming an object ("degenerate collision edge" on Containment and Sanctuary, a plane-builder assertion on District), now step every Halo 2 structure piece's collision down together (cleaned surfaces, then welded harder) and compile again. A Halo 2 kit level without a lightmap (Uplift) gets Tool's test lighting instead of failing. A Halo 2 scenario whose script text the kit's Tool writes in the wrong encoding (Relic) is read anyway, and spawns or multiplayer objects that can't be read or written never fail the level.
- **Fixed: Halo 2 skies with a sun but no outdoor ambient (Beaver Creek) failed test lighting.** The converted sky had only its sun, and Tool asserted ("-1 is not a valid sky_lights_block index"). Such a sky now gets a dim sky fill tinted like its sun, so it has Bungie's 200 sky lights like the others.
- **New: Halo 2 spawns and kill volumes.** With a Halo 2 Editing Kit scenario, the map's player starting locations (68 on Ascension) replace the single test spawn, and its kill trigger volumes (Ascension's cloud sea) become Halo 3 trigger volumes marked as kill volumes (as Bungie marks Narrows' `kill_drop`), so falling off the map kills as in Halo 2. Its netgame flags become Halo 3's multiplayer objects (crates with multiplayer data, in the Halo 3 Editing Kit): CTF flag spawns and returns, assault bomb spawns and goals, oddball spawns, territories, and teleporter senders/receivers (Halo 2's identifier becomes the teleporter channel, the team its owner team); each King of the Hill hill (Halo 2 traces it with points around its edge) becomes one hill with a cylinder boundary through those points. Read from the kit's scenario (export-tag-to-xml, cached); placed objects are named `hb_ng_<n>` and updated when prepared again. Race checkpoints and headhunter bins have no Halo 3 counterpart and are left out. Halo 2's multiplayer vehicles (netgame equipment such as Ascension's Banshee) are placed as the Halo 3 vehicle of the same name when the Halo 3 Editing Kit has it (banshee, ghost, warthog, scorpion, wraith ...; the Spectre has none); weapons and grenades are left for the level designer.

- **New: copy Halo 2's original lighting.** For a Halo 2 map imported from a Halo 2 Editing Kit `.scenario`, **Copy Halo 2's original lighting** (under Generate Test Lighting, on by default) puts Halo 2's own baked light, shadows and colour on the terrain instead of baking new lighting. The Halo 2 kit's Tool exports the level's lightmap (cached); Halo 2's terrain clusters are compiled as the level structure, as in Halo 2, since Halo 3 only gives the structure per-pixel lightmaps; Tool's test lighting runs as usual (it lights objects and other pieces); then each structure lightmap pixel takes Halo 2's light from the same spot on Halo 2's surface, written as the light data Tool stores after its test lighting (9 SH layers), and Tool's own last steps build the game's lightmap textures from it. Halo 2's light is spread 60% from a direction between its light direction and the surface, 40% evenly, so shade and bump detail don't turn black. A **Brightness** slider scales it (1 = Halo 2's sunlit ground at the brightness of Bungie's Halo 3 multiplayer maps). Halo 2's BSP instances (rocks, boulders and other placed level pieces) are compiled as structure too and get their own Halo 2 lightmaps, placed where Halo 2's BSP puts them. Tested on all of Coagulation: 111 terrain clusters and BSP pieces compiled as structure, 953,698 lightmap pixels copied (524 found no Halo 2 surface and kept Tool's light), 8.4 minutes for the whole preparation, checked in Sapien. Pieces Halo 2 lit per vertex (Ascension's rock columns and doors) get Halo 2's per-vertex light, read from the lightmap's geometry buckets. Terrain clusters Halo 2 never lightmapped (Ascension's 700 x 700 water plane) are compiled as per-vertex pieces instead of structure, so they take no lightmap space; on Ascension that plane had taken 72% of the lightmap page. Black smudges fading into a tint are fixed: texels and vertices Halo 2 left unbaked (black) now take the nearest baked light instead of being copied as darkness, and each pixel takes light from the Halo 2 surface facing the same way, not just the nearest one (where a rock meets the ground, the closest point was sometimes on the other surface). Small pieces get tiny lightmap charts (Ascension's rocks: under half a pixel per triangle): every pixel a triangle covers or reaches through filtering now gets Halo 2's light (before, only pixels whose centre was inside a triangle did, and edge padding spread a neighbouring surface's light into the rest), and a pixel shared by faces pointing different ways gets even light, since directional light for one face read as negative (black, tinted red, green or blue) on the other. The copy step also got faster (about 3 minutes on Ascension). Halo 2 objects compiled into the level (machines such as Ascension's antennas, scenery, crates, controls) are now lit per pixel as part of the structure: lit per vertex by Tool, a long piece whose few corners sit inside rock came out black end to end. Halo 2 baked no light for objects; like Halo 2, which lit them from the level around them, their pixels take the nearest Halo 2 surface's light (within 10 world units, half as directional), so they match the level instead of Tool's darker, blue-tinted draft light. Ascension: 986,003 lightmap pixels copied with none missed, about 6 minutes, checked in Sapien from several angles. Needs the Halo 2 Editing Kit the level was built from.
- **Fixed: Halo 2 see-through layers drew as solid sheets.** Halo 2 transparent shader templates other than skies (Ascension's cloud sea below the level uses `transparent\two_alpha_clouds`) were read as opaque. They now become unlit Halo 3 shaders that alpha-blend (or add, for `add` templates) as in Halo 2. Halo 2 maps are extracted again once to pick this up.
- **Fixed: Halo 2 maps with many see-through surfaces failed to compile.** In the level structure Tool splits blended faces into separate sorted parts, and a section allows 255 (Midship: "cluster 0 has too many parts (count=330)"; Colossus' gas containers). Halo 2 objects with see-through layers now stay instanced pieces, and a structure piece's see-through faces (glass, energy panels) are compiled as a separate piece; the layers are unlit, so nothing is lost.
- **Fixed: Halo CE / Halo 2 skies too big for Sapien.** These skies are drawn around the camera in their own game, so HaloBridge sizes them around the level; they were 2,000 world units across or more and Sapien cut them off. They are now 5 times the level's radius, between 900 and 1,800 world units (Coagulation: about 1,170), for a sky imported with the map and one chosen under Sapien Sky, including skies placed before this version.
- **Fixed: striped sky pieces on Halo 2 maps.** Uncompressed 32-bit Halo 2 bitmaps (such as Coagulation's second moon, `coag_moon2`) were read with original-Xbox row padding, which scrambled them into coloured stripes and repeated circles. MCC PC maps store these as plain rows; they now decode the same as the Halo 2 Editing Kit shows them. Halo 2 maps are extracted again once to pick this up.
- **Fixed: Halo 2 water showing purple.** Halo 2's water shaders take their colour from a reflection cube map; only their wave normal map was read, as the colour. They now convert to dark water with the waves as bump map.

- **New: Halo 2: Anniversary.** The **Import game** list has Halo 2: Anniversary (multiplayer, MCC `groundhog\maps`, Editing Kit `H2AMPEK`). Index .map Assets, asset placement and **Import entire .map** work like the other games (tested on `ca_coagulation`: 1/1 BSP, 884 instances, 509 scenery, 185/185 materials with textures, sky). Its assets and sky go into a Halo 3 or ODST level with converted materials; its objects use box or mesh collision. There's no Anniversary `.scenario` import: a map built by the H2AMPEK Tool is uncompressed past 2 GB and can't be read, and the installed maps already contain every level.
- **Fixed: Halo 2: Anniversary foliage showing as squares.** Anniversary's foliage and `*_clip` material shaders cut out on the color map's alpha, but are stored with an opaque blend mode, so leaves imported as solid squares; the fake-lit foliage shader's tint gradient also replaced the leaf texture. These materials now import as cut-outs with their own leaf texture, keep the cut-out in Halo 3, and leaves from Anniversary foliage shaders are walk-through like Halo 3 foliage. Anniversary map imports are re-extracted once; re-import the map to get the fix.
- **Fixed: blurry Halo 2 ground in Halo 3.** Halo 2 outdoor ground (for example Coagulation's `coag_ground`) stretches one base texture over the whole level and blends two small detail textures, repeated many times, with the base texture's alpha. Only the stretched base texture was converted, so the ground was low resolution up close. These shaders now become a Halo 3 `detail_blend` shader with both detail textures at their original repeat (Coagulation: grass and pebbles 60 times). Halo 2 shaders with one detail texture (for example the cliffs' sandstone) keep it too, and a bump map that repeats more often than the base texture now repeats in the shader instead of being squeezed into one texture. Halo 2 maps are re-extracted once; re-import the map to get the fix.
- **Fixed: Halo 2 sky layers drawn in the wrong order (Coagulation's ring behind the blue sky).** Halo 2 draws a sky's layers one over the other in a fixed order; in Halo 3 they are see-through surfaces of one model at the same distance from the camera, so that order was lost. The backmost layer now becomes opaque when it covers the whole sky (Coagulation's blue sky dome, so the ring, moons and clouds always show in front of it), and the other layers keep Halo 2's order through Halo 3's shader sort layer: the first third pre-pass, the last third post-pass. Layers in the same third (for example Coagulation's heavenly glow and ring) can still swap.
- **New: Halo 2 levels are lit by their own sun and sky.** A converted sky had no light of its own, so its level was lit with another Halo 3 level's sky (Deadlock's by default). The Halo 2 sky's lights and outdoor ambient color are now read from the map and written into the converted Halo 3 sky as its 200 sky lights, the form Bungie's skies use: one sun and 199 patches of sky. Direction and color are Halo 2's (Coagulation: a warm sun 28° above the horizon and a pale blue sky). Halo 2's light power has no Halo 3 unit, so brightness starts from Bungie's Halo 3 multiplayer skies and is set brighter, because Halo 2 suns are often low (Coagulation's is 28° up, Deadlock's 55°) and Halo 2 shows its shade much lighter than Halo 3: Coagulation's sun gives 7.5 facing it (3.5 on flat ground) and its sky 5.5 to 6.1 on flat ground. Two sliders under Generate Test Lighting, **Sun** and **Shade** (1 = default), adjust the sun and the sky light that fills shadows and interiors. Tested with Tool's test lighting on Coagulation's sky and ground. Halo 2 maps are re-extracted once; re-import the map to get it.
- **New: H3LM lighting bake.** Under Generate Test Lighting, **Lighting bake** can be set to **H3LM (graphics card)**: the [H3LM Lightmapper](https://github.com/Zoephie/H3LM) by Zoephie bakes Halo 3 lightmaps on a DirectX 12 graphics card, with bounced light, instead of Tool's draft test lighting (which has no bounced light, so shaded areas come out very dark). Download H3LM separately, unzip it, and choose its folder; pick a quality (Low to Ultra, default Optimized) and optional ambient occlusion. Progress shows in the preparation status, Cancel stops it (H3LM installs nothing from a cancelled bake), and H3LM keeps its work files and tag backups in the kit's `h3lm_work` folder. Tested on Coagulation's sky and ground: a Low bake took 5 minutes and used the sky's 200 sky lights.
- **Fixed: a Halo 2 sky chosen under Sapien Sky lit the level with Deadlock's sky.** A Halo 2 sky picked from the sky list now also brings its sun and sky light (read when it is chosen; a sky chosen earlier is looked up when the level is prepared) and keeps its layer order, like a map's own imported sky.
- **Fixed: Halo 2 sun missing from the bake.** The converted sky's sun was the first of its 200 sky lights; Tool and H3LM take the last one as the sun (as in every Bungie sky), so the sun was baked as one more patch of sky and the level had no sunlight or sun shadows. It is now last (H3LM: "199 (+1 sun)", sun 4.3 on flat ground).
- **Fixed: no sun shadows, and lighting steps between level pieces.** Tool gives every instanced piece per-vertex lighting (light kept only at triangle corners), so on Halo 2 terrain, made of large low-detail triangles, sun shadows disappeared and the light smeared into triangles with hard steps where pieces meet. With the H3LM lighting bake, pieces 2 world units or more across now get per-pixel lighting ("per-pixel shared"; Tool refuses "per-pixel separate"); small pieces keep per-vertex. Tool's own draft lighting crashes on per-pixel pieces (faux_rasterizer.cpp), so with it they stay per-vertex: use H3LM for sun shadows. For H3LM, Tool first makes the level's lightmap data and UVs, as H3LM can't yet give per-pixel pieces UVs on a level that was never lit. (Tested: H3LM baked 10 per-pixel Coagulation pieces with 0 left per-vertex.)
- **Fixed: Tool's red "overlapping surfaces" markers covering the view in Sapien.** Tool's warning reports are cleared from the compiled level (the game never uses them; the preparation report still lists every warning). **Show Tool warning markers in Sapien** keeps them.
- **Fixed: blocky Halo 2 skies.** A sky layer's textures are enlarged to its largest texture's size when converted; they were enlarged by repeating texels, so Coagulation's cloud mask (256 pixels, stretched under a cloud texture repeated 8 times) became 8x8 squares over the sky and ring. They are now filtered smoothly.
- **Fixed: Halo 2 banners and other bump-mapped cut-outs missing pieces.** Halo 2's alpha-tested bump-mapped shaders cut out with the bump map's alpha; the color map's alpha was used, which on Coagulation's flags is a torn pattern covering about half the flag. Halo 2 maps are re-extracted once; re-import the map to get it.
- **Fixed: "collision geometry is too large" stopping preparation.** Tool allows 32,767 collision surfaces per object; very detailed pieces (for example Halo 2: Anniversary's `h2a_emp_device`, 36,308) stopped the whole build. Objects whose collision surfaces are denser than that now collide with a simplified copy of their own surfaces, made before Tool runs, and if Tool still reports one as too large it is simplified further and recompiled automatically (not replaced by a box). Halo 2: Anniversary pieces over 10,000 collision triangles get their collision decimated to half with Blender's Decimate (Collapse), then cut into pieces of up to 10,000 triangles, each its own collision object in the same place, instead of being simplified until one piece fits; the render mesh is unchanged. (Tested on Coagulation's ten densest rock clusters and cave branches, 40,854 to 63,524 triangles each: 3 or 4 collision pieces each, compiled by Tool.) Only very dense collision (over 8 pieces' worth after decimating) is decimated further. Cleaned surfaces that Tool still rejects for broken edges are welded harder twice before a box is tried.
- **Fixed: Tool crashing on an object ("ASSERTION FAILED ... connected_geometry_plane_builder.cpp").** Tool can crash when it combines the render and separate collision of an object placed more than once (a Halo 2: Anniversary Coagulation piece compiled fine alone, and with only its render or only its collision). The crash is now treated like rejected collision: that object's collision is replaced by cleaned surfaces, then a box, then none, and the level is compiled again. With Skip objects with export problems on, an object Tool still crashes on is left out. The error now names your Blender object instead of `poop hb_839.001 merged`.
- **Blender no longer freezes during preparation, and repeat preparations are much faster.** Stage 1 now reads the scene a few objects at a time, so Blender keeps redrawing and showing progress. The level file (ASS) is still written by the Halo toolset, but in background Blender processes running side by side instead of in Blender itself (it took about 5 minutes of frozen Blender on Halo 2: Anniversary Coagulation). Each mesh's part of the file is kept, and the next preparation only re-exports meshes that changed; placements, materials and geometry are verified identical to the toolset's single-file export.
- **Fixed: "section 'global' has too many vertices" stopping preparation.** Halo 3 allows 32,767 render vertices per object part. Dense objects such as grass cards could stay under the 16,000-triangle split HaloBridge already made and still go over the vertex limit; they're now split by vertex count too, before Tool runs. Tool's vertex count can't be predicted from Blender's (it counted 36,964 for a decimated two-sided Anniversary tree cluster whose distinct vertices came to 28,562), so parts are sized by face corners, which Tool never exceeds.
- **New: Quick test compile first** (on by default). Tool's geometry compile can't be resumed and checks each object's limits only while building it, so a rejected object could stop a long compile near its end. Preparation now first compiles only the level's riskiest objects in a temporary test level, then the full level: the densest (those near Halo 3's render vertex, render triangle or collision limits), and objects placed more than once with all their placements, since Tool builds those a second time and can crash there (on Coagulation it crashed after 29 minutes; the quick test found it in 2.5). A rejection found there stops preparation the same way as before (Skip objects with export problems and the collision retries handle it), without waiting for the full compile. The temporary level (`hb_quick_test`) is removed afterwards.
- **Skip objects with export problems now skips everything it can.** Besides the problems found before compiling, it now also leaves out an object that fails while being converted, and an object Halo Tool rejects: HaloBridge remembers it and prepares again without it, automatically. The objects left out are listed in the preparation report and stay in Blender; a rejected object is tried again once you change it (for example its Decimate ratio), or with **Retry objects Tool rejected**.
- **Easier-to-read preparation activity.** Tool's own step names (for example "building bsp3d children...... 68%") are shown in plain words, such as "Building collision for the level's 865 meshes". Tool works on many objects at once and names one only in a warning or error, so those now show your Blender object's name, once per object and kind of warning. Tool's jumping percentages and HaloBridge's own harmless collision-copy warnings are left out (the full compiler output is still available).
- **New: Decimate very dense objects.** An option under Sapien Map Preparation adds a **HaloBridge Decimate** modifier (ratio 0.5 by default) to every exported object over 30,000 triangles when you prepare, or right away with **Add Decimate to dense objects now**. Each object's ratio can be changed in Modifier Properties; the export uses the decimated mesh for both rendering and collision.
- **Faster retries after a failed preparation.** Tool's geometry compile can't be resumed, but the work before it is kept: converted textures are reused when their source is unchanged, and the Halo 3 bitmaps Tool compiled from them are saved outside the level, so a retry after an error (which restores the previous level) or a repeat build skips the bitmap import when no texture changed.
- **Fixed: Tool's "failed to add import info" counted as a failure.** On very large level files Tool can't embed a copy of the source file in the tag; the level still compiles, so this line no longer fails a finished build.
- **Fixed: Halo 2: Anniversary skies missing from the Sapien Sky list.** Anniversary keeps its sky in folders like `ca_coagulation_sky`, which the list didn't recognise. **Index .map Assets** now marks the scenario's own sky, and existing Anniversary indexes are recognised by their `_sky` folder.
- **Panel:** **Import sky with the level** shows **ON** or **OFF**; **Viewport Shadows** start **Off** (faster) in every scene, and stay as you set them afterwards; **Import level from .scenario** no longer says "(Recommended)"; **Skip objects with export problems** sits next to **Generate Test Lighting for Sapien Level**.
- **New: Import sky toggle.** **Import sky with the level** (ON by default) can be turned OFF to import a `.scenario` or an entire `.map` without its sky objects; preparation then uses the **Sapien Sky** setting.
- **Clearer Halo 3 instance limit.** One Halo 3 BSP allows 1,024 instanced geometry definitions. Preparation now stops early with a plain explanation when a level clearly has more, warns when it is close, and explains Tool's own limit error. Tool can reject several imported objects' collision one at a time, so the automatic collision retry now allows up to 12 rounds instead of 2.
- **Fewer box collisions.** When Tool rejects an object's collision (for example "degenerate collision edge" on Halo 2: Anniversary pieces), the automatic retry now gives that object its own mesh surfaces cleaned for Tool (near-duplicate vertices merged, zero-length edges and slivers removed) instead of a simple box. A box is only the last resort before no collision. Collision-only faces no longer count toward the render index limit, so they don't split pieces into extra instances.
- **Clear message for levels too large for Tool.** Halo 3's Tool can't import a level file over about 2 GB (it crashes with "MAXIMUM_MEMSET_SIZE"). Preparation now stops before Tool with an explanation.
- **Fixed: converted textures larger than 4096.** Halo 3's Tool rejects bitmaps over 4096 pixels (some Halo 2: Anniversary textures are 8192 wide); converted textures are now halved until they fit.
- **Fixed: pixelated, see-through Halo 2 skies.** Halo 2 sky layers use "sky" shader templates Reclaimer does not read, so they imported as lit materials whose brightness became dithered transparency, and cloud layers lost their tiling and coverage mask. Each layer now previews unlit, alpha-blended or additive as in the game, with its tiling, mask, detail map and tint. Halo 2 map imports are re-extracted once; re-import the map to get the new skies.
- **New: an imported Halo: CE / Halo 2 / Halo 2: Anniversary map keeps its own sky in Halo 3.** With **Sapien Sky** on "Original map / default sky", preparing an imported map from those games converts its sky layers into the level's sky at their imported size, position and rotation, instead of using Deadlock. Halo 2 layers keep their alpha or additive blending.
- **Fixed: "Access is denied: 'projects'" when preparing after importing another game.** Switching the import game (for example to Halo 2) could save Halo 3's storage folder as blank, so preparing for Halo 3 tried to create its project folder inside Blender's install folder. A blank folder now falls back to the detected or default HaloBridge storage.

- **Fixed: white surfaces in `.scenario` imports.** A BSP or model material without a collection prefix (for example `panel_ext_vert_minimal` in 070_waste) was left without a shader when two shaders shared that name in different folders (070_waste's own and Citadel's), so it imported untextured. It now resolves to the owning level's or object's own `shaders` folder, as Tool does. Cached scenario imports rebuild once.
- **Fixed: more untextured surfaces.** Material names ending in Halo's `{` (ignored by lightmapper), `[` (blocks sound), `]` (decal offset) or `(` symbols kept the symbol in the shader name and found no shader (for example `cit glass_activation]`, `s3dwtf lamp_01_blue_01!)(`). Across every Halo 3 scenario this cut unmatched names sharply (s3d_waterfall: 144 → 5).
- **Fixed: blurry painted terrain in Sapien.** Paintable terrain, including the starter level shell's Jungle ground, was baked into one image (1024×1024 by default) stretched across the whole terrain, so it looked very low resolution. It now exports as a real Halo 3 `shader_terrain`: each layer keeps its own full-resolution base, detail and bump textures with their original repeat, and only the painted result becomes the blend map.
- **New: add terrain layers.** **Add layer** adds another paintable layer, up to Halo 3's limit of four terrain materials. The starter Jungle ground has three. A new layer starts as a copy of layer 1; it is painted with white in a terrain made from a Halo terrain shader, or blue in one made from a plain texture.
- **Fixed: untextured retextured models.** Snow vehicles (`warthog_snow`, `hornet_snow`, `mongoose_snow`, `scorpion_snow`) keep their original source material names ("exterior", "glass") but their tags point at the `_snow` shaders, and some models use default 3ds Max names ("Material #288") or collision material names. A render-model material whose name finds no shader now takes the shader at its position in the tag's own materials list. This only happens when every material that does match by name sits at its expected position. Materials the original tag leaves on `shaders\invalid` get their own warning.
- **Fixed: "Assertion Failed" pop-ups during `.scenario` import.** ManagedBlam raises a .NET assertion on some render models (for example `objects\cinematics\texture_camera`), which showed a dialog and could crash the import. It is now written to the job log, and that model uses its map mesh.
- **Fixed: detail-mapped surfaces too dark.** Halo 3 "double-multiplies" detail maps over the base map in its gamma-encoded colour; the preview used ×2 in Blender's linear colour, which made those surfaces about half as bright and washed out. The preview now uses 2^2.2 (×4.59, ×21.1 for two detail layers). Materials in scenes saved with older versions are brightened when the file is opened.

- **Faster viewport on whole levels.** Imported levels overflowed EEVEE's shadow memory ("Error: Shadow buffer full … (3969 / 2048)") and slowed Material Preview. Level imports (`.scenario` and entire `.map`) now turn EEVEE shadows off, and **Folders and Setup** has a **Viewport Shadows** on/off button (Blender 4.2+). Measured on 070_waste (4,609 objects): the message disappears, the preview looks almost the same, and in the first measurement the frame time fell from about 55 ms to 25 ms.

- **Fixed: preparation failing with "ASSERTION FAILED … faux_material.cpp … parameter_success".** Halo Tool's test lighting cannot evaluate some animated shaders, such as 070_waste's sky waterfall (`waterfall.shader_custom`), and crashed, which rolled back the whole build. The level is now kept without test lighting, and the preparation report names the shader and the Blender objects using it. Verified with a test level using that shader; the other waterfall shaders and converted Reach shaders (including alpha-tested ones) light normally.
- **Fixed: "JMS triangle uses a missing material" stopped `.scenario` imports** (for example `levels\solo\070_waste\070_waste`, whose cinematic sky has 1,498 faces with no material). Faces that have no material in the original source file are now skipped and listed in the import report; the rest of the level imports. Tested with 070_waste: 13/13 BSPs, 4,609 placements, all 5 skies.
- **Fixed: BSP pieces dropped for one unassigned face.** A BSP source object with a few faces without a material was skipped entirely; now only those faces are left out, so geometry missing from earlier imports (about 20 pieces in 070_waste) comes back. Cached scenario imports are rebuilt once.

## 0.10.0 — Editing Kit scenario import and Blender 5.2

- **Import level from .scenario.** New Halo 3 route that reads a level from its Editing Kit `.scenario` tag with ManagedBlam: BSP geometry from the ASS source stored in each BSP tag, instance names and transforms, all scenery/crate/machine/control/vehicle placements with variants, weapons/equipment for reference, skies, and the exact shader tag of every surface with its source flags. The matching `.map` is used only for preview textures (looked up by shader path) and as a reported fallback for render models without embedded source.
- **Original scenery placements.** Unedited scenario scenery is prepared as placements of its own scenery tag (keeping its collision, physics and variants); vehicles keep their vehicle tags. Edited objects export as static geometry and are listed in the preparation warnings.
- **Original collision lookup** accepts the scenario's model tag when it differs from the render model path.
- **Blender 4.0 to 5.2.** Handles the removed Auto Smooth setting, EEVEE Next material render methods, brush assets (4.3+), per-mode unified paint settings (5.0+) and registered-property access (5.0+). On Blender 4.1+, the toolset is accepted when it provides the ASS export options and material flags HaloBridge uses (v432 or newer, verified with v432 on 5.2); 4.0 keeps the v364/v432 requirement.
- **Faster mesh signatures** using bulk reads; the digest is unchanged, so existing scenes stay valid.
- **Fixed:** original vehicle and invisible-block placements now use Halo's yaw/pitch/roll order (Blender `ZYX`), matching scenery export and Reclaimer. Objects with pitch or roll were previously rotated incorrectly.
- **Fixed after the first H3EK run (Guardian):** JMS names and material definitions are read as whole lines, so render models use their embedded source instead of the map; material names with lighting parameters (`lm:5.0`) no longer abort the import; shader collections resolve `<folder>\shaders\<name>`; an unbalanced trailing `)` in weapon material names is ignored; the preparation warnings popup no longer crashes background Blender. Cached scenario scenes from earlier 0.10.0 test builds are rebuilt.
- **Fixed after the Outskirts run (6 BSPs):** ASS names containing a quote no longer drop a BSP; `blur)!=`-style and `'name` material names resolve; shaders in collection subfolders resolve; imported vehicles and static objects are no longer rejected for float rounding of their 100x scale. Toolsets that still use v364's frame-locals hack now stop with a clear message on Blender 5.x instead of failing inside the ASS export; v432 is accepted and no longer reported as Blender 4.0-only.
- **Fixed on Blender 5.x:** the sidebar stopped drawing below Preview Mode (Blender 5 renamed the `SEQUENCE_COLOR_*` icons), hiding Prepare for Sapien and every section after it. The Collision material list now uses Blender's `MATERIAL_UL_matslots`. New `tests/blender_icons.py` checks icon and list names against the running Blender.
- **Fixed:** generated box collision left the new faces' UVs uninitialized on Blender 5.2, so a random set of objects exported NaN texture coordinates and Tool rejected the level ("mesh definition vertex texcoords invalid"). Collision faces now get zero UVs and white colors, and any remaining non-finite UVs are set to 0 in the export copy and listed in the preparation report.
- **Sidebar:** every section collapses (Folders and Setup, Indexed Asset List, Selected Asset, Materials and Shaders, Collision, Editable Materials, Sky, Map Preparation); warnings, preparation status and the Prepare button stay visible. Each terrain shader layer (up to four) is its own collapsed section with its Paint button in the header. **Import level from .scenario (Recommended)** is followed directly by **Import entire .map**. Removed **Repair incomplete map import**. New **Remove Grey Blender Fog (View Distance)** sets Clip Start 0.1 / Clip End 999999.
- **Starter template:** a paintable Jungle terrain plane, a see-through SkyBoundary wall (+sky faces are dropped in preparation, which builds its own sky boundary) and Master Chief for scale (not exported), extracted from `010_jungle.map`.
- **Halo 3: ODST** is a full game: index and import `.map` files, **Import level from .scenario** from the H3ODSTEK, and Sapien preparation into the ODST Editing Kit (original scenery, vehicles, sky and test spawn). Selecting a game whose kit supports Sapien also sets **Export to Sapien** to it.
- **Halo: CE and Halo 2 importing** from MCC `.map` files: Index .map Assets (shaders, models, scenery, Halo 2 instanced geometry), preview/placement and Import entire .map (all BSPs, skies and object placements; tested on Blood Gulch, a10 9/9 BSPs, Ascension and Old Mombasa 4/4 BSPs).
- **Every game in a Halo 3 level.** Material conversion, previously Reach-only, now covers any asset whose shader is not from the Sapien destination (ODST, Reach, Halo CE, Halo 2; Halo 3 assets in an ODST level). Layered/detail previews fall back to the textures recorded at import; ODST shaders that exist in H3EK are reused. Original collision is read from each asset's own kit.
- **Sidebar:** the per-material **Collision** control is removed (settings saved by older versions are ignored; the toolset's **Render Only** material flag still works); Object collision's first choice reads **(Default) Automatic**; the output level name starts as **levelname123**; **Import game** lists **Halo: Reach** without "(Experimental)".
- **Folder detection on other PCs:** **Detect folders** also finds MCC installed through the Xbox app / PC Game Pass (`XboxGames`), checks only local fixed drives (no stalls on card readers or network drives), reads Foundry settings from `%APPDATA%`, and only accepts a maps folder that contains `.map` files. New storage goes in the real Windows Documents folder, including one redirected by OneDrive; an existing `Documents\HaloBridge` keeps being used.
- **Documentation rewritten:** new installation guide with a per-task requirements table, importing guide, first-map tutorial, a sidebar reference covering every control, a new supported-games page, and refreshed troubleshooting, limits, editable materials, Reach and how-it-works pages.
- **Fixed: Remove Grey Blender Fog** set Clip Start/End in Blender units, so with HaloBridge's 0.03048 unit scale they read 0.003048 m and 30480 m. They are now set in the scene's displayed units: 0.1 m and 999999 m.
- **Halo: CE and Halo 2 .scenario import.** The kit's own Tool builds a map from the scenario (`build-cache-file`), which is then imported or indexed like an installed map; the built map is cached until the scenario's tags change, and a map of the same name in the kit's output folder is restored. Tested with Blood Gulch (HCEEK) and Ascension (H2EK).
- **Skies from any game.** **Sapien Sky** now has a **Game** choice. The destination game keeps its Editing Kit sky list; for any other game a sky model from its asset list is placed in a **Sapien Sky** collection and, on preparation, converted (self-lit textures, `render-sky` render model, model and scenery tags) and set as the level's sky. Test lighting is baked with the destination kit's sky first, since converted skies carry no sky lighting. Tested with Halo: CE's "mp clear afternoon" in a Halo 3 Blood Gulch level and Halo 2's Ascension sky in a Halo 3 Ascension level. Halo: CE and Halo 2 sky layers use additive blending.
- **Fixed: white Halo: CE and Halo 2 textures.** Halo 2 shaders whose template Reclaimer does not recognise (skies, many effects) lost their bitmaps or kept them only as transparency, and Halo: CE `shader_transparent_generic` shaders had no textures at all (and were missing from the index). Such shaders now use their own bitmap as the base texture, skipping Halo 2's `default_bitmaps` placeholders. Halo: CE / Halo 2 assets and whole-map imports are re-extracted once.
- **Tool collision rejections are retried automatically:** objects whose collision Tool reports as ambiguous or degenerate are recompiled with a simple box, then without collision (up to three compiles), and listed in the report. Collision with welded overlapping pieces is detected before export. Fixed a Blender crash (access violation) when adding collision to meshes with converted materials.
- Sky models placed from an index are omitted like imported skies; objects beyond Halo 3's 10,000 world-unit limit are reported before Tool runs.
- **Halo: Reach .scenario import:** placements come from the HREK scenario tags. The Reach kit ships no source models or BSP sources, so geometry comes from the matching `.map` and this is stated in the import report. Reach Sapien preparation is still unavailable: the Halo toolset's ASS exporter only targets Halo 2/3.
- **Index .scenario Assets:** lists every distinct object, instanced mesh and shader in a scenario in the Indexed Asset List, next to **Index .map Assets**. A new source filter (All Sources / .map Assets / .scenario Assets) shows a one-line summary of what each source is best for.
- **Apply material to selected object** adds the material as a new slot and assigns it (only the selected faces in Edit Mode) instead of replacing the existing material. Unused slots are ignored at export.
- **Sidebar:** each section has its own box; Imported/Hidden Assets sit side by side; **Materials and Shaders** is now **Shaders** without the level filter and shader count; **Remove Grey Blender Fog** uses Clip End 999999; the output level name starts as the placeholder **Level_Name_Here**, which Prepare asks you to replace.
- **Helpers:** new `scenario_scene` tag-helper operation and `materials` extractor operation; ODST maps; Reach shader previews for scenario imports; Reach object names (string IDs) and the ODST spawn block. Rebuild both helpers (`source\Build.ps1`).
- Add-on renamed to **HaloBridge - Halo Level Importing**.

## 0.9.1 — collision, materials and shader workflow

- **Original collision first.** Automatic collision tries verified source collision geometry for eligible imported models and BSP instances. Edited or unmatched objects use the available box or surface fallback. Preparation reports list the collision route for each exported static object.
- **Large static models.** Oversized instances can export as several aligned Halo instances while staying one editable Blender object. This addresses the Reach Elite render-index overflow while retaining its visible triangles.
- **Paintable terrain.** Supported layered terrain starts with the original blended appearance. Numbered shader-layer buttons paint an overlay, and Paint original blend restores the source mixture. Texture resolution has 512, 1024, 2048 and 4096 options. Repeat controls start collapsed.
- **Original vehicle paint.** Editable colors can generate level-local vehicle/model/render-model copies for matched Halo 3 vehicles, with the original gameplay and physics references retained.
- **Snowbound materials.** Halo 3 previews now support default, detail blend, two-detail and two-detail-overlay albedo operations when their parameters are available. The missing second detail texture is extracted, restoring Snowbound's purple icy-metal layer.
- **Paired transparent faces.** Imported meshes whose transparent triangles all have opposite-facing mates get a local material with backface culling, reducing overlapping front/back rendering. This preserves the mesh faces.
- **Shader controls.** Materials and Shaders identifies the active object/material. Assign shader to active material explains its Sapien effect. The picker captures its chosen category, shows the matching count, and keeps manual path entry. Collision controls have their own section.
- **Texture-loading label.** The button is now Load Halo Shader Textures/Masks for Currently selected Material.
- **Neutral normal fallback.** The known unreadable default_vector placeholder can use a flat normal instead of interrupting extraction for that specific decode error.

## 0.9 — shared game workflow and documentation refresh

## v0.9 public early release refresh

Added selectable and separable model variants, terrain painting, static color masks and support for toolset v432. Updated source-map lookup, wrapped color UV validation and reporting of recoverable instance collision diagnostics.


- Shared Halo 3/Reach panels with independent Halo 3 export routing and one saved kit path.
- Multi-object greybox swapping using original asset scale; map picker with manual filename entry.
- Single-sided and open-surface handling, structure-source diagnostics, reports opening at line 1.
- Mirrored warnings panels, preview status icons and placement highlighting.
- Workflow-specific installation requirements, Blender-only import guide and updated user documentation.
- Earlier 0.8.6–0.8.9 work included original Halo 3 vehicle placement, foliage collision policy and live preparation logs; see TESTING.md and release history for scope.

## 0.8.5 — preparation fixes and searchable material/sky pickers

- **Skip objects with export problems:** optional partial preparation lists each excluded object and reason before confirmation. Objects stay in Blender. Compiler failures still stop preparation; at least one valid mesh is required.
- **Material validation:** uses materials assigned to evaluated faces. Unused material slots no longer prevent export. Highlighting an Asset List material still does not assign it.
- **Preparation warnings:** Continue/Cancel remain visible above Prepare. Warnings are no longer saved as failed builds, and underlying error lists are no longer overwritten by a generic confirmation error.
- **Existing shader picker:** shaders are grouped by level/shared category and selected through a searchable popup. Use Scan existing shaders first. Manual path entry remains available.
- **Sky picker:** searchable selection, visible selected scenario path, and selection stored independently of the scanned list. Use Find map skies first.
- **Level Imported:** normalized map-name matching and retained dropdown entries improve selection stability. The exact reported disappearance was not reproduced locally.
- **Static model:** replaces the confusing Source check label.
- **Export target:** Halo 3 supported; Reach Sapien is explicitly unavailable. Reach assets can still be converted to static Halo 3 geometry.


## 0.8.4

- Display original Halo material and bitmap names while preserving cache IDs, shader paths and image filenames.
- Upgrade old hashed material and numeric image names on scene load; recover missing bitmap names from the source map metadata. Preserve custom names and distinguish duplicate names with Blender suffixes.
- Keep Reach conversion IDs stable across display-name migration.

## 0.8.3

- Show current asset names and counts during material checks, mesh preparation and player-start checks.
- Show 16 numbered lighting stages, elapsed tool time, last output and time since output; no estimated percentage.
- Rename Folders and Setup and Halo 3 .map Files.

## 0.8.2

- Fix lightmapping scenes exported entirely as instances: export one existing renderable mesh as main structure, preferring authored geometry; retain other meshes as instances.
- Include the chosen structure object in the preparation report. Reject scenes containing no renderable surfaces before compilation.

## 0.8.1

- Clarify experimental Sapien preparation, shader, sky and repair labels.
- Add a separate preparation status box and loading button text, resetting after completion, cancellation or errors.

## 0.8.0

- Convert imported Reach meshes and preview textures into static Halo 3 level geometry, bitmap/shader tags and generated collision.
- Keep source meshes/materials/UVs intact; retain explicit Halo 3 shader overrides.
- Ignore unavailable Reach scenario skies when choosing an automatic Halo 3 sky.
- Rename the game selector to Import game and document the mixed-game workflow.

# 0.7.1

- Separate material loading from explicit assignment; identify material-only rows.
- Commit extracted placements inside an undo operator and discard pending results before undo/redo.
- Explicit material assignment isolates shared meshes.

# 0.7.0 - Reach importing and native scene origins

- Add Halo game selector with remembered folders, storage and catalogues.
- Add Reach indexing, resource-resolved BSP instances, material previews and static map extraction.
- Keep Reach previews separate from Halo 3 collision tools and retain source-game identity. Reach export is not implemented.
- Use native Origin to Geometry (Median Center) on all scene meshes, including previously centered meshes.
- Convert only diffuse, normal and transparency textures used in Blender previews, skipping unrelated lookup textures.

# 0.6.7 - Early public release

- Public name: HaloBridge - Blender 4.0 Importing.
- Add installation, first-map, feature, troubleshooting, architecture and limitations guides, release notes and contribution templates.
- Correct obsolete original-map collision/lighting descriptions; keep the draft-lighting option visible for imported scenes. Extraction and geometry-export algorithms are unchanged.

# 0.6.6

- Make pasted HaloBridge assets active instead of leaving the original object active. Deselect the temporary preview when its copy is selected, so moving the copy leaves the original in place.
- Give pasted ordinary assets distinct placement IDs when correcting stale paste selection.

# 0.6.5

- Track the actual temporary preview object separately from copied custom properties. Preview cleanup never deletes pasted or duplicated copies.
- Convert copies of previews to normal visible, exportable assets with independent placement identities, preserving their transforms and selection.
- Handle Blender retaining an unselected original preview as the active object after native paste.
- Check for copied preview flags on object-count/selection changes, without repeatedly scanning an unchanged scene.

# 0.6.4

- Choose the exposed upper surface at the 3D cursor for the initial test spawn, avoiding large underground terrain skirts. Existing Sapien starts remain untouched.
- Verified full saved Shrine geometry loading and player simulation in Sapien.

# 0.6.3

- Prepare now compiles current evaluated Blender meshes instead of cloning an original map base. Mesh edits, deletions, modifiers and transforms reach the static geometry export.
- Generate surface collision, an invisible sky boundary and an initial test player start. Original gameplay and animated object behavior are not reconstructed.
- Continue/Cancel popup explains incomplete-import and static-geometry limitations. Compiler errors remain fatal and roll back generated tags.
- Stage uniquely named shader tags locally; automatically select the imported map sky.
- Read map/category filters once per asset-list pass.
- Center disposable previews at the cursor without modifying cached or placed meshes; preserve the centered preview when placing.
- Fix float precision in legacy reference validation and add incomplete-import repair preserving existing edits/deletions.

## 0.6.2

- Highlight Create starter level shell template in blue.
- Report all detected validation issues with a count, keep all missing/deleted-piece details, log individual issues to Blender Info, and save timestamped diagnostic reports in managed storage. Background jobs preserve structured errors.
- Retain compiler errors from anywhere in the log, including errors followed by long progress output.
- Retry incomplete map caches in new folders without replacing files used by existing Blender scenes. Warn immediately after an incomplete map import and include the BSP names and extraction causes during preparation.
- Confirm a fresh Citadel extraction decodes all 16 BSPs. Jungle intro geometry still fails resource decoding; no universal whole-map or edited-map export claim.

## 0.6.1

- Correct the mistaken rendering warning: Shrine renders textured geometry above terrain; green wireframe was the underground camera view.
- Recover embedded BSP ASS source into a private content-addressed cache, verify size and Halo CRC, and reuse verified cached files. Never follow embedded file paths when writing recovered files.
- Keep edited-map export blocked while shader resolution and rebuilt collision/gameplay validation are unfinished. Recovery alone does not mark a map export-ready.

## 0.6.0

- Rename warning surfaces to HaloBridge Warnings and Messages and preparation to Prepare current scene for sapien.
- Add a map-sky picker populated from available Editing Kit scenarios. Preserve BSP sky slots when changing sky references.
- Route validated, unchanged whole-map imports through original editable terrain/collision/gameplay tags under the existing Prepare button. Added scenery is synchronized with persistent ownership.
- Check source BSP instance transforms; protect existing outputs and roll back failed preparation. Preserve original lighting.
- Report unsupported edited/deleted/duplicated original pieces and mixed custom terrain explicitly. Arbitrary edited-map BSP reconstruction remains unimplemented.

## 0.5.9

- Remove the original-map-copy operator/menu and clarify current-scene preparation.
- Always show Folders and setup; highlight Detect folders.
- Identify the Output level name field and show the rejected value in validation errors.
- Expose the sky source scenario instead of always using Deadlock. New full-map imports populate it.
- Stop before any export when visual map-reference objects are present, including mixed shell/map scenes. Previously these could be silently omitted.
- Whole-map round-trip export and skipped scenery extraction remain unresolved; this is not a playable-map reconstruction release.

# Changelog

## 0.5.8 — original-map Sapien copies

- Added Copy original map to Sapien, separate from Blender geometry preparation. It reads the selected map's scenario identity and copies that level's existing H3EK tag folder into a new output namespace.
- Redirects level-local tag references while retaining gameplay blocks, terrain/collision resources, scripts and lighting. External assets remain shared; compiled-map modifications absent from H3EK tags are not reconstructed.
- Verifies original file hashes remain unchanged and checks serialized tag data around reference relocation and scenario block counts. Pre-existing missing references are retained and reported.
- Uses the kit-wide lock and rollback on failure/cancellation. Existing levels and subsequent Sapien edits cannot be overwritten by repeating the copy; geometry builds cannot overwrite the copy project.
- Camera settings unsupported by this ManagedBlam are preserved byte-for-byte when they contain no source-level path requiring relocation.

## 0.5.7 — faster list redraws and verified scenery recovery

- Cached source-map enum options rather than rebuilding them for every row; cached asset icon lookups instead of scanning every scene object for each visible row.
- Kept the 100x working scale. A 1,500-row filtering benchmark (five passes) fell from 1.31 seconds to 0.012 seconds; this measures list filtering, not viewport rendering.
- Prepare for Sapien now resolves placed raw models through actual scenery → model → render/collision tag links. Only a unique match with an existing collision tag is accepted; missing/ambiguous matches report specific failures.
- Verified automatic warehouse-door linking and compilation in a separate H3EK test scenario with correct game-unit placement. No runtime collision or full-map round-trip claim is made.
- Fixed timer handoff between source resolution and level compilation. Full-map reference conversion remains separate work.

## 0.5.6 — 100x working units and source-map filtering

- New placements, map references and starter shells use 100 Blender units per Halo world unit, including map spacing and origins.
- Normalize geometry and scenery transforms on export so working units do not change in-game size. Mixed older/newer export units are rejected explicitly; existing objects are not silently resized.
- Added Level Imported map filtering alongside existing search/category/tab filters.
- Whole-map completion explicitly identifies the result as a visual reference, not Sapien-exportable content. Full-map gameplay/collision reconstruction remains unsupported.

## 0.5.5 — clearer asset search

- Promoted search to a boxed Search Assets bar immediately above the index list, with a magnifying-glass icon and clear button.
- Search updates while typing and filters by asset name, map or kind within the current tab and enabled categories.

## 0.5.4 — centered map origins and Outliner reveal

- Whole-map imports center each mesh's origin at its local bounding-box center and compensate object transforms to preserve world-space geometry and shared mesh data.
- Added Center existing map origins for older imported reference maps, with Blender Undo support; unrelated mesh users are preserved.
- Added Reveal selected asset in Outliner, enabled by default. Active HaloBridge object changes reveal the collection hierarchy in visible View Layer Outliners without changing selection.
- Retains 0.5.2 message controls; the reverted 0.5.3 scroll buttons are not included.

## 0.5.2 — visible messages and clearer export diagnostics

- Added a Warnings/Messages panel above HaloBridge and a fixed 3D View header control with message preview and full-message popover. Sidebar panels still share Blender's scrollbar.
- Removed bottom-of-panel messages; kept cancellation and report actions with messages.
- Marked raw render models as preview-only in the list and explained missing export collision before preparation.
- Replaced the generic source-mapping error with specific raw-model, legacy-model and missing-BSP-collision guidance; added selection of affected placed objects.
- Cached BSP assets with missing collision files now re-extract instead of reusing an incomplete cache. Raw-model gameplay/collision conversion is still unsupported.

## 0.5.1 — asset-list history and faster map assembly

- Added Asset List title and dedicated session Undo/Redo for hide, unhide, delete and indexing (30 changes), restoring list order and check state without touching scene objects.
- Added a centered empty-state hint in Hidden Assets.
- Batch original-map placement in short timer bursts; assemble off-scene and link the completed collection once, retaining cancellation rollback.
- Avoid repeated preview-icon scene searches while a job is running.
- Validated the cached Jungle map: 5,251 placements with preserved world transforms in 73 timer updates, about 6 seconds in background Blender. This excludes extraction and interactive viewport rendering.

## 0.5.0 — original map layout import

- Replaced full asset-library import with scenario-driven static scene reconstruction.
- Preserves original terrain and object world matrices, sharing meshes across repeated placements.
- Added grouped collections, cached scene extraction, per-stage progress, cancellation rollback, and an import report.
- Missing BSPs, textures and approximate variants are reported explicitly; gameplay and collision restoration are outside this visual-reference route.


## 0.4.0 — unified placement and import controls

- Unified Place asset(s) uses checked entries or the highlighted entry; multiple models share the cursor position.
- Added independent category toggle buttons and an always-highlighted Preview Mode control below the list.
- Renamed the swap action as requested.
- Bulk import loads materials without a mesh, reports individual extraction failures, and yields between placements with progress and cancellation.
- Added Import entire .map for the full indexed asset library at the cursor, not original level reconstruction.
- Starter shell now extracts ground textures, sets floor UVs, and enables Material Preview.


## 0.3.0 — catalogue organization

- Added checkboxes, filtered Select all/Clear checks, and batch placement with rollback on failure.
- Added Imported Assets / Hidden Assets tabs, per-row eye controls, bulk hide/unhide, and catalogue-only deletion.
- Replaced confusing replacement wording with Replace selected object, actionable guidance, and disabled invalid actions.
- Clarified map filename and Sapien preparation labels; moved Create starter level shell template directly below Detect folders.
- Hidden entries retain their original order and survive re-indexing.


## 0.2.0 — public alpha

- Public source and add-on archives exclude local demos, caches, game content, debug symbols, and machine-specific build paths.
- Steam library discovery supports custom library locations; missing requirements are explained by Check setup.
- Storage is automatic, with an optional Advanced storage control that preserves existing settings.
- Live selection previews, preview on/off, and placement preserving position, rotation and scale.
- Descriptive control tooltips and simplified setup.
- Includes source build scripts, synthetic tests, dependency notices, and release packaging checks.

Earlier 0.1.x packages were local development builds and are not intended as public releases.
