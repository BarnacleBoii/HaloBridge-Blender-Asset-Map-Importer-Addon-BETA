"""Halo 2 sky layers: unlit alpha/additive preview, cloud mask, tiling and bake; synthetic images only."""
import sys, json, tempfile
from pathlib import Path
import bpy
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import classic_sky, cross_game, games, original_collision


def image(folder, name, rgba, size=4):
    img = bpy.data.images.new(name, width=size, height=size, alpha=True)
    img.pixels[:] = list(rgba) * (size * size)
    path = Path(folder) / (name + '.png')
    img.filepath_raw = str(path); img.file_format = 'PNG'; img.save()
    bpy.data.images.remove(img)
    return path.name


with tempfile.TemporaryDirectory() as folder:
    tile = image(folder, 'tile', (1, 1, 1, 1))
    mask = image(folder, 'mask', (.2, .2, .2, .5), size=8)
    clouds = dict(name='clouds', alpha='blend', options={'sky': 'alpha'}, tints=[],
                  textures=[dict(usage='diffuse', path=tile, tiling=[8, 8]), dict(usage='transparency', path=mask, tiling=[1, 1])])
    sun = dict(name='sun', alpha='additive', options={'sky': 'additive'}, tints=[dict(usage='albedo', color=[1, .5, .25, 1])],
               textures=[dict(usage='diffuse', path=tile, tiling=[1, 1]), dict(usage='diffuse_detail', path=tile, tiling=[3, 3])])
    plain = dict(name='rock', alpha='opaque', options={}, tints=[], textures=[dict(usage='diffuse', path=tile, tiling=[1, 1])])
    made = {}
    for meta in (clouds, sun, plain):
        mat = bpy.data.materials.new(meta['name']); mat.use_nodes = True
        mat['hb_texture_directory'] = folder
        made[meta['name']] = (mat, classic_sky.apply(mat, meta, folder))
    mat, ok = made['clouds']
    assert ok and mat['hb_sky_blend'] == 'alpha' and mat['hb_alpha_mode'] == 'blend'
    types = {n.type for n in mat.node_tree.nodes}
    assert {'EMISSION', 'MIX_SHADER', 'BSDF_TRANSPARENT'} <= types and 'BSDF_PRINCIPLED' not in types, types
    assert any(n.type == 'VECT_MATH' and tuple(n.inputs[1].default_value[:2]) == (8, 8) for n in mat.node_tree.nodes)
    mat, ok = made['sun']
    assert ok and mat['hb_sky_blend'] == 'additive' and any(n.type == 'ADD_SHADER' for n in mat.node_tree.nodes)
    assert not made['rock'][1], 'ordinary materials are not sky layers'
    # Bake: clouds become one RGBA texture, tiled color with the mask as alpha, at 8x the tile.
    with tempfile.TemporaryDirectory() as out:
        entry = classic_sky.bake(made['clouds'][0], out, 'sky_test')
        assert entry['blend'] == 'alpha' and entry['tiling'] == (1.0, 1.0)
        baked = bpy.data.images.load(entry['maps']['base_map'])
        assert tuple(baked.size) == (32, 32), tuple(baked.size)
        px = np.array(baked.pixels[:]).reshape(-1, 4)
        assert abs(px[:, 3].mean() - .5) < .02 and px[:, 0].min() > .95, (px[:, 3].mean(), px[:, 0].min())
        bpy.data.images.remove(baked)
        entry = classic_sky.bake(made['sun'][0], out, 'sun_test')
        baked = bpy.data.images.load(entry['maps']['base_map'])
        px = np.array(baked.pixels[:]).reshape(-1, 4)
        assert entry['blend'] == 'additive' and abs(px[:, 1].mean() - .5) < .02 and px[:, 3].min() > .99
        bpy.data.images.remove(baked)
