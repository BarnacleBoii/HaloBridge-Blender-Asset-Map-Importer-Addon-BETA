"""A structure piece's see-through (Halo 2 transparent) faces become a separate instance piece."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from halo_bridge.geometry_export import _split_see_through

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
temp = bpy.data.scenes.new('temp')
mesh = bpy.data.meshes.new('piece')
mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0, 0), (2, 1, 0)], [], [(0, 1, 2, 3), (1, 4, 5, 2)])
wall, glass = bpy.data.materials.new('wall'), bpy.data.materials.new('glass')
glass['hb_transparent'] = 'alpha'
mesh.materials.append(wall); mesh.materials.append(glass)
mesh.polygons[1].material_index = 1
clone = bpy.data.objects.new('hb_0', mesh); temp.collection.objects.link(clone)
shared = bpy.data.objects.new('%hb_1', mesh); temp.collection.objects.link(shared)  # another placement of the same mesh
meshes = []
piece = _split_see_through(clone, temp, meshes)
assert piece is not None and piece.name.startswith('%hb_'), piece
assert [p.material_index for p in clone.data.polygons] == [0] and len(piece.data.polygons) == 1
assert piece.data.materials[piece.data.polygons[0].material_index].name == 'glass'
assert len(shared.data.polygons) == 2, 'the shared mesh is left whole'
assert len(meshes) == 2
# Nothing see-through: nothing split.
solid_only = bpy.data.objects.new('hb_2', bpy.data.meshes.new('solid')); temp.collection.objects.link(solid_only)
solid_only.data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)]); solid_only.data.materials.append(wall)
assert _split_see_through(solid_only, temp, meshes) is None
print('PASS: see-through faces of a structure piece become a separate instance piece')
