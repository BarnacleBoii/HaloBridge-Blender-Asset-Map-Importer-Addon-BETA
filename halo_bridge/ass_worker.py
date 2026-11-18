"""Background Blender: export a saved collection of objects with the Halo toolset (see ass_parts.py)."""
import json
import sys
import addon_utils
import bpy

args = json.loads(sys.argv[sys.argv.index('--') + 1])
# The exporter looks itself up in the preferences, so enable it there (not saved: factory startup).
addon_utils.enable(args['addon'], default_set=True)
scene = bpy.context.scene
for obj in list(scene.objects):  # factory startup's cube, camera and light
    bpy.data.objects.remove(obj, do_unlink=True)
scene.unit_settings.system, scene.unit_settings.scale_length = args['units']
with bpy.data.libraries.load(args['blend'], link=False) as (source, target):
    target.collections = [args['collection']]
collection = target.collections[0]
scene.collection.children.link(collection)
bpy.context.view_layer.update()
bpy.ops.export_scene.ass(filepath=args['out'], **args['options'])
