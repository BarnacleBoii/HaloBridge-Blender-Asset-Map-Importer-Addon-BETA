"""Export current evaluated meshes as static test geometry, never a donor BSP."""
import hashlib
from collections import Counter
from pathlib import Path
import bpy
from mathutils import Vector, Matrix
from . import blender_ops, compat, cross_game, export_review, vehicles, collision_policy, invisible_blocks, original_scenery
from .catalog import read_json
from .diagnostics import ValidationError


H2_OBJECT_COLLECTIONS = ('Machines', 'Scenery', 'Controls', 'Crates')
H2_STRUCTURE_COLLECTIONS = ('Terrain', 'BSP instances') + H2_OBJECT_COLLECTIONS


def _split_see_through(clone, temp, meshes):
    """Move a structure piece's see-through faces (Halo 2 transparent layers: Midship's glass and
    energy panels) into a separate instance object; returns it, or None when there are none.
    Tool sorts blended faces in the structure as separate parts, and a section allows 255
    ("section 'cluster 0' has too many parts (count=330, max=255)"). The layers are unlit, so
    they lose nothing as an instance. Works on a copy: BSP pieces can share one mesh."""
    import bmesh
    mats = clone.data.materials
    # Halo CE glows (chicago/generic, additive) stay in the structure as before: split out, Death
    # Island's and Infinity's layers became one piece Tool merges over its 32,767-vertex limit.
    see = {i for i, m in enumerate(mats) if m and m.get('hb_transparent') and not m.get('hb_h1_class')}
    if not see or not any(p.material_index in see for p in clone.data.polygons):
        return None
    solid = clone.data.copy(); layer = clone.data.copy(); meshes += [solid, layer]
    for mesh, drop in ((solid, lambda f: f.material_index in see), (layer, lambda f: f.material_index not in see)):
        bm = bmesh.new(); bm.from_mesh(mesh)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if drop(f)], context='FACES')
        bm.to_mesh(mesh); bm.free()
    clone.data = solid
    piece = bpy.data.objects.new('%hb_' + str(len(temp.objects)), layer); temp.collection.objects.link(piece)
    piece.matrix_world = clone.matrix_world.copy(); piece['hb_working_units'] = clone.get('hb_working_units', 1)
    return piece


def _h2_unlit_cluster(obj, config, progress=lambda m: None):
    """True for a Halo 2 terrain cluster Halo 2 did not lightmap (see h2_lightmaps.unlit_clusters).
    Its object is named '<BSP tag> / <Clusters> / NNN' (NNN the cluster index)."""
    parts = obj.name.split(' / ')
    index = parts[-1].split('.')[0]  # Blender may add .001
    if len(parts) < 3 or parts[-2] != '<Clusters>' or not index.isdigit() or not config.get('h2_lightmap_source'):
        return False
    if 'h2_unlit' not in config:
        from . import h2_lightmaps
        try:
            h2ek, scenario = config['h2_lightmap_source']
            config['h2_unlit'] = h2_lightmaps.unlit_clusters(h2_lightmaps.export(h2ek, scenario, config['cache'], progress))
        except Exception as error:  # the lighting copy reports this again later; keep every cluster
            config['h2_unlit'] = {}
            progress('Halo 2 lighting could not be read: ' + str(error).splitlines()[0][:200])
    unlit = config['h2_unlit'].get(parts[0].lower(), set())
    if int(index) in unlit:
        progress('Halo 2 terrain ' + obj.name + ': not lightmapped in Halo 2 (water or a far plane); compiled as a per-vertex lit piece so it takes no lightmap space')
        return True
    return False


def sky_strength(config):
    """(sun, shade) strengths for a Halo 2 sky's lights, from the Sapien preparation panel."""
    return (float(config.get('h2_sun_strength', 1.0)), float(config.get('h2_sky_strength', 1.0)))


def objects(scene):
    return [o for o in scene.objects if o.type=='MESH' and not o.get('hb_preview') and not vehicles.selected_vehicle(o) and not invisible_blocks.selected(o)
            and not original_scenery.selected(o) and (o.get('hb_map_reference') or not o.get('hb_ignore'))]


SKY_FOLDERS = {'sky', 'skies'}
INSTANCE_DEFINITION_LIMIT = 1024

def is_sky(obj):
    if obj.get('hb_map_reference') and any(c.name.split('.')[0]=='Skies' for c in obj.users_collection):
        return True
    # Sky models placed from an index (Halo CE "sky\...", Halo 2 "scenarios\skies\...")
    # are enormous domes; the selected Sky supplies the level's sky instead.
    tag = obj.get('hb_source_tag', '').lower().replace('/', '\\')
    return bool(tag) and obj.get('hb_kind') == 'model' and any(part in SKY_FOLDERS for part in tag.split('\\')[:-1])


def warnings(scene):
    result=[]
    kept=[o for o in scene.objects if original_scenery.selected(o)]
    if kept:
        result.append(str(len(kept))+' unedited scenery object(s) from the Editing Kit scenario will be placed as their original scenery tags, keeping their own collision and physics.')
    changed=original_scenery.edited(scene)
    if changed:
        result.append(str(len(changed))+' edited scenario scenery object(s) will export as static geometry instead of their original scenery tags: '+', '.join(o.name for o in changed[:5])+(' ...' if len(changed)>5 else ''))
    if any(o.get('hb_map_reference') or o.get('hb_id') for o in objects(scene)):
        result.append('Automatic collision first tries the verified original source-game collision geometry. Unmatched or edited static meshes use the available box or surface fallback. Render-only foliage has no generated collision. Original vehicle placements use their game tags instead.')
    if any(m and m.name.startswith('+sky') for o in objects(scene) for m in o.data.materials):
        result.append('Sky-only faces are replaced by an enclosing sky boundary; solid ground and other mesh surfaces are retained.')
    if any(simple_collision(o) for o in objects(scene)):
        result.append("Simple box fallback encloses eligible character and shield surfaces when original collision is unavailable. Set Static collision to Mesh surfaces for detailed contact or openings.")
    if any(is_sky(o) for o in objects(scene)):
        result.append('Imported sky meshes are omitted from solid geometry. With Sapien Sky on "Original map / default sky", a Halo CE or Halo 2 map\'s own sky layers are converted into the level\'s sky; otherwise the selected sky is used.')
    for manifest in sorted({o.get('hb_map_manifest') for o in objects(scene) if o.get('hb_map_manifest')}):
        data=read_json(manifest,{})
        if data.get('decoded_bsps',0)<data.get('expected_bsps',0):
            result.append('The import is incomplete: only geometry currently present in Blender will be exported. Missing terrain will remain missing.')
    if any(m and m.get('hb_custom_shader') for o in objects(scene) for m in o.data.materials):
        result.append('Editable materials are baked into level-local textures and shaders. Save your painted images in the blend. Dynamic Halo color changes, reflections and layered shader behavior are not preserved in this baked result.')
    if any(not m.get('hb_custom_shader') for m in cross_game.reach_materials(objects(scene)).values()):
        result.append("Assets from other games use converted textures on static geometry. Layered shaders, water, glow and animated behavior are approximated; transparency uses cutout alpha.")
    return result


