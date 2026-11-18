"""Add portal grid: vertical +portal planes across the level, replaced (not stacked) when run again."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from halo_bridge import portals

o = portals.PORTAL_OFFSET
cuts = portals.grid_cuts(0, 100, 40)
assert all(abs(a - b) < 1e-9 for a, b in zip(cuts, [100 * (1 + o) / 3, 100 * (2 + o) / 3])) and len(cuts) == 2, cuts
assert portals.grid_cuts(0, 30, 40) == []
# Never on a symmetric map's centre line, and every piece stays close to the spacing.
assert all(abs(c) > 1 for c in portals.grid_cuts(-100, 100, 50)), portals.grid_cuts(-100, 100, 50)
assert all(b - a <= 40 * (1 + o) for a, b in zip([0] + portals.grid_cuts(0, 250, 40), portals.grid_cuts(0, 250, 40) + [250]))

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
# A 100 x 60 world-unit level at HaloBridge's 100x working scale.
bpy.ops.mesh.primitive_plane_add(size=1)
ground = bpy.context.active_object
ground.scale = (100 * 100, 60 * 100, 1)
ground.data.materials.append(bpy.data.materials.new('ground'))
scene = bpy.context.scene
count = portals.add_grid(scene, 40, 100)
obj = bpy.data.objects[portals.OBJECT]
assert portals.is_portal(obj) and not portals.is_portal(ground)
assert obj.users_collection[0].name == portals.COLLECTION
# 100 units with 2% margins -> 3 pieces in x (2 planes); 60 units -> 2 pieces in y (1 plane).
assert count == 3 and len(obj.data.polygons) == 3, count
xs = sorted({round(v.co.x) for v in obj.data.vertices if abs(v.co.x) < 5000})
assert all(abs(x) < 5000 for x in xs)
# Run again with a smaller spacing: the grid is replaced, not added to. With the margins the level is
# about 105 x 65 units: 6 pieces in x (5 planes), 4 in y (3 planes).
count = portals.add_grid(scene, 20, 100)
assert len([o for o in bpy.data.objects if portals.is_portal(o)]) == 1 and count == len(bpy.data.objects[portals.OBJECT].data.polygons) == 8, count
# Automatic cuts follow the triangles: a dense corner gets its own small cells, and none is over budget.
import random
random.seed(1)
dense = [(random.uniform(0, 10), random.uniform(0, 10)) for _ in range(40000)]
sparse = [(random.uniform(0, 200), random.uniform(0, 200)) for _ in range(10000)]
xs, ys = portals.adaptive_cuts(dense + sparse, (0, 0), (200, 200))
import bisect
cells = {}
for x, y in dense + sparse:
    key = (bisect.bisect(xs, x), bisect.bisect(ys, y)); cells[key] = cells.get(key, 0) + 1
assert max(cells.values()) <= portals.CELL_TRIANGLES, max(cells.values())
assert sum(1 for x in xs if x < 10) >= 2, xs
assert portals.adaptive_cuts(dense[:portals.AUTO_TRIANGLES], (0, 0), (10, 10)) == ([], [])
# Retries after a leaf-map failure: parallel slabs across the long side, then the short side.
wide = [(random.uniform(0, 300), random.uniform(0, 100)) for _ in range(30000)]
assert all(portals.adaptive_cuts(wide, (0, 0), (300, 100), attempt=1))
xs, ys = portals.adaptive_cuts(wide, (0, 0), (300, 100), attempt=2)
assert xs and not ys and len(wide) / (len(xs) + 1) <= portals.CELL_TRIANGLES * 1.2, (xs, ys)
xs, ys = portals.adaptive_cuts(wide, (0, 0), (300, 100), attempt=3)
assert ys and not xs, (xs, ys)
assert all(portals.adaptive_cuts(wide, (0, 0), (300, 100), attempt=4))
# Pieces a portal plane crosses (by world bounding box).
import bmesh
box_mesh = bpy.data.meshes.new('cross_box'); bm = bmesh.new(); bmesh.ops.create_cube(bm, size=2); bm.to_mesh(box_mesh); bm.free()
box = bpy.data.objects.new('cross_box', box_mesh); box.location = (10, 0, 0); bpy.context.scene.collection.objects.link(box)
bpy.context.view_layer.update()
assert portals.crosses(box, [10.5], []) and portals.crosses(box, [], [0.2])
assert not portals.crosses(box, [8.5, 12], [3])
# Cuts slide into the gap between pieces (within half the distance to their neighbours).
moved = portals.avoid_spans([10.0], [(8, 12, 500), (13, 20, 100)], 0, 30)
assert moved[0] < 8 or 12 < moved[0] < 13, moved  # clear of both pieces, never on a side
assert portals.avoid_spans([10.0], [], 0, 30) == [10.0]
# Smaller clusters after "too many vertices": lower threshold and cell size.
assert portals.adaptive_cuts(dense[:10000], (0, 0), (10, 10), 3000, 0, 8000) != ([], [])
print('PASS: portal grid planes across the level, replaced when run again; automatic cuts follow the triangles')
