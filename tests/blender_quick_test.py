"""The quick test compile runs before the full compile, stops on object rejections only, and cleans up."""
import sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parent))
from halo_bridge import build
from halo_bridge.diagnostics import ValidationError
from test_quick_test import ass,material,mesh,instance
level_file=ass([material('leaves','1001000000000100000000')],[mesh(3000,0),mesh(12,0)],
               [instance(-1,'Scene Root',-1),instance(0,'%hb_0.001',1),instance(1,'Sky boundary.001',2)])
with tempfile.TemporaryDirectory() as tmp:
    kit=Path(tmp)/'kit';source=Path(tmp)/'level.ASS';source.write_bytes(level_file)
    shaders=kit/'tags/levels/multi/fixture/shaders';shaders.mkdir(parents=True);(shaders/'leaves.shader').write_bytes(b'x')
    calls=[];messages=[]
    def tool(*args,structure=None):
        test=kit/'data'/args[1]
        assert test.is_file() and structure=='levels\\multi\\hb_quick_test\\hb_quick_test',(args,structure)
        assert (kit/'tags/levels/multi/hb_quick_test/shaders/leaves.shader').is_file()
        calls.append(args)
        return behaviour()
    config={'level':'fixture'}
    behaviour=lambda:'ok'
    build.quick_test(config,source,kit,tool,messages.append)
    assert len(calls)==1 and any('passed' in m for m in messages),messages
    assert not (kit/'data/levels/multi/hb_quick_test').exists() and not (kit/'tags/levels/multi/hb_quick_test').exists()
    # A geometry rejection stops preparation (for the skip and collision retries).
    def rejected():
        raise ValidationError(["-ERROR- (object Tree) section 'global' has too many vertices (count=36964, max=32767)",
                               '-FATAL- (object Tree) FATAL ERROR!  Instance had fatal error!',
                               "-ERROR- (object Rock) unable to find shader 'x' anywhere",
                               '-FATAL- (object Rock) FATAL ERROR!  Instance had fatal error!'],'Halo Tool')
    behaviour=rejected
    try:build.quick_test(config,source,kit,tool,messages.append)
    except ValidationError as error:
        assert any('too many vertices' in i for i in error.issues) and not any('Rock' in i for i in error.issues),error.issues
        assert 'quick test' in error.issues[-1]
    else:raise AssertionError('Rejection ignored')
    assert not (kit/'data/levels/multi/hb_quick_test').exists()
    # A Tool crash on an object stops preparation too (it has no 'Instance had fatal error' line).
    def crashed():
        raise ValidationError(['-FATAL- (object Tree)',
                               r'-FATAL- (object Tree) ### ASSERTION FAILED:  at c:\mcc\release\h3\source\tool\geometry\connected_geometry\process\connected_geometry_plane_builder.cpp,#4092'],'Halo Tool')
    behaviour=crashed
    try:build.quick_test(config,source,kit,tool,messages.append)
    except ValidationError as error:assert any('ASSERTION' in i for i in error.issues),error.issues
    else:raise AssertionError('Crash ignored')
    # Anything else is reported and the full compile goes ahead.
    def other():raise ValidationError(['-FATAL- structure import pipeline failed'],'Halo Tool')
    behaviour=other;messages.clear()
    build.quick_test(config,source,kit,tool,messages.append)
    assert any('could not finish' in m for m in messages),messages
    # A level someone named hb_quick_test is never touched.
    theirs=kit/'tags/levels/multi/hb_quick_test';theirs.mkdir(parents=True);(theirs/'hb_quick_test.scenario').write_bytes(b'x')
    calls.clear();messages.clear();build.quick_test(config,source,kit,tool,messages.append)
    assert not calls and (theirs/'hb_quick_test.scenario').is_file() and any('already exists' in m for m in messages),messages
    import shutil;shutil.rmtree(theirs)
    # Nothing dense: no Tool run.
    source.write_bytes(ass([material('g','0'*22)],[mesh(10,0),mesh(12,0)],[instance(-1,'Scene Root',-1),instance(0,'%hb_0',1),instance(1,'Sky boundary',2)]))
    calls.clear();build.quick_test(config,source,kit,tool,messages.append);assert not calls
print('PASS: quick test compile runs on dense objects, stops only on object rejections, and cleans up')