def simple_collision(obj):
    mode = getattr(obj, 'hb_static_collision', 'AUTO')
    if mode != 'AUTO':
        return mode == 'BOX'
    tag = obj.get('hb_source_tag', '').lower().replace(chr(92), '/')
    return tag.startswith('objects/characters/') or tag.endswith('/cov_portable_shield/cov_portable_shield')


def ambiguous_collision(vertices, faces):
    """True when welded collision edges are shared by more than two faces.

    Tool welds coincident vertices, so separate pieces that touch create
    ambiguous edges even though each piece is clean on its own.
    """
    if not vertices: return False
    lo = [min(v[a] for v in vertices) for a in range(3)]
    hi = [max(v[a] for v in vertices) for a in range(3)]
    step = max(max(h - l for l, h in zip(lo, hi)) * 1e-5, 1e-6)
    key = [tuple(round(c / step) for c in v) for v in vertices]
    uses = Counter()
    for face in faces:
        welded = [key[i] for i in face]
        for a, b in zip(welded, welded[1:] + welded[:1]):
            if a != b: uses[(a, b) if a < b else (b, a)] += 1
    return any(count > 2 for count in uses.values())


CLEAN_DISTANCE = 0.002  # world units (about 0.24 inch): below what Tool can tell apart


# Halo 3 Tool allows 32,767 collision surfaces per instance ("collision geometry is too
# large"); its surface count runs well above the triangle count (Anniversary rock
# clusters simplified to 20,000 triangles were still over), so keep a wide margin.
COLLISION_TRIANGLE_LIMIT=10000


def triangle_count(mesh, slots):
    return sum(len(f.vertices) - 2 for f in mesh.polygons if f.material_index in slots)


# Halo 2: Anniversary collision over the limit is decimated to half, and what is still over
# is cut into pieces (each its own collision object) rather than simplified further. Each
# piece is one more instanced geometry definition (1,024 per BSP), so at most this many.
COLLISION_DECIMATE_RATIO = 0.5
MAX_COLLISION_PIECES = 8


def _clean_pass(bm, weld):
    import bmesh
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=weld)
    bmesh.ops.dissolve_degenerate(bm, edges=bm.edges, dist=weld)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_area() <= weld * weld * .5], context='FACES')
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')


def _triangles(bm):
    return sum(len(f.verts) - 2 for f in bm.faces)


def decimated(bm, ratio):
    """bm reduced with Blender's Decimate modifier (Collapse) to about ratio of its triangles."""
    import bmesh
    # Only the current view layer has an evaluated depsgraph outside a window; the
    # temporary object is evaluated there on its own and removed again.
    mesh = bpy.data.meshes.new('HaloBridge collision decimate'); bm.to_mesh(mesh)
    obj = bpy.data.objects.new('HaloBridge collision decimate', mesh)
    try:
        bpy.context.scene.collection.objects.link(obj)
        modifier = obj.modifiers.new('Decimate', 'DECIMATE'); modifier.ratio = ratio
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = obj.evaluated_get(depsgraph)
        out = bmesh.new(); out.from_mesh(evaluated.to_mesh())
        evaluated.to_mesh_clear()
        return out
    finally:
        bpy.data.objects.remove(obj, do_unlink=True); bpy.data.meshes.remove(mesh)


def cleaned_surface(mesh, slots, distance=CLEAN_DISTANCE, max_triangles=COLLISION_TRIANGLE_LIMIT, decimate=False):
    """The mesh's own collision surfaces, cleaned the way Tool needs them.

    Imported render meshes can hold vertices a hair apart, zero-length edges
    and sliver triangles; Tool welds those into "degenerate collision edges" and
    stops. Merge vertices closer than distance, dissolve degenerate edges and
    faces, and drop loose pieces. Surfaces denser than Tool's collision limit are
    simplified by welding nearby vertices with a growing distance until they fit.
    With decimate (Halo 2: Anniversary), they are instead decimated to half (further
    only when even MAX_COLLISION_PIECES pieces wouldn't hold them) and may stay over
    max_triangles: faces come sorted along the longest axis, so that chunk_instances
    can cut them into compact pieces.
    Returns (vertices, faces) in mesh space.
    """
    import bmesh
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.material_index not in slots], context='FACES')
        size = max((max(v.co[a] for v in bm.verts) - min(v.co[a] for v in bm.verts) for a in range(3)), default=0)
        weld = distance
        _clean_pass(bm, weld)
        if decimate and max_triangles and _triangles(bm) > max_triangles:
            ratio = min(COLLISION_DECIMATE_RATIO, max_triangles * MAX_COLLISION_PIECES / _triangles(bm))
            reduced = decimated(bm, ratio); bm.free(); bm = reduced
            bmesh.ops.triangulate(bm, faces=bm.faces)
            _clean_pass(bm, weld)
        else:
            for _ in range(24):
                if not max_triangles or _triangles(bm) <= max_triangles:
                    break
                weld = max(weld * 1.6, size / 4000)
                _clean_pass(bm, weld)
        bm.verts.index_update()
        vertices = [tuple(v.co) for v in bm.verts]
        faces = [tuple(v.index for v in f.verts) for f in bm.faces]
        if decimate and vertices:
            axis = max(range(3), key=lambda a: max(v[a] for v in vertices) - min(v[a] for v in vertices))
            faces.sort(key=lambda face: sum(vertices[i][axis] for i in face) / len(face))
        return vertices, faces
    finally:
        bm.free()


def add_collision_geometry(mesh, slot, corners, faces):
    # Append only to the temporary export mesh, keeping all render loops and UVs.
    # bmesh resizes every attribute layer consistently. Raw loops.add/polygons.add
    # crashed (access violation) on meshes whose UV layers were rebuilt for
    # converted cross-game materials.
    import bmesh
    start, loop_start = len(mesh.vertices), len(mesh.loops)
    bm = bmesh.new()
    try:
        bm.from_mesh(mesh)
        added = [bm.verts.new(co) for co in corners]
        bm.verts.index_update()
        for vertices in faces:
            try:
                face = bm.faces.new([added[v] for v in vertices])
            except (ValueError, IndexError):
                continue  # duplicate or degenerate collision face
            face.material_index = slot
        bm.to_mesh(mesh)
    finally:
        bm.free()
    mesh.update(calc_edges=True)
    # Added elements keep uninitialized attribute memory (Blender 5.2): their UVs
    # could be NaN, which makes Tool reject the whole ASS. Collision faces are not
    # rendered, so zero UVs and white colors are safe.
    for layer in mesh.uv_layers:
        values = [0.0] * (len(layer.data) * 2)
        layer.data.foreach_get('uv', values)
        values[loop_start * 2:] = [0.0] * (len(values) - loop_start * 2)
        layer.data.foreach_set('uv', values)
    for attribute in mesh.color_attributes:
        first_new = loop_start if attribute.domain == 'CORNER' else start
        values = [0.0] * (len(attribute.data) * 4)
        attribute.data.foreach_get('color', values)
        values[first_new * 4:] = [1.0] * (len(values) - first_new * 4)
        attribute.data.foreach_set('color', values)


