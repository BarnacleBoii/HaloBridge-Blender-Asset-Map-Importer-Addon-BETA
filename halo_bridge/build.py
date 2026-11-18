"""Transactional level compilation. Only the explicitly selected project namespace is replaced."""
import contextlib
import json
import os
import shutil
import subprocess
import time
import re
from pathlib import Path
from .catalog import read_json, write_json, safe_level
from .jobs import helper, run_process, Cancelled
from .diagnostics import ValidationError,geometry_warnings
from .progress import ToolProgress,tool_label

def ensure_sapien_closed():
    if os.name!='nt': return
    r=subprocess.run(['tasklist','/FO','CSV','/NH'],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if r.returncode: raise RuntimeError('Cannot check whether Sapien is running. Close Sapien and retry.')
    if any('"'+name+'"' in r.stdout.lower() for name in ('sapien.exe','sapien_play.exe')):
        raise RuntimeError('Save and close Sapien before preparing the level. This prevents overwriting unsaved editor changes.')

def faux_shader_failure(issues):
    """True for Tool's test-lighting assertion on a shader it cannot evaluate (faux_material.cpp)."""
    text='\n'.join(str(i) for i in issues).lower()
    return 'faux_material.cpp' in text or ('faux' in text and 'parameter_success' in text)

PER_PIXEL_RADIUS=2.0  # world units (bounding sphere radius): pieces this size or larger are lit per pixel
H3LM_EXE='h3lm-lm.exe'
H3LM_QUALITIES=('low','medium','high','super_slow','optimized','ultra')

def h3lm_exe(folder):
    """h3lm-lm.exe in the chosen H3LM folder (or the exe itself), or None."""
    if not folder:return None
    path=Path(folder);path=path if path.suffix.lower()=='.exe' else path/H3LM_EXE
    return path if path.is_file() else None

def bake_h3lm(config,kit,scenario,jobs,progress,cancel=None):
    """Bake the level's lightmaps with H3LM (Zoephie's GPU lightmapper for the Halo 3 Editing
    Kit). It makes the lightmap tags a new level lacks and installs the bake only when it
    finishes; a cancelled or failed bake installs nothing."""
    exe=h3lm_exe(config.get('h3lm_path'))
    if exe is None:
        raise RuntimeError('Lighting bake is set to H3LM, but '+H3LM_EXE+' was not found in "'+(config.get('h3lm_path') or 'no folder chosen')+'". '
                           'Download the H3LM Lightmapper, unzip it, and choose its folder under Generate Test Lighting; or set Lighting bake to Halo Tool.')
    quality=config.get('h3lm_quality','optimized')
    if quality not in H3LM_QUALITIES:quality='optimized'
    args=[exe,'lightmap','--scenario='+str(kit/'tags'/(scenario+'.scenario')),'--game=halo3','--quality='+quality]
    if config.get('h3lm_ao'):args.append('--ao')
    log=jobs/('h3lm-'+str(time.time_ns())+'.log')
    progress('Baking lighting with H3LM ('+quality+' quality) on the graphics card')
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    started=time.monotonic();shown=''
    with log.open('w',encoding='utf-8') as stream:
        p=subprocess.Popen([str(a) for a in args],cwd=str(exe.parent),stdout=stream,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,creationflags=flags)
        try:
            while p.poll() is None:
                if cancel and cancel.is_set():
                    subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=flags)
                    p.wait();raise Cancelled('Cancelled; H3LM installs nothing from a cancelled bake.')
                line=_last_line(log)
                if line and line!=shown:
                    shown=line;elapsed=int(time.monotonic()-started)
                    progress(f'H3LM [{elapsed//60}:{elapsed%60:02}]: '+line[:180])
                time.sleep(.5)
        finally:
            if p.poll() is None:p.kill();p.wait()
    text=log.read_text(encoding='utf-8',errors='replace')
    if p.returncode:
        lines=[l.strip() for l in re.split(r'[\r\n]+',text) if l.strip()]
        found=[l for l in lines if re.search(r'\b(error|failed|cannot|could not|unsupported)\b',l,re.I)]
        raise ValidationError((found or lines[-12:] or ['H3LM exited with code '+str(p.returncode)+'.'])[:20],'H3LM lighting bake failed (exit code '+str(p.returncode)+'); full log: '+str(log))
    elapsed=int(time.monotonic()-started)
    progress(f'H3LM finished the lighting bake in {elapsed//60}:{elapsed%60:02}')
    return text

