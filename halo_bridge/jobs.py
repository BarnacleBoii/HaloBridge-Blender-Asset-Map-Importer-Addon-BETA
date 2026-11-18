"""Cancelable external jobs with readable logs and content-aware extraction caching."""
import json
import os
import subprocess
import threading
import time
from pathlib import Path
from .catalog import read_json, write_json, fingerprint, stable_id
from .diagnostics import ValidationError, compiler_errors

BIN=Path(__file__).parent/'bin'

class Cancelled(RuntimeError): pass

def process_activity(process):
    """CPU seconds and resident bytes from our own child process handle."""
    if os.name!='nt':return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    handle=wintypes.HANDLE(int(process._handle));times=[wintypes.FILETIME() for _ in range(4)]
    if not ctypes.windll.kernel32.GetProcessTimes(handle,*[ctypes.byref(t) for t in times]):return None
    counters=Counters();counters.cb=ctypes.sizeof(counters)
    if not ctypes.windll.psapi.GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):return None
    cpu=sum((t.dwHighDateTime<<32)|t.dwLowDateTime for t in times[2:])/10000000
    return cpu,counters.WorkingSetSize

def _peak_memory(process):
    if os.name!='nt':return 0
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_=[('cb',wintypes.DWORD),('PageFaultCount',wintypes.DWORD)]+[(n,ctypes.c_size_t) for n in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]
    c=Counters();c.cb=ctypes.sizeof(c)
    ok=ctypes.windll.psapi.GetProcessMemoryInfo(wintypes.HANDLE(int(process._handle)),ctypes.byref(c),c.cb)
    return c.PeakWorkingSetSize if ok else 0

def run_process(args, log, cwd=None, cancel=None, status=None, structure=None):
    log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with log.open('w',encoding='utf-8') as stream:
        p=subprocess.Popen([str(a) for a in args],cwd=cwd,stdout=stream,stderr=subprocess.STDOUT,creationflags=flags)
        if hasattr(status,'bind_process'):status.bind_process(p,process_activity)
        started=time.perf_counter();peak=0
        try:
            while p.poll() is None:
                if status:status()
                peak=max(peak,_peak_memory(p))
                if cancel and cancel.is_set():
                    subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,creationflags=flags)
                    if p.poll() is None:p.kill()
                    p.wait();raise Cancelled('Cancelled; the previous successful level is retained.')
                time.sleep(.1)
            if status:
                if hasattr(status,'last_update'):status.last_update=-float('inf')
                status()
        finally:
            if p.poll() is None: p.kill();p.wait()
            write_json(log.with_suffix('.metrics.json'),dict(seconds=time.perf_counter()-started,peak_working_set_bytes=peak,exit_code=p.returncode))
    text=log.read_text(encoding='utf-8',errors='replace')
    errors=compiler_errors(text, structure if p.returncode == 0 else None)
    if p.returncode or errors:
        raise ValidationError(errors or ['Process exited with code '+str(p.returncode)+'.\n'+text],
                              'External job failed; full log: '+str(log))
    return text

def helper(kind, job, directory, cancel=None):
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    nonce=str(time.time_ns());file=directory/(kind+'_'+nonce+'.json');write_json(file,dict(version=1,**job))
    exe=BIN/('extractor/HaloBridge.Extractor.exe' if kind=='extractor' else 'tags/HaloBridge.Tags.exe')
    if not exe.is_file():raise RuntimeError('HaloBridge helper is missing. Install the release add-on ZIP, or build helpers from source. Use Check setup for details.')
    run_process([exe,file], file.with_suffix('.log'), cancel=cancel)
    return read_json(job['output']) if Path(job['output']).is_file() else None

def extract_h2a_campaign_asset(asset, config, cancel=None):
    """An indexed Halo 2: Anniversary campaign template or material (asset['map'] is shared.pck) as a
    preview.json, extracted on first use; its textures go to the campaign texture folder."""
    cache=Path(config['cache'])/'assets'/asset['id'];stamp=cache/'stamp.json'
    max_texture=int(config.get('max_texture_size',2048))
    # Asset 2: variants, damage states and lower LODs are switchable parts (parts.json) instead of hidden.
    signature={'h2a_campaign_asset':2,'map':fingerprint(asset['map']),'tag':asset['tag'],'max_texture':max_texture}
    if read_json(stamp)==signature and (cache/'preview.json').is_file():return cache/'preview.json'
    cache.mkdir(parents=True,exist_ok=True);stamp.unlink(missing_ok=True)
    helper('extractor',dict(operation='h2a_campaign_extract',game='h2a',map=asset['map'],tag=asset['tag'],max_texture=max_texture,
                            textures=str(h2a_campaign_textures(config,max_texture)),output=str(cache)),Path(config['cache'])/'jobs',cancel)
    write_json(stamp,signature)
    return cache/'preview.json'


