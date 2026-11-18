"""Skip objects with export problems: an object Halo Tool rejects is left out and preparation starts again."""
import sys,tempfile,time
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import halo_bridge
halo_bridge.register()
from halo_bridge import ui,blender_ops
from halo_bridge.diagnostics import ValidationError
import addon_utils;addon_utils.enable('io_scene_halo',default_set=True)
for obj in list(bpy.context.scene.objects):bpy.data.objects.remove(obj,do_unlink=True)
with tempfile.TemporaryDirectory() as tmp:
    s=bpy.context.scene.halo_bridge;s.cache=tmp;s.kit=tmp;s.level='hb_skip_fixture';s.lighting=False;s.open_sapien=False
    shader=Path(tmp)/'tags/fixture/ground.shader';shader.parent.mkdir(parents=True);shader.write_bytes(b'fixture')
    mat=bpy.data.materials.new('Ground');mat['hb_shader']='fixture/ground'
    for name,x in (('Ground',0),('Dense tree',300)):
        mesh=bpy.data.meshes.new(name);mesh.from_pydata([(x,0,0),(x+100,0,0),(x,100,0)],[],[(0,1,2)]);mesh.materials.append(mat)
        bpy.context.scene.collection.objects.link(bpy.data.objects.new(name,mesh))
    bpy.context.view_layer.update()
    ui.build.ensure_sapien_closed=lambda:None
    exported=[];compiles=[]
    def export(cfg,path,scene=None):
        exported.append(sorted(set(cfg['geometry_names'].values())))
        yield
        return []
    blender_ops.export_scene_steps=export
    def build(cfg,path,placements,cancel,progress):
        compiles.append(1)
        if 'Dense tree' in cfg['geometry_names'].values():
            raise ValidationError(["-ERROR- (object Dense tree) section 'global' has too many vertices (count=36964, max=32767)",
                                   '-FATAL- (object Dense tree) FATAL ERROR!  Instance had fatal error! (fix pervious error in tool output)',
                                   '-FATAL- FATAL ERROR!  Import failed because 1 or more instanced had a critical error'],'Halo Tool')
        return 'fixture.scenario'
    ui.build.prepare=build
    def run():
        bpy.ops.halo_bridge.prepare(warnings_accepted=True)
        deadline=time.monotonic()+20
        while ui._task and time.monotonic()<deadline:
            ui.poll();time.sleep(.01)
    # Without skipping, Tool's rejection stops the build.
    s.skip_invalid=False;run()
    assert ui._error and len(compiles)==1 and not ui.tool_rejected(bpy.context.scene),(ui._error,compiles)
    # With skipping, the object is left out and preparation starts again by itself.
    s.skip_invalid=True;compiles.clear();exported.clear();ui._error=''
    run()
    assert not ui._task and not ui._error,ui._error
    assert exported==[['Dense tree','Ground'],['Ground']],exported
    assert len(compiles)==2 and ui._message=='Ready: fixture.scenario',(compiles,ui._message)
    tree=bpy.context.scene.objects['Dense tree']
    assert 'too many vertices' in tree['hb_tool_rejected']
    report=bpy.data.texts['HaloBridge preparation report'].as_string()
    assert 'Left out' in report and 'Dense tree' in report,report
    # The next preparation leaves it out straight away.
    compiles.clear();exported.clear();run()
    assert exported==[['Ground']] and len(compiles)==1,(exported,compiles)
print('PASS: Tool-rejected objects are skipped and preparation restarts; without skipping the build stops')
