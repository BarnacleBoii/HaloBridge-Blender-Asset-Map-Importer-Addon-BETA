"""Skies from other games, rebuilt as a Halo 3 / ODST sky object.

A Halo 3 sky is a scenery object whose render model surrounds the level (Deadlock's
is about 5,500 world units across) and uses ordinary shaders. A sky model chosen
from another game's index is placed in Blender in the "Sapien Sky" collection, so
its size and position can be checked and changed. Preparation converts its textures
like other cross-game materials, writes it as a JMS render model and Tool's
render-sky builds it; the tag helper then creates the model and scenery tags and
puts the sky in the scenario.
"""
import json
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
from . import blender_ops, cross_game

PROPERTY = 'hb_sapien_sky'
COLLECTION = 'Sapien Sky'
SKY_FOLDERS = {'sky', 'skies'}
# Halo CE and Halo 2 draw their sky models around the camera at their own small
# scale; Halo 3 places the sky in the world, so those skies are enlarged to
# surround the level. Halo 3, ODST and Reach skies are already world-sized.
CAMERA_SKIES = {'halo1', 'halo2'}
# The sky's radius: SKY_RADIUS_FACTOR x the level's, within these world units. Coagulation's sky
# at 2,000 units was cut off in Sapien; at about 700 it looked too small.
SKY_RADIUS_FACTOR = 5.0
MIN_RADIUS, MAX_RADIUS = 900.0, 1800.0


def camera_sky_radius(scene):
    """The radius a camera sky (Halo CE / Halo 2) gets around this scene's level."""
    level = [o for o in scene.objects if o.type == 'MESH' and not o.get(PROPERTY) and not o.get('hb_preview') and not o.hide_get()
             and not any(c.name.split('.')[0] == 'Skies' for c in o.users_collection)]
    return min(MAX_RADIUS, max(MIN_RADIUS, SKY_RADIUS_FACTOR * world_radius(level)))


def is_sky_asset(asset):
    tag = asset.get('tag', '').lower().replace('/', '\\')
    # Halo 2: Anniversary's index marks the scenario's own sky scenery (its folder is e.g. ca_coagulation_sky).
    # Older Anniversary indexes lack the mark; their sky folders end in _sky.
    folders = tag.split('\\')[:-1]
    h2a_folder = asset.get('game') == 'h2a' and any(part.endswith('_sky') for part in folders)
    return asset.get('kind') in ('model', 'scenery') and (bool(asset.get('sky')) or h2a_folder or any(part in SKY_FOLDERS for part in folders))


def sky_object(scene):
    return next((o for o in scene.objects if o.get(PROPERTY) and o.type == 'MESH'), None)


def collection(scene):
    found = bpy.data.collections.get(COLLECTION)
    if found is None:
        found = bpy.data.collections.new(COLLECTION)
    if found.name not in scene.collection.children:
        scene.collection.children.link(found)
    return found


def world_radius(objects, depsgraph=None):
    """Largest distance from the origin of any bounding-box corner, in world units."""
    radius = 0.0
    for obj in objects:
        units = float(obj.get('hb_working_units', 100))
        for corner in obj.bound_box:
            radius = max(radius, (obj.matrix_world @ Vector(corner)).length / units)
    return radius


def place(context, asset, path, config):
    """Replace any previous Sapien sky with the chosen sky model."""
    scene = context.scene
    for old in [o for o in scene.objects if o.get(PROPERTY)]:
        bpy.data.objects.remove(old, do_unlink=True)
    # Always build the sky from the current extraction, not an older mesh of the same asset.
    for mesh in bpy.data.meshes:
        if mesh.get('hb_asset_id') == asset['id']:
            mesh['hb_asset_id'] = asset['id'] + '_previous'
    obj = blender_ops.place(asset, path, config, location=(0, 0, 0))
    for col in list(obj.users_collection):
        col.objects.unlink(obj)
    collection(scene).objects.link(obj)
    obj[PROPERTY] = True
    obj['hb_ignore'] = True  # never part of the level geometry
    obj.name = 'Sapien sky - ' + asset['name']
    if asset.get('game') in CAMERA_SKIES:
        target = camera_sky_radius(scene)
        current = world_radius([obj])
        if current > 0:
            obj.scale = obj.scale * (target / current)
    obj['hb_sky_game'] = asset.get('game', '')
    obj['hb_sky_asset'] = json.dumps(dict(id=asset['id'], name=asset['name'], tag=asset.get('tag', ''), level=asset.get('level', '')))
    return obj


PRE_PASS, NORMAL, POST_PASS = 1, 2, 3  # Halo 3 shader "sort layer"