def index_h2a_campaign(config, output, cancel=None):
    """Index every placeable Anniversary campaign template and material in shared.pck."""
    paks=h2a_campaign_paks(config.get('maps'))
    if paks is None:
        raise RuntimeError('Halo 2: Anniversary campaign files not found. Select MCC\'s groundhog maps folder (the campaign is in halo2\\preload\\paks of the same MCC install).')
    return helper('extractor',dict(operation='h2a_campaign_index',game='h2a',map=str(paks/'shared.pck'),output=str(output)),Path(config['cache'])/'jobs',cancel)


def extract(asset, config, cancel=None):
    if asset.get('source')=='h2a_campaign':
        return extract_h2a_campaign_asset(asset,config,cancel)
    if asset.get('source')=='scenario' and not asset.get('map'):
        from . import scenario_scene
        return scenario_scene.asset_path(asset,config,cancel)
    if asset.get('source')=='scenario' and not Path(asset['map']).is_file():
        # Halo CE / Halo 2 scenario assets read a map built by the kit's Tool; rebuild it if storage was cleared.
        from . import classic_scenario
        asset=dict(asset,map=str(classic_scenario.build_map(dict(config,game=asset.get('game',config.get('game'))),asset['scenario'],cancel)))
    if asset['kind']=='legacy':
        mapped=asset.get('mapping')
        if not mapped: return Path(asset['path'])
        asset=mapped
    cache=Path(config['cache'])/'assets'/asset['id']
    if asset['kind'] in ('model','scenery'):cache=cache/'model_parts_v2'
    stamp=cache/'stamp.json'
    # Resource cache updates can change an asset even if the selected map does not.
    resources=sorted(Path(asset['map']).parent.glob('*.map'))
    # Extractor 5: Halo CE / Halo 2 shaders without a recognised diffuse use their own bitmap.
    # Extractor 6: Halo 2 sky layers carry their template's maps, tiling, tint and blending.
    # Extractor 7: Halo 2: Anniversary foliage and *_clip materials are cut-outs; tint maps aren't color maps.
    # Extractor 8: Halo 2 detail_blend shaders (outdoor ground) carry their two tiling detail maps.
    # Extractor 9: Halo 2 bump-mapped alpha-test shaders cut out with the bump map's alpha.
    # Extractor 7 (Halo CE): shaders carry their class (plasma, glass, water, chicago ...).
    signature={'extractor':{'h2a':7,'halo2':11}.get(asset.get('game'),7) if asset.get('game') in ('halo1','halo2','h2a') else 4,'files':[fingerprint(p) for p in resources], 'tag':asset['tag'],'section':asset['section']}
    if asset['kind']=='instance' and asset.get('game','halo3') in ('halo3','odst'):
        signature['source_bsp']=fingerprint(Path(config['kit'])/'tags'/(asset['tag']+'.scenario_structure_bsp'))
    if (read_json(stamp)==signature and (cache/'preview.json').is_file()
            and (asset['kind']!='instance' or asset.get('game','halo3') not in ('halo3','odst') or (cache/'collision.json').is_file())): return cache/'preview.json'
    cache.mkdir(parents=True,exist_ok=True)
    stamp.unlink(missing_ok=True)
    # Re-extraction must not retain textures from an older resource cache.
    for texture in cache.glob('texture_*.*'):texture.unlink()
    helper('extractor',dict(operation='material' if asset['kind']=='material' else 'extract',game=asset.get('game','halo3'),map=asset['map'],tag=asset['tag'],section=asset['section'],output=str(cache)),Path(config['cache'])/'jobs',cancel)
    if asset['kind']=='instance' and asset.get('game','halo3') in ('halo3','odst'):
        helper('tags',dict(operation='collision',kit=config['kit'],scenario=asset['tag'],section=asset['section'],asset_name=asset['name'],output=str(cache/'collision.json')),Path(config['cache'])/'jobs',cancel)
    write_json(stamp,signature)
    return cache/'preview.json'

