"""Halo 2 detail maps keep their own size and repeat in the Halo 3 shader instead of being dropped."""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from halo_bridge import cross_game

tmp = tempfile.mkdtemp()
def png(name, size=4):
    image = bpy.data.images.new(name, size, size, alpha=True)
    image.filepath_raw = str(Path(tmp) / (name + '.png')); image.file_format = 'PNG'; image.save()
    return name + '.png'

mesh = bpy.data.meshes.new('ground'); mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
obj = bpy.data.objects.new('ground', mesh); bpy.context.scene.collection.objects.link(obj)

def material(textures, template='shaders\\shader_templates\\opaque\\tex_bump_detail_blend_detail'):
    mat = bpy.data.materials.new('coag_ground'); mesh.materials.clear(); mesh.materials.append(mat)
    mat['hb_texture_sources'] = json.dumps(textures); mat['hb_texture_directory'] = tmp
    if template: mat['hb_h2_template'] = template
    if mat.node_tree: mat.node_tree.nodes.clear()  # layered preview: the recorded textures are used
    return mat

ground = [dict(usage='normal', path=png('bump'), tiling=[60, 60], name='dirt_pebble_bmp'),
          dict(usage='diffuse', path=png('base', 8), tiling=[1, 1], name='coag_ground'),
          dict(usage='diffuse_detail', path=png('grass'), tiling=[60, 60], blend_channel=1, name='coag_grass'),
          dict(usage='diffuse_detail', path=png('pebble'), tiling=[30, 60], blend_channel=2, name='dirt_pebble')]

# detail_blend: both detail maps, first = alpha 0; the bump map repeats in the shader, unbaked.
mat = material(ground)
entry = cross_game.prepare([obj], Path(tmp) / 'out', materials={mat.as_pointer(): mat})[mat.as_pointer()]
assert set(entry['maps']) == {'base_map', 'normal_map', 'detail_map', 'detail_map2'}, entry['maps']
assert entry['scales'] == {'detail_map': [60.0, 60.0], 'detail_map2': [30.0, 60.0], 'normal_map': [60.0, 60.0]}, entry['scales']
size = bpy.data.images.load(entry['maps']['normal_map']).size[:]
assert tuple(size) == (4, 4), 'bump map kept at its own size, not tiled 60 times into one texture'

# A single detail map (Halo 2 tex_bump) multiplies over the base; neutral default maps are left out.
mat = material([ground[1], dict(usage='diffuse_detail', path=png('sandstone'), tiling=[12, 12], name='sandstone')])
entry = cross_game.prepare([obj], Path(tmp) / 'out', materials={mat.as_pointer(): mat})[mat.as_pointer()]
assert set(entry['maps']) == {'base_map', 'detail_map'} and entry['scales'] == {'detail_map': [12.0, 12.0]}, entry
mat = material([ground[1], dict(usage='diffuse_detail', path=png('neutral'), tiling=[16, 16], name='shaders\\default_bitmaps\\bitmaps\\default_detail')])
entry = cross_game.prepare([obj], Path(tmp) / 'out', materials={mat.as_pointer(): mat})[mat.as_pointer()]
assert set(entry['maps']) == {'base_map'} and 'scales' not in entry, entry

# Other games' detail maps are not converted (their detail functions differ).
mat = material(ground, template=None)
entry = cross_game.prepare([obj], Path(tmp) / 'out', materials={mat.as_pointer(): mat})[mat.as_pointer()]
assert 'detail_map' not in entry['maps'], entry['maps']
print('PASS: Halo 2 detail maps keep their own repeat in the Halo 3 shader')