# Converted textures over the Texture size setting (2048 by default; never over Halo 3's 4096) are halved until they fit.
big = np.ones((10, 8192, 4), dtype=np.float32); big[:, ::2, 0] = 0
assert cross_game.MAX_BITMAP == 2048
small = cross_game.fit(big)
assert small.shape == (3, 2048, 4) and abs(small[:, :, 0].mean() - .5) < 1e-6, small.shape
cross_game.MAX_BITMAP = 8192  # never past Tool's own limit
assert cross_game.fit(big).shape == (5, 4096, 4)
cross_game.MAX_BITMAP = 4096
assert cross_game.fit(np.ones((4096, 64, 4), dtype=np.float32)).shape == (4096, 64, 4)
cross_game.MAX_BITMAP = cross_game.DEFAULT_BITMAP
# Cleaned mesh-surface collision: near-duplicate vertices weld, slivers and other slots drop out.
from halo_bridge import geometry_export, ui
mesh = bpy.data.meshes.new('clean')
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (1.0005, 0, 0), (2, 0, 0), (2, 1, 0), (5, 5, 5), (6, 5, 5), (5, 6, 5)], [],
                 [(0, 1, 2, 3), (4, 5, 6, 2), (1, 4, 2), (7, 8, 9)])
mesh.polygons[3].material_index = 1
vertices, faces = geometry_export.cleaned_surface(mesh, {0})
assert len(vertices) == 6 and len(faces) == 2, (vertices, faces)
# Retry order after Tool rejects collision: cleaned surfaces -> box -> none.
assert ui.next_collision_fallback(None, True) == 'clean' and ui.next_collision_fallback(None, False) == 'clean'
assert ui.next_collision_fallback('clean', True) == 'box' and ui.next_collision_fallback('box', True) == 'none'
# One rejected Anniversary piece cleans every Anniversary piece in the same round; Halo 3 pieces keep theirs.
pieces = {}
for name, game in (('rejected', 'h2a'), ('sibling', 'h2a'), ('h3 piece', 'halo3')):
    o = bpy.data.objects.new(name, bpy.data.meshes.new(name)); bpy.context.scene.collection.objects.link(o)
    o['hb_source_tag'] = 'x'; o['hb_game'] = game; o['hb_map_reference'] = True; o['hb_ignore'] = True
    pieces[name] = o
ui.prepare_status = lambda message: None
ui.retry_with_box_collision(type('E', (Exception,), {})('-ERROR- (object rejected) degenerate collision edge'))
assert pieces['rejected']['hb_collision_fallback'] == 'clean' and pieces['sibling']['hb_collision_fallback'] == 'clean'
assert 'hb_collision_fallback' not in pieces['h3 piece']
ui._box_retry = 0
# Halo 2: Anniversary is an import game, not a Sapien target; its collision uses the fallback.
assert games.GAMES['h2a']['import_enabled'] and not games.GAMES['h2a']['sapien_enabled']
assert 'h2a' not in original_collision.COLLISION_GAMES
# Anniversary foliage: a cut-out preview from the color map's alpha, and walk-through by its engine shader.
from halo_bridge import blender_ops, collision_policy
with tempfile.TemporaryDirectory() as folder:
    leaf = image(folder, 'leaf', (.2, .5, .1, 0))
    meta = dict(id=1, name='h2a_leaves', shader=r'levels\sway\x\materials\trees\leaves', alpha='clip', tints=[],
                options={'material_shader': r'shaders\material_shaders\materials\special\srf_ca_special_foliage_fakelit'},
                textures=[dict(usage='diffuse', path=leaf, tiling=[1, 1], channels=0), dict(usage='transparency', path=leaf, tiling=[1, 1], channels=8)])
    leaves = blender_ops.material(meta, folder)
    bsdf = leaves.node_tree.nodes['Principled BSDF']
    assert bsdf.inputs['Alpha'].is_linked and leaves['hb_source_alpha'] == 'clip'
    assert collision_policy.h2a_foliage(leaves)
    grate = blender_ops.material(dict(meta, id=2, name='h2a_grate', options={'material_shader': r'shaders\material_shaders\materials\srf_pbr_grime_clip'}), folder)
    assert not collision_policy.h2a_foliage(grate), 'cut-out grates stay solid'
