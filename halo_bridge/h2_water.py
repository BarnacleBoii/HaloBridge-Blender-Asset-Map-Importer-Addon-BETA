"""Halo 2 water definitions as Halo 3 water.

Some Halo 2 levels (Zanzibar, Needle, Headlong, Dune, Grotto, Beaver Creek) draw their sea with a
BSP "water definitions" entry: an infinite plane at a fixed height, not geometry, so an imported
map has no water there. At preparation each definition becomes a temporary flat grid at its height
over the level's terrain, with a material that uses the chosen Halo 3 water shader (standins.py);
it is compiled into the structure as a water surface without collision, then removed again.
"""
import hashlib
import json
import re
from pathlib import Path

WATER_TEMPLATE = r'shaders\shader_templates\water\water_definition'  # any water\ template path
CELL = 8.0  # world units per grid cell
# One quad: Halo 3 tessellates water itself, and an 8-unit grid (thousands of evenly spread
# triangles) moved the automatic portal cuts until Tool could not build the leaf map
# (Zanzibar, Needle).
MAX_CELLS = 1
INSET = 2.0  # world units kept between the water's edge and the level's outer bounds


def parse(xml_text):
    """[(shader, height)] from a Halo 2 BSP exported as XML."""
    block = re.search(r'<block name="water definitions">(.*?)</block>', xml_text, re.S)
    if not block:
        return []
    result = []
    for element in re.findall(r'<element index="\d+">(.*?)</element>', block.group(1), re.S):
        shader = re.search(r'shader[^>]*>([^<]*)<', element)
        height = re.search(r'name="height"[^>]*>([^<]*)<', element)
        shader = shader.group(1).strip() if shader else ''
        if not shader:
            continue  # empty entries (Coagulation, Warlock ...) draw nothing in Halo 2 either
        try:
            result.append((shader, float(height.group(1)) if height else 0.0))
        except ValueError:
            continue
    return result


def definitions(h2ek, scenario, cache, run):
    """The water definitions of every BSP beside a Halo 2 kit scenario (cached per BSP file)."""
    h2ek = Path(h2ek)
    folder = h2ek / 'tags' / Path(scenario.replace('\\', '/')).parent
    store = Path(cache) / 'halo2' / 'water'
    store.mkdir(parents=True, exist_ok=True)
    result = []
    for bsp in sorted(folder.glob('*.scenario_structure_bsp')):
        stat = bsp.stat()
        key = hashlib.sha256(f'{bsp}|{stat.st_size}|{stat.st_mtime_ns}'.encode()).hexdigest()[:24]
        record = store / (key + '.json')
        if record.is_file():
            result += [tuple(d) for d in json.loads(record.read_text(encoding='utf-8'))]
            continue
        xml = store / (key + '.xml')
        run([h2ek / 'tool.exe', 'export-tag-to-xml', bsp, xml], h2ek)
        found = parse(xml.read_text(encoding='utf-8', errors='replace')) if xml.is_file() else []
        xml.unlink(missing_ok=True)
        record.write_text(json.dumps(found), encoding='utf-8')
        result += found
    return result


def grid(lo, hi, z, units):
    """Vertices and quads of a flat grid from lo to hi (x, y) at height z, in cells of about CELL
    world units (Blender coordinates are world units x units)."""
    nx = max(1, min(MAX_CELLS, round((hi[0] - lo[0]) / (CELL * units))))
    ny = max(1, min(MAX_CELLS, round((hi[1] - lo[1]) / (CELL * units))))
    verts = [(lo[0] + (hi[0] - lo[0]) * i / nx, lo[1] + (hi[1] - lo[1]) * j / ny, z) for j in range(ny + 1) for i in range(nx + 1)]
    faces = [(j * (nx + 1) + i, j * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i + 1, (j + 1) * (nx + 1) + i) for j in range(ny) for i in range(nx)]
    return verts, faces