def layer_order(converted, order):
    """Halo 2 draws its sky layers one over the other in a fixed order and writes no depth;
    Halo 3 sorts see-through surfaces of one model by distance, which is the same for every
    layer of a sky around the camera, so that order is lost and a back layer can cover a front one (the blue sky
    over Coagulation's ring). order is {material pointer: Halo 2 draw position}. The first
    layer becomes opaque when it covers the whole sky; the other see-through layers keep their
    order through the shader sort layer: the earlier third before the rest, the last third after.
    Returns {pointer: shader fields}."""
    ranked = sorted((rank, pointer) for pointer, rank in order.items() if converted.get(pointer, {}).get('blend'))
    if not ranked:
        return {}
    result = {}
    first = ranked[0][1]
    if converted[first].get('covers'):
        result[first] = dict(blend='opaque', additive=False)
        ranked = ranked[1:]
    count = len(ranked)
    for index, (_, pointer) in enumerate(ranked):
        layer = PRE_PASS if index * 3 < count else POST_PASS if index * 3 >= 2 * count else NORMAL
        result[pointer] = dict(sort_layer=layer)
    return result


def export(obj, folder, progress=None, order=None, target_radius=None):
    """Convert the sky's materials and write sky.JMS; returns the JMS path and shader entries.
    order: {material pointer: draw position} for a Halo 2 sky's layers (see layer_order)."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    materials = {m.as_pointer(): m for m in obj.data.materials if m and not m.name.startswith('+')}
    if not materials:
        raise RuntimeError(obj.name + ': the sky has no materials.')
    converted = cross_game.prepare([obj], folder / 'textures', progress, materials=materials)
    units = float(obj.get('hb_working_units', 100))
    temp = bpy.data.scenes.new('HaloBridge sky export')
    mesh = obj.data.copy()
    made = []
    try:
        for index, mat in enumerate(list(mesh.materials)):
            if mat is None or mat.as_pointer() not in converted:
                continue
            entry = converted[mat.as_pointer()]
            copy = bpy.data.materials.new(entry['name'])
            copy.ass_jms.name_override = entry['name']
            made.append(copy)
            mesh.materials[index] = copy
            u, v = entry['tiling']
            if mesh.uv_layers.active and (u, v) != (1.0, 1.0):
                layer = mesh.uv_layers.active.data
                for face in mesh.polygons:
                    if face.material_index == index:
                        for loop in face.loop_indices:
                            layer[loop].uv.x *= u
                            layer[loop].uv.y *= v
        frame = bpy.data.objects.new('frame root', None)
        temp.collection.objects.link(frame)
        copy_obj = bpy.data.objects.new('sky', mesh)
        temp.collection.objects.link(copy_obj)
        copy_obj.parent = frame
        # JMS at scale "1" writes 100 units per Blender unit, Tool reads 100 per world unit.
        # A camera sky (Halo CE / Halo 2) is sized around the level (target_radius, world units).
        resize = 1.0
        if target_radius and obj.get('hb_sky_game') in CAMERA_SKIES and world_radius([obj]) > 0:
            resize = target_radius / world_radius([obj])
        copy_obj.matrix_world = Matrix.Scale(resize / units, 4) @ obj.matrix_world
        from .compat import toolset_module
        import importlib
        toolset = toolset_module()
        if toolset is None:
            raise RuntimeError('Enable the Halo Asset Blender Development Toolset to export the sky.')
        export_jms = importlib.import_module(toolset.__name__ + '.file_jms.export_jms')
        functions = importlib.import_module(toolset.__name__ + '.global_functions.global_functions')
        path = folder / 'sky.JMS'
        path.unlink(missing_ok=True)
        messages = []
        with bpy.context.temp_override(scene=temp, view_layer=temp.view_layers[0]):
            export_jms.write_file(bpy.context, str(path), 'halo3', 8210, '', '', False, 0, False, False, False, False, True, False, False,
                                  True, True, False, False, functions.EdgeSplit(False, True, 0.523599, True), False, False, False,
                                  functions.set_scale('1', 1.0), False, lambda *a: messages.append(a))
        if not path.is_file():
            raise RuntimeError('The sky JMS was not written. ' + ' '.join(str(m) for m in messages))
    finally:
        for o in list(temp.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.scenes.remove(temp)
        bpy.data.meshes.remove(mesh)
        for mat in made:
            bpy.data.materials.remove(mat)
    # Halo CE / Halo 2 skies are stacked layers drawn additively; opaque layers would
    # hide each other behind their black backgrounds.
    # Halo 2 sky layers say how they blend (alpha or additive); other games' sky
    # materials that were additive in their own game stay additive.
    camera = obj.get('hb_sky_game') in CAMERA_SKIES
    layered = layer_order(converted, order or {})
    shaders = []
    for pointer, entry in converted.items():
        source = materials.get(pointer)
        if entry.get('blend'):
            additive = entry['blend'] == 'additive'
        else:
            additive = camera or (source is not None and source.get('hb_source_alpha') == 'additive')
        shader = dict(entry, folder='sky', additive=additive)
        shader.pop('covers', None)
        shader.update(layered.get(pointer, {}))
        shaders.append(shader)
    return dict(jms=str(path), shaders=shaders, name=obj.name, radius=world_radius([obj]) * resize * 1.05)


def export_chosen_sky(scene, obj, folder, progress=None, strength=(1.0, 1.0)):
    """Export a sky chosen under Sapien Sky. A Halo 2 sky keeps its layer order (its material
    slots follow the model's sections, which Halo 2 draws in order) and its sun and sky light,
    read when the sky was chosen or, for a sky chosen before, looked up now."""
    radius = camera_sky_radius(scene)
    if obj.get('hb_sky_game') != 'halo2':
        return export(obj, folder, progress, target_radius=radius)
    order = {m.as_pointer(): rank for rank, m in enumerate(obj.data.materials) if m}
    result = export(obj, folder, progress, order=order, target_radius=radius)
    lighting = None
    try:
        lighting = json.loads(obj['hb_sky_lighting']) if obj.get('hb_sky_lighting') else _look_up_lighting(scene, obj)
    except Exception as error:
        (progress or (lambda m: None))('The Halo 2 sky\'s lights could not be read (' + str(error) + '); the level is lit with a Halo 3 sky')
    from . import sky_lights
    lights = sky_lights.h2_sky_lights(lighting, *strength)
    if lights:
        result['sky_lights'] = lights
    return result


def _look_up_lighting(scene, obj):
    from . import skies, jobs, games
    chosen = json.loads(obj.get('hb_sky_asset', '{}'))
    settings = scene.halo_bridge
    asset = next((a for a in skies.catalogue_skies(settings, 'halo2') if a.get('id') == chosen.get('id')
                  or a.get('tag', '').lower() == chosen.get('tag', '').lower()), None)
    if asset is None:
        return None
    profile = games.profile(settings, 'halo2')
    lighting = jobs.sky_lighting(dict(asset, game='halo2'), dict(cache=bpy.path.abspath(profile['cache'])))
    if lighting:
        obj['hb_sky_lighting'] = json.dumps(lighting)
    return lighting


def map_skies(scene, target):
    """Visible sky layers of an imported map from a game whose tags the destination kit lacks."""
    from . import games
    return [o for o in scene.objects if o.type == 'MESH' and o.get('hb_map_reference') and not o.hide_get()
            and any(c.name.split('.')[0] == 'Skies' for c in o.users_collection)
            and not games.shares_tags(o.get('hb_game', 'halo3'), target)]


def export_map_sky(scene, layers, folder, progress=None, strength=(1.0, 1.0)):
    """Join an imported map's sky layers into one sky object, unchanged in size,
    position and rotation, and export it like a chosen sky."""
    import bmesh
    # Halo 2 draws a sky's layers in the order the map lists them.
    layers = sorted(layers, key=lambda o: int(o.get('hb_map_placement_index', 0)))
    radius = camera_sky_radius(scene)  # before the joined sky object joins the scene
    materials = []
    for obj in layers:
        for mat in obj.data.materials:
            if mat is not None and mat not in materials:
                materials.append(mat)
    bm = bmesh.new()
    pieces = []
    try:
        for obj in layers:
            piece = obj.data.copy()
            pieces.append(piece)
            piece.transform(obj.matrix_world)
            lookup = [materials.index(m) if m in materials else 0 for m in obj.data.materials] or [0]
            for poly in piece.polygons:
                poly.material_index = lookup[min(poly.material_index, len(lookup) - 1)]
            bm.from_mesh(piece)
        mesh = bpy.data.meshes.new('HaloBridge map sky')
        bm.to_mesh(mesh)
    finally:
        bm.free()
        for piece in pieces:
            bpy.data.meshes.remove(piece)
    for mat in materials:
        mesh.materials.append(mat)
    sky = bpy.data.objects.new('Original map sky', mesh)
    scene.collection.objects.link(sky)
    try:
        sky['hb_working_units'] = float(layers[0].get('hb_working_units', 100))
        game = layers[0].get('hb_game', '')
        sky['hb_sky_game'] = game
        # The layers keep their position and rotation; a camera sky is sized around the level.
        bpy.context.view_layer.update()
        result = export(sky, folder, progress, order={m.as_pointer(): rank for rank, m in enumerate(materials)}, target_radius=radius)
        # The original sky's sun and sky light (Halo 2), so the level is lit by its own sky.
        from . import sky_lights
        from .catalog import read_json
        manifest = layers[0].get('hb_map_manifest')
        lighting = read_json(Path(manifest), {}).get('sky_lighting') if manifest and Path(manifest).is_file() else None
        lights = sky_lights.h2_sky_lights(lighting, *strength) if game == 'halo2' else []
        if lights:
            result['sky_lights'] = lights
        return result
    finally:
        bpy.data.objects.remove(sky, do_unlink=True)
        bpy.data.meshes.remove(mesh)