def copy_h2_lighting(config,kit,scenario,level,jobs,tool,progress,cancel=None):
    """Halo 2's own baked lighting on the level structure (Halo 2's terrain), see h2_lightmaps.
    Tool's draft test lighting runs first: it makes the lightmap data, lights everything that is
    not Halo 2 terrain (instances per vertex, objects) and leaves the 9-layer master after
    faux_farm_finish; Halo 2's light then replaces the master's structure pixels, and Tool's last
    steps build the game's textures from it."""
    from . import h2_lightmaps
    if config.get('h2_lightmap_source'):
        h2ek,h2_scenario=config['h2_lightmap_source']
        exports=h2_lightmaps.export(h2ek,h2_scenario,config['cache'],progress,cancel)
    else:
        # Halo CE: its lighting is read from the .map itself (h1_lightmaps).
        from . import h1_lightmaps
        progress('Reading Halo CE\'s lighting from '+Path(config['h1_lightmap_map']).name)
        exports=h1_lightmaps.export(config['h1_lightmap_map'],config['cache'],helper,cancel)
    blob=str(100000000+time.time_ns()%900000000);blobdir='faux\\'+blob
    tool('faux_data_sync',scenario,level)
    tool('faux_farm_begin',scenario,level,'all','draft',blob)
    for step in ('dillum','pcast','radest','extillum','fgather'):
        tool('faux_farm_'+step,blobdir,'0','1')
        tool('faux_farm_'+step+'_merge',blobdir,'1')
    tool('faux_farm_finish',blobdir)
    work=jobs/('h2-lighting-'+str(time.time_ns()));work.mkdir(parents=True,exist_ok=True)
    def tags(operation,**kw):
        return helper('tags',dict(operation=operation,kit=str(kit),scenario=scenario,output=str(work/(operation+'.json')),**kw),jobs,cancel)
    mesh=work/'lightmap_mesh.csv'
    tags('lightmap_mesh',sources=[str(mesh)])
    tags('lightmap_write',template='read',sources=[str(work/'master_in.bin')])
    # Instances lit per vertex (see h2_lightmap_worker): their meshes, placements and light blocks.
    pervertex=None
    try:
        tags('pervertex_read')
        if (work/'pervertex_read.json').is_file():pervertex=work/'pervertex_read.json'
    except Exception as error:
        progress('Instances keep Tool\'s lighting (their per-vertex light could not be read: '+str(error)[:200]+')')
    progress('Copying Halo 2\'s lighting onto the level\'s lightmap (this takes several minutes)')
    job=dict(package=str(Path(__file__).resolve().parents[1]),exports=exports,mesh_csv=str(mesh),
             master_in=str(work/'master_in.bin'),master_out=str(work/'master_out.bin'),
             brightness=h2_lightmaps.BRIGHTNESS*float(config.get('h2_lightmap_brightness',1.0)))
    if pervertex:job.update(pervertex_in=str(pervertex),pervertex_order=str(work/'pervertex_order.json'),pervertex_out=str(work/'pervertex.bin'))
    log=work/'transfer.log'
    run_process([config['blender'],'-b','--factory-startup','--python-exit-code','1','--python',str(Path(__file__).with_name('h2_lightmap_worker.py')),'--',json.dumps(job)],
                log,cancel=cancel,status=lambda:_transfer_status(log,progress))
    result=json.loads([l for l in log.read_text(encoding='utf-8',errors='replace').splitlines() if l.startswith('{')][-1])
    progress(f"Halo 2 lighting copied to {result['pixels']:,} lightmap pixels"+(f" ({result['misses']:,} found no Halo 2 surface and keep Tool's light)" if result['misses'] else ''))
    tags('lightmap_write',sources=[str(work/'master_out.bin')])
    for step in ('faux-build-linear-textures-with-intensity-from-quadratic','faux-compress-scenario-bitmaps-dxt5','faux-farm-compression-merge'):
        tool(step,scenario,level)
    if result.get('vertices') and (work/'pervertex.bin').is_file():
        # Written last: the per-vertex light is already in its final (linear) form.
        try:
            tags('pervertex_write',sources=[str(work/'pervertex_order.json'),str(work/'pervertex.bin')])
            progress(f"Halo 2 lighting copied to {result['vertices']:,} vertices of instanced pieces")
        except Exception as error:
            progress('Instanced pieces keep Tool\'s lighting (writing their per-vertex light failed: '+str(error)[:200]+')')
    if not os.environ.get('HALO_BRIDGE_KEEP_WORK'):  # set to keep the lighting copy's files for debugging
        shutil.rmtree(work,ignore_errors=True)

def load_h2_gameplay(config,progress,cancel=None):
    """The Halo 2 Editing Kit scenario's gameplay data (see h2_scenario), or None if unreadable."""
    from . import h2_lightmaps,h2_scenario
    h2ek,h2_scenario_path=config['h2_lightmap_source']
    try:
        return h2_scenario.export(h2ek,h2_scenario_path,config['cache'],lambda args,cwd:h2_lightmaps._run(args,cwd,cancel))
    except Cancelled:
        raise
    except Exception as error:  # optional: an unreadable scenario must not fail the level
        error=str(error) or type(error).__name__
        progress('Halo 2 spawns, kill volumes and multiplayer objects were not read: '+str(error).splitlines()[0][:200])
        return None