def repair_texcoords(objects):
    """Replace non-finite UVs with 0 on export copies; returns {mesh name: count}.

    Tool rejects the whole level for one NaN texture coordinate. They can come
    from user UV operations on zero-area faces; the source meshes are not changed.
    """
    import math
    repaired = {}
    for mesh in {obj.data for obj in objects if obj.type == 'MESH'}:
        for layer in mesh.uv_layers:
            values = [0.0] * (len(layer.data) * 2)
            layer.data.foreach_get('uv', values)
            bad = [i for i, value in enumerate(values) if not math.isfinite(value)]
            if bad:
                for i in bad:
                    values[i] = 0.0
                layer.data.foreach_set('uv', values)
                repaired[mesh.name] = repaired.get(mesh.name, 0) + len({i // 2 for i in bad})
    return repaired


# Tool: "section 'global' has too many vertices (count=35764, max=32767)". Render
# vertices are distinct position/UV/normal corners; keep a margin for Tool's own count.
RENDER_VERTEX_LIMIT=30000


def corner_keys(data):
    """One integer per corner (loop): equal for corners that make the same render vertex."""
    import numpy as np
    count=len(data.loops)
    vertex=np.empty(count,dtype=np.int32);data.loops.foreach_get('vertex_index',vertex)
    columns=[vertex.astype(np.float64)[:,None]]
    if data.uv_layers.active:
        uv=np.empty(count*2,dtype=np.float32);data.uv_layers.active.data.foreach_get('uv',uv)
        columns.append(np.round(uv.reshape(-1,2).astype(np.float64),4))
    columns.append(np.round(np.array(compat.corner_normals(data),dtype=np.float64).reshape(-1,3),3))
    return np.unique(np.hstack(columns),axis=0,return_inverse=True)[1].ravel()


def chunk_instances(scene, meshes, names, progress):
    steps = chunk_instances_steps(scene, meshes, names, progress)
    for _ in steps:
        pass


def chunk_instances_steps(scene, meshes, names, progress):
    """chunk_instances() one object at a time (a generator, so Blender keeps responding).

    Partition temporary instance faces in local space, keeping shared placements aligned.

    Each part stays under Tool's render limits: 16,000 render triangles (indices) and
    RENDER_VERTEX_LIMIT render vertices (dense cards such as grass reach the vertex
    limit first)."""
    import bmesh
    shared={}
    for obj in list(scene.objects):
        if not obj.name.startswith('%'):continue
        data=obj.data
        if data not in shared:
            yield
            batches=[];start=0;cost=0;vertices=0;collision=0
            # Set on cleaned Halo 2: Anniversary collision still over Tool's limit after decimating.
            collision_limit=int(data.get('hb_collision_part_limit',0))
            for face in data.polygons:
                flags=data.materials[face.material_index].ass_jms
                # Collision-only faces are not rendered, so they don't use render indices.
                double=2 if flags.two_sided or flags.transparent_2_sided else 1
                triangles=0 if flags.collision_only else (len(face.vertices)-2)*double
                # Tool's render vertex count can't be predicted from Blender's shared
                # vertices (it counted 36,964 for a two-sided tree whose distinct corners
                # gave 28,562), but it never exceeds one vertex per face corner.
                corners=0 if flags.collision_only else face.loop_total*double
                solid=len(face.vertices)-2 if collision_limit and not flags.render_only else 0
                if (cost+triangles>16000 or vertices+corners>RENDER_VERTEX_LIMIT or collision+solid>collision_limit>0) and start<face.index:
                    batches.append((start,face.index));start=face.index;cost=0;vertices=0;collision=0
                vertices+=corners
                cost+=triangles;collision+=solid
            if not batches:shared[data]=[];continue
            batches.append((start,len(data.polygons)))
            parts=[]
            for lo,hi in batches:
                bm=bmesh.new()
                try:
                    bm.from_mesh(data)
                    bmesh.ops.delete(bm,geom=[f for f in bm.faces if not lo<=f.index<hi],context='FACES')
                    part=data.copy();meshes.append(part);bm.to_mesh(part);part.update();parts.append(part)
                finally:bm.free()
            shared[data]=parts
        parts=shared[data]
        if not parts:continue
        label=names[obj.name.lstrip('%').split('.')[0]]
        obj.data=parts[0]
        for part in parts[1:]:
            clone=bpy.data.objects.new('%hb_'+str(len(scene.objects)),part);scene.collection.objects.link(clone)
            clone.matrix_world=obj.matrix_world.copy();clone['hb_working_units']=1
            names[clone.name.lstrip('%').split('.')[0]]=label
        limit=int(obj.data.get('hb_collision_part_limit',0))
        progress(f'{label}: exported as {len(parts)} aligned parts to stay under Halo 3\'s render limits (16,000 triangles and {RENDER_VERTEX_LIMIT:,} vertices per part)'
                 +(f' and collision limit ({limit:,} collision triangles per part)' if limit else '')+'.')


def export(config,path,progress=None):
    steps=export_steps(config,path,progress)
    while True:
        try:next(steps)
        except StopIteration as done:return done.value


def export_steps(config,path,progress=None):
    """export() a little at a time: yields between materials and objects, so preparation
    can run from a timer and Blender keeps redrawing and responding. Halo 2 water definitions
    (h2_water) are added to the scene for the export and removed afterwards."""
    from . import h2_water
    progress=progress or (lambda message:None)
    added=h2_water.add_planes(bpy.context.scene,config,progress)
    if added:bpy.context.view_layer.update()
    try:
        return (yield from _export_steps(config,path,progress))
    finally:
        h2_water.remove(added)


def _export_steps(config,path,progress=None):
    progress=progress or (lambda message:None)
    source=bpy.context.scene;depsgraph=bpy.context.evaluated_depsgraph_get()
    original_scenery.reset_cache()
    blockers=invisible_blocks.plan(source,config)+original_scenery.plan(source,config)
    config['vehicle_placements']=vehicles.plan(source,config)
    for placement in config['vehicle_placements']:progress('Original vehicle placement: '+placement['tag']+' (excluded from static geometry)')
    selected=[o for o in objects(source) if not is_sky(o)]
    if not selected:raise ValidationError(['There are no meshes to export.'])
    blender_ops.ensure_exporter()
    progress(f'Checking {len(selected):,} objects and their materials...')
    issues,used,reach=yield from export_review.inspect_steps(selected,config)
    if issues and not config.get('skip_invalid'):
        raise ValidationError(export_review.messages(issues)+['To omit these entire objects, enable Skip objects with export problems and prepare again.'])
    selected=[obj for obj in selected if obj.name not in issues]
    config['skipped_objects']=issues
    if not selected:raise ValidationError(['No exportable objects remain. Fix at least one object before preparing.'])
    paints = {}
    managed_ids = {p['id'] for p in config['vehicle_placements']}
    for obj in source.objects:
        if not vehicles.selected_vehicle(obj) or obj.get('hb_vehicle_id') not in managed_ids or obj.get('hb_preview') or obj.get('hb_ignore') and not obj.get('hb_map_reference'):
            continue
        slots = {}
        for material_slot in obj.material_slots:
            mat = material_slot.material
            if not mat or not mat.get('hb_custom_shader'):
                continue
            original = mat.get('hb_source_shader')
            if not original or mat.get('hb_custom_shader') != 'colors':
                raise ValidationError([obj.name + ': select an original vehicle material and create editable colors from it.'])
            if original in slots and slots[original] != mat.as_pointer():
                raise ValidationError([obj.name + ': two paint materials replace the same original shader: ' + original])
            from . import editable_materials
            editable_materials.validate(mat)
            if not editable_materials.repeats_on_uv_tiles(mat):
                raise ValidationError([obj.name + ': original vehicle paint requires repeating images and whole-number UV tiling.'])
            slots[original] = mat.as_pointer()
            reach[mat.as_pointer()] = mat
        if slots:
            paints[obj['hb_vehicle_id']] = slots
    cross_game.MAX_BITMAP=int(config.get('max_texture_size',cross_game.DEFAULT_BITMAP))
    # The Halo 2 Editing Kit an imported Halo 2 map was built with: its shader tags name each
    # surface's material (footstep sounds, impact effects).
    from . import h2_lightmaps
    found=h2_lightmaps.source([o for o in selected if o.get('hb_game')=='halo2'][:200])
    if found:config['h2_kit']=found[0]
    converted=yield from cross_game.prepare_steps(selected,Path(path).parent/"converted_textures",progress,materials=reach,config=config)
    for placement in config['vehicle_placements']:
        slots = paints.get(placement['id'], {})
        if slots:
            placement['paint'] = {tag: converted[key]['name'] for tag, key in slots.items()}
    config["converted_shaders"]=[entry for entry in converted.values() if not entry.get('standin')]
    if config.get('sky_mode')=='object':
        from . import sky_export
        sky=sky_export.sky_object(source)
        if sky is None:
            raise ValidationError(['Sapien Sky is set to a sky from another game, but its sky object (Sapien Sky collection) is missing. Choose the sky again under Sapien Sky, or choose a sky from the '+config.get('game','halo3')+' Editing Kit.'])
        progress('Converting the sky: '+sky.name)
        config['sky_object']=sky_export.export_chosen_sky(source,sky,Path(path).parent/'sky',progress,strength=sky_strength(config))
        config['converted_shaders']+=config['sky_object']['shaders']
    elif config.get('sky_auto'):
        # An imported Halo CE / Halo 2 map keeps its own sky: its layers become the level's sky.
        from . import sky_export
        layers=sky_export.map_skies(source,config.get('game','halo3'))
        if layers:
            progress('Converting the imported map sky ('+str(len(layers))+' layers)')
            config['sky_object']=sky_export.export_map_sky(source,layers,Path(path).parent/'sky',progress,strength=sky_strength(config))
            config['converted_shaders']+=config['sky_object']['shaders']
    aliases={entry["name"]:dict(name=entry["name"],generated=True) for entry in converted.values()}
    for entry in converted.values():
        if entry.get('standin'):  # a Halo 3 shader copied into the level under the material's name
            aliases[entry["name"]]=dict(name=entry["name"],source=str(Path(config['kit'])/'tags'/entry['standin']))
    for obj in selected:
        for mat in used[obj.name]:
            if mat.name.startswith('+') or mat.as_pointer() in converted:continue
            tag=mat.get('hb_shader','').replace('/','\\')
            aliases[tag]=dict(name='hb_'+hashlib.sha256(tag.encode()).hexdigest()[:20],source=str(export_review.shader_file(config['kit'],tag)))
    config['shader_aliases']=aliases
    config['geometry_names']={}
    config['collision_routes']={};routes={}
    temp=bpy.data.scenes.new('HaloBridge current geometry');meshes=[];materials=[];cache={};material_cache={}
    old=bpy.context.window.scene;bounds=[];spawn=None;spawn_area=0;structure_candidates=[]
    try:
        for index,obj in enumerate(selected,1):
            yield
            key=None;clone=None;fresh=False
            try:
                progress(f'Preparing asset {index}/{len(selected)}: {obj.name}')
                units=float(obj.get('hb_working_units',source.get('hb_working_units',100)))
                if units<=0:raise ValidationError([obj.name+': invalid working scale.'])
                location,rotation,scale=obj.matrix_world.decompose()
                stretch=(rotation.to_matrix().inverted()@obj.matrix_world.to_3x3())*(1/units)
                original_key=(obj.get('hb_game',''),obj.get('hb_section'),obj.get('hb_source_tag',''),obj.get('hb_cache',''),obj.get('hb_parts_enabled',''),getattr(obj,'hb_static_collision','AUTO'),obj.get('hb_mesh_signature',''),str(obj.get('hb_collision_fallback','')))
                proxy=simple_collision(obj)
                precise=bool(obj.get("hb_id") or obj.get("hb_map_reference"))
                key=(original_key,proxy,precise,obj.data.as_pointer(),obj.as_pointer() if obj.modifiers else 0,tuple(v for row in stretch for v in row))
                if key not in cache:
                    fresh=True
                    mesh=bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph),preserve_all_data_layers=True,depsgraph=depsgraph)
                    meshes.append(mesh);cache[key]=mesh
                    if any(m and m.as_pointer() in converted for m in mesh.materials):
                        # Blender 4 can share evaluated UV buffers; recreate layers before writes.
                        layers=[(layer.name,[tuple(loop.uv) for loop in layer.data]) for layer in mesh.uv_layers]
                        active=mesh.uv_layers.active_index
                        for layer in list(mesh.uv_layers):mesh.uv_layers.remove(layer)
                        for name,values in layers:
                            layer=mesh.uv_layers.new(name=name)
                            layer.data.foreach_set('uv',[value for pair in values for value in pair])
                        if layers:mesh.uv_layers.active_index=active
                    # Unused legacy slots must not reach the ASS material validator.
                    slot_ids=sorted({face.material_index for face in mesh.polygons})
                    slots=[mesh.materials[i] for i in slot_ids]
                    indices=[slot_ids.index(face.material_index) for face in mesh.polygons]
                    mesh.materials.clear()
                    for mat in slots:mesh.materials.append(mat)
                    for face,index in zip(mesh.polygons,indices):face.material_index=index
                    mesh.transform(stretch.to_4x4())
                    if stretch.determinant()<0:mesh.flip_normals()
                    sky_slots={i for i,m in enumerate(mesh.materials) if m and m.name.startswith('+sky')}
                    if sky_slots:
                        import bmesh
                        bm=bmesh.new();bm.from_mesh(mesh)
                        bmesh.ops.delete(bm,geom=[f for f in bm.faces if f.material_index in sky_slots],context='FACES')
                        bm.to_mesh(mesh);bm.free()
                    # Open imported render meshes are surfaces, not sealed volumes.
                    # Halo's one-sided transparent geometry flag permits open collision
                    # edges without duplicating render faces or changing shader alpha.
                    edge_uses=Counter(edge for face in mesh.polygons for edge in face.edge_keys)
                    open_surface=any(count!=2 for count in edge_uses.values())
                    # Leaf cards must not become solid collision solely because they render.
                    from . import original_collision
                    original=original_collision.get(obj, config, progress) if getattr(obj,'hb_static_collision','AUTO')=='AUTO' else None
                    # Set when Tool rejected this object's collision: 'clean' (its own surfaces,
                    # cleaned), then 'box', then 'none' (render only).
                    fallback=obj.get('hb_collision_fallback') if getattr(obj,'hb_static_collision','AUTO')=='AUTO' else None
                    # Object collision "No collision": rendered only, walked through.
                    no_collision=fallback=='none' or getattr(obj,'hb_static_collision','AUTO')=='NONE'
                    # "No leaf collision": see-through materials (leaf cards) render only; the rest collides.
                    leaves=getattr(obj,'hb_static_collision','AUTO')=='NO_LEAVES'
                    def walk_through(mat,shader,tag):
                        return collision_policy.render_only(mat,shader,tag) or (leaves and collision_policy.leaf(mat))
                    if not original and not fallback and getattr(obj,'hb_static_collision','AUTO') in ('AUTO','NO_LEAVES'):
                        collidable={i for i,mat in enumerate(mesh.materials) if mat and not mat.name.startswith('+')
                                    and not walk_through(mat,aliases.get(mat.get('hb_shader',''),{}).get('source'),mat.get('hb_shader',''))}
                        if triangle_count(mesh,collidable)>COLLISION_TRIANGLE_LIMIT:
                            # Too dense for Tool's collision limit: collide with a simplified copy instead.
                            # Remembered, so a later Tool rejection steps on from here.
                            fallback='clean';obj['hb_collision_fallback']='clean'
                            progress('Collision simplified for Tool (more than '+format(COLLISION_TRIANGLE_LIMIT,',')+' triangles): '+obj.name)
                    # After Tool rejected its collision, an object collides with its own surfaces
                    # cleaned for Tool (a collision-only copy; only then, to keep levels small).
                    clean=fallback=='clean' and not original
                    proxy=(bool(original) or proxy or bool(fallback) or clean) and not no_collision
                    proxy_slots = set()
                    if proxy:
                        for i, mat in enumerate(mesh.materials):
                            tag = mat.get('hb_shader', '')
                            shader = aliases.get(tag, {}).get('source')
                            if not mat.name.startswith('+') and not walk_through(mat, shader, tag):
                                proxy_slots.add(i)
                    points = [mesh.vertices[v].co for f in mesh.polygons if f.material_index in proxy_slots for v in f.vertices]
                    corners = []; split_collision = 0
                    proxy_faces=[(0,1,3,2),(4,6,7,5),(0,4,5,1),(2,3,7,6),(0,2,6,4),(1,5,7,3)]
                    if original and proxy_slots and ambiguous_collision(original[0],original[1]):
                        # Touching collision pieces weld into edges shared by 3+ faces, which
                        # Tool rejects ("bad connections - ambiguous"); use the box instead.
                        progress('Original collision has overlapping pieces; using a simple box: '+obj.name)
                        original=None
                    if original and proxy_slots:
                        vertices,proxy_faces,offset=original
                        corners=[stretch @ (Vector(v)-offset) for v in vertices]
                        if stretch.determinant()<0:proxy_faces=[face[::-1] for face in proxy_faces]
                    elif clean and proxy_slots:
                        # The mesh is already in world units here (stretch applied above).
                        part_limit=int(obj.get('hb_collision_triangles',COLLISION_TRIANGLE_LIMIT))
                        before=triangle_count(mesh,proxy_slots)
                        h2a=obj.get('hb_game')=='h2a'
                        corners,proxy_faces=cleaned_surface(mesh,proxy_slots,float(obj.get('hb_collision_weld',CLEAN_DISTANCE)),max_triangles=part_limit,decimate=h2a)
                        if not proxy_faces:corners=[]
                        collision_triangles=sum(len(face)-2 for face in proxy_faces)
                        if h2a and before>part_limit and corners:
                            pieces=-(-collision_triangles//part_limit)
                            progress(f'Collision decimated for Tool ({before:,} to {collision_triangles:,} triangles'
                                     +(f', cut into {pieces} pieces of up to {part_limit:,}' if pieces>1 else '')+'): '+obj.name)
                            if pieces>1:split_collision=part_limit
                    elif points:
                        limits = [(min(p[a] for p in points), max(p[a] for p in points)) for a in range(3)]
                        if all(hi-lo > 0.0001 for lo,hi in limits):
                            corners = [(x,y,z) for x in limits[0] for y in limits[1] for z in limits[2]]
                    for i,mat in enumerate(list(mesh.materials)):
                        if mat:
                            mk=mat.as_pointer();material_key=(mk,open_surface,precise,bool(corners) and i in proxy_slots,no_collision,leaves)
                            if material_key not in material_cache:
                                copy=mat.copy();materials.append(copy);material_cache[material_key]=copy
                                if mk in converted:copy["hb_shader"]=converted[mk]["name"]
                                shader=aliases.get(mat.get('hb_shader','').replace('/','\\'),{}).get('source')
                                if precise:copy.ass_jms.precise=True
                                copy.ass_jms.render_only=no_collision or (bool(corners) and i in proxy_slots) or walk_through(mat,shader,mat.get('hb_shader',''))
                                # Source surfaces flagged collision-only in the original level stay invisible.
                                from .scenario_scene import material_flags
                                source_flags=material_flags(mat)
                                copy.ass_jms.collision_only='collision_only' in source_flags and not copy.ass_jms.render_only
                                if copy.ass_jms.render_only:progress('Render-only material (no generated collision): '+mat.name)
                                # Preserve explicit Halo sidedness. Imported alpha cards
                                # already display both sides when backface culling is off.
                                # Opaque viewport defaults alone do not request duplication.
                                if not mat.name.startswith('+'):
                                    copy.ass_jms.two_sided=bool(mat.ass_jms.two_sided or
                                        (compat.is_transparent(mat) and not mat.use_backface_culling))
                                    if open_surface and not copy.ass_jms.two_sided and not copy.ass_jms.transparent_2_sided and not copy.ass_jms.render_only:
                                        copy.ass_jms.transparent_1_sided=True
                            mesh.materials[i]=material_cache[material_key]
                            if mk in converted and mesh.uv_layers.active:
                                u,v=converted[mk]["tiling"]
                                for face in mesh.polygons:
                                    if face.material_index==i:
                                        for loop in face.loop_indices:
                                            mesh.uv_layers.active.data[loop].uv.x*=u
                                            mesh.uv_layers.active.data[loop].uv.y*=v
                    if corners:
                        cm = mesh.materials[min(proxy_slots)].copy()
                        materials.append(cm)
                        cm.ass_jms.render_only = False
                        cm.ass_jms.collision_only = True
                        cm.ass_jms.two_sided = False
                        # Cleaned surfaces of an open render mesh stay open, like the render faces.
                        # Cut pieces have open edges where they were cut.
                        cm.ass_jms.transparent_1_sided = bool(clean and not original and (open_surface or split_collision))
                        cm.ass_jms.transparent_2_sided = False
                        mesh.materials.append(cm)
                        add_collision_geometry(mesh, len(mesh.materials)-1, corners, proxy_faces)
                        # chunk_instances cuts the collision into pieces of at most this many triangles.
                        if split_collision:mesh['hb_collision_part_limit']=split_collision
                        progress(('Original Halo collision: ' if original else 'Mesh surface collision (cleaned for Tool): ' if clean else 'Simple box collision: ')+obj.name)
                    routes[key]=('Not exported: only +sky faces (the generated sky boundary encloses the level)' if not mesh.polygons else
                                 ('Original Halo collision' if original else 'Mesh surfaces (cleaned for Tool)'+(' (decimated and cut into pieces)' if split_collision else '')+(' (Tool rejected the original collision)' if fallback else '') if clean else 'Simple box'+(' (Tool rejected the cleaned surfaces)' if fallback else '')) if corners else
                                 'Render only (Tool rejected its collision)' if no_collision else
                                 ('Mesh surfaces' if any(m and not m.ass_jms.render_only for m in mesh.materials) else 'Render only'))
                config['collision_routes'][obj.name]=routes[key]
                if not cache[key].polygons:continue
                clone=bpy.data.objects.new('%hb_'+str(len(temp.objects)),cache[key]);temp.collection.objects.link(clone)
                config['geometry_names'][clone.name.lstrip('%').split('.')[0]]=obj.name
                clone.matrix_world=Matrix.LocRotScale(location/units,rotation,Vector((1,1,1)))
                clone['hb_working_units']=1
                solid_faces=[f for f in clone.data.polygons if f.material_index<len(clone.data.materials) and clone.data.materials[f.material_index] and not clone.data.materials[f.material_index].name.startswith('+') and not clone.data.materials[f.material_index].ass_jms.render_only]
                # Copying Halo 2's own lightmaps: Halo 2's terrain clusters compile as the level
                # structure, as in Halo 2 (Tool gives only structure per-pixel lightmap UVs).
                # Halo 2 objects compiled into the level (machines such as Ascension's antennas,
                # scenery) too: Tool lights instanced pieces per vertex, and a long piece with few
                # vertices whose corners are buried in rock comes out black end to end; per pixel,
                # a buried corner only darkens itself. (Halo 2 baked no lightmap for objects, so
                # their pixels keep Tool's light.)
                if config.get('h2_lightmaps') and obj.get('hb_game')=='halo1' and any(c.name.split('.')[0] in H2_STRUCTURE_COLLECTIONS for c in obj.users_collection):
                    # Halo CE: the same copy, from the lighting stored in the .map itself.
                    if 'h1_lightmap_map' not in config:
                        from . import h1_lightmaps
                        found=h1_lightmaps.source([obj])
                        if found:config['h1_lightmap_map']=found;config['blender']=bpy.app.binary_path
                    clone['hb_structure']=True
                if config.get('h2_lightmaps') and obj.get('hb_game')=='halo2' and any(c.name.split('.')[0] in H2_STRUCTURE_COLLECTIONS for c in obj.users_collection):
                    if 'h2_lightmap_source' not in config:
                        from . import h2_lightmaps
                        found=h2_lightmaps.source([obj])
                        if found:config['h2_lightmap_source']=list(found);config['blender']=bpy.app.binary_path
                    # An object with see-through layers (Colossus' gas containers: alpha-blended gas)
                    # stays an instance: in the structure Tool splits blended faces into sorted parts
                    # ("section has too many parts", over 255). The layers are unlit anyway.
                    see_through=any(c.name.split('.')[0] in H2_OBJECT_COLLECTIONS for c in obj.users_collection) and any(m and m.get('hb_transparent') for m in obj.data.materials)
                    # Halo 3 water (a .shader_water stand-in) draws only in the structure: as a per-vertex
                    # lit piece it has no shader ("vertex shader entry point doesn't exist") and vanishes.
                    water=any(m and str(converted.get(m.as_pointer(),{}).get('standin','')).lower().endswith('.shader_water') for m in obj.data.materials)
                    if not see_through and (water or not _h2_unlit_cluster(obj,config,progress)):
                        clone['hb_structure']=True
                        clone['hb_terrain']=any(c.name.split('.')[0]=='Terrain' for c in obj.users_collection)
                    if clone.get('hb_structure'):
                        layer=_split_see_through(clone,temp,meshes)
                        if layer is not None:
                            config['geometry_names'][layer.name.lstrip('%').split('.')[0]]=obj.name
                            progress(obj.name+': its see-through faces (glass, energy) are compiled as a separate piece; in the structure Tool splits blended faces into too many parts')
                # +portal planes (portals.add_grid) cut the structure into clusters, so they
                # belong to the structure, never to an instance.
                from .portals import is_portal
                if is_portal(obj):clone['hb_portal']=True;continue
                if solid_faces:
                    authored=not obj.get('hb_id') and not obj.get('hb_map_reference')
                    area=sum(f.area for f in solid_faces)
                    structure_candidates.append((authored,area,clone))
                for face in clone.data.polygons:
                    if clone.data.materials[face.material_index].ass_jms.render_only:continue
                    area=face.area
                    if area>spawn_area and (rotation@face.normal).z>.5:
                        spawn_area=area;spawn=(clone.matrix_world@face.center)+Vector((0,0,1))
                for corner in obj.bound_box:bounds.append((obj.matrix_world@Vector(corner))/units)
            except Exception as error:
                # Skip objects with export problems: an object that can't be converted is
                # left out entirely (like the review's problems) instead of stopping the build.
                if not config.get('skip_invalid'):raise
                reason=(error.issues[0] if isinstance(error,ValidationError) and error.issues else str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__)
                if fresh:cache.pop(key,None);routes.pop(key,None)
                if clone is not None:
                    structure_candidates[:]=[c for c in structure_candidates if c[2] is not clone]
                    config['geometry_names'].pop(clone.name.lstrip('%').split('.')[0],None)
                    bpy.data.objects.remove(clone,do_unlink=True)
                config['collision_routes'].pop(obj.name,None)
                config['skipped_objects'][obj.name]=['Could not be exported: '+reason]
                progress('Skipped (export problem): '+obj.name+': '+reason)
        progress(f'{len(selected)}/{len(selected)} assets processed. Building the level boundary and player start...')
        # Lightmapping requires a renderable structure mesh, not just % instances.
        # Reuse actual scene geometry; never inject a hidden floor or duplicate it.
        if not structure_candidates:raise ValidationError(['No renderable surfaces remain. Add solid geometry with a Halo material before preparing.'])
        base=max(structure_candidates,key=lambda item:(item[0],item[1]))[2]
        terrain=[o for o in temp.objects if o.get('hb_structure')]
        for obj in terrain:obj.name=obj.name.lstrip('%')
        portal_objects=[o for o in temp.objects if o.get('hb_portal')]
        if bpy.context.scene.get('hb_portals_failed') and not portal_objects:
            # Tool could not portalize this level (see ui.retry_with_shifted_portals): fit the
            # structure in one cluster instead, moving its biggest non-terrain pieces (BSP pieces,
            # objects) out to instances, lit per vertex, until it is under the limit.
            from . import portals
            count=lambda o:sum(len(p.vertices)-2 for p in o.data.polygons)
            total=sum(count(o) for o in terrain)
            # hb_cluster_scale shrinks the target after Tool found too many vertices (ui.retry_with_smaller_clusters).
            target=portals.AUTO_TRIANGLES*float(bpy.context.scene.get('hb_cluster_scale',1.0))
            for obj in sorted((o for o in terrain if not o.get('hb_terrain')),key=count,reverse=True):
                if total<=target:break
                total-=count(obj);del obj['hb_structure'];obj.name='%'+obj.name
            terrain=[o for o in temp.objects if o.get('hb_structure')]
            moved=[o for o in temp.objects if o.name.startswith('%') and o.get('hb_terrain') is False]
            progress('Tool could not use portals on this level: '+str(len(moved))+' BSP pieces and objects are compiled as instanced pieces instead, so the structure ('+format(total,',')+' triangles) fits in one cluster')
        if not portal_objects and not bpy.context.scene.get('hb_portals_failed'):
            # A structure too big for one Halo 3 cluster mesh gets an automatic portal grid.
            from . import portals
            body=terrain or [base]
            tris=sum(len(p.vertices)-2 for o in body for p in o.data.polygons)
            pts=[o.matrix_world@Vector(c) for o in body for c in o.bound_box]
            lo=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)));hi=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
            scale=float(bpy.context.scene.get('hb_cluster_scale',1.0))
            if tris>portals.AUTO_TRIANGLES*scale:
                # Cuts placed by where the triangles are (each polygon's centre, weighted by its triangles).
                centers=[(c.x,c.y) for o in body for p in o.data.polygons for c in [o.matrix_world@p.center] for _ in range(len(p.vertices)-2)]
                attempt=int(bpy.context.scene.get('hb_portal_attempt',0))
                xs,ys=portals.adaptive_cuts(centers,lo,hi,portals.CELL_TRIANGLES*scale,attempt,portals.AUTO_TRIANGLES*scale)
                # Cuts slide into gaps between BSP pieces and objects: they overlap the terrain, and a
                # portal through them can leave Tool unable to build its leaf map.
                pieces=[o for o in terrain if o.get('hb_terrain') is False]
                boxes=[([o.matrix_world@Vector(c) for c in o.bound_box],sum(len(p.vertices)-2 for p in o.data.polygons)) for o in pieces]
                xs=portals.avoid_spans(xs,[(min(p.x for p in b),max(p.x for p in b),w) for b,w in boxes],lo.x,hi.x)
                ys=portals.avoid_spans(ys,[(min(p.y for p in b),max(p.y for p in b),w) for b,w in boxes],lo.y,hi.y)
                if attempt>=portals.INSTANCED_FROM:
                    # A retry after Tool could not build its leaf map: BSP pieces and objects a portal
                    # still crosses become instanced pieces (lit by Tool, not Halo 2), so portals cross only terrain.
                    moved=[o for o in pieces if portals.crosses(o,xs,ys)]
                    for obj in moved:del obj['hb_structure'];obj.name='%'+obj.name
                    terrain=[o for o in temp.objects if o.get('hb_structure')]
                    if moved:progress('Tool could not build its leaf map with portals through BSP pieces and objects: the '+str(len(moved))+' that portals cross are compiled as instanced pieces')
                verts,faces=portals.grid_from_cuts(lo,hi,xs,ys)
                if faces:
                    mesh=bpy.data.meshes.new('hb_auto_portals');mesh.from_pydata(verts,[],faces);mesh.uv_layers.new();mesh.update()
                    mesh.materials.append(portals.material());meshes.append(mesh)
                    auto=bpy.data.objects.new('hb_auto_portals',mesh);temp.collection.objects.link(auto)
                    auto['hb_portal']=True;auto['hb_working_units']=1;portal_objects=[auto]
                    progress('The level structure has '+format(tris,',')+' triangles, more than one Halo 3 cluster holds: added '+str(len(faces))+' +portal planes, placed by where its triangles are, to cut it into clusters (Add portal grid places your own)')
        for obj in portal_objects:obj.name=obj.name.lstrip('%')
        if portal_objects:progress('Portals: '+str(sum(len(o.data.polygons) for o in portal_objects))+' +portal faces cut the level structure into clusters')
        if terrain:base=max(terrain,key=lambda o:sum(f.area for f in o.data.polygons))
        base.name=base.name.lstrip('%')
        config['structure_source']=config['geometry_names'][base.name.split('.')[0]]
        if terrain:
            config['structure_source']='Halo 2 terrain and BSP pieces ('+str(len(terrain))+' objects)'
            config['h2_structure_names']=[o.name.split('.')[0] for o in terrain]
            if config.get('lighting',True) and not config.get('h2_lightmap_source') and not config.get('h1_lightmap_map'):
                progress('Halo 2\'s original lighting can\'t be copied: this map wasn\'t built by a Halo 2 Editing Kit known to HaloBridge (import the level from the kit\'s .scenario). Tool\'s test lighting is used instead.')
        yield from chunk_instances_steps(temp,meshes,config['geometry_names'],progress)
        temp.view_layers[0].update()
        # Each distinct instance mesh is one instanced geometry definition; Halo 3's
        # Tool fails the whole structure import above 1024 of them.
        definitions={o.data.name for o in temp.objects if o.type=='MESH' and o.name.startswith('%')}
        if len(definitions)>INSTANCE_DEFINITION_LIMIT:
            raise ValidationError(['This level has '+f'{len(definitions):,}'+' different instanced meshes; one Halo 3 BSP allows at most '+str(INSTANCE_DEFINITION_LIMIT)+' (Tool: "instanced geometry definitions"). '
                                   'Delete or hide pieces you don\'t need (small scenery, crates and decorations count one each per distinct mesh; copies of the same mesh count once), '
                                   'or join pieces that never move into fewer objects, then prepare again.'],'Halo 3 instance limit')
        if len(definitions)>INSTANCE_DEFINITION_LIMIT*3//4:
            progress(f'{len(definitions):,} different instanced meshes: close to Halo 3\'s limit of {INSTANCE_DEFINITION_LIMIT} instanced geometry definitions, and Tool can count more than Blender does. If Tool reports the limit, remove some small pieces.')
        structure=terrain or [base]
        triangles=sum(max(0,len(face.vertices)-2) for o in structure for face in o.data.polygons)
        progress(f'Main structure: {config["structure_source"]} — {sum(len(o.data.vertices) for o in structure):,} vertices, {triangles:,} triangles. Halo compiles these surfaces into the level BSP.')
        if triangles>20000:
            progress('Complex structure warning: the main structure exceeds 20,000 triangles. This is a performance advisory, not a Halo limit; dense or heavily subdivided terrain can make plane generation very slow. Geometry has not been simplified.')
        # A closed sky hull supplies a valid exterior for extracted render clusters.
        if not bounds:raise ValidationError(['The scene contains only sky faces; add solid geometry.'])
        lo=Vector(tuple(min(v[i] for v in bounds)-10 for i in range(3)))
        hi=Vector(tuple(max(v[i] for v in bounds)+10 for i in range(3)))
        # Largest-area faces can be underground terrain skirts. Prefer the
        # uppermost exposed surface at the cursor instead of spawning below it.
        from mathutils.bvhtree import BVHTree
        cursor=source.cursor.location/float(source.get('hb_working_units',100))
        ray_origin=Vector((cursor.x,cursor.y,hi.z));top=None;trees={}
        for index,obj in enumerate(temp.objects,1):
            if index%25==0:yield
            progress(f'Checking player start {index}/{len(temp.objects)} assets: '+config['geometry_names'].get(obj.name.lstrip('%').split('.')[0],obj.name))
            corners=[obj.matrix_world@Vector(c) for c in obj.bound_box]
            if not all(min(c[i] for c in corners)-.0001<=cursor[i]<=max(c[i] for c in corners)+.0001 for i in (0,1)):continue
            key=obj.data.as_pointer()
            if key not in trees:
                faces=[p.vertices for p in obj.data.polygons if not obj.data.materials[p.material_index].ass_jms.render_only]
                trees[key]=BVHTree.FromPolygons([v.co for v in obj.data.vertices],faces) if faces else None
            if trees[key] is None:continue
            inv=obj.matrix_world.inverted()
            hit,normal,_,_=trees[key].ray_cast(inv@ray_origin,inv.to_3x3()@Vector((0,0,-1)))
            if hit is not None and (obj.matrix_world.to_3x3()@normal).z>.5:
                point=obj.matrix_world@hit
                if top is None or point.z>top.z:top=point
        if top is not None:spawn=top+Vector((0,0,1))
        config['spawn_position']=list(spawn if spawn is not None else Vector(((lo.x+hi.x)/2,(lo.y+hi.y)/2,hi.z-9)))
        verts=[(x,y,z) for x in (lo.x,hi.x) for y in (lo.y,hi.y) for z in (lo.z,hi.z)]
        mesh=bpy.data.meshes.new('Sky boundary');meshes.append(mesh)
        mesh.from_pydata(verts,[],[(0,2,3,1),(4,5,7,6),(0,1,5,4),(2,6,7,3),(0,4,6,2),(1,3,7,5)])
        sky=bpy.data.materials.new('+sky');materials.append(sky);mesh.materials.append(sky)
        hull=bpy.data.objects.new('Sky boundary',mesh);temp.collection.objects.link(hull);hull['hb_working_units']=1
        if portal_objects:
            from . import portals
            portals.fit_to_box(portal_objects,lo,hi)
        # Normalize working units before passing to the established ASS adapter.
        for obj in temp.objects:
            units=obj['hb_working_units'];obj.matrix_world=Matrix.Scale(1/units,4)@obj.matrix_world;obj['hb_working_units']=1
        repaired=repair_texcoords(temp.objects)
        if repaired:
            owners={}
            for obj in temp.objects:
                if obj.data.name in repaired:
                    owners.setdefault(obj.data.name,config['geometry_names'].get(obj.name.lstrip('%').split('.')[0],obj.name))
            config['uv_repairs']=[f'{owners.get(name,name)}: {count} invalid texture coordinate(s) set to 0 in the export copy' for name,count in sorted(repaired.items())]
            for line in config['uv_repairs']:progress('Repaired '+line)
        yield
        progress(f'{len(selected)}/{len(selected)} assets processed. '+('Preparing the level file pieces...' if config.get('ass_parts') else 'Writing geometry file; waiting for the Blender exporter...'))
        if config.get('ass_parts'):
            # Written in background Blender processes: no need to switch the active scene,
            # so this can pause between objects too.
            placements=yield from blender_ops.export_scene_steps(config,path,scene=temp)
        else:
            bpy.context.window.scene=temp
            placements=blender_ops.export_scene(config,path)
        return placements+blockers
    finally:
        config.pop('_collision_reads',None)
        if bpy.context.window.scene!=old:bpy.context.window.scene=old
        # One batch removal: removing thousands of datablocks one by one is slow.
        bpy.data.batch_remove([*temp.objects,*meshes,*materials])
        bpy.data.scenes.remove(temp)