def sky_lighting(asset,config,cancel=None):
    """A Halo 2 sky's lights and ambient color (see sky_lights), or None: for a sky chosen from
    the asset list, found by its render model. Cached next to the asset's extraction."""
    if asset.get('game')!='halo2' or not asset.get('map') or not Path(asset['map']).is_file():return None
    cache=Path(config['cache'])/'assets'/asset['id']
    cache.mkdir(parents=True,exist_ok=True)
    result=cache/'sky_lighting.json';stamp=cache/'sky_lighting.stamp.json'
    signature={'sky_lighting':1,'map':fingerprint(Path(asset['map'])),'tag':asset['tag']}
    if read_json(stamp)!=signature or not result.is_file():
        result.unlink(missing_ok=True)
        helper('extractor',dict(operation='sky_lighting',game='halo2',map=asset['map'],tag=asset['tag'],output=str(result)),Path(config['cache'])/'jobs',cancel)
        write_json(stamp,signature)
    return read_json(result,{}).get('sky_lighting')

def h2a_campaign_paks(maps):
    """MCC's Halo 2: Anniversary campaign paks folder (halo2/preload/paks: level .pck files and the
    13 GB shared.pck holding their textures), found from the selected maps folder (groundhog/maps
    sits beside halo2 in the MCC install), or None."""
    if not maps:return None
    path=Path(maps)
    for folder in (path,*path.parents):
        if folder.name.lower()=='paks' and (folder/'shared.pck').is_file():return folder
        candidate=folder/'halo2'/'preload'/'paks'
        if (candidate/'shared.pck').is_file():return candidate
    return None


def h2a_campaign_levels(maps):
    """Campaign level .pck names (shared.pck and cache.pck hold common data, not levels)."""
    paks=h2a_campaign_paks(maps)
    if paks is None:return []
    return sorted((p.name for p in paks.glob('*.pck') if p.stem.lower() not in ('shared','cache')),key=str.casefold)


def h2a_campaign_textures(config,max_texture):
    """One texture folder for every campaign level at this texture size: levels reuse many of
    shared.pck's textures, so each is stored once. Imported materials load their images from here,
    so it is kept (unlike the per-level geometry files)."""
    return Path(config['cache'])/'map_scenes'/('h2a_campaign_textures_'+str(int(max_texture)))


def _scene_complete(manifest):
    data=read_json(manifest,{}) if Path(manifest).is_file() else {}
    meshes=list(data.get('meshes',{}).values())
    return bool(meshes) and all((Path(manifest).parent/name).is_file() for name in meshes)


def discard_h2a_campaign_meshes(manifest):
    """After a successful import, delete a campaign scene's geometry files (about half its storage).
    Blender keeps the imported meshes and Prepare only reads scene.json; importing the level again
    re-extracts the geometry from the .pck (seconds). Textures are kept: the materials use them.
    Returns the bytes freed."""
    manifest=Path(manifest);data=read_json(manifest,{})
    if data.get('source')!='h2a_campaign':return 0
    freed=0
    for name in data.get('meshes',{}).values():
        path=(manifest.parent/name).resolve()
        if path.parent!=manifest.parent.resolve() or not path.is_file():continue
        freed+=path.stat().st_size;path.unlink()
    return freed