# Collision denser than Tool's limit is simplified until it fits.
dense = bpy.data.meshes.new('dense')
grid = 120
verts = [(x * .01, y * .01, ((x * 7 + y * 3) % 5) * .0004) for y in range(grid) for x in range(grid)]
faces = [(y * grid + x, y * grid + x + 1, (y + 1) * grid + x + 1, (y + 1) * grid + x) for y in range(grid - 1) for x in range(grid - 1)]
dense.from_pydata(verts, [], faces)
assert geometry_export.triangle_count(dense, {0}) == 2 * len(faces)
v, f = geometry_export.cleaned_surface(dense, {0}, max_triangles=4000)
tris = sum(len(x) - 2 for x in f)
assert 0 < tris <= 4000, tris
v, f = geometry_export.cleaned_surface(dense, {0}, max_triangles=50000)
assert sum(len(x) - 2 for x in f) == 2 * len(faces), 'under the limit nothing is simplified'
# "collision geometry is too large": simplify further instead of a box.
big = bpy.data.objects.new('emp device', dense); bpy.context.scene.collection.objects.link(big)
big['hb_source_tag'] = 'x'; big['hb_game'] = 'h2a'; big['hb_map_reference'] = True
ui._box_retry = 0
ui.retry_with_box_collision(type('E', (Exception,), {})('-ERROR- (object emp device) collision geometry is too large (36308/32767 surfaces, 1/2 edges, 1/2 vertices)'))
assert big['hb_collision_fallback'] == 'clean' and big['hb_collision_triangles'] == geometry_export.COLLISION_TRIANGLE_LIMIT // 2
assert 'hb_collision_fallback' not in pieces['h3 piece']
# Cleaned surfaces that still have broken edges are welded harder twice before a box.
edge = lambda: type('E', (Exception,), {})('-ERROR- (object emp device) degenerate collision edge')
steps = []
for _ in range(4):
    ui.mark_collision_fallbacks(edge()); steps.append((big['hb_collision_fallback'], round(big.get('hb_collision_weld', 0), 4)))
assert steps == [('clean', .008), ('clean', .032), ('box', .032), ('none', .032)], steps
# Tool crashing in its plane builder on an object placed twice (the Coagulation case):
# cleaned surfaces, then straight to a box, then none; same-game pieces are left alone.
crash = lambda: type('E', (Exception,), {})('\n'.join([
    '-FATAL- (object emp device) tool  test x64 untracked version  Jan  3 2024 10:12:33',
    r'-FATAL- (object emp device) ### ASSERTION FAILED:  at c:\mcc\release\h3\source\tool\geometry\connected_geometry\process\connected_geometry_plane_builder.cpp,#4092',
    '-FATAL- (object emp device)   realpoint3dcmp(point, fit_info->real_points.get_element(point_index_index))']))
del big['hb_collision_fallback']
sibling = bpy.data.objects.new('h2a sibling', dense); bpy.context.scene.collection.objects.link(sibling)
sibling['hb_source_tag'] = 'x'; sibling['hb_game'] = 'h2a'; sibling['hb_map_reference'] = True
steps = []
for _ in range(3):
    ui.mark_collision_fallbacks(crash()); steps.append(big['hb_collision_fallback'])
