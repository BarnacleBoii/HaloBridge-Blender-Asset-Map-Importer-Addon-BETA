"""Instances are split under Halo 3's render limits: 16,000 triangles and the render vertex limit."""
import sys
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from halo_bridge import geometry_export, blender_ops
blender_ops.ensure_exporter()
for obj in list(bpy.data.objects): bpy.data.objects.remove(obj, do_unlink=True)
scene = bpy.context.scene


def cards(name, count):
    """count separate quads (grass cards): 4 render vertices and 2 triangles each."""
    verts, faces = [], []
    for i in range(count):
        x, y = i % 100, i // 100
        base = len(verts)
        verts += [(x, y, 0), (x + .5, y, 0), (x + .5, y, 1), (x, y, 1)]
        faces.append((base, base + 1, base + 2, base + 3))
    mesh = bpy.data.meshes.new(name); mesh.from_pydata(verts, [], faces)
    mesh.uv_layers.new()
    mat = bpy.data.materials.new(name); mesh.materials.append(mat)
    obj = bpy.data.objects.new('%' + name, mesh); scene.collection.objects.link(obj)
    return obj, mat


# 9,000 cards: 18,000 triangles and 36,000 vertices. Triangles alone would split it into
# 16,000 + 2,000 triangles, leaving 32,000 vertices in the first part (over Tool's 32,767
# once Tool adds its own); the vertex limit splits it further.
grass, _ = cards('hb_0', 9000)
meshes = []; names = {'hb_0': 'dry grass'}; messages = []
geometry_export.chunk_instances(scene, meshes, names, messages.append)
parts = [o for o in scene.objects if o.name.startswith('%')]
for part in parts:
    keys = geometry_export.corner_keys(part.data)
    triangles = sum(len(p.vertices) - 2 for p in part.data.polygons)
    assert int(keys.max()) + 1 <= geometry_export.RENDER_VERTEX_LIMIT and triangles <= 16000, (len(set(keys)), triangles)
assert len(parts) == 2 and sum(len(p.data.polygons) for p in parts) == 9000, [len(p.data.polygons) for p in parts]
assert messages and 'dry grass' in messages[0] and 'vertices' in messages[0], messages
# Two-sided cards count their vertices twice.
for o in parts: bpy.data.objects.remove(o, do_unlink=True)
leaves, mat = cards('hb_1', 5000); mat.ass_jms.two_sided = True
names['hb_1'] = 'leaves'
geometry_export.chunk_instances(scene, meshes, names, messages.append)
parts = [o for o in scene.objects if o.name.startswith('%')]
assert len(parts) == 2, len(parts)
# A two-sided grid shares its vertices: 8,181 distinct vertices, but Tool can count up to
# one per face corner (32,000, doubled for the back faces), so it is split by corners.
for o in parts: bpy.data.objects.remove(o, do_unlink=True)
grid = bpy.data.meshes.new('hb_3')
grid.from_pydata([(x, y, 0) for y in range(81) for x in range(101)], [],
                 [(y * 101 + x, y * 101 + x + 1, (y + 1) * 101 + x + 1, (y + 1) * 101 + x) for y in range(80) for x in range(100)])
grid.uv_layers.new(); gmat = bpy.data.materials.new('hb_3'); gmat.ass_jms.two_sided = True; grid.materials.append(gmat)
scene.collection.objects.link(bpy.data.objects.new('%hb_3', grid)); names['hb_3'] = 'tree'
geometry_export.chunk_instances(scene, meshes, names, messages.append)
parts = [o for o in scene.objects if o.name.startswith('%')]
assert len(parts) == 3 and sum(len(p.data.polygons) for p in parts) == 8000, [len(p.data.polygons) for p in parts]
assert all(len(p.data.loops) * 2 <= geometry_export.RENDER_VERTEX_LIMIT for p in parts), [len(p.data.loops) for p in parts]
# A small mesh is left alone.
for o in parts: bpy.data.objects.remove(o, do_unlink=True)
small, _ = cards('hb_2', 100); names['hb_2'] = 'small'
geometry_export.chunk_instances(scene, meshes, names, messages.append)
assert [o.name for o in scene.objects if o.name.startswith('%')] == ['%hb_2']
print('PASS render limits: vertex and triangle splits, two-sided doubling, small meshes untouched')