def extract_h2a_campaign_scene(config,level,cancel=None,progress=None):
    """A Halo 2: Anniversary campaign level (remastered Saber3D geometry and textures) as a map
    scene manifest, read by the extractor's h2a_campaign_scene operation (source/H2ACampaign).
    Geometry is in classic Halo 2 world coordinates, so it lines up with the original level."""
    paks=h2a_campaign_paks(config.get('maps'))
    if paks is None:
        raise RuntimeError('Halo 2: Anniversary campaign files not found. Select MCC\'s groundhog maps folder (the campaign levels are in halo2\\preload\\paks of the same MCC install).')
    level_path=paks/level;shared=paks/'shared.pck'
    if not level_path.is_file() or level_path.suffix.lower()!='.pck':raise RuntimeError('Choose a campaign level .pck from '+str(paks)+'.')
    max_texture=int(config.get('max_texture_size',2048))
    # Scene 1: first campaign export (LOD0, no helpers, layer-0 materials, base + normal textures).
    # Scene 2: textures as the game's own block-compressed data (DDS), in one folder shared by all levels.
    signature={'h2a_campaign_scene':2,'max_texture':max_texture,'level':fingerprint(level_path),'shared':fingerprint(shared)}
    folder=Path(config['cache'])/'map_scenes'/stable_id(str(level_path.resolve()),json.dumps(signature,sort_keys=True))
    textures=h2a_campaign_textures(config,max_texture)
    candidates=[folder]+sorted(folder.parent.glob(folder.name+'_retry_*'),reverse=True)
    for candidate in candidates:
        # Geometry files are removed after an import (discard_h2a_campaign_meshes); re-extract then.
        if read_json(candidate/'stamp.json')==signature and _scene_complete(candidate/'scene.json'):return candidate/'scene.json'
    # A completed extraction whose geometry was discarded after import is rebuilt in place (same
    # output, so scenes that reference its scene.json stay valid); only a failed one gets a new folder.
    if folder.exists() and read_json(folder/'stamp.json')!=signature:folder=folder.with_name(folder.name+'_retry_'+str(time.time_ns()))
    folder.mkdir(parents=True,exist_ok=True)
    directory=Path(config['cache'])/'jobs';directory.mkdir(parents=True,exist_ok=True)
    job=directory/('h2a_campaign_scene_'+str(time.time_ns())+'.json')
    write_json(job,dict(version=1,operation='h2a_campaign_scene',game='h2a',map=str(level_path),shared=str(shared),max_texture=max_texture,textures=str(textures),output=str(folder)))
    def status():
        if progress:
            try:
                data=read_json(folder/'progress.json',{})
                if data.get('message'):progress(data['message'])
            except (OSError,ValueError):pass
    run_process([BIN/'extractor/HaloBridge.Extractor.exe',job],job.with_suffix('.log'),cancel=cancel,status=status)
    manifest=folder/'scene.json'
    if not manifest.is_file():raise RuntimeError('The campaign level extractor did not create a scene manifest.')
    write_json(folder/'stamp.json',signature)
    return manifest


def extract_map_scene(config,map_name,cancel=None,progress=None):
    mp=Path(config['maps'])/map_name
    if not mp.is_file():raise RuntimeError('Choose an existing MCC .map filename for the selected game.')
    # Map scene 5 (Halo 2): detail_blend ground shaders carry their two tiling detail maps.
    # Map scene 6 (Halo 2): the sky's lights and ambient color (sky_lighting).
    # Map scene 7 (Halo 2): bump-mapped alpha-test shaders cut out with the bump map's alpha.
    # Map scene 4 (Halo CE): shaders carry their class (plasma, glass, water, chicago ...).
    signature={'map_scene':{'h2a':4,'halo2':9}.get(config.get('game'),4) if config.get('game') in ('halo1','halo2','h2a') else 1,'game':config.get('game','halo3'),'resources':[fingerprint(p) for p in sorted(mp.parent.glob('*.map'))]}
    # Content-addressed generation keeps a prior completed map cache intact.
    folder=Path(config['cache'])/'map_scenes'/stable_id(str(mp.resolve()),json.dumps(signature,sort_keys=True))
    # A failed BSP extraction must not become a permanently reusable cache.
    # Fresh attempts use new directories so an open Blender scene retains its
    # existing mesh identities and cached files, including user edits.
    candidates=[folder]+sorted(folder.parent.glob(folder.name+'_retry_*'),reverse=True)
    for candidate in candidates:
        manifest=candidate/'scene.json'
        data=read_json(manifest,{})
        if (read_json(candidate/'stamp.json')==signature and data.get('expected_bsps',0)>0
                and data.get('decoded_bsps')==data['expected_bsps']):
            if not (candidate/'texture_names.json').is_file():
                helper('extractor',dict(operation='texture_names',map=str(mp),output=str(candidate/'texture_names.json')),Path(config['cache'])/'jobs',cancel)
            return manifest
    if folder.exists():folder=folder.with_name(folder.name+'_retry_'+str(time.time_ns()))
    manifest=folder/'scene.json';stamp=folder/'stamp.json'
    folder.mkdir(parents=True,exist_ok=True)
    directory=Path(config['cache'])/'jobs';directory.mkdir(parents=True,exist_ok=True)
    job=directory/('map_scene_'+str(time.time_ns())+'.json')
    write_json(job,dict(version=1,operation='map_scene',game=config.get('game','halo3'),map=str(mp),output=str(folder)))
    def status():
        if progress:
            try:
                data=read_json(folder/'progress.json',{})
                if data.get('message'):progress(data['message'])
            except (OSError,ValueError):pass
    run_process([BIN/'extractor/HaloBridge.Extractor.exe',job],job.with_suffix('.log'),cancel=cancel,status=status)
    if not manifest.is_file():raise RuntimeError('Map extractor did not create a scene manifest.')
    write_json(stamp,signature)
    return manifest