def port_h2_gameplay(data,tag_job,progress):
    """The Halo 2 map's player starting locations, kill trigger volumes (falling off the map kills)
    and multiplayer objects, written into the Halo 3 scenario."""
    from . import h2_scenario
    starts=[dict(position=s['position'],facing=h2_scenario.facing_degrees(s),team=s['team']) for s in data.get('starts',[])]
    # Halo 3 trigger volumes are placed like Halo 2's: a corner, extended along forward, left and up.
    kills=[dict(name=v['name'],position=v['position'],forward=v['forward'],up=v['up'],extents=v['extents']) for v in h2_scenario.kill_volumes(data)]
    netgame=h2_scenario.netgame_objects(data)
    if not starts and not kills and not netgame:return
    try:
        tag_job('gameplay',starts=starts,kill_volumes=kills,netgame=netgame)
    except Cancelled:
        raise
    except Exception as error:  # optional, like reading it
        progress('Halo 2 spawns, kill volumes and multiplayer objects were not written: '+(str(error) or type(error).__name__).splitlines()[0][:200]);return
    progress('Original gameplay: '+str(len(starts))+' player starting locations, '+str(len(kills))+' kill trigger volume(s) and '+str(len(netgame))+' multiplayer objects (flags, teleporters, hills, bombs, oddballs) ported')


_transfer_shown={}
def _transfer_status(log,progress):
    line=_last_line(log)
    if line and line.startswith('Copying Halo 2') and _transfer_shown.get(str(log))!=line:
        _transfer_shown[str(log)]=line;progress(line)

def _last_line(path):
    try:
        with open(path,'rb') as f:
            f.seek(0,2);size=f.tell();f.seek(max(0,size-4096))
            tail=f.read().decode('utf-8','replace')
    except OSError:return ''
    lines=[l.strip() for l in re.split(r'[\r\n]+',tail) if l.strip()]
    return lines[-1] if lines else ''

# Shader types whose animated parameters Tool's test lighting cannot evaluate.
FAUX_RISKY_SUFFIXES=('.shader_custom',)
MAX_ASS_BYTES=1_900_000_000  # Tool's structure import fails on files near 2 GB

def bitmap_signatures(shaders,bitmap_dir):
    """{bitmap stem: [usage, source size, source mtime]} for every converted texture a build imports."""
    result={}
    for item in shaders:
        maps=[(usage,value) for usage,value in item.items() if isinstance(value,str) and usage not in ('path','blend')]
        for layer in item.get('layers',[]):maps+=[(m['usage'],m['bitmap']) for m in layer['maps']]
        for usage,bitmap in maps:
            stem=bitmap.rsplit('\\',1)[-1]
            source=next((p for p in (bitmap_dir/(stem+'.tif'),bitmap_dir/(stem+'.tiff')) if p.is_file()),None)
            if source is None:continue
            stat=source.stat();result[stem]=[usage,stat.st_size,stat.st_mtime_ns]
    return result

def lighting_suspects(config):
    """Original shader tags in this level that Tool's test lighting is known to reject."""
    return sorted(tag for tag,alias in config.get('shader_aliases',{}).items()
                  if Path(alias.get('source','')).suffix.lower() in FAUX_RISKY_SUFFIXES)

BACKUPS_KEPT=1  # per level: the Editing Kit folders as they were before the latest finished Prepare

def prune_backups(folder, keep=BACKUPS_KEPT):
    """Delete backups that are no longer needed (each holds a full copy of a level's data and tags).

    A rolled-back backup has already been copied back. Only the newest `keep` finished backups of
    each level stay. A backup still marked running (Blender closed mid-Prepare) is never deleted.
    Returns the bytes freed."""
    folder=Path(folder);kept={};freed=0
    if not folder.is_dir():return 0
    for backup in sorted((p for p in folder.iterdir() if p.is_dir() and p.name.isdigit()),key=lambda p:int(p.name),reverse=True):
        try:state=read_json(backup/'transaction.json') or {}
        except Exception:continue  # unreadable: leave it
        level=str(state.get('level','')).lower()
        if state.get('state')=='committed':
            kept[level]=kept.get(level,0)+1
            if kept[level]<=keep:continue
        elif state.get('state')!='rolled_back':continue
        size=sum(f.stat().st_size for f in backup.rglob('*') if f.is_file())
        try:shutil.rmtree(backup);freed+=size
        except OSError:pass  # in use; the next Prepare tries again
    return freed

@contextlib.contextmanager
def project_transaction(kit, level, cache):
    safe_level(level);kit=Path(kit).resolve();cache=Path(cache)
    # The lock is shared by every project/cache using this editing kit.
    lock=kit/'halo_bridge.build.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    os.write(fd,str(os.getpid()).encode());os.close(fd)
    backup=cache/'backups'/str(time.time_ns());backup.mkdir(parents=True)
    targets=[]
    try:
        for kind in ('data','tags'):
            target=kit/kind/'levels/multi'/level
            if target.resolve().parent != (kit/kind/'levels/multi').resolve(): raise ValueError('Unsafe output directory')
            existed=target.exists();targets.append((kind,target,existed))
            if existed: shutil.copytree(target,backup/kind)
        write_json(backup/'transaction.json',{'kit':str(kit),'level':level,'state':'running'})
        try:
            yield backup
        except BaseException:
            for kind,target,existed in targets:
                if target.exists(): shutil.rmtree(target)
                if existed: shutil.copytree(backup/kind,target)
            write_json(backup/'transaction.json',{'kit':str(kit),'level':level,'state':'rolled_back'})
            raise
        write_json(backup/'transaction.json',{'kit':str(kit),'level':level,'state':'committed'})
    finally:
        lock.unlink(missing_ok=True)
        try:prune_backups(cache/'backups')
        except Exception:pass  # cleanup never fails a Prepare

