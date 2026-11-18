"""Halo 2: Anniversary collision over Tool's limit: decimated to half, then cut into pieces."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from halo_bridge import geometry_export, blender_ops
blender_ops.ensure_exporter()

grid = 120
dense = bpy.data.meshes.new('dense')
verts = [(x * .05, y * .05, ((x * 7 + y * 3) % 5) * .01) for y in range(grid) for x in range(grid)]
faces = [(y * grid + x, y * grid + x + 1, (y + 1) * grid + x + 1, (y + 1) * grid + x) for y in range(grid - 1) for x in range(grid - 1)]
dense.from_pydata(verts, [], faces)
source = 2 * len(faces)  # 28,322 triangles

# Decimated to half, not welded down to the limit; faces sorted along the longest axis.
v, f = geometry_export.cleaned_surface(dense, {0}, max_triangles=4000, decimate=True)
tris = sum(len(x) - 2 for x in f)
assert .4 * source < tris < .6 * source, tris
centers = [sum(v[i][0] + 0 for i in face) / len(face) for face in f]
assert all(a <= b + 1e-6 for a, b in zip(centers, centers[1:])) or all(
    sum(v[i][1] for i in face) / len(face) <= sum(v[i][1] for i in g) / len(g) + 1e-6 for face, g in zip(f, f[1:])), 'sorted along an axis'
# More than MAX_COLLISION_PIECES pieces' worth: decimated further, to fit them.
v, f = geometry_export.cleaned_surface(dense, {0}, max_triangles=1000, decimate=True)
tris = sum(len(x) - 2 for x in f)
assert tris <= 1000 * geometry_export.MAX_COLLISION_PIECES * 1.05, tris
# Under the limit nothing changes; other games keep the welded simplification.
v, f = geometry_export.cleaned_surface(dense, {0}, max_triangles=50000, decimate=True)
assert sum(len(x) - 2 for x in f) == source
v, f = geometry_export.cleaned_surface(dense, {0}, max_triangles=4000)
assert sum(len(x) - 2 for x in f) <= 4000
assert not [s for s in bpy.data.scenes if 'decimate' in s.name] and not [m for m in bpy.data.meshes if 'decimate' in m.name]

# The part splitter cuts collision pieces of at most hb_collision_part_limit triangles.
scene = bpy.data.scenes.new('parts')
render = bpy.data.materials.new('render'); render.ass_jms.render_only = True
solid = bpy.data.materials.new('collision'); solid.ass_jms.collision_only = True
mesh = bpy.data.meshes.new('%hb_0')
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)] + [(x, 0, 1) for x in range(3000)] + [(x, 1, 1) for x in range(3000)], [],
                 [(0, 1, 2)] + [(3 + i, 4 + i, 3003 + i) for i in range(2999)])
mesh.materials.append(render); mesh.materials.append(solid)
for p in mesh.polygons[1:]: p.material_index = 1
mesh['hb_collision_part_limit'] = 1000
obj = bpy.data.objects.new('%hb_0', mesh); scene.collection.objects.link(obj)
names = {'hb_0': 'Rock'}; messages = []
for _ in geometry_export.chunk_instances_steps(scene, [], names, messages.append): pass
parts = [o for o in scene.objects if o.name.startswith('%')]
counts = sorted(sum(1 for p in o.data.polygons if p.material_index == 1) for o in parts)
assert len(parts) == 3 and max(counts) <= 1000 and sum(counts) == 2999, counts
assert all(n == 'Rock' for n in names.values()) and 'collision limit' in messages[0], messages
print('PASS: Anniversary collision is decimated to half and cut into pieces under the limit')
