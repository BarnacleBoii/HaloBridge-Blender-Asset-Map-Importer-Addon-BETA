# Halo 2 Anniversary campaign (Saber3D) formats

Research notes for `HaloBridge.H2ACampaign`, a standalone reader for the remastered Halo 2
Anniversary campaign data shipped in MCC (`halo2\preload\paks\*.pck`). The tool lists and
extracts `.pck` entries, decodes `.pct` textures to PNG/DDS, and exports `.tpl` templates and
`.lg` level scenes to OBJ. It also writes HaloBridge map scenes, which the add-on imports
(see "HaloBridge integration" below).

All offsets are little-endian. "Verified" means checked against the MCC files with this tool
(numbers below are from the 2026-11 Steam build).

## Prior work and credits

H2A campaign extraction has been done before. Please credit these projects:

- **Haus (Wildenhaus)**: [Index](https://github.com/Wildenhaus/Index) (H2A asset browser and
  exporter, 2022, MIT-licensed `LibH2A`) and its successor library
  [LibSaber](https://github.com/Wildenhaus/LibSaber) (`LibSaber.Halo2A`). These are the source
  of the container layout, sentinel IDs, template/scene/geometry serializers, picture formats,
  buffer flag names (from game RTTI), and the normal unpacking math (from the game's
  `common_input.vsh`). Index credits zatarita, sleepyzay and Unordinal as well.
- **Zatarita**: [SeT](https://github.com/Zatarita/SeT), Saber editing tools for Halo CE
  Anniversary (`s3dpak`/`ipak`). It is the same engine family but a different container.

No code was copied. This tool is a fresh, dependency-free C# implementation that follows the
structure documented by LibSaber and checks it against the data. Findings that go beyond
those projects are marked **(new)**.

## Usage

Build (writes nothing into the repo except `obj/`, which is git-ignored):

```powershell
dotnet build source\H2ACampaign -c Release -o <outDir>
```

```text
HaloBridge.H2ACampaign list     <pck> [pattern]
HaloBridge.H2ACampaign header   <pck>
HaloBridge.H2ACampaign csvcheck <pck> [csv]
HaloBridge.H2ACampaign extract  <pck> <pattern> <outDir>
HaloBridge.H2ACampaign pct      <pck|file.pct> [pattern] <outDir> [--dds] [--all-mips]
HaloBridge.H2ACampaign pctinfo  <pck|file.pct> [pattern]
HaloBridge.H2ACampaign tpl      <pck|file.tpl> [pattern] <outDir> [--all-lods] [--helpers]
HaloBridge.H2ACampaign lg       <pck|file.lg>  [pattern] <outDir> [--all-lods] [--helpers]
HaloBridge.H2ACampaign info     <pck|file>     <pattern>
```

Patterns match the raw entry name, the name without its `<category>`, or the file name, and
accept `*` and `?`. Examples:

```powershell
$paks = "E:\SteamLibrary\steamapps\common\Halo The Master Chief Collection\halo2\preload\paks"
HaloBridge.H2ACampaign pct "$paks\shared.pck" "unsc_packing_crate-lid*" out\tex --dds
HaloBridge.H2ACampaign tpl "$paks\shared.pck" "<tpl>\crate_packing__h.tpl" out\obj
HaloBridge.H2ACampaign lg  "$paks\01a_tutorial.pck" out\level
```

OBJ output uses the game's Y-up space, with one `o` per submesh. The `.mtl` names the first
material texture as `<name>.png`, so decode those with `pct` into the same folder.

## Where things live (new)

| File | Contents |
|---|---|
| `<level>.pck` | Everything level-specific: one nested `1SERpak` for the scene (`...\prebuild\scenes\<level>.scn`, holding `.lg`, `.cdt`, `.ssl`, ...), plus per-level `<scene>\tpl\*.tpl` (`sm_geom_*`, `h00xx_7__h_tpl`). |
| `shared.pck` (13 GB) | All textures (4,632 `<textures>` + lightmaps/cube maps under `<project>\prebuild\scenes\<level>.scn\lm\` and `\lc\`) and all `<database>` templates (1,148 props, weapons, characters, vehicles). |
| `cache.pck` | Shaders (`<common>\prebuild\shaders\*.fx/.psh/.vsh`) and other common data. |
| `<name>.csv` | Directory listing of the matching `.pck` (see below). |

A level `.pck` lists every texture and database template it uses, but with **size 0**. Those
entries are references, and the bytes live in `shared.pck`. The tutorial has 1,321 such
references; only the 191 scene entries carry data.

## `.pck` container

Verified on all 19 paks (the csvs match 100%: 1,512/1,512 tutorial entries and 8,397/8,397
shared entries by name, size and nesting depth).

### Chunked zlib wrapper

```text
0x000000  int32   chunkCount          (tutorial: 0x2172 = 8,562)
0x000004  int32   mode                0 = zlib-compressed chunks
0x000008  int64   chunkOffset[chunkCount]   absolute file offsets
...       zero padding up to 0x600000 (the table area is fixed-size)
0x600000  chunk data
```

Each chunk is an independent zlib stream that inflates to 0x8000 bytes (the last one may be
shorter). Uncompressed offset `x` lives in chunk `x / 0x8000` at `x % 0x8000`. The tutorial
inflates to 280,542,886 bytes. `ChunkedFile` reads randomly with a one-chunk cache.

### `1SERpak` directory (inside the inflated stream)

```text
0x00  char[8]  "1SERpak\0"
0x08  ...      0x45-byte header in total. Contains what look like leaked 64-bit pointers
               (0x00007FFA...), a GUID at 0x24, int32 at 0x20 (unknown, not the entry count),
               and ends with 01 00 00 00 01. Not needed for reading.
0x45  int32    entryCount
0x49  int32    unknown (4 in every pak seen)
0x4D  byte     0
      entryCount x { int32 length; char[length] name }
      byte     0
      entryCount x int64 offset    (relative to this 1SERpak's start)
      byte     0
      entryCount x int32 size
```

If an entry's data starts with `1SERpak\0`, it is a nested directory with the same layout, and
its offsets are relative to the nested start. Scenes and the per-level `tpl`s are nested
(`<scene>\tpl\sm_geom_00011.tpl` wraps the single file `<scene>\tpl\sm_geom_00011.tpl\sm_geom_00011.tpl`).
Names keep their category prefix: `<textures>:x.pct`, `<database>:x.tpl`, `<scene>\...`,
`<tpl>\...`, `<project>\...`.

### `.csv`

One line per directory entry in the same order, formatted `<raw name>,<size>`. Nested entries
are prefixed with `- ` once per depth level. It is a convenience listing, and the binary
directory above is authoritative.

## Saber "1SER" files

Most payloads start with `"1SER"` followed by a 4- to 12-byte type tag, for example
`tpl\0`, `lg\0\xFF`, `cdt\0`, `cd_list\0`, `light_probe\0`, `ssl_data\0` or `sm_tpl_tbl\0`.
`.ssl` and `.ssl_vars` are plain text (`/* S3D_RESOURCE, VERSION 1000 ...`).

Header shared by `tpl` and `lg` (after the 8-byte magic and type):

```text
uint64 unk, uint64 unk, uint64 unk, int32 flags, GUID(16), int32 unk,
int32 stringCount, int32 unk,
stringCount x { uint16, byte, byte, int64, int64, int32 len + chars }   e.g. "<textures>:flat_nm.pct"
```

Many blocks inside use **sentinels**: `int16 id, int32 endOffset`. The end offset is
*absolute within the entry*, so unknown blocks can be skipped safely.

## `.pct` textures

Verified: all **6,099** `.pct` files in `shared.pck` parse, and every data block is exactly the
size the header predicts.

Sentinel blocks (int16 id, int32 absolute end):

| id | payload |
|---|---|
| `0x00F0` | uint32 `0x50494354` ("TCIP") |
| `0x0102` | int32 width, height, depth, faces |
| `0x00F2` | int32 format |
| `0x00F9` | int32 mip count (often a partial chain, e.g. 10 mips for 2048²) |
| `0x00FF` | pixel data to the block end |
| `0x0001` | end of file |

| format | meaning | count in shared.pck |
|---|---|---|
| `0x00` A8R8G8B8 | BGRA8 | 17 |
| `0x0A` A8L8 | L8, A8 (lightmap `*_dir`) | 28 |
| `0x0C` OXT1 | BC1, opaque | 1,372 |
| `0x0D` AXT1 | BC1, 1-bit alpha | 1 |
| `0x0F` DXT3 | BC2 | 0 seen |
| `0x11` DXT5 | BC3 (diffuse+alpha, `_spec`, cube maps) | 3,045 |
| `0x16` X8R8G8B8 | BGRX8 | 86 |
| `0x24` DXN | BC5 normal maps (`_nm`), Z reconstructed | 1,183 |
| `0x25` DXT5A | BC4 single channel | 281 |
| `0x26` A16B16G16R16F | RGBA half float | 2 |
| `0x2D` R9G9B9E5 | shared-exponent HDR (lightmap `*_rnm0..2`) | 84 |

No BC6H or BC7 appear. 1,366 textures have `faces = 6` (cube maps: `lc\*_cube.pct`,
`*_cube.pct` skies).

**Layout (new, verified visually):** face-major, like DDS. Face 0 comes with its whole mip chain
(largest first), then face 1, and so on. The opposite order produced scrambled faces.
`--dds` writes a DX10 DDS with the blocks unchanged. PNG output decodes mip 0, one file per
face (`_faceN`). HDR formats are clamped to [0,1] and sRGB-encoded for preview only.

Lightmaps: `lm\<level>_tex_rnm0..2` (4096², RGB9E5) are three-basis radiosity normal maps.
`_tex_dir` and `_vc_*` hold direction and vertex-colour variants. The atlas is packed per
object, and how its UVs map is not traced yet (UV set 1 in the `.lg` is the likely candidate).

## `.tpl` templates

```text
"1SER" "tpl\0" <1SER header>
"TPL1"
int32 bitCount, bytes[(bitCount+7)/8]   property bitset, then the properties present, in order:
  0 name (int32 str)   1 nameClass (int32 str)   2 state (uint16 + uint32)
  3 affixes (int32 str, e.g. "export_preserve_hierarchy\n\n...")
  4 ps (int32 str script, e.g. __type = "halo_actor")
  5 skin (count, uint16, byte, then 0xFFFF-terminated 4x4 matrices)
  6 trackAnim (animation; not parsed, the tool scans forward to "OGM1")
  7 onReadAnimExtra   8 bbox (2 x float3)
  9 lodDefinitions (int32 n, int32 props; [byte flag + n x int16 objectId] [flag + n x byte index] [flag + n x byte isLast])
 10 texList (uint32 n, uint16, uint32 end; n x int16 str; uint16 0xFFFF; uint32)
 11 geometry ("OGM1" graph, below)
```

Verified: all 1,148 `<database>` templates in `shared.pck` and all 89 tutorial `tpl`s export
without errors. 118 have animation tracks, and those reach the graph by scanning for `OGM1`.
61 hold no geometry (volumes, projectiles, spline cables).

## `OGM1` geometry graph (templates and `.lg`)

```text
"OGM1"  uint16 graphType (1 normal, 3 props, 4 = scene with LOD roots)  uint16  uint16
byte hasObjects; objects (below)
graphType 3: prop strings; graphType 4: [object ps strings] + LOD roots (below)
data sections, each uint16 id:
  0x0000 header   int32 end; int16 rootNode; int32 nodeCount, bufferCount, meshCount, subMeshCount; 2 x uint32
  0x0002 buffers  int32 end; sentinels 0 flags (uint16 bitCount + uint64 flags) / 1 strides (uint16) /
                  2 lengths (uint32) / 3 raw data (buffers back to back)
  0x0003 meshes   int32 end; sentinels 0 flags (bitset<int16>) / 2 per mesh: byte n, n x (int32 bufferId, int32 byteOffset)
  0x0004 submesh  int32 end; sentinels:
                  0 per submesh: uint16 vertexOffset, vertexCount, faceOffset, faceCount; int16 nodeId, skinCompoundId
                    (+ uint32 rotating flags and float pairs when the block is larger than 12 bytes per submesh)
                  1 int32 meshId   2 unknown (skipped by end offset)   3 bone ids (mesh flag 9)
                  4 UV scaling (mesh flag 30): byte n, n x (byte uvSet, int16 scale)
                  5 position/scale (mesh flag 3): 3 x int16 position, 3 x int16 scale
                  6/7/8 material as text / static binary / dynamic binary property bag
  0xFFFF end      int32 end
```

**Objects:** int16 count, uint16, uint16 propertyCount, uint16. Then, per property, a byte
"present" flag and one value per object, in this order: id, readName, state (7 bytes), parentId,
nextId, prevId, childId, animNumber, readAffixes, **matrixLT** (16 floats, row-vector),
matrixModel, **geomData** (bitset; for each set bit: uint32 3, byte 7, uint32 splitIndex,
uint32 numSplits, bbox), unkName (`|`-separated scene path), OBB (60 bytes), name (int16 str),
affixes.

**Buffer element types** (by flags): no flags means faces (3 x uint16). `VERT` means positions.
Flags equal to `BONE` alone mean a separate normal stream **(new)**. Anything else is
interleaved tangent/colour/UV data. The tool's computed strides match `ElementSize` for every
buffer in all 1,237 templates and all 15 `.lg` scenes.

| layout | bytes |
|---|---|
| `COMPRESSED_VERT` | 3 x int16 SNORM (/32767) position |
| `+NORM_IN_VERT4` (compressed) | +int16 packed normal (game `common_input.vsh` math) |
| uncompressed | 3 x float; `NORM_IN_VERT4` +float packed normal; `COMPRESSED_NORM` without `NORM_IN_VERT4` +3 floats **(new)** |
| `WEIGHT1..4`, `INDEX` | +1 byte each, +4 bytes bone indices |
| normal stream (`BONE` only, stride 4) **(new)** | UNORM8 x,y,z (+pad): n = 2v-1 |
| interleaved | per `TANG0..4` 4 x SNORM8, per `COLOR0..2` RGBA8, per `TEX0..4` 2 x int16 SNORM (if `CTEXn`) or 2 x float |

**Assembling a submesh:** for each `(bufferId, byteOffset)` of its mesh, element `i` sits at
`buffer.start + byteOffset + (vertexOffset + i) * stride`, and faces at
`... + (faceOffset + i) * 6`. Face indices are in the vertex-buffer space, so subtract
`vertexOffset`. Compressed positions are `snorm * scale + position` from section 5. UV0 is
multiplied by the UV-scaling value and V is flipped (`1 - v`).

**Object ownership and transform (new, verified):** a submesh belongs to the object whose
`geomData` split range `[splitIndex, splitIndex + numSplits)` contains the submesh index. Its
world position is `vertex × matrixLT` (row-vector). The submesh `nodeId` is 0 in all 11,982
submeshes listed by `info` across shared, tutorial and `.lg` files, so it does not identify the owner. On `crate_packing__h` the `.render.g` object's
matrixLT has a 0.317 scale; applying it puts the vertices inside the template bounding box
(−0.686..0.686 × 0..1.372 vs bbox −0.692..0.692 × 0..1.378). `matrixModel` looks like the same
transform in a Z-up convention and is not used.

**Normals check:** decoded normals agree with counter-clockwise triangle winding for 99.99% of
tutorial faces, and for ≥ 90% of faces in 1,015 of 1,087 shared templates. The rest are
foliage cards (acacia, fern, grass, vines) whose normals are deliberately bent or two-sided.

**LOD and helper filtering (new):**
- `.lg` LOD roots (graph type 4): uint32 n, uint32 props; then, each behind a byte flag:
  objectIds lists, `maxObjectLodIndices` lists, LOD distance lists (int32 n, uint32, flag,
  floats) and bboxes. `maxObjectLodIndices[k]` is the **end index of LOD level k** in that
  root's objectIds list (e.g. `[5,9,13]` with distances `[30,70,100]`). LOD0 is
  `objectIds[0 .. max[0])`.
- Templates: lodDefinitions point at `<tpl>@SkinCompound_N` objects (merged copies of the
  parts, one per LOD), and per-part lower LODs are children named `*_LOD1..3`. Exporting
  everything gives overlapping duplicates (the battle rifle came out twice), so by default the
  tool drops skin compounds and `_LODn` (n ≥ 1) objects. Index also skips skin compounds.
- Helper geometry hidden by default (`--helpers` keeps it): occluders (`*occl*`, `sun_ocluder`)
  and shadow casters (`*shadow_caster*`, `.shadowcaster_o`). Without this, the tutorial shows a
  1,300-unit occluder box.

## `.lg` level scene

```text
"1SER" "lg\0\xFF" <1SER header>
"SCN1"  uint32 propertyCount, bitset(propertyCount)
  0 texList (as in tpl)   1 ps (int32 str)   2 instMaterialInfo (uint32 n, byte, n x (str, str))
"OGM1" graph (graphType 4 with LOD roots on 13 of 15 levels)
```

Verified on all 15 campaign scenes. `00a_introduction` is a cutscene with an empty graph.

| level | objects | submeshes | normals OK |
|---|---|---|---|
| 01a_tutorial | 8,294 | 8,293 | 99.3% |
| 01b_spacestation | 11,575 | 11,574 | 98.9% |
| 03a_oldmombasa | 7,393 | 7,384 | 99.1% |
| 03b_newmombasa | 5,637 | 5,626 | 99.9% |
| 04a_gasgiant | 3,697 | 3,695 | 100% |
| 04b_floodlab | 4,795 | 4,793 | 100% |
| 05a_deltaapproach | 12,133 | 12,125 | 78.2% (heavy foliage) |
| 05b_deltatowers | 7,134 | 7,133 | 97.3% |
| 06a_sentinelwalls | 6,006 | 6,005 | 99.9% |
| 06b_floodzone | 3,365 | 3,362 | 100% |
| 07a_highcharity | 5,292 | 5,291 | 99.1% |
| 07b_forerunnership | 2,739 | 2,738 | 99.7% |
| 08a_deltacliffs | 8,876 | 8,874 | 99.9% |
| 08b_deltacontrol | 7,654 | 7,652 | 99.9% |

The tutorial exports (LOD0, no helpers) to 5.69 M vertices and 4.74 M triangles in about 8 s
(≈ 750 MB OBJ). Rendered in Blender, it is clearly Cairo Station's tower and ring of rooms.
The `.lg` holds the visible level geometry and its materials (138 distinct diffuse textures in
the tutorial), already placed in world space through each object's matrixLT.

## Saber → Halo coordinates (new, verified)

Saber is Y-up and measured in metres. Halo is Z-up and measured in world units (10 ft). Fitting the tutorial `.lg`
against the classic Halo 2 `01a_tutorial.map` BSP (via HaloBridge's own extractor) gives:

```text
halo = (x, -z, y) / 3.048        normals: normalize(x, -z, y)        no translation
```

Scale 1/3.048 fits best (106 of 6,000 sampled vertices within 5 cm of a classic vertex, against at most 61 for any
other scale). An ICP translation search moves the result by less than 3 cm. The axis swap is a proper rotation
(determinant +1), so triangle winding is kept. The remaining median vertex gap (~0.36 WU) is the remaster's new
detail geometry, not misalignment. Remastered visuals therefore line up with the classic level's collision and
object placements.

## HaloBridge integration (`map_scene`)

`HaloBridge.H2ACampaign map_scene <level.pck> <outDir>` (and the extractor job operation `h2a_campaign_scene`,
which calls the same code) writes the folder layout the extractor already uses for `.map` files:

- `scene.json`: `kind = halo3_map_scene`, `game = h2a`, `matrix_convention = row_vector`, one placement per
  LOD0 object (identity matrix; vertices are already in world space), grouped into Level geometry / Decals / Glass.
- `mesh_N.json`: `{materials, meshes:[{positions, uv, normals, segments:[{material, indices}]}]}` in Halo units.
- `tex_<name>.dds` / `.png`: base (`layer0.texName`) and normal (`<name>_nm`) textures from `shared.pck`, at
  the first mip no wider than `--max-texture` (default 2048, matching HaloBridge's texture-size setting).
  Each is kept as whichever is smaller: a single-mip DX10 DDS holding the game's own block data (no
  re-encoding; Blender 4.4 and 5.2 load BC1/BC3/BC5 DDS with pixels matching this tool's decoder, without a
  flip) or an optimized PNG (RGB when opaque, per-row filters, maximum deflate). On 120 campaign textures,
  BC1 was smaller as DDS 53/55 times (so BC1 isn't PNG-encoded), BC5 normal maps were about half the size as
  PNG (51/54), and BC3 varied. `--textures <dir>` puts them in a folder shared between levels.

Storage in the add-on: textures go to one `map_scenes\h2a_campaign_textures_<size>` folder for all levels
(the imported materials load their images from it, so it is kept). After a successful import, the level's
`mesh_N.json` geometry files are deleted, because Blender keeps the meshes and Prepare only reads `scene.json`.
Importing the level again re-extracts them in place in a few seconds. Measured on 01a_tutorial plus
07b_forerunnership: 366 MB in total after import (363 MB textures, 2 MB scene files), against ~1.1 GB with
per-level PNGs and kept geometry.

Material mapping from the Saber property bag:

| Saber | HaloBridge material JSON |
|---|---|
| `layer0.texName` | `diffuse` texture; `<texName>_nm` (if it exists) as `normal` |
| `layer0.tilingU/V` | texture `tiling` |
| `layer0.uvSetIdx` | which UV set is written as the mesh `uv` |
| `mtlName` contains `glass` (not `notransp_*`) | `alpha = blend`, `options.transparent = alpha` |
| `extraParams.transparency.enabled`, `mtlName = decal`, or a `*decal*` texture | `alpha = clip` |
| everything else | `alpha = opaque` |

Left out: lower LODs, helpers (occluders, shadow casters, `refl_box` reflection volumes) and the untextured
`red` placeholder material (no UVs, no lightmap). The tutorial has 7,734 pieces, 173 materials and 254
textures and is written in ~25 s (textures are prepared in parallel).

In the add-on, *Import Anniversary campaign level* (shown when the import game is Halo 2: Anniversary) finds
`halo2\preload\paks` from the groundhog maps folder. It runs the job into the content-addressed `map_scenes`
cache and imports with `map_scene.import_scene`, so objects carry `hb_game = h2a`. On Prepare,
`cross_game.prepare_steps` converts every material to TIFFs and a Halo 3 shader (`base_map`, `normal_map`,
`alpha_map`, tiling), the same route Reach and H2A multiplayer materials take.

### Individual assets (Index All Individual Assets)

`asset_index <shared.pck> <out.json>` (extractor job `h2a_campaign_index`) lists 1,070 templates with visible
LOD0 geometry as `model` assets and 2,250 base textures (names without `_nm`, `_spec`, `_em`, `_det`, `_mask`,
`_illum`) as `material` assets. `asset <shared.pck> <tag> <outDir>` (job `h2a_campaign_extract`) writes one
of them as a HaloBridge `preview.json` (Halo units, object transforms applied), with textures in the shared
campaign texture folder. Indexing reads every template once (~80 s cold, seconds when cached by the OS).
Extracting one asset takes 0.3–2 s.

Switchable parts for models (new). Every object is sorted into a HaloBridge region/permutation
(`SaberModel.ClassifyParts`), so the add-on's part toggles can switch variants in real time:

| objects (or their ancestors) | region / permutation | on by default |
|---|---|---|
| `_LODn`, `lodN`, LOD definitions/roots past LOD0 | `lod / lodN` | no |
| `_<group>_<variant>` with geometry (`_helmet_council`, `_lights_honor`, `_l_gun_major`...) | `<group> / <variant>` | the group's `base`/`default`/`*_base` variant (or every variant if it has none); never `shield`, never damage-like variants (`destroyed`, `major`, `medium`, `minor`, `broken`, `damage`) |
| other `damage` / `destroyed` objects | `damage / <name>` | no |
| everything else | `body / default` | yes |

`@SkinCompound_N` objects (merged duplicates of the parts, one per LOD) and engine helpers are left out.
When there is more than one part, the asset is written like the extractor's model parts: `parts.json`
holds every choice and `preview.json` (`selection_policy = 2`) the default selection. For example, the Elite
has helmet base/council/honor/ultra, lights, head, shield and lod regions, and the Ghost has damage, guns
and lod. Degenerate triangles (a repeated vertex) are dropped everywhere, because Blender's custom-normals
setter crashes on them (`battle_rifle__h` has 10).

Not right yet: props, weapons, vehicles, Marine and Master Chief come out correctly, but some skinned
characters (Elite, Grunt, Jackal) have parts out of place, because their pieces are stored relative to their
bones and are not skinned to the bind pose. The index notes this in the status of rigged models.

## Other scene files (not decoded yet)

| file | what is known |
|---|---|
| `sm_geom_NNNNN.tpl` | Ordinary templates, untextured (UV-less or a single UV set). **(new)** `sm_obj_tbl.tbl` (`1SERsm_tpl_tbl`) maps each light (`...\|main_light`) to an `sm_geom_*`, so these are **per-light shadow-map caster geometry**, not visible level geometry. They export fine but should not be imported as render geometry. |
| `h00xx_7__h_tpl.tpl` | Small per-level templates with `|shadowcaster` children in the `.lg` paths. Likely instanced level pieces; placement is not traced. |
| `.cdt` (`1SERcdt`, 40 MB) | Probably collision (Havok?). Not looked at beyond the magic. |
| `.cd_list` / `.h2a2_cd_list` (`1SERcd_list`) | Collision/instance list. LibSaber has a `CdListSerializer` that would be the starting point. |
| `.ssl` / `.ssl_vars` | Text "SSL" scene script, autogenerated by `MayaSSLGenerator`: imports `classes.*` and declares one `var $<scene path> : <Class>` per scripted object (lights, flares, terminals, glass). Instance transforms are not in the script itself. |
| `.ssl_data` | `1SERssl_data` binary companion to the script. |
| `.light_probe2` (`1SERlight_probe`) | Light probe grid, 8.5 MB. |
| `.class_list`, `.dom_list`, `.light_list` | Small lists, not examined. |
| Materials | Property bags (`layer0..3` with `texName`, `tint`, `tilingU/V`, `uvSetIdx`, `blending`; `shadingMtl_Tex/Mtl`; `lm`; `extraParams`). The tool reads all three encodings into a dictionary but only uses `texName` and `shadingMtl_Tex`. |

## Still unknown or not done

- Placement of actors/props (`<database>` templates) inside a level: the `.lg` only contains
  baked level geometry. Spawned objects probably come from `.cd_list` / `.ssl_data`.
- Skinning export (bone weights are decoded by flag size but not written; OBJ has no skin).
- Which UV set the lightmap atlas uses, and the RNM basis convention.
- Collision (`.cdt`), light probes, and the unknown submesh block 2.
- The 1SER header fields and the 0x45-byte 1SERpak header.
- Material layers 1–3 (vertex-colour blended, 499 tutorial submeshes) use layer 0 only. They could become
  `shader_terrain` blends later.
- Specular (`_spec`) maps and the shading presets behind `mtlName` (not found in any `.pck` listing) are not
  converted.
- Normal-map green-channel convention (DirectX vs OpenGL) is not verified against Halo 3 in Sapien.