def mark_water_surfaces(ass_file,names):
    """Mark materials with Halo 3 water shaders as water surfaces: the ' symbol before the
    material name. Without it Tool builds the faces as ordinary geometry, which a water shader
    cannot draw ("vertex shader entry point doesn't exist": the water vanishes). The ASS has no
    water flag among its BM_FLAGS, and the Blender toolset drops symbols from ASS names."""
    if not names:return 0
    path=Path(ass_file);data=path.read_bytes();count=0
    for name in names:
        quoted=('"'+name+'"').encode()
        if quoted in data:data=data.replace(quoted,('"\''+name+'"').encode());count+=1
    if count:path.write_bytes(data)
    return count

def remove_stale_shaders(folder,name,keep):
    """Remove <folder>/<name>.shader* tags of any type other than `keep` (a suffix)."""
    folder=Path(folder)
    if not folder.is_dir():return
    for path in folder.glob(name+'.shader*'):
        if path.stem==name and path.suffix.lower()!=keep.lower():
            try:path.unlink()
            except OSError:pass

QUICK_TEST_LEVEL='hb_quick_test'

def quick_test(config,ass_file,kit,tool,progress):
    """Compile only the level's riskiest objects first (quick_test.py).

    Tool checks an object's limits only while building it, often near the end of a long
    compile that keeps nothing when it fails. A rejection found here stops preparation
    the same way (so Skip objects with export problems and the collision retries handle
    it) before the full compile starts. Anything else that goes wrong in the test is
    reported and the full compile runs as usual. The test level is always removed."""
    from . import quick_test as qt
    selection=qt.choose(ass_file)
    if not selection['chosen']:
        progress('Quick test compile: no objects near Halo 3\'s per-object limits; skipped');return
    folders=[kit/kind/'levels/multi'/QUICK_TEST_LEVEL for kind in ('data','tags')]
    marker=folders[0]/'halobridge_quick_test.txt'
    if any(folder.exists() for folder in folders) and not marker.is_file():
        # Never delete a level someone made with this name.
        progress('Quick test compile skipped: a level named '+QUICK_TEST_LEVEL+' already exists in the Editing Kit');return
    for folder in folders:shutil.rmtree(folder,ignore_errors=True)
    folders[0].mkdir(parents=True);marker.write_text('Temporary HaloBridge quick test level; safe to delete.\n')
    relative='levels\\multi\\'+QUICK_TEST_LEVEL+'\\structure\\'+QUICK_TEST_LEVEL+'.ASS'
    progress(f'Quick test compile: the {len(selection["chosen"]):,} objects most likely to be rejected ({selection["triangles"]:,} triangles) on their own, '
             'so an object Halo Tool rejects is found before the full compile')
    started=time.monotonic()
    try:
        qt.write(selection,kit/'data'/relative)
        # Tool looks for an object's shaders in its level's own shaders folder.
        shaders=kit/'tags/levels/multi'/safe_level(config['level'])/'shaders'
        if shaders.is_dir():shutil.copytree(shaders,folders[1]/'shaders')
        tool('structure',relative,structure='levels\\multi\\'+QUICK_TEST_LEVEL+'\\'+QUICK_TEST_LEVEL)
    except ValidationError as error:
        # Objects Tool rejected for their geometry (not a shader the test level couldn't find).
        def named(issue):
            found=re.search(r'\(object (.+?)\) ',issue);return found.group(1) if found else None
        bad={named(i) for i in error.issues if named(i) and 'unable to find shader' not in i and 'FATAL ERROR' not in i}
        rejected=[issue for issue in error.issues if named(issue) in bad]
        if rejected:
            raise ValidationError(rejected+['Found by the quick test compile, before the full compile.'],error.stage) from error
        progress('Quick test compile could not finish ('+(error.issues[0] if error.issues else 'no details')[:200]+'); continuing with the full compile')
    else:
        progress(f'Quick test compile passed in {int(time.monotonic()-started)//60}:{int(time.monotonic()-started)%60:02}; starting the full compile')
    finally:
        for folder in folders:shutil.rmtree(folder,ignore_errors=True)