assert steps == ['clean', 'box', 'none'], steps
assert 'hb_collision_fallback' not in sibling
# At 'none' the collision retry can't help; Skip objects with export problems leaves it out.
assert ui.mark_collision_fallbacks(crash()) is None
assert ui.mark_tool_rejections(crash()) == [big] and 'crashed' in big['hb_tool_rejected'] and 'plane_builder' in big['hb_tool_rejected']
for key in ('hb_tool_rejected', 'hb_tool_rejected_shape'): del big[key]
bpy.data.objects.remove(sibling, do_unlink=True)
ui._box_retry = 0
# Optional Decimate for dense objects: added once with the chosen ratio, kept per object, exported applied.
from halo_bridge import dense_meshes
assert dense_meshes.triangles(big) == 2 * len(faces)
added = dense_meshes.add(bpy.context.scene, 20000, .4)
assert added == [big] and abs(big.modifiers[dense_meshes.MODIFIER_NAME].ratio - .4) < 1e-6, added
big.modifiers[dense_meshes.MODIFIER_NAME].ratio = .3
assert dense_meshes.add(bpy.context.scene, 20000, .5) == [] and abs(big.modifiers[dense_meshes.MODIFIER_NAME].ratio - .3) < 1e-6
evaluated = big.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
assert len(evaluated.polygons) < .35 * 2 * len(faces), len(evaluated.polygons)
big.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh_clear()
assert dense_meshes.add(bpy.context.scene, 10 ** 6, .5) == []
big.modifiers.remove(big.modifiers[dense_meshes.MODIFIER_NAME])
# Tool's "failed to add import info" is not a failure once the structure imported.
from halo_bridge.diagnostics import compiler_errors
log = "=== starting import of structure 'a\\b'-ERROR- failed to add import info - tag_data_resize() failed\n=== imported structure 'a\\b' in 3s"
assert compiler_errors(log, 'a\\b') == [] and compiler_errors(log) != []
# Anniversary sky scenery is marked by the index (or found in its *_sky folder).
from halo_bridge import sky_export
assert sky_export.is_sky_asset(dict(kind='scenery', tag=r'levels\sway\ca_coagulation\ca_coagulation_sky\ca_coagulation_sky', game='h2a'))
assert sky_export.is_sky_asset(dict(kind='scenery', tag=r'levels\x\y\z', sky=True, game='h2a'))
assert not sky_export.is_sky_asset(dict(kind='scenery', tag=r'levels\x\blue_sky\rock', game='halo3'))
# Converted textures are reused when their source image is unchanged.
import os, time
with tempfile.TemporaryDirectory() as folder:
    src = Path(folder) / 'src.png'
    img = bpy.data.images.new('src', 8, 8, alpha=True); img.filepath_raw = str(src); img.file_format = 'PNG'; img.save(); bpy.data.images.remove(img)
    img = bpy.data.images.load(str(src))
    out = Path(folder) / 'out.tif'
    cross_game.write_image(img, out); first = out.stat().st_mtime_ns
    time.sleep(.05); cross_game.write_image(img, out)
    assert out.stat().st_mtime_ns == first, 'unchanged source reuses the converted texture'
    time.sleep(.05); os.utime(src, None); img.reload(); cross_game.write_image(img, out)
    assert out.stat().st_mtime_ns != first, 'a changed source is converted again'
    # Compiled bitmaps are matched to their converted sources.
    from halo_bridge import build
    bitmap_dir = Path(folder); (bitmap_dir / 'k_base.tif').write_bytes(b'x')
    sig = build.bitmap_signatures([dict(path='p', base_map='levels\\multi\\l\\bitmaps\\reach\\k_base', sky=False)], bitmap_dir)
    assert list(sig) == ['k_base'] and sig['k_base'][0] == 'base_map'
# Viewport shadows start off once per scene; a later choice is kept.
from halo_bridge import compat
if compat.has_eevee_shadow_switch(bpy.context.scene):
    compat.set_eevee_shadows(bpy.context.scene, True)
    if 'hb_shadows_default' in bpy.context.scene: del bpy.context.scene['hb_shadows_default']
    ui.shadows_off_by_default(); assert not compat.eevee_shadows(bpy.context.scene)
    compat.set_eevee_shadows(bpy.context.scene, True); ui.shadows_off_by_default(); assert compat.eevee_shadows(bpy.context.scene)
print('PASS Halo 2 sky layers (alpha/additive preview, cloud mask and tiling, baked RGBA), Halo 2: Anniversary game entry, foliage cut-outs, collision size, resume caches')