def add_planes(scene, config, progress=lambda m: None):
    """Add a water grid for each Halo 2 water definition of the scene's Halo 2 map. Returns the
    added objects, materials, meshes and collections for remove()."""
    import bpy
    from . import h2_lightmaps, standins
    added = []
    if not standins.water_shader(config.get('water_shader', standins.DEFAULT_WATER)):
        return added  # "Converted" water needs Halo 2's own textures, which a definition has none of
    # Imported map pieces are references marked hb_ignore; export takes them anyway (geometry_export.objects).
    terrain = [o for o in scene.objects if o.type == 'MESH' and o.get('hb_game') == 'halo2' and (o.get('hb_map_reference') or not o.get('hb_ignore'))
               and any(c.name.split('.')[0] == 'Terrain' for c in o.users_collection)]
    if not terrain:
        return added
    source = h2_lightmaps.source(terrain[:200])
    if not source:
        return added
    try:
        found = definitions(source[0], source[1], config['cache'], lambda args, cwd: h2_lightmaps._run(args, cwd, None))
    except Exception as error:  # optional: the level prepares without its sea
        progress('Halo 2 water definitions were not read: ' + str(error).splitlines()[0][:200])
        return added
    if not found:
        return added
    template = terrain[0]
    units = float(template.get('hb_working_units', scene.get('hb_working_units', 100)))
    xs, ys = [], []
    for obj in terrain:
        for corner in obj.bound_box:
            world = obj.matrix_world @ __import__('mathutils').Vector(corner)
            xs.append(world.x); ys.append(world.y)
    # Kept off the generated sealed box: geometry lying on its walls leaves Tool unable to build
    # the leaf map (Zanzibar: "couldn't build leaf map during portalization" with a full-size plane).
    inset = max(INSET * units, 0.02 * min(max(xs) - min(xs), max(ys) - min(ys)))
    lo, hi = (min(xs) + inset, min(ys) + inset), (max(xs) - inset, max(ys) - inset)
    if hi[0] <= lo[0] or hi[1] <= lo[1]:
        return added
    collection = bpy.data.collections.new('Terrain')  # a Halo 2 structure collection
    scene.collection.children.link(collection); added.append(collection)
    for index, (shader, height) in enumerate(found):
        verts, faces = grid(lo, hi, height * units, units)
        mesh = bpy.data.meshes.new('Halo 2 water')
        mesh.from_pydata(verts, [], faces); mesh.update()
        uv = mesh.uv_layers.new(name='UVMap')
        for loop in mesh.loops:
            co = mesh.vertices[loop.vertex_index].co
            uv.data[loop.index].uv = (co.x / (10 * units), co.y / (10 * units))
        mat = template.data.materials[0].copy() if template.data.materials and template.data.materials[0] else bpy.data.materials.new('h2 water')
        for key in ('hb_transparent', 'hb_sky_blend', 'hb_sky_layer', 'hb_custom_shader'):
            if key in mat:
                del mat[key]
        mat.name = 'Halo 2 water ' + shader.rsplit('\\', 1)[-1]
        mat['hb_h2_template'] = WATER_TEMPLATE; mat['hb_shader'] = shader; mat['hb_label'] = mat.name
        mat['hb_conversion_id'] = 'h2water|' + shader; mat['hb_material_key'] = 'h2water|' + shader
        mesh.materials.append(mat)
        obj = bpy.data.objects.new('Halo 2 water ' + str(index), mesh)
        for key in template.keys():
            if key.startswith('hb_') and key not in ('hb_id', 'hb_mesh_signature', 'hb_source_tag', 'hb_kind', 'hb_structure',
                                                     'hb_map_placement_index', 'hb_tool_rejected', 'hb_tool_rejected_shape'):
                obj[key] = template[key]
        obj['hb_h2_water'] = True
        collection.objects.link(obj)
        added += [obj, mat, mesh]
        progress(f'Halo 2 water definition: {shader} at height {height:g}, added as Halo 3 water')
    return added


def remove(added):
    import bpy
    order = (bpy.types.Object, bpy.types.Mesh, bpy.types.Material, bpy.types.Collection)
    for item in sorted(added, key=lambda i: next((n for n, t in enumerate(order) if isinstance(i, t)), 9)):
        try:
            if isinstance(item, bpy.types.Object):
                bpy.data.objects.remove(item, do_unlink=True)
            elif isinstance(item, bpy.types.Material):
                bpy.data.materials.remove(item)
            elif isinstance(item, bpy.types.Mesh):
                bpy.data.meshes.remove(item)
            elif isinstance(item, bpy.types.Collection):
                bpy.data.collections.remove(item)
        except ReferenceError:
            pass