def prepare(config, ass_file, placements, cancel=None, progress=None):
    progress=progress or (lambda message:None)
    def stage(number,name):
        if hasattr(progress,'stage'):progress.stage(number,name)
        else:progress(f'Stage {number}/5: '+name)
    level=safe_level(config['level']);kit=Path(config['kit']);cache=Path(config['cache'])
    scenario='levels\\multi\\'+level+'\\'+level
    manifest=cache/'projects'/level/'manifest.json';previous=read_json(manifest,{})
    target=kit/'tags'/(scenario+'.scenario')
    if (cache/'projects'/level/'map-build.json').exists():
        raise RuntimeError('This output was created using the older original-map mode. Choose a new Output level name to compile your edited Blender geometry and preserve that previous level.')
    if (cache/'projects'/level/'original-copy.json').exists():
        raise RuntimeError('This level is an original-map copy. Choose a new output level name for Blender geometry exports to protect its gameplay and Sapien edits.')
    if target.exists() and not previous:
        raise RuntimeError('This level already exists and is not owned by HaloBridge. Choose a new level name.')
    if previous and previous.get('kit')!=str(kit.resolve()): raise RuntimeError('Manifest belongs to a different editing kit.')
    sky_object=config.get('sky_object')
    sky=config.get('sky_scenario',r'levels\multi\isolation\isolation').replace('/', '\\')
    sky_parts=sky.split('\\')
    if sky_object:
        # Converted skies carry no sky lighting. Test lighting is baked with a kit sky
        # (the one chosen for this game, or its default) and the converted sky is set after.
        light_sky=sky if sky and ':' not in sky and (kit/'tags'/(sky+'.scenario')).is_file() else config.get('default_sky','')
        if not light_sky or not (kit/'tags'/(light_sky+'.scenario')).is_file():light_sky=''
        sky='converted:'+sky_object['name']
    elif not sky or any(p in ('','.','..') or ':' in p for p in sky_parts) or not (kit/'tags'/(sky+'.scenario')).is_file():
        raise RuntimeError('Sky source scenario must name an existing Editing Kit scenario without its extension, for example levels\\multi\\shrine\\shrine.')
    ensure_sapien_closed()
    if config.get('lighting',True) and config.get('lighting_baker')=='H3LM' and not h3lm_exe(config.get('h3lm_path')):
        raise RuntimeError('Lighting bake is set to H3LM, but '+H3LM_EXE+' was not found in "'+(config.get('h3lm_path') or 'no folder chosen')+'". '
                           'Download the H3LM Lightmapper, unzip it, and choose its folder under Generate Test Lighting; or set Lighting bake to Halo Tool.')
    jobs=cache/'jobs';jobs.mkdir(parents=True,exist_ok=True)
    def tag_job(operation,**kw):
        progress({'inspect':'Checking scenario state','environment':'Applying the selected sky','sync':'Updating scenario placements','sync_vehicles':'Updating original vehicle placements','ensure_spawn':'Checking the player start','prepare_bitmaps':'Configuring converted textures','import_shaders':'Creating converted Halo 3 shaders','lightmap_policy':'Setting how each piece is lit'}.get(operation,operation))
        ensure_sapien_closed()
        return helper('tags',dict(operation=operation,kit=str(kit),scenario=scenario,output=str(jobs/'tag-result.json'),**kw),jobs,cancel)
    def tool(*args,structure=None):
        ensure_sapien_closed();progress(tool_label(args[0]))
        if cancel and cancel.is_set():raise Cancelled('Cancelled')
        try:
            log=jobs/(str(time.time_ns())+'.log')
            return run_process([kit/'tool.exe',*args],log,cwd=kit,cancel=cancel,status=ToolProgress(args[0],log,progress,config.get('geometry_names',{})),
                               structure=(structure or scenario) if args[0]=='structure' else None)
        except ValidationError as error:
            names=config.get('geometry_names',{})
            def friendly(match):
                return '(object '+names[match[1]]+')' if match[1] in names else match[0]
            # Objects placed more than once get a second ' merged' pass in Tool.
            issues=[re.sub(r'\(poop (hb_\d+)(?:\.\d+)?(?: merged)?\)',friendly,issue) for issue in error.issues]
            if any('instanced geometry definitions' in issue for issue in issues):
                issues.append('Halo 3 allows at most 1024 instanced geometry definitions in one BSP, and this level has more (Tool can count more than the number of distinct meshes in Blender). '
                              'Delete or hide pieces you don\'t need, such as small scenery, crates and decorations, or join pieces that never move into fewer objects, then prepare again.')
            source=config.get('structure_source')
            if source and any("section 'cluster " in issue or 'plane builder unable to converge' in issue for issue in issues):
                issues.append('Structure geometry context: Blender object "'+source+'" was exported as the main level structure. '
                              'Cluster numbers name regions generated by Halo Tool, not Blender objects; this is the structure source, not an exact failed-face selection. '
                              'Find this object by name in the Outliner and inspect its evaluated geometry and subdivision modifiers. '
                              'Strip segment limits require less complex geometry or a properly designed cluster/portal layout; retrying unchanged geometry will not fix a limit error.')
            raise ValidationError(issues,error.stage) from error
    progress('Backing up the previous level before compilation...')
    with project_transaction(kit,level,cache):
        if previous:
            state=tag_job('inspect')['state']
            if state!=previous['state']:raise RuntimeError('CONFLICT: Sapien changed Blender-owned placements. Restore those edits or explicitly choose Resolve conflict: use Blender.')
        # Tool crashes ("MAXIMUM_MEMSET_SIZE") importing a structure file near 2 GB.
        size=Path(ass_file).stat().st_size
        if size>MAX_ASS_BYTES:
            raise ValidationError(['The exported level is '+f'{size/2**30:.1f}'+' GB; Halo 3\'s Tool cannot import a level file this large (about 2 GB at most, and a working Halo 3 level is usually far smaller). '
                                   'Very detailed levels such as Halo 2: Anniversary maps exceed it. Delete or hide parts of the level you don\'t need, or use fewer, simpler pieces, then prepare again.'],'Level too large for Tool')
        relative='levels\\multi\\'+level+'\\structure\\'+level+'.ASS'
        destination=kit/'data'/relative;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ass_file,destination)
        mark_water_surfaces(destination,[a['name'] for a in config.get('shader_aliases',{}).values() if str(a.get('source','')).lower().endswith('.shader_water')])
        aliases=list(config.get('shader_aliases',{}).values())
        stage(2,'Prepare Halo materials')
        terrain_names={entry['name'] for entry in config.get('converted_shaders',[]) if entry.get('terrain')}
        for index,alias in enumerate(aliases,1):
            progress(f'Preparing Halo materials {index}/{len(aliases)}: '+Path(alias.get('source',alias['name'])).stem)
            suffix='.shader_terrain' if alias['name'] in terrain_names else '.shader' if alias.get('generated') else Path(alias['source']).suffix
            # A shader of another type under the same name, left by an earlier Prepare (a converted
            # .shader, now a Halo 3 .shader_water), would be found by Tool instead of this one.
            remove_stale_shaders(kit/'tags/levels/multi'/level/'shaders',alias['name'],suffix)
            if alias.get('generated'):continue
            source=Path(alias['source']);destination_shader=kit/'tags/levels/multi'/level/'shaders'/(alias['name']+source.suffix)
            destination_shader.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination_shader)
        converted=config.get('converted_shaders',[])
        if converted:
            bitmap_root='levels\\multi\\'+level+'\\bitmaps\\reach'
            shader_root='levels\\multi\\'+level+'\\shaders'
            bitmap_dir=kit/'data'/bitmap_root;bitmap_dir.mkdir(parents=True,exist_ok=True)
            shaders=[]
            sky_shader_root='levels\\multi\\'+level+'\\sky\\shaders'
            for index,entry in enumerate(converted,1):
                progress(f'Copying converted material {index}/{len(converted)}: '+entry['name'])
                def copied(source):
                    source=Path(source);shutil.copy2(source,bitmap_dir/source.name)
                    return bitmap_root+'\\'+source.stem
                if entry.get('terrain'):
                    # Paintable terrain: a shader_terrain with a blend map and one tiled material per layer.
                    item=dict(path=shader_root+'\\'+entry['name'],terrain=True,blend_map=copied(entry['maps']['blend_map']),layers=[])
                    for layer in entry['layers']:
                        part=dict(maps=[])
                        for usage,key in (('base','base_map'),('detail','detail_map'),('bump','normal_map')):
                            if not layer.get(key):continue
                            prefix=key.split('_')[0];scale=layer.get(prefix+'_scale',[1,1]);offset=layer.get(prefix+'_offset',[0,0])
                            part['maps'].append(dict(usage=usage,bitmap=copied(layer[key]),scale_x=scale[0],scale_y=scale[1],offset_x=offset[0],offset_y=offset[1]))
                        item['layers'].append(part)
                    shaders.append(item)
                    continue
                # Tool's render-sky finds a sky's shaders in the sky folder's own shaders folder.
                item=dict(path=(sky_shader_root if entry.get('folder')=='sky' else shader_root)+'\\'+entry['name'],sky=entry.get('folder')=='sky',additive=bool(entry.get('additive')),blend=entry.get('blend',''),sort_layer=int(entry.get('sort_layer',0)),material=entry.get('material',''))
                for usage,source in entry['maps'].items():
                    source=Path(source);shutil.copy2(source,bitmap_dir/source.name)
                    item[usage]=bitmap_root+'\\'+source.stem
                # How often a map repeats over the base map (detail and bump maps).
                for usage,scale in entry.get('scales',{}).items():
                    item[usage.replace('_map','')+'_scale']=[float(scale[0]),float(scale[1])]
                shaders.append(item)
            # Compiled bitmaps are kept outside the kit, so a retry after a failed (rolled
            # back) build, or a repeat build, reuses them when no converted texture changed.
            saved=cache/'projects'/level/'compiled_bitmaps'
            tags_bitmaps=kit/'tags'/bitmap_root
            wanted=bitmap_signatures(shaders,bitmap_dir)
            if wanted and read_json(saved/'sources.json',{})==wanted and all((saved/(stem+'.bitmap')).is_file() for stem in wanted):
                progress('Reusing '+str(len(wanted))+' converted textures compiled by an earlier preparation')
                tags_bitmaps.mkdir(parents=True,exist_ok=True)
                for stem in wanted:shutil.copy2(saved/(stem+'.bitmap'),tags_bitmaps/(stem+'.bitmap'))
            else:
                tag_job('prepare_bitmaps',shaders=shaders)
                tool('bitmaps',bitmap_root)
                if saved.exists():shutil.rmtree(saved)
                saved.mkdir(parents=True)
                for stem in wanted:
                    compiled=tags_bitmaps/(stem+'.bitmap')
                    if compiled.is_file():shutil.copy2(compiled,saved/compiled.name)
                write_json(saved/'sources.json',wanted)
            tag_job('import_shaders',shaders=shaders)
        stage(3,'Compile geometry and collision')
        if config.get('quick_test',True):quick_test(config,ass_file,kit,tool,progress)
        text=tool('structure',relative)
        config['compiler_warnings']=geometry_warnings(text,config.get('geometry_names',{}))
        if config['compiler_warnings']:
            warning_report=jobs/('geometry-warnings-'+str(time.time_ns())+'.txt')
            warning_report.write_text('\n'.join(config['compiler_warnings']),encoding='utf-8')
            progress(str(len(config['compiler_warnings']))+' geometry warning(s). These may appear as red debug geometry in Sapien. Report: '+str(warning_report))
        if f"=== imported structure '{scenario}' in " not in text or not target.is_file() or not target.with_suffix('.scenario_structure_bsp').is_file():
            raise RuntimeError('Halo did not confirm the level structure import or produce its scenario and BSP tags.')
        # Large pieces get per-pixel lighting (Tool gives every piece per-vertex lighting, which
        # loses sun shadows and leaves steps between Halo 2 terrain pieces); Tool's red warning
        # markers are cleared unless asked to keep them (the report lists them).
        # Only for an H3LM bake: Tool's own draft lighting asserts on per-pixel pieces
        # (faux_rasterizer.cpp), so with it they keep Tool's per-vertex lighting.
        h3lm=config.get('lighting',True) and config.get('lighting_baker')=='H3LM' and config.get('h3lm_per_pixel',True)
        result=tag_job('lightmap_policy',radius=PER_PIXEL_RADIUS if h3lm else 1e9,template='keep_markers' if config.get('show_tool_markers') else '')
        if result and result.get('per_pixel'):progress(str(result['per_pixel'])+' of '+str(result['instances'])+' pieces get per-pixel lighting (sharper light and sun shadows)')
        stage(4,'Apply sky and scenario settings')
        if sky_object:
            # A sky converted from another game: build its render model, then its model,
            # scenery and the scenario's sky reference.
            sky_root='levels\\multi\\'+level+'\\sky'
            render=kit/'data'/sky_root/'render';render.mkdir(parents=True,exist_ok=True)
            shutil.copy2(sky_object['jms'],render/'sky.JMS')
            progress('Building the converted sky: '+sky_object['name'])
            tool('render-sky',sky_root)
            # A Halo 2 sky brings its own sun and sky light; other converted skies have none,
            # so their level is lit with another level's sky (light_sky) and given back its own after.
            own_light=bool(sky_object.get('sky_lights'))
            tag_job('sky_object',template=sky_root+'\\sky',radius=float(sky_object.get('radius',0)),sky_lights=sky_object.get('sky_lights') or [])
            if own_light:progress('The converted sky lights the level with the original sun and sky ('+str(len(sky_object['sky_lights']))+' sky lights)')
            if config.get('lighting',True) and light_sky and not own_light:tag_job('environment',template=light_sky)
        elif not previous or previous.get('sky_scenario',r'levels\multi\isolation\isolation')!=sky: tag_job('environment',template=sky)
        # Compilation may legitimately update derived placement fields. User edits
        # were checked above, before running Tool with Sapien closed.
        h2_data=load_h2_gameplay(config,progress,cancel) if config.get('h2_lightmap_source') else None
        if h2_data is None and config.get('h1_lightmap_map'):
            # Halo CE: its spawns and netgame flags, read from the .map, in Halo 2's form.
            from . import h1_scenario
            try:h2_data=h1_scenario.load(config['h1_lightmap_map'],jobs,helper,cancel)
            except Cancelled:raise
            except Exception as error:progress('Halo CE spawns and multiplayer objects were not read: '+(str(error) or type(error).__name__).splitlines()[0][:200])
            ce_vehicles=h1_scenario.vehicles(dict(vehicles=h2_data.get('ce_vehicles',[])),kit/'tags',config['h1_lightmap_map']) if h2_data else []
            if ce_vehicles:
                config['vehicle_placements']=list(config.get('vehicle_placements') or [])+ce_vehicles
                progress('Halo CE vehicles: '+str(len(ce_vehicles))+' placed with Halo 3 vehicle tags')
        if h2_data and config.get('h2_lightmap_source'):
            from . import h2_scenario
            h2_vehicles=h2_scenario.vehicles(h2_data,kit/'tags',config['h2_lightmap_source'][1])
            if h2_vehicles:
                config['vehicle_placements']=list(config.get('vehicle_placements') or [])+h2_vehicles
                progress('Halo 2 vehicles: '+', '.join(sorted({v['tag'].rsplit(chr(92),1)[-1] for v in h2_vehicles}))+' ('+str(len(h2_vehicles))+') placed with Halo 3 vehicle tags')
        after_compile=tag_job('inspect')['state']
        tag_job('sync',placements=placements,previous=after_compile)
        if config.get('vehicle_placements') or any(key.startswith('vehicle:') for key in after_compile):
            progress('Placing original vehicles (using existing vehicle tags)')
            tag_job('sync_vehicles',placements=config.get('vehicle_placements',[]),previous=after_compile)
        if config.get('spawn_position'):tag_job('ensure_spawn',position=config['spawn_position'])
        if h2_data:port_h2_gameplay(h2_data,tag_job,progress)
        lit=False
        if config.get('h2_lightmap_source') and not config.get('h1_lightmap_map'):
            from . import h2_lightmaps
            if not h2_lightmaps.lightmap_tags(*config['h2_lightmap_source']):
                # Some Halo 2 kit levels have no lightmap (Uplift): Tool's test lighting instead.
                progress('The Halo 2 Editing Kit has no lightmap for this level; Tool\'s test lighting lights it instead')
                config['h2_lightmap_source']=None
        if config.get('lighting',True) and config.get('h2_lightmaps') and (config.get('h2_lightmap_source') or config.get('h1_lightmap_map')):
            stage(5,'Copy the original game\'s lighting and finalize' if config.get('h1_lightmap_map') and not config.get('h2_lightmap_source') else 'Copy Halo 2\'s original lighting and finalize')
            copy_h2_lighting(config,kit,scenario,level,jobs,tool,progress,cancel)
            lit=True
        elif config.get('lighting',True) and config.get('lighting_baker')=='H3LM':
            stage(5,'Bake lighting with H3LM and finalize')
            # Tool makes the lightmap data and UVs first: H3LM can't yet give per-pixel pieces
            # their lightmap UVs on a level that was never lit ("not supported for a fresh map").
            tool('faux_data_sync',scenario,level)
            bake_h3lm(config,kit,scenario,jobs,progress,cancel)
            lit=True
        elif config.get('lighting',True):
            stage(5,'Generate test lighting and finalize')
            progress('Starting test lighting: 16 tool stages. Each stage can take several minutes.')
            blob=str(100000000+time.time_ns()%900000000);blobdir='faux\\'+blob
            try:
                tool('faux_data_sync',scenario,level)
                tool('faux_farm_begin',scenario,level,'all','draft',blob)
                for stage in ('dillum','pcast','radest','extillum','fgather'):
                    tool('faux_farm_'+stage,blobdir,'0','1')
                    tool('faux_farm_'+stage+'_merge',blobdir,'1')
                tool('faux_farm_finish',blobdir)
                tool('faux-build-linear-textures-with-intensity-from-quadratic',scenario,level)
                tool('faux-compress-scenario-bitmaps-dxt5',scenario,level)
                tool('faux-farm-compression-merge',scenario,level)
                lit=True
            except ValidationError as error:
                if not faux_shader_failure(error.issues):raise
                # Tool's test lighting (faux) asserts on some animated shaders (for example
                # 070_waste's waterfall.shader_custom). The compiled level is still valid,
                # so it is kept without test lighting instead of rolling everything back.
                suspects=lighting_suspects(config)
                config['lighting_skipped_shaders']=suspects
                note=('Test lighting was skipped: Halo Tool\'s test lighting cannot process '
                      +(('the animated shader(s) '+', '.join(suspects)) if suspects else 'one of this level\'s shaders')
                      +'. The level was prepared without test lighting. To light it, give those objects a different shader or remove them, '
                      'or turn off Generate Test Lighting. Tool log: '+str(error.stage))
                config.setdefault('compiler_warnings',[]).append(note)
                progress(note)
        else:stage(5,'Finalize (test lighting disabled)')
        if sky_object and light_sky and config.get('lighting',True) and not sky_object.get('sky_lights'):
            progress('Setting the converted sky'+(' (lighting was baked with '+light_sky.rsplit('\\',1)[-1]+')' if lit else ''))
            tag_job('sky_object',template='levels\\multi\\'+level+'\\sky\\sky',radius=float(sky_object.get('radius',0)))
        final=tag_job('inspect')
        write_json(manifest,dict(version=1,kit=str(kit.resolve()),scenario=scenario,state=final['state'],placements=placements,completed=time.time(),lighting=lit,sky_scenario=sky))
    progress('Ready in Sapien')
    return str(target)

