"""Per-object omissions, used material slots, filter state and shader selection."""
import sys,tempfile
from pathlib import Path
import bpy
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import halo_bridge
halo_bridge.register()
from halo_bridge import ui,export_review,geometry_export,shader_choices,blender_ops
from halo_bridge.diagnostics import ValidationError
for obj in list(bpy.data.objects):bpy.data.objects.remove(obj,do_unlink=True)
def triangle(name,mat):
    mesh=bpy.data.meshes.new(name);mesh.from_pydata([(0,0,0),(100,0,0),(0,100,0)],[],[(0,1,2)])
    if mat:mesh.materials.append(mat)
    obj=bpy.data.objects.new(name,mesh);bpy.context.scene.collection.objects.link(obj);return obj
with tempfile.TemporaryDirectory() as tmp:
    tags=Path(tmp)/'tags';tags.mkdir();(tags/'terrain.shader').write_text('synthetic')
    good=bpy.data.materials.new('Halo terrain');good['hb_shader']='terrain'
    unused=bpy.data.materials.new('Unused ordinary material')
    floor=triangle('Valid terrain',good);floor.data.materials.append(unused)
    bad=triangle('Unassigned plane',unused)
    empty=triangle('Missing slot',None)
    bpy.context.view_layer.update()
    cfg={'kit':tmp,'skip_invalid':False}
    issues,used,_=export_review.inspect([floor,bad,empty],cfg)
    assert floor.name not in issues and used[floor.name]==[good]
    assert set(issues)=={bad.name,empty.name}
    try:ui.preparation_warnings(bpy.context,cfg)
    except ValidationError as e:assert 'Unassigned plane' in str(e) and 'Missing slot' in str(e)
    else:raise AssertionError('Invalid objects were not blocked by default')
    cfg['skip_invalid']=True
    warnings=ui.preparation_warnings(bpy.context,cfg)
    assert len([w for w in warnings if w.startswith('WILL NOT EXPORT')])==2
    # Exercise the complete Blender geometry staging route; stub only ASS IO.
    def capture(config,path):
        names=set(config['geometry_names'].values())
        assert names=={'Valid terrain'},names
        assert set(config['skipped_objects'])=={'Unassigned plane','Missing slot'}
        for o in bpy.context.scene.objects:
            assert unused not in list(o.data.materials)
        return []
    with patch.object(blender_ops,'ensure_exporter'),patch.object(blender_ops,'export_scene',side_effect=capture):
        # Temporary material flags belong to the installed exporter.
        import addon_utils;addon_utils.enable('io_scene_halo')
        geometry_export.export(cfg,Path(tmp)/'export.ASS')
    assert floor.name in bpy.context.scene.objects and bad.name in bpy.context.scene.objects
    assert list(floor.data.materials)==[good,unused]
    # An object that fails while it is converted is skipped too, instead of stopping the build.
    broken=triangle('Broken piece',good);bpy.context.view_layer.update()
    real=geometry_export.simple_collision
    def fails(obj):
        if obj.name=='Broken piece':raise RuntimeError('fixture conversion failure')
        return real(obj)
    def capture_broken(config,path):
        assert set(config['geometry_names'].values())=={'Valid terrain'},config['geometry_names']
        assert 'fixture conversion failure' in config['skipped_objects']['Broken piece'][0]
        assert 'Broken piece' not in config['collision_routes']
        return []
    with patch.object(blender_ops,'ensure_exporter'),patch.object(blender_ops,'export_scene',side_effect=capture_broken),patch.object(geometry_export,'simple_collision',side_effect=fails):
        geometry_export.export(cfg,Path(tmp)/'export.ASS')
        try:geometry_export.export(dict(cfg,skip_invalid=False),Path(tmp)/'export.ASS')
        except Exception as e:assert 'fixture conversion failure' in str(e) or 'Unassigned plane' in str(e),e
        else:raise AssertionError('Conversion failure ignored without skipping')
    bpy.data.objects.remove(broken,do_unlink=True)
    # Objects Tool rejects are remembered and left out until they change.
    error=ValidationError(["-ERROR- (object Valid terrain) section 'global' has too many vertices (count=36964, max=32767)",
                           '-FATAL- (object Valid terrain) FATAL ERROR!  Instance had fatal error! (fix pervious error in tool output)',
                           '-FATAL- FATAL ERROR!  Import failed because 1 or more instanced had a critical error'])
    assert ui.mark_tool_rejections(error)==[floor] and 'too many vertices' in floor['hb_tool_rejected']
    assert ui.tool_rejected(bpy.context.scene)==[floor]
    issues,_,_=export_review.inspect([floor],cfg)
    assert 'rejected' in issues[floor.name][0],issues
    floor.data.vertices.add(1);floor.data.update();bpy.context.view_layer.update()
    issues,_,_=export_review.inspect([floor],cfg)
    assert floor.name not in issues,issues  # changed: tried again
    ui.HBRetryRejected.run(None,bpy.context)
    assert not ui.tool_rejected(bpy.context.scene)
    assert ui.mark_tool_rejections(ValidationError(['-ERROR- structure import pipeline failed']))==[]
    s=bpy.context.scene.halo_bridge;s.kit=tmp
    assert shader_choices.scan(tmp)==1
    s.shader_choice='terrain';bpy.context.view_layer.objects.active=bad
    ui.HBShader.run(None,bpy.context)
    assert unused['hb_shader']=='terrain' and unused['hb_shader_game']=='halo3'
    # Legacy .map/path casing and saved numeric selection must agree.
    s.assets.clear()
    for level in ['010_jungle','010_JUNGLE.map','levels\\010_jungle','100_citadel']:
        row=s.assets.add();row.level=level;row.category='Structures';row.kind='instance'
    ui._level_items_token=None;s.filter_level='010_jungle'
    assert sum(ui.row_visible(s,a) for a in s.assets)==3
    s.filter_level='__ALL__';assert sum(ui.row_visible(s,a) for a in s.assets)==4
    s.filter_level='010_jungle';assert sum(ui.row_visible(s,a) for a in s.assets)==3
print('PASS: unused slots ignored; invalid objects reviewed and omitted without scene edits; shader dropdown preserves tags; normalized level filter works')
