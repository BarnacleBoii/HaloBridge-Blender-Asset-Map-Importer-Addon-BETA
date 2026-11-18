"""A Halo 2 sky chosen under Sapien Sky keeps its layer order and brings its sun and sky light."""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bpy
from halo_bridge import sky_export

calls = []
def fake_export(obj, folder, progress=None, order=None, target_radius=None):
    calls.append(order)
    assert sky_export.MIN_RADIUS <= target_radius <= sky_export.MAX_RADIUS, target_radius
    return dict(jms='sky.JMS', shaders=[], name=obj.name, radius=1.0)
sky_export.export = fake_export

mesh = bpy.data.meshes.new('sky'); mesh.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
for name in ('stars', 'ring', 'clouds'): mesh.materials.append(bpy.data.materials.new(name))
obj = bpy.data.objects.new('Sapien sky - coagulation', mesh); bpy.context.scene.collection.objects.link(obj)
obj['hb_sky_game'] = 'halo2'
obj['hb_sky_lighting'] = json.dumps(dict(outdoor_ambient=[.79, .84, .87], lights=[dict(direction=[.88, .08, .47], color=[.95, .91, .87], power=.3, diameter=.0035, flags=15)]))

result = sky_export.export_chosen_sky(bpy.context.scene, obj, Path(bpy.app.tempdir) / 'sky')
assert [calls[-1][m.as_pointer()] for m in mesh.materials] == [0, 1, 2], 'material slots give the Halo 2 draw order'
assert len(result['sky_lights']) == 200 and result['sky_lights'][-1]['solid_angle'] < .001, 'sky patches, then the sun last'

# Other games' chosen skies: no order, no lights.
obj['hb_sky_game'] = 'reach'
result = sky_export.export_chosen_sky(bpy.context.scene, obj, Path(bpy.app.tempdir) / 'sky')
assert calls[-1] is None and 'sky_lights' not in result

# A Halo 2 sky whose lights can't be found still exports, without lights.
obj['hb_sky_game'] = 'halo2'; del obj['hb_sky_lighting']
sky_export._look_up_lighting = lambda scene, o: None
result = sky_export.export_chosen_sky(bpy.context.scene, obj, Path(bpy.app.tempdir) / 'sky')
assert 'sky_lights' not in result and calls[-1] is not None
print('PASS: a chosen Halo 2 sky keeps its layer order and its sun and sky light')
