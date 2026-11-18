import json
import sys
import copy
import time
import textwrap
import subprocess
import threading
import traceback
from pathlib import Path
import bpy
from bpy.app.handlers import persistent
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty, CollectionProperty, PointerProperty, EnumProperty
from .catalog import detect_paths,default_storage,read_json,write_json,scan_library,merge_assets,indexed_assets,safe_level
from . import jobs, build, blender_ops, setup, map_scene, navigation, map_export, skies, geometry_export
from .diagnostics import ValidationError
from . import source_names,export_review,shader_choices,vehicles,invisible_blocks,model_parts,editable_materials,standins
from .progress import PreparationActivity
from . import games, compat, scenario_scene, original_scenery, classic_scenario, sky_export

def record_failure(error, details=None):
    global _error,_message,_reported_issues
    issues=getattr(error,'issues',None) or [str(error).strip() or type(error).__name__]
    _reported_issues=issues
    _message=(str(len(issues))+' issue(s) detected. Open diagnostic report for the complete list.')
    _error='\n\n'.join(str(i+1)+'. '+item for i,item in enumerate(issues))
    _error+='\n\nChecks stop when a dependent stage cannot run; this is every issue detected so far, not a guarantee that later compilation will pass.'
    if details:_error+='\n\nTechnical details:\n'+details
    text=bpy.data.texts.get('HaloBridge diagnostics') or bpy.data.texts.new('HaloBridge diagnostics');text.clear();text.write(_error)
    try:
        folder=Path(config(bpy.context)['cache'])/'diagnostics';folder.mkdir(parents=True,exist_ok=True)
        report=folder/('failure-'+str(time.time_ns())+'.txt');report.write_text(_error,encoding='utf-8')
        text.write('\n\nSaved report: '+str(report))
    except Exception:pass # Reporting must not hide the original failure.
    return issues

_catalogue={'version':1,'assets':[]}
_catalogue_path=None
_list_undo=[]
_list_redo=[]

def list_snapshot(context):
    s=context.scene.halo_bridge
    return dict(data=copy.deepcopy(_catalogue),path=_catalogue_path,
                checked=[a.asset_id for a in s.assets if a.checked],
                active=s.assets[s.active_index].asset_id if 0<=s.active_index<len(s.assets) else None)

def remember_list(context,before):
    after=list_snapshot(context)
    if before['data']==after['data']:return
    if _list_undo and (_list_undo[-1][1]['data']!=before['data'] or _list_undo[-1][1]['path']!=before['path']):_list_undo.clear()
    _list_undo.append((before,after));del _list_undo[:-30];_list_redo.clear()

def history_available(redo=False):
    stack=_list_redo if redo else _list_undo
    if not stack:return False
    expected=stack[-1][0 if redo else 1]
    return expected['path']==_catalogue_path and expected['data']==_catalogue
_task=None
LEVEL_PLACEHOLDER='levelname123'
SOURCE_SUMMARIES={
    'map':'.map assets: everything the game map loads, including shared objects and characters. Best for browsing and kitbashing.',
    'scenario':'.scenario assets: the level\'s own objects, built from Editing Kit source files with exact shader names. Best for editing and Sapien.',
}
_preview_generation=0
_preview_pending=None
_error=''
_message='Connect your folders, then index a map to browse its assets.'

class HBAsset(bpy.types.PropertyGroup):
    asset_id:StringProperty()
    level:StringProperty()
    category:StringProperty()
    kind:StringProperty()
    source:StringProperty(default='map')
    checked:BoolProperty(name='Select asset',description='Include this asset in actions for checked entries in the current list')
    hidden:BoolProperty(default=False)

def visibility_predicate(settings):
    query=settings.search.lower();level=settings.filter_level_selected or settings.filter_level;hidden=settings.asset_tab=='HIDDEN'
    # Resolve the stored enum number against retained entries. Normalize old
    # catalogues that used paths, .map extensions or inconsistent casing.
    raw=settings.get('filter_level')
    if not settings.filter_level_selected and isinstance(raw,int):level=next((row[0] for row in level_items(settings,None) if row[3]==raw),'__ALL__')
    level=level_key(level)
    categories={name:getattr(settings,'show_'+name,True) for name in ('vegetation','structures','materials','rocks','water')}
    source={'MAP':'map','SCENARIO':'scenario'}.get(getattr(settings,'filter_source','ALL'))
    return lambda item: (item.hidden==hidden and (level=='__ALL__' or level_key(item.level)==level)
                        and (source is None or (item.source or 'map')==source)
                        and (not query or query in (item.name+' '+item.level+' '+item.kind).lower())
                        and categories.get(item.category.lower(),True))

def row_visible(settings,item):
    return visibility_predicate(settings)(item)

_level_items=[]
_retired_level_items=[]
_level_items_token=None
def level_key(value):
    if value=='__ALL__':return value
    return str(value).strip().replace('\\','/').rsplit('/',1)[-1].lower().removesuffix('.map')
def level_items(settings,context):
    global _level_items,_level_items_token
    token=(settings.id_data.as_pointer(),len(settings.assets))
    if token==_level_items_token:return _level_items
    levels=sorted({level_key(a.level) for a in settings.assets})
    # Keep strings alive for Blender's dynamic enum callback.
    if [entry[0] for entry in _level_items[1:]]!=levels or not _level_items:
        _retired_level_items.append(_level_items)
        _level_items=[('__ALL__','All Levels','Show assets from every indexed map',0)]+[(level,level,'Show assets indexed from '+level,1+(__import__('zlib').crc32(level.encode())&0x3fffffff)) for level in levels]
    _level_items_token=token
    return _level_items

def level_filter_changed(settings,context):
    # Persist the source identifier independently of Blender's dynamic enum value.
    settings.filter_level_selected=settings.filter_level
    browsing_changed(settings,context)


def browsing_changed(settings,context):
    visible=visibility_predicate(settings)
    settings.active_index=next((i for i,item in enumerate(settings.assets) if visible(item)),-1)
    if context and context.window_manager:
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                if area.type=='VIEW_3D':area.tag_redraw()

def selection_changed(settings,context):
    global _preview_generation,_preview_pending
    if not settings.preview_enabled:return
    _preview_generation+=1
    _preview_pending=(settings.id_data.as_pointer(),_preview_generation)
    if not bpy.app.timers.is_registered(preview_tick):
        bpy.app.timers.register(preview_tick,first_interval=.05)

def preview_tick():
    global _preview_pending,_error,_message
    if _preview_pending is None:return None
    context=bpy.context
    if _preview_pending[0]!=context.scene.as_pointer() or not context.scene.halo_bridge.preview_enabled:
        _preview_pending=None;return None
    # Hide the previous asset immediately, even while an extraction finishes.
    clear_previews(context)
    if _task:return .05
    _preview_pending=None
    s=context.scene.halo_bridge
    if not 0<=s.active_index<len(s.assets) or not row_visible(s,s.assets[s.active_index]):return None
    try:bpy.ops.halo_bridge.place(preview_only=True)
    except Exception as e:
        _error=traceback.format_exc();_message=str(e).strip() or type(e).__name__
    return None

def stop_preview(context):
    global _preview_generation,_preview_pending
    context.scene.halo_bridge.preview_enabled=False
    _preview_generation+=1;_preview_pending=None
    if _task and getattr(_task,'preview_generation',None) is not None:_task.cancel.set()
    clear_previews(context)

def game_changed(settings,context):
    global _catalogue,_catalogue_path,_level_items_token
    if not context:return
    stop_preview(context)
    profiles=json.loads(settings.game_profiles or '{}')
    keys=('kit','maps','cache','map_name','scenario_path')
    profiles[settings.previous_game]={k:getattr(settings,k) for k in keys}
    # A blank storage folder would resolve against Blender's own folder.
    if not profiles[settings.previous_game]['cache']:profiles[settings.previous_game]['cache']=str(default_storage(settings.previous_game or 'halo3'))
    game=games.GAMES[settings.game]
    detected=dict(detect_paths(settings.game),map_name=game['map_name'],scenario_path=game.get('scenario',''))
    chosen=profiles.get(settings.game) or detected
    for key in keys:setattr(settings,key,chosen.get(key) or detected.get(key) or '')
    # Prepare for the game being imported when its Editing Kit supports Sapien.
    if game['sapien_enabled']:settings.export_target=settings.game
    settings.shader_choice='NONE';settings.shader_level='ALL';settings.game_profiles=json.dumps(profiles);settings.previous_game=settings.game
    _catalogue_path=None;_level_items_token=None
    _catalogue=read_json(Path(bpy.path.abspath(settings.cache))/'catalogue.json',{'version':1,'assets':[]})
    refresh(context,persist=False)


class HBSettings(bpy.types.PropertyGroup):
    game:EnumProperty(name='Import game',items=games.IMPORT_ITEMS,default='halo3',update=game_changed)
    previous_game:StringProperty(default='halo3')
    game_profiles:StringProperty(default='{}')
    kit:StringProperty(name='Halo 3 Editing Kit',subtype='DIR_PATH',description='Editing Kit folder containing tool.exe, sapien.exe, and your editable tags')
    maps:StringProperty(name='Halo 3 .map Files',subtype='DIR_PATH',description='Your installed MCC maps folder for the selected Halo game')
    library:StringProperty(name='Extracted library',subtype='DIR_PATH')
    cache:StringProperty(name='Project and cache folder',subtype='DIR_PATH',description='Stores automatically extracted assets, project records, backups, and job logs for reuse')
    scenario_path:StringProperty(name='Editing Kit scenario',default='levels\\multi\\guardian\\guardian',description='Scenario tag path relative to the Editing Kit tags folder, without .scenario. Use the adjacent dropdown to search the kit')
    map_name:StringProperty(name='Choose .map file',default='010_jungle.map',description='Type a map filename, or use the adjacent dropdown to search maps in the selected game folder')
    h2a_campaign_level:StringProperty(name='Campaign level',default='01a_tutorial.pck',description='Halo 2: Anniversary campaign level (.pck in MCC\'s halo2\\preload\\paks). Type a filename, or use the adjacent dropdown')
    level:StringProperty(name='Output Level Name (without .map)',default=LEVEL_PLACEHOLDER,description='Name for your generated level: 3–32 lowercase letters, digits, or underscores, starting with a letter. Give each level its own name')
    export_target:EnumProperty(name='Export to Sapien',items=games.SAPIEN_ITEMS,default='halo3')
    decimate_dense:BoolProperty(name='Decimate very dense objects',default=False,description='When preparing, add a Decimate modifier to every exported object over the triangle limit. The modifier stays on the object: change its Ratio per object in Modifier Properties, or remove it to restore the full mesh')
    water_shader:EnumProperty(name='Water',default=standins.DEFAULT_WATER,items=[(key,label,('Halo 3 water: '+path) if path else 'HaloBridge\'s conversion: dark still water with Halo 2\'s waves as its bump map') for key,label,path in standins.WATER_SHADERS],description='Halo 3 water shader used for Halo 2 water (pools, rivers). Halo 2 water draws its color from a reflection cube map that does not convert')
    effect_standins:BoolProperty(name='Halo 3 energy and glass',default=True,description='Halo 2 plasma fields (teleporters, grav lifts) and reflective glass use Halo 3 shaders that draw the same animated or see-through effect. Off: they are converted from their textures, which come out white or grey')
    max_texture_size:EnumProperty(name='Texture size',default='2048',items=(('512','512','Textures at most 512 pixels wide: the least storage and memory, visibly softer',3),('1024','1024','Converted textures at most 1024 pixels wide: most Halo 3 textures',0),('2048','2048','Converted textures at most 2048 pixels wide: Halo 3\'s largest textures (default)',1),('4096','4096','Converted textures at most 4096 pixels wide: the most Halo 3 Tool accepts; much more memory',2)),description='Largest size for textures converted from other games (Reach, Halo 2: Anniversary and others have 4K and 8K textures). Larger ones are scaled down')
    decimate_ratio:FloatProperty(name='Ratio',default=.5,min=.05,max=1,precision=2,description='Decimate ratio for newly added modifiers (0.5 keeps about half the triangles). Objects that already have the modifier keep their own ratio')
    decimate_threshold:IntProperty(name='Over',default=30000,min=1000,max=10000000,description='Objects with more triangles than this get the Decimate modifier')
    portal_spacing:FloatProperty(name='Every',default=40.0,min=2.0,max=2000.0,precision=1,description='Distance between +portal planes in Halo world units (Halo 3 multiplayer maps are about 50-200 units across)')
    quick_test:BoolProperty(name='Quick test compile first',default=True,description='Before the full compile, compile only the densest objects on their own, so an object Halo Tool rejects is found in minutes instead of near the end of the full compile')
    skip_invalid:BoolProperty(name='Skip objects with export problems',default=False,description='Leave out entire objects that have mesh or material problems, can\'t be converted, or that Halo Tool rejects (preparation then starts again without them). Objects stay in Blender')
    sky_choice:EnumProperty(name='(Experimental) Sky From Map',description='Choose the primary sky from any scanned Editing Kit map. Existing lightmaps and weather are not converted',items=skies.items)
    sky_selected:StringProperty(default='AUTO',description='Selected source scenario, stored independently of the scanned list')
    sky_game:EnumProperty(name='Sky game',items=skies.GAME_ITEMS,default='halo3',description='Game to take the Sapien sky from. A sky from the Sapien destination game uses its Editing Kit sky as-is; a sky from any other game is rebuilt as a converted sky object')
    sky_scenario:StringProperty(name='Sky source scenario',default='levels\\multi\\isolation\\isolation',description='Existing Editing Kit scenario whose sky references are used; no .scenario extension. Whole-map imports fill this from their source. This does not copy terrain or gameplay')
    lighting:BoolProperty(name='Generate Test Lighting for Sapien Level',default=True,description='Generate quick test lighting during Sapien preparation; turn off for faster geometry iterations')
    lighting_baker:EnumProperty(name='Lighting bake',default='TOOL',description='What bakes the lighting when Generate Test Lighting is on',
                                items=[('TOOL','Halo Tool (draft)','Tool\'s quick draft lighting on the processor: no bounced light, so shaded areas come out very dark'),
                                       ('H3LM','H3LM (graphics card)','H3LM Lightmapper by Zoephie: Halo 3 lightmaps baked on the graphics card (DirectX 12), with bounced light. Download it separately and choose its folder')])
    h3lm_path:StringProperty(name='H3LM folder',subtype='DIR_PATH',description='Folder with h3lm-lm.exe (the H3LM Lightmapper download, unzipped)')
    h3lm_quality:EnumProperty(name='H3LM quality',default='optimized',description='H3LM bake quality. Low is a fast preview; Optimized is H3LM\'s recommended setting; Ultra is for a final bake and much slower',
                              items=[('low','Low (preview)','Bungie\'s Tool "low" settings: fast preview'),('medium','Medium','Bungie\'s Tool "medium" settings'),
                                     ('high','High','Bungie\'s Tool "high" settings'),('optimized','Optimized','H3LM\'s recommended quality, between High and Super'),
                                     ('ultra','Ultra (final)','Bungie\'s Super settings doubled; much slower')])
    h2_sun_strength:FloatProperty(name='Sun',default=1.0,min=0.0,soft_max=3.0,max=10.0,description='Halo 2 sky: strength of the original sun in the lighting bake (1 = HaloBridge\'s default). Takes effect when the level is prepared again')
    h2_sky_strength:FloatProperty(name='Shade',default=1.0,min=0.0,soft_max=3.0,max=10.0,description='Halo 2 sky: strength of the light from the whole sky, which is what lights the shade and interiors (1 = HaloBridge\'s default). Raise it for lighter shadows, as in Halo 2. Takes effect when the level is prepared again')
    h2_lightmaps:BoolProperty(name='Copy Halo 2\'s original lighting',default=True,description='Halo 2 maps imported from a Halo 2 Editing Kit .scenario: copy Halo 2\'s own baked lighting (light, shadows and colour) onto the terrain instead of baking new lighting. Halo 2\'s terrain is compiled as the level structure, as in Halo 2. Objects and other pieces get Tool\'s test lighting. Needs the Halo 2 Editing Kit the level was built from')
    h2_lightmap_brightness:FloatProperty(name='Brightness',default=1.0,min=0.1,soft_max=3.0,max=10.0,description='Brightness of the copied Halo 2 lighting (1 = Halo 2\'s sunlit ground at the brightness of Bungie\'s Halo 3 multiplayer maps)')
    show_tool_markers:BoolProperty(name='Show Tool warning markers in Sapien',default=False,description='Keep Halo Tool\'s warning reports (red "overlapping surfaces" text and lines) in the level so Sapien draws them. Off: they are cleared; the preparation report still lists every warning')
    h3lm_per_pixel:BoolProperty(name='Per-pixel lighting for large pieces',default=True,description='H3LM bake: large pieces (terrain, buildings) are lit per pixel, which keeps sun shadows and avoids steps between pieces. Off: every piece keeps Tool\'s per-vertex lighting (light only at triangle corners), as Tool\'s own bake does')
    h3lm_ao:BoolProperty(name='Ambient occlusion',default=False,description='Bake ambient occlusion into the lightmap (H3LM --ao)')
    open_sapien:BoolProperty(name='Open Sapien when ready',default=False,description='Launch the prepared scenario in Sapien automatically after a successful build')
    search:StringProperty(name='Search Assets',description='Filter assets as you type by name, source map, or asset type; applies within the active tab and enabled categories',options={'TEXTEDIT_UPDATE'},update=browsing_changed)
    filter_level_selected:StringProperty(default='',options={'HIDDEN'})
    filter_level:EnumProperty(name='Level Imported',description='Filter by the .map file an asset was indexed from. Shared assets can appear in more than one map',items=level_items,update=level_filter_changed)
    filter_source:EnumProperty(name='Asset source',description='Show assets indexed from .map files, from Editing Kit .scenario tags, or both',
                               items=[('ALL','All Sources','Assets from both .map files and .scenario tags'),
                                      ('MAP','.map Assets','Assets indexed from installed .map files'),
                                      ('SCENARIO','.scenario Assets','Assets indexed from Editing Kit .scenario tags')],update=browsing_changed)
    filter_category:EnumProperty(name='Category',items=[(n,n,'') for n in ('All','Vegetation','Rocks','Structures','Water','Materials')],update=browsing_changed)
    show_vegetation:BoolProperty(name='Vegetation',default=True,update=browsing_changed)
    show_rocks:BoolProperty(name='Rocks',default=True,update=browsing_changed)
    show_structures:BoolProperty(name='Structures',default=True,update=browsing_changed)
    show_water:BoolProperty(name='Water',default=True,update=browsing_changed)
    show_materials:BoolProperty(name='Materials',default=True,update=browsing_changed)
    asset_tab:EnumProperty(name='Asset list',items=[('IMPORTED','Imported Assets','Available indexed assets; extraction happens on first use'),('HIDDEN','Hidden Assets','Hidden catalogue entries; restore them at any time')],update=browsing_changed)
    assets:CollectionProperty(type=HBAsset)
    active_index:IntProperty(default=0,update=selection_changed)
    preview_enabled:BoolProperty(default=False)
    follow_outliner:BoolProperty(name='Reveal selected asset in Outliner',default=True,description='Expand collections and scroll to the newly selected HaloBridge object in visible View Layer Outliners')
    shader_path:StringProperty(name='(Experimental) Shader Tag Path',description='Existing shader path relative to the Editing Kit tags folder, without its file extension')
    shader_choice:EnumProperty(name='Existing Halo shader',items=shader_choices.items,description='Choose an installed shader for the active Blender material; does not create a shader or change preview textures')
    shader_level:EnumProperty(name='Shader level / category',items=shader_choices.level_items,update=shader_choices.level_changed,description='Limit the shader search to a source level or shared asset category')
    shader_manual:BoolProperty(name='Enter shader path manually',default=False)
    setup:BoolProperty(name='Folders and Setup',default=True,description='Show or hide installation folders and map indexing controls')
    preview_previous_object:PointerProperty(type=bpy.types.Object)
    preview_object:PointerProperty(type=bpy.types.Object)
    import_sky:BoolProperty(name='Import sky',default=True,description='Include the level\'s sky objects when importing a .scenario or an entire .map. Off: import the rest of the level without its sky; preparation then uses the Sapien Sky setting')
    advanced:BoolProperty(name='Advanced storage',default=False,description='Choose where cached assets and project records are stored; keep the existing folder when continuing a level')

def config(context):
    s=context.scene.halo_bridge
    # Keep saved project locations; new scenes use managed storage automatically.
    if not s.cache:s.cache=str(default_storage(s.game or 'halo3'))
    result={n:getattr(s,n) for n in ('game','kit','maps','library','cache','level','lighting','sky_scenario')}
    for n in ('kit','maps','library','cache'):result[n]=bpy.path.abspath(result[n])
    result['skip_invalid']=s.skip_invalid;result['quick_test']=s.quick_test;result['export_target']=s.export_target
    result['lighting_baker']=s.lighting_baker;result['h3lm_path']=bpy.path.abspath(s.h3lm_path) if s.h3lm_path else ''
    result['h3lm_quality']=s.h3lm_quality;result['h3lm_ao']=s.h3lm_ao
    result['h2_sun_strength']=s.h2_sun_strength;result['h2_sky_strength']=s.h2_sky_strength
    result['show_tool_markers']=s.show_tool_markers;result['h3lm_per_pixel']=s.h3lm_per_pixel
    result['h2_lightmaps']=s.h2_lightmaps;result['h2_lightmap_brightness']=s.h2_lightmap_brightness
    result['max_texture_size']=int(s.max_texture_size)
    result['water_shader']=s.water_shader;result['effect_standins']=s.effect_standins
    if s.sky_selected!='AUTO':result['sky_scenario']=s.sky_selected
    elif s.sky_choice and s.sky_choice!='AUTO':result['sky_scenario']=s.sky_choice
    # "Original map / default sky": an imported map's own sky is converted when its game differs.
    result['sky_auto']=s.sky_selected=='AUTO' and (not s.sky_choice or s.sky_choice=='AUTO')
    return result

def export_config(context):
    result=config(context);target=games.destination(context.scene.halo_bridge)
    if not games.GAMES[target.game]['sapien_enabled']:
        raise RuntimeError('Sapien export for '+games.GAMES[target.game]['label']+' is not implemented. Choose Halo 3 to prepare mixed-game assets.')
    settings=context.scene.halo_bridge
    result['source_kits']={key:bpy.path.abspath(kit) for key,kit in games.source_kits(settings).items()}
    result['reach_collision_kit']=result['source_kits'].get('reach','')
    result.update(game=target.game,kit=bpy.path.abspath(target.kit),maps=bpy.path.abspath(target.maps),cache=bpy.path.abspath(target.cache))
    # Another game's default sky scenario does not exist in this kit; use this game's default.
    defaults={g.get('sky') for key,g in games.GAMES.items() if key!=target.game and g.get('sky')}
    if result.get('sky_scenario') in defaults and games.GAMES[target.game].get('sky'):
        result['sky_scenario']=games.GAMES[target.game]['sky']
    result['sky_mode']='kit' if skies.kit_sky(settings) else 'object'
    result['default_sky']=games.GAMES[target.game].get('sky','')
    return result


def ensure_catalogue(context,force=False):
    global _catalogue,_catalogue_path
    folder=context.scene.halo_bridge.cache
    path=str(Path(bpy.path.abspath(folder)).resolve()/'catalogue.json') if folder else None
    if force or path!=_catalogue_path or not _catalogue.get('assets'):
        data=read_json(path) if path else None
        if not isinstance(data,dict) or not isinstance(data.get('assets'),list):
            raise RuntimeError('The saved asset catalogue is missing. Click Detect folders, then Index map. Expected catalogue: '+str(path))
        _catalogue=data;_catalogue_path=path
    return _catalogue

def selected(context):
    s=context.scene.halo_bridge
    if not 0<=s.active_index<len(s.assets):raise RuntimeError('Select an asset first.')
    if not row_visible(s,s.assets[s.active_index]):raise RuntimeError('Select an asset in the current list first.')
    asset_id=s.assets[s.active_index].asset_id
    for force in (False,True):
        data=ensure_catalogue(context,force)
        asset=next((a for a in data['assets'] if a.get('id')==asset_id),None)
        if asset:return asset
    raise RuntimeError('This asset is no longer in the catalogue. Click Detect folders to reload the list, then select the asset again.')

def refresh(context,persist=True):
    global _catalogue_path,_level_items_token
    s=context.scene.halo_bridge
    previous_level=s.filter_level
    previous=s.assets[s.active_index].asset_id if 0<=s.active_index<len(s.assets) else None
    checked={a.asset_id for a in s.assets if a.checked}
    s.assets.clear()
    for a in _catalogue['assets']:
        row=s.assets.add();row.name=a['name'];row.asset_id=a['id'];row.level=a['level'];row.category=a['category'];row.kind=a['kind'];row.source=a.get('source','map')
        row.hidden=bool(a.get('hidden',False));row.checked=a['id'] in checked
    _level_items_token=None
    if previous_level!='__ALL__' and level_key(previous_level) not in {level_key(a.level) for a in s.assets}:s.filter_level='__ALL__'
    predicate=visibility_predicate(s)
    visible=[i for i,a in enumerate(s.assets) if predicate(a)]
    s.active_index=next((i for i in visible if s.assets[i].asset_id==previous),visible[0] if visible else -1)
    _catalogue_path=str(Path(bpy.path.abspath(s.cache)).resolve()/'catalogue.json') if s.cache else None
    if persist and _catalogue_path:write_json(_catalogue_path,_catalogue)

def reconcile_preview_copies(context):
    """A copied flag does not make a pasted object our disposable preview."""
    owners={s.halo_bridge.preview_object for s in bpy.data.scenes if s.halo_bridge.preview_object}
    selected_copies=[]
    for obj in context.scene.objects:
        if obj.get('hb_preview') and obj not in owners:
            del obj['hb_preview']
            obj['hb_ignore']=False;obj.hide_render=False
            obj['hb_id']=blender_ops.new_id()
            if obj.name.startswith('[Preview] '):obj.name=obj.name[len('[Preview] '):]
            if obj.select_get():selected_copies.append(obj)
    if selected_copies:
        for owner in owners:
            if owner.name in context.view_layer.objects:owner.select_set(False)
        context.view_layer.objects.active=selected_copies[-1]
    repair_paste_active(context)


def repair_paste_active(context):
    """Native paste can leave an unselected source active (including its gizmo)."""
    active=context.active_object
    if not active or active.select_get() or not active.get('hb_id'):return
    copies=[obj for obj in context.selected_objects
            if obj!=active and obj.get('hb_id')==active.get('hb_id')]
    if copies:
        context.view_layer.objects.active=copies[-1]
        for obj in copies:obj['hb_id']=blender_ops.new_id()


@persistent
def paste_selection_updated(scene,depsgraph):
    # Selection-only fix is cheap and runs before the next interactive transform.
    # Do not change an intentional multi-selection or scan all scene geometry.
    if bpy.context.scene==scene:repair_paste_active(bpy.context)


_preview_check_token=None
def check_preview_copies():
    global _preview_check_token
    context=bpy.context
    if not context.scene or not hasattr(context.scene,'halo_bridge'):return .25
    active=context.active_object;owner=context.scene.halo_bridge.preview_object
    token=(context.scene.as_pointer(),len(context.scene.objects),active.as_pointer() if active else 0,owner.as_pointer() if owner else 0)
    if token!=_preview_check_token:
        reconcile_preview_copies(context);_preview_check_token=token
    return .25


def clear_previews(context,keep=None):
    s=context.scene.halo_bridge
    reconcile_preview_copies(context)
    obj=s.preview_object
    restore=bool(obj and context.active_object==obj and obj!=keep)
    if obj and obj!=keep:
        s.preview_object=None
        mesh=obj.data;bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
    if keep is None:
        previous=s.preview_previous_object
        if restore and previous and previous.name in context.view_layer.objects:
            previous.select_set(True)
            context.view_layer.objects.active=previous
        s.preview_previous_object=None

def preview_active(context):
    return any(obj.get('hb_preview') for obj in context.scene.objects)

def show_preview(context,obj,name):
    clear_previews(context,keep=obj)
    context.scene.halo_bridge.preview_object=obj
    obj['hb_preview']=True;obj['hb_ignore']=True;obj.hide_render=True
    # Center only the disposable preview mesh; cached and placed meshes stay unchanged.
    original_mesh=obj.data;obj.data=original_mesh.copy()
    obj.data.use_fake_user=False
    if original_mesh.users==0:bpy.data.meshes.remove(original_mesh)
    map_scene.center_mesh_origin(obj.data)
    obj.matrix_world.translation=context.scene.cursor.location
    obj.name='[Preview] '+name
    if obj.get('hb_parts_path'):obj['hb_parts_signature']=blender_ops.mesh_signature(obj.data)

class HBTask:
    def __init__(self,fn,done):
        self.done_callback=done;self.cancel=threading.Event();self.result=None;self.error=None;self.finished=False
        self.scene=bpy.context.scene.as_pointer()
        def run():
            try:self.result=fn(self.cancel)
            except Exception as error:self.error=error;self.traceback=traceback.format_exc()
            finally:self.finished=True
        self.thread=threading.Thread(target=run,daemon=True);self.thread.start()

_box_retry=0
MAX_COLLISION_RETRIES=12
COLLISION_ERRORS=r'\(object (.+?)\) (?:bad connections - \d+ ambiguous|degenerate collision edge|bad connections|collision geometry is too large|### ASSERTION FAILED:.*plane_builder)'
# Tool crashes in its plane builder when it combines some objects' render and collision
# (seen on Halo 2: Anniversary pieces placed more than once); a simpler collision avoids it.
PLANE_BUILDER_CRASH=r'\(object (.+?)\) ### ASSERTION FAILED:.*plane_builder'

def next_collision_fallback(current,had_original=True):
    """Collision to try after Tool rejected an object's (original collision or its
    plain mesh surfaces): its own surfaces cleaned for Tool, then a simple box as a
    last resort, then none."""
    if not current:return 'clean'
    return {'clean':'box'}.get(current,'none')

PORTAL_ATTEMPTS=3
RETRY_SETTINGS=('hb_portal_attempt','hb_portals_failed','hb_cluster_scale')
_retrying=False

def _prepare_again():
    """Prepare again after a Tool failure, keeping the retry settings (RETRY_SETTINGS) that a new
    preparation started by the user clears."""
    global _retrying
    _retrying=True
    try:bpy.ops.halo_bridge.prepare('EXEC_DEFAULT',warnings_accepted=True)
    finally:_retrying=False

def retry_with_shifted_portals(error):
    """Tool could not build its leaf map from the automatic portal planes ("couldn't build leaf map
    during portalization": Burial Mounds, Cyclotron, Zanzibar). Whether a set of cuts works depends
    on the geometry they cross, so prepare again with the cuts moved (geometry_export reads the
    attempt), up to PORTAL_ATTEMPTS times."""
    text='\n'.join(str(i) for i in (getattr(error,'issues',None) or [str(error)]))
    if 'leaf map during portalization' not in text:return False
    scene=bpy.context.scene;attempt=int(scene.get('hb_portal_attempt',0))
    if scene.get('hb_portals_failed'):
        return False  # already compiling without portals
    if attempt>=PORTAL_ATTEMPTS:
        # Last resort: no portals; the structure is made to fit one cluster (geometry_export).
        scene['hb_portal_attempt']=0;scene['hb_portals_failed']=True
        prepare_status('Tool could not portalize this level; compiling it as one cluster with its biggest pieces instanced...')
    else:
        scene['hb_portal_attempt']=attempt+1
        prepare_status('Tool could not use the automatic portal planes here; moving them and compiling again ('+str(attempt+1)+' of '+str(PORTAL_ATTEMPTS)+')...')
    try:_prepare_again()
    except Exception:return False
    return _task is not None

CLUSTER_SCALES=(0.6,0.35,0.2)

def retry_with_smaller_clusters(error):
    """Tool found a cluster with more than Halo 3's 32,767 vertices per section ("section 'cluster
    0' has too many vertices": Warlock compiled as one cluster still had 34,208). Triangles are
    only an estimate of Tool's vertices, so prepare again aiming for smaller clusters
    (hb_cluster_scale, read by geometry_export), up to len(CLUSTER_SCALES) times."""
    text='\n'.join(str(i) for i in (getattr(error,'issues',None) or [str(error)]))
    if 'has too many vertices' not in text:return False
    scene=bpy.context.scene;scale=float(scene.get('hb_cluster_scale',1.0))
    smaller=[s for s in CLUSTER_SCALES if s<scale-1e-6]
    if not smaller:return False
    scene['hb_cluster_scale']=smaller[0]
    prepare_status('A cluster had more vertices than Halo 3 allows; compiling again with smaller clusters ('+format(smaller[0],'.0%')+' of the usual size)...')
    try:_prepare_again()
    except Exception:return False
    return _task is not None

def retry_with_box_collision(error):
    """Tool rejected the collision of specific imported objects.

    Collision taken from another game (or its render mesh) can contain pieces
    Tool welds into ambiguous or degenerate edges. Step only those objects down:
    original collision -> cleaned mesh surfaces -> simple box -> render only (no collision), remembered
    on the object as hb_collision_fallback, and compile again. Tool stops at the
    first rejected object, so for games without original collision every piece
    of that game is cleaned in the same round.
    """
    global _box_retry
    if _box_retry>=MAX_COLLISION_RETRIES:
        _box_retry=0;return False
    marked=mark_collision_fallbacks(error)
    handled={o.name for o in marked[0]} if marked else set()
    # With Skip objects with export problems on, any other object Tool rejects is left
    # out of the next attempt instead of failing the build.
    settings=getattr(bpy.context.scene,'halo_bridge',None)
    skipped=mark_tool_rejections(error,handled) if settings and settings.skip_invalid else []
    if not marked and not skipped:
        _box_retry=0;return False
    if marked:
        objects,others=marked
        prepare_status('Tool rejected the collision of '+', '.join(o.name for o in objects[:5])+('; their surfaces, and those of '+str(len(others))+' other imported piece(s) from the same game, are cleaned for Tool' if others else '; recompiling with simpler collision')+'. Compiling again...')
    if skipped:
        prepare_status('Tool rejected '+', '.join(o.name+' ('+o['hb_tool_rejected']+')' for o in skipped[:5])+(' and '+str(len(skipped)-5)+' more' if len(skipped)>5 else '')
                       +'. Skip objects with export problems is on, so '+('it is' if len(skipped)==1 else 'they are')+' left out. Preparing again...')
    _box_retry+=1
    try:_prepare_again()
    except Exception:
        _box_retry=0;return False
    return _task is not None

def mark_tool_rejections(error,handled=()):
    """Remember the objects Tool stopped on, so the next preparation skips them (until they
    change). Returns those objects; [] when the error names no object in this scene."""
    import re
    from .export_review import shape
    text='\n'.join(str(i) for i in (getattr(error,'issues',None) or [str(error)]))
    fatal=set();reasons={}
    for match in re.finditer(r'\(object (.+?)\) ([^\n]+)',text):
        name,message=match.group(1),match.group(2).strip()
        if 'Instance had fatal error' in message:fatal.add(name)
        elif 'ASSERTION FAILED' in message:
            # Tool crashed while building this object (the whole compile stops).
            fatal.add(name);reasons[name]='Halo Tool crashed while building it: '+message.split(' at ')[-1].split('\\')[-1]
        elif 'FATAL ERROR' not in message:reasons.setdefault(name,message)
    targets=(fatal or set(reasons))-set(handled)
    objects=[o for o in (bpy.context.scene.objects.get(name) for name in sorted(targets)) if o and o.type=='MESH']
    depsgraph=bpy.context.evaluated_depsgraph_get()
    for obj in objects:
        evaluated=obj.evaluated_get(depsgraph);mesh=evaluated.to_mesh(preserve_all_data_layers=True,depsgraph=depsgraph)
        try:obj['hb_tool_rejected_shape']=shape(mesh)
        finally:evaluated.to_mesh_clear()
        obj['hb_tool_rejected']=reasons.get(obj.name,'Tool stopped on this object')
    return objects

def tool_rejected(scene):
    return [o for o in scene.objects if o.get('hb_tool_rejected')]

def mark_collision_fallbacks(error):
    """Step the collision of the objects Tool rejected (and their same-game siblings) down
    one level. Returns (rejected objects, siblings), or None when the error isn't one of these."""
    import re
    text='\n'.join(str(i) for i in (getattr(error,'issues',None) or [str(error)]))
    names={m.group(1) for m in re.finditer(COLLISION_ERRORS,text)}
    if not names and re.search(r'-ERROR- (?:degenerate collision edge|bad connections)|ASSERTION FAILED:.*plane_builder',text):
        # The error is in the level structure itself (Halo 2 terrain compiled as one structure;
        # Containment: "degenerate collision edge"), which Tool doesn't name: step every imported
        # structure piece's collision down together - cleaned surfaces, then welded harder.
        from .geometry_export import CLEAN_DISTANCE,H2_STRUCTURE_COLLECTIONS
        pieces=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.get('hb_map_reference') and getattr(o,'hb_static_collision','AUTO')=='AUTO'
                and any(c.name.split('.')[0] in H2_STRUCTURE_COLLECTIONS for c in o.users_collection)]
        if not pieces:return None
        changed=[]
        for obj in pieces:
            weld=float(obj.get('hb_collision_weld',CLEAN_DISTANCE))
            if obj.get('hb_collision_fallback') is None:obj['hb_collision_fallback']='clean';changed.append(obj)
            elif obj.get('hb_collision_fallback')=='clean' and weld<CLEAN_DISTANCE*16:obj['hb_collision_weld']=weld*4;changed.append(obj)
        return (changed,[]) if changed else None
    objects=[o for name in names for o in [bpy.context.scene.objects.get(name)]
             if o and o.get('hb_source_tag') and o.get('hb_collision_fallback')!='none' and getattr(o,'hb_static_collision','AUTO')=='AUTO']
    if not objects or len(objects)!=len(names):return None
    from .original_collision import COLLISION_GAMES
    from .geometry_export import COLLISION_TRIANGLE_LIMIT
    too_large={m.group(1) for m in re.finditer(r'\(object (.+?)\) collision geometry is too large',text)}
    crashed={m.group(1) for m in re.finditer(PLANE_BUILDER_CRASH,text)}
    from .geometry_export import CLEAN_DISTANCE
    for obj in objects:
        if obj.name in crashed:
            # Welding more rarely helps a crash: cleaned surfaces, then a box, then none.
            obj['hb_collision_fallback']=next_collision_fallback(obj.get('hb_collision_fallback'))
            continue
        limit=int(obj.get('hb_collision_triangles',COLLISION_TRIANGLE_LIMIT))
        if obj.name in too_large and obj.get('hb_collision_fallback') in (None,'clean') and limit>2500:
            # Already simplified automatically (or cleaned) and still too dense for Tool:
            # simplify further rather than falling back to a box.
            obj['hb_collision_fallback']='clean';obj['hb_collision_triangles']=limit//2
            continue
        weld=float(obj.get('hb_collision_weld',CLEAN_DISTANCE))
        if obj.get('hb_collision_fallback')=='clean' and weld<CLEAN_DISTANCE*16:
            # Cleaned surfaces still had broken edges: weld more before trying a box.
            obj['hb_collision_weld']=weld*4
            continue
        obj['hb_collision_fallback']=next_collision_fallback(obj.get('hb_collision_fallback'),obj.get('hb_game','halo3') in COLLISION_GAMES)
    # Tool names only the first rejected object per compile. Pieces from games without
    # original collision (Halo CE, Halo 2, Halo 2: Anniversary) tend to share the
    # problem, so all of that game's imported pieces get cleaned surfaces in this round.
    # (Only for broken edges; one oversized piece says nothing about the others.)
    games_hit={o.get('hb_game','halo3') for o in objects if o.name not in too_large|crashed}-set(COLLISION_GAMES)
    def exported(o):  # imported map pieces are flagged hb_ignore but still exported
        return o.get('hb_map_reference') or not o.get('hb_ignore')
    others=[o for o in bpy.context.scene.objects if o.type=='MESH' and o.get('hb_source_tag') and exported(o)
            and not o.get('hb_collision_fallback') and o.get('hb_game','halo3') in games_hit
            and getattr(o,'hb_static_collision','AUTO')=='AUTO']
    for obj in others:obj['hb_collision_fallback']='clean'
    return objects,others

def start(context,fn,done,message,undo=False):
    global _task,_message,_error
    if _task:raise RuntimeError('Wait for the current job or cancel it.')
    _error='';_message=message;_task=HBTask(fn,done);_task.undo=undo
    if not bpy.app.timers.is_registered(poll):bpy.app.timers.register(poll,first_interval=.2)

def poll():
    global _task,_error,_message
    if not _task:return None
    sync_activity_texts()
    if bpy.context.scene.as_pointer()!=_task.scene:_task.cancel.set()
    if _task.finished:
        task=_task;_task=None
        try:
            generation=getattr(task,'preview_generation',None)
            if generation is not None and (generation!=_preview_generation or not bpy.context.scene.halo_bridge.preview_enabled):
                return None
            if task.error:raise task.error
            if task.cancel.is_set():raise jobs.Cancelled('Job cancelled; no new placements were applied.')
            if bpy.context.scene.as_pointer()!=task.scene:raise RuntimeError('The active scene changed during the job. Its result was not applied to this scene.')
            if getattr(task,'undo',False):
                global _apply_task
                _apply_task=task
                try:bpy.ops.halo_bridge.apply_extracted('EXEC_DEFAULT',True)
                finally:_apply_task=None
                return None
            if not hasattr(task,'application'):
                result=task.done_callback(task.result)
                if hasattr(result,'__next__'):task.application=result
            if hasattr(task,'application'):
                next(task.application)
                deadline=time.perf_counter()+getattr(task,'application_budget',0)
                while getattr(task,'application_budget',0) and time.perf_counter()<deadline:
                    if task.cancel.is_set():raise jobs.Cancelled('Import cancelled.')
                    next(task.application)
                _task=task
                for area in bpy.context.screen.areas if bpy.context.screen else []:area.tag_redraw()
                return .01
        except StopIteration:pass
        except Exception as e:
            if getattr(task,'is_prepare',False) and (retry_with_shifted_portals(e) or retry_with_smaller_clusters(e) or retry_with_box_collision(e)):
                return .2 if _task else None
            if getattr(task,'is_prepare',False):prepare_status(('Preparation cancelled.' if isinstance(e,jobs.Cancelled) else 'Preparation failed: '+(str(e).strip() or type(e).__name__).splitlines()[0]))
            if hasattr(task,'application'):task.application.close()
            record_failure(e,getattr(task,'traceback',None) or traceback.format_exc())
            bpy.ops.halo_bridge.report_diagnostics()
        for area in bpy.context.screen.areas if bpy.context.screen else []:area.tag_redraw()
        sync_activity_texts()
        return .2 if _task else None
    for area in bpy.context.screen.areas if bpy.context.screen else []:area.tag_redraw()
    return .2

_apply_task=None

class HBApplyExtracted(bpy.types.Operator):
    bl_idname='halo_bridge.apply_extracted';bl_label='Place HaloBridge assets'
    bl_description='Commit extracted assets as one undoable scene change'
    bl_options={'INTERNAL','UNDO'}
    def execute(self,context):
        task=_apply_task
        if task is None:return {'CANCELLED'}
        result=task.done_callback(task.result)
        if hasattr(result,'__next__'):
            for _ in result:pass
        context.view_layer.update()
        return {'FINISHED'}

@persistent
def cancel_before_history(_=None):
    # Undo replaces RNA datablocks. Never call a closure holding the old objects.
    global _task,_preview_pending,_preview_generation
    _preview_generation+=1;_preview_pending=None
    if _task:
        _task.cancel.set()
        if getattr(_task,'is_prepare',False):prepare_status('Preparation cancelled by Undo/Redo.')
        if hasattr(_task,'application'):_task.application.close()
        _task=None

class Guard:
    def execute(self,context):
        global _error,_message
        try:
            if _task:raise RuntimeError('A HaloBridge job is running. Wait or cancel it first.')
            return self.run(context) or {'FINISHED'}
        except Exception as e:
            # Registered operator instances can expose the RNA-style identifier
            # HALO_BRIDGE_OT_prepare instead of the Python dotted identifier.
            operator_id=self.bl_idname.lower().replace('_ot_','.')
            if operator_id in {'halo_bridge.prepare','halo_bridge.confirm_prepare'} and _task is None:
                global _pending_prepare_warning
                _pending_prepare_warning=None
                prepare_status('Preparation stopped: '+(str(e).strip() or type(e).__name__).splitlines()[0]+' Fix the issues or review exclusions, then prepare again.')
            issues=record_failure(e,traceback.format_exc())
            for issue in issues:self.report({'WARNING'},issue)
            self.report({'ERROR'},_message);return {'CANCELLED'}

class HBDetect(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.detect';bl_label='Detect folders'
    bl_description='Find the selected game Editing Kit and MCC maps and reload its saved asset list'
    def run(self,context):
        global _catalogue,_message
        s=context.scene.halo_bridge
        for key,value in detect_paths(s.game).items():
            if key=='library':continue  # Legacy exports are optional, not part of setup.
            if not getattr(s,key):setattr(s,key,value)
        _catalogue=read_json(Path(bpy.path.abspath(s.cache))/'catalogue.json',{'version':1,'assets':[]});refresh(context,persist=False);_message='Folders detected. Index a map to browse its assets.'

class HBCheckSetup(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.check_setup';bl_label='Check setup'
    bl_description='Check Blender, Halo tools, required tags, helper programs and .NET runtimes; show instructions for missing components'
    def run(self,context):
        global _message,_error
        issues=setup.check(config(context),Path(__file__).parent)
        if bpy.app.version<(4,0,0):issues.append('HaloBridge needs Blender 4.0 or newer (4.0 and 5.2 are the tested targets).')
        try:blender_ops.ensure_exporter()
        except Exception as e:issues.append(str(e))
        if sys.version_info>=(3,13) and compat.toolset_frame_hack():
            issues.append('This Halo Asset Blender Development Toolset release cannot export on Blender '+'.'.join(map(str,bpy.app.version[:2]))+' (Python 3.13). Install the current General-101 release (v432 or newer).')
        text=bpy.data.texts.get('HaloBridge diagnostics') or bpy.data.texts.new('HaloBridge diagnostics')
        text.clear();text.write('\n\n'.join(issues) if issues else 'Setup checks passed. Index a map to begin.')
        _error='\n'.join(issues)
        _message=(str(len(issues))+' setup items need attention. Open the diagnostic report.') if issues else 'Setup checks passed. Index a map to begin.'

class HBScan(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.scan';bl_label='Scan extracted library'
    bl_description='Legacy import: catalogue previously exported AMF and JMS files; unnecessary for direct Halo 3 map browsing'
    def run(self,context):
        cfg=config(context)
        if not Path(cfg['library']).is_dir():raise RuntimeError('Choose your extracted library folder.')
        base=read_json(Path(cfg['cache'])/'catalogue.json',{'version':1,'assets':[]})
        def done(result):
            global _catalogue,_message
            before=list_snapshot(context);before['data']=copy.deepcopy(base);before['path']=str((Path(cfg['cache'])/'catalogue.json').resolve())
            _catalogue=merge_assets(base,result['assets']);refresh(context);remember_list(context,before);_message=f"Found {len(result['assets'])} extracted models."
        start(context,lambda cancel:scan_library(cfg['library']),done,'Scanning existing models and textures…')

_map_file_items=[]
_map_file_retired=[]


def refresh_map_files(context):
    global _map_file_items
    folder=Path(bpy.path.abspath(context.scene.halo_bridge.maps))
    if not context.scene.halo_bridge.maps or not folder.is_dir():
        raise RuntimeError('Choose the selected game .map Files folder first, or type a filename manually.')
    names=sorted((p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower()=='.map'),key=str.casefold)
    if not names:raise RuntimeError('No .map files found in '+str(folder)+'. Check the folder or type a filename manually.')
    _map_file_retired.append(_map_file_items)
    _map_file_items=[(name,name,'Use '+name,index) for index,name in enumerate(names)]
    return _map_file_items


class HBChooseMap(bpy.types.Operator):
    bl_idname='halo_bridge.choose_map';bl_label='Choose .map file'
    bl_description='Search .map files in the selected game folder; choosing one fills the editable filename without importing'
    bl_property='choice'
    choice:EnumProperty(items=lambda self,context:_map_file_items)
    @classmethod
    def poll(cls,context):return _task is None
    def invoke(self,context,event):
        try:refresh_map_files(context)
        except (OSError,RuntimeError) as error:
            self.report({'WARNING'},str(error));return {'CANCELLED'}
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}
    def execute(self,context):
        if self.choice not in {item[0] for item in _map_file_items}:return {'CANCELLED'}
        context.scene.halo_bridge.map_name=self.choice
        return {'FINISHED'}


class HBIndex(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.index';bl_label='Index .map Assets'
    bl_description='List every asset the chosen .map loads (including shared objects, weapons and characters) in the Indexed Asset List; models and textures are extracted and cached when first used'
    def run(self,context):
        cfg=config(context);s=context.scene.halo_bridge;mp=Path(cfg['maps'])/s.map_name
        if not mp.is_file():raise RuntimeError('Choose an existing .map file for the selected game.')
        base=read_json(Path(cfg['cache'])/'catalogue.json',{'version':1,'assets':[]})
        out=Path(cfg['cache'])/'indexes'/(mp.stem+'.json');out.parent.mkdir(parents=True,exist_ok=True)
        def done(result):
            global _catalogue,_message
            before=list_snapshot(context);before['data']=copy.deepcopy(base);before['path']=str((Path(cfg['cache'])/'catalogue.json').resolve())
            _catalogue=merge_assets(base,indexed_assets(result));refresh(context);remember_list(context,before);_message=f"Indexed {len(result['assets'])} assets from {mp.stem}."
            if result.get('warnings'):
                report=bpy.data.texts.get('HaloBridge index report') or bpy.data.texts.new('HaloBridge index report')
                report.clear();report.write('\n'.join(result['warnings']))
                _message+=f" {len(result['warnings'])} omissions; see HaloBridge index report in the Text Editor."
        start(context,lambda cancel:jobs.helper('extractor',dict(operation='index',game=cfg['game'],map=str(mp),output=str(out)),Path(cfg['cache'])/'jobs',cancel),done,'Reading map asset index…')


class HBIndexH2ACampaign(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.index_h2a_campaign';bl_label='Index All Individual Assets'
    bl_description=('List every Halo 2: Anniversary campaign prop, weapon, character and vehicle model (1,000+) and texture '
                    'material (2,000+) in the Indexed Asset List. Each is extracted and cached the first time it is '
                    'previewed or placed. Models are static: skinned ones come in their rest pose without animation')
    def run(self,context):
        cfg=config(context)
        base=read_json(Path(cfg['cache'])/'catalogue.json',{'version':1,'assets':[]})
        out=Path(cfg['cache'])/'indexes'/'h2a_campaign.json';out.parent.mkdir(parents=True,exist_ok=True)
        def done(result):
            global _catalogue,_message
            before=list_snapshot(context);before['data']=copy.deepcopy(base);before['path']=str((Path(cfg['cache'])/'catalogue.json').resolve())
            assets=indexed_assets(result)
            for asset in assets:
                asset['source']='h2a_campaign';asset['level']='H2A campaign'
                if asset.get('note'):asset['status']=asset['note']
            _catalogue=merge_assets(base,assets);refresh(context);remember_list(context,before)
            models=sum(1 for a in assets if a['kind']=='model')
            _message=f"Indexed {models} Anniversary campaign models and {len(assets)-models} materials."
            if result.get('warnings'):
                report=bpy.data.texts.get('HaloBridge index report') or bpy.data.texts.new('HaloBridge index report')
                report.clear();report.write('\n'.join(result['warnings']))
                _message+=f" {len(result['warnings'])} omissions; see HaloBridge index report in the Text Editor."
        start(context,lambda cancel:jobs.index_h2a_campaign(cfg,out,cancel),done,'Indexing Anniversary campaign assets (about a minute and a half)…')

def replacement_target(context,asset):
    targets=[o for o in context.selected_objects if not o.get('hb_preview')]
    if not targets and context.active_object and context.active_object.get('hb_preview'):
        previous=context.scene.halo_bridge.preview_previous_object
        if previous and not previous.get('hb_preview'):targets=[previous]
    if not targets:return [],'Select one or more objects in the 3D View first.'
    if context.mode!='OBJECT':return [],'Switch to Object Mode before swapping objects.'
    if any(o.library or o.override_library for o in targets):return [],'Selected objects must be editable; make linked objects local first.'
    if asset['kind'] not in ('instance','scenery','model','legacy'):
        return [],'Choose a geometry asset; materials cannot replace objects.'
    return targets,''


def swap_objects(context,targets,asset,path,cfg):
    # Build every replacement before removing any original, so import errors
    # leave the greybox intact. Snapshot transforms before parenting changes.
    from mathutils import Matrix
    snapshots=[(o,o.matrix_world.copy(),list(o.users_collection),o.parent,
                [(child,child.matrix_world.copy()) for child in o.children]) for o in targets]
    before=set(bpy.data.objects);created={};active=context.active_object
    try:
        for old,matrix,collections,parent,children in snapshots:
            obj=blender_ops.place(asset,path,cfg);created[old]=obj;obj.asset_mark()
            location,rotation,_=matrix.decompose()
            obj.matrix_world=Matrix.LocRotScale(location,rotation,obj.scale.copy())
            if old.get('hb_id'):obj['hb_id']=old['hb_id']
            for col in collections:
                if obj.name not in col.objects:col.objects.link(obj)
            for col in list(obj.users_collection):
                if col not in collections:col.objects.unlink(obj)
    except Exception:
        for obj in set(bpy.data.objects)-before:bpy.data.objects.remove(obj,do_unlink=True)
        for old in targets:old.select_set(True)
        context.view_layer.objects.active=active
        raise
    for old,matrix,collections,parent,children in snapshots:
        obj=created[old];world=obj.matrix_world.copy()
        obj.parent=created.get(parent,parent);obj.matrix_world=world
        for child,world in children:
            if child not in created:child.parent=obj;child.matrix_world=world
        for entry in _catalogue['assets']:
            if entry['id']==old.get('hb_asset_id') and entry['kind']=='legacy':entry['mapping']=dict(asset)
    for old in targets:bpy.data.objects.remove(old,do_unlink=True)
    for obj in context.selected_objects:obj.select_set(False)
    for obj in created.values():obj.select_set(True)
    context.view_layer.objects.active=created.get(active,next(iter(created.values())))
    refresh(context)
    return list(created.values())

class HBPlace(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.place';bl_label='Place asset(s)'
    bl_description='Place the selected asset, keeping its preview position, rotation and scale; materials are loaded separately without changing existing objects'
    apply_material:BoolProperty(default=False)
    preview_only:BoolProperty(default=False)
    replace_selected:BoolProperty(default=False)
    @classmethod
    def description(cls,context,properties):
        if properties.replace_selected:
            return 'Swap all selected 3D View objects, including greybox cubes, for the highlighted asset; keep positions, rotations and collections, using the original asset import scale. Mesh edits and modifiers are replaced'
        if properties.preview_only:
            return 'Show a temporary preview of this asset; previews are excluded from level export'
        return cls.bl_description+'; checked entries take priority, otherwise uses the highlighted entry; turns Preview Mode off'
    def run(self,context):
        if not self.preview_only and not self.replace_selected and not self.apply_material and checked_ids(context):
            return bpy.ops.halo_bridge.place_checked()
        asset=selected(context);cfg=config(context)
        # Blender frees the operator RNA after execute returns; worker callbacks
        # must retain plain values, never properties on self.
        preview_only=bool(self.preview_only);apply_material=bool(self.apply_material)
        if asset['game']!=cfg['game']:raise RuntimeError('Choose an asset indexed for the selected Halo game.')
        targets=[]
        if self.replace_selected:
            targets,reason=replacement_target(context,asset)
            if reason:raise RuntimeError(reason)
        preview_matrix=None;preview_parts=None;preview_center=None
        if not preview_only and not self.replace_selected and asset['kind']!='material':
            preview=next((obj for obj in context.scene.objects
                          if obj.get('hb_preview') and obj.get('hb_asset_id')==asset['id']),None)
            if preview:
                # Retain a value copy before stop_preview removes its object.
                context.view_layer.update()
                preview_matrix=preview.matrix_world.copy()
                if preview.get('hb_parts_path'):
                    preview_parts=model_parts.enabled(preview)
                    preview_center=list(preview.data.get('hb_origin_center',(0,0,0)))
        if preview_only:
            context.scene.halo_bridge.preview_enabled=True
            active=context.active_object
            if not preview_active(context) or (active and not active.get('hb_preview')):
                context.scene.halo_bridge.preview_previous_object=active
        else:
            stop_preview(context)
        target=context.active_object
        if asset['kind']=='material' and apply_material and (not target or target.type!='MESH'):
            raise RuntimeError('Select a mesh to apply this material to, or click Preview.')
        if asset['kind']=='material' and apply_material and target.get('hb_preview'):
            raise RuntimeError('Select the level object that should receive this material; the preview sphere is not exported.')
        def done(path):
            global _message
            if asset['kind']=='material':
                data=read_json(path);mat=blender_ops.material(data['materials'][0],Path(path).parent);mat['hb_game']=asset['game']
                mat['hb_game']=asset['game'];mat['hb_asset_id']=asset['id'];mat.use_fake_user=True;mat.asset_mark()
                if apply_material:
                    blender_ops.add_material(target,mat)
                    clear_previews(context)
                elif preview_only:
                    bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=16,location=context.scene.cursor.location)
                    sphere=bpy.context.object;sphere.data.materials.append(mat)
                    show_preview(context,sphere,asset['name'])
                _message='Material preview shown in viewport (excluded from export).' if preview_only else ('Added and assigned material (earlier materials kept in their slots): ' if apply_material else 'Loaded material (no object changed): ')+asset['name']
                return
            if targets:
                swapped=swap_objects(context,targets,asset,path,cfg)
                _message=f'Swapped {len(swapped)} object(s) to '+asset['name']+'.'
                return
            obj=blender_ops.place(asset,path,cfg)
            if preview_parts is not None and obj.get('hb_parts_path'):
                model_parts.apply(obj,preview_parts)
            if preview_matrix is not None:
                obj.data=obj.data.copy()
                if preview_center is not None:
                    from mathutils import Matrix,Vector
                    obj.data.transform(Matrix.Translation(-Vector(preview_center)));obj.data['hb_origin_center']=preview_center
                else:map_scene.center_mesh_origin(obj.data)
                obj.matrix_world=preview_matrix
                if obj.get('hb_parts_path'):obj['hb_parts_signature']=blender_ops.mesh_signature(obj.data)
            obj.asset_mark()
            import_warnings=json.loads(obj.get('hb_import_warnings','[]'))
            if import_warnings:
                report=bpy.data.texts.get('HaloBridge asset import warnings') or bpy.data.texts.new('HaloBridge asset import warnings')
                report.clear();report.write(obj.name+'\n\n'+'\n'.join(import_warnings))
            if preview_only:
                # Native asset_generate_preview starts an asynchronous renderer.
                # Unlinking its object immediately afterwards can crash Blender 4.0.
                # Keep a visible, explicitly non-exported preview instead.
                show_preview(context,obj,asset['name'])
                _message='Preview shown in viewport (excluded from export). Place asset adds the level object.'
            else:
                clear_previews(context)
                _message='Placed '+asset['name']+'. Duplicate with Alt+D to share mesh data.'
            if import_warnings:_message+=' Import warning: '+'; '.join(import_warnings)
        start(context,lambda cancel:jobs.extract(asset,cfg,cancel),done,'Preparing '+asset['name']+'…',undo=not preview_only)
        if preview_only:_task.preview_generation=_preview_generation

def checked_ids(context):
    s=context.scene.halo_bridge
    visible=visibility_predicate(s)
    return [a.asset_id for a in s.assets if a.checked and visible(a)]

class HBClearSearch(bpy.types.Operator):
    bl_idname='halo_bridge.clear_search';bl_label='Clear asset search'
    bl_description='Clear the search text to show all assets allowed by the current tab and category filters'
    def execute(self,context):
        context.scene.halo_bridge.search=''
        return {'FINISHED'}

class HBCheckAssets(bpy.types.Operator):
    bl_idname='halo_bridge.check_assets';bl_label='Select all listed'
    bl_description='Check or uncheck all entries currently shown by this tab and its search/category filters'
    check:BoolProperty(default=True)
    def execute(self,context):
        s=context.scene.halo_bridge
        visible=visibility_predicate(s)
        for a in s.assets:
            if visible(a):a.checked=self.check
        return {'FINISHED'}

class HBListHistory(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.list_history';bl_label='Undo / Redo asset list'
    bl_description='Undo or redo the last hide, unhide, delete or index change in this session (up to 30 changes); scene objects and cached files are kept'
    redo:BoolProperty(default=False)
    def run(self,context):
        global _catalogue,_message
        if not history_available(self.redo):raise RuntimeError('No matching asset-list history is available.')
        source=_list_redo if self.redo else _list_undo
        destination=_list_undo if self.redo else _list_redo
        entry=source[-1];state=entry[1 if self.redo else 0]
        expected=entry[0 if self.redo else 1]
        if read_json(_catalogue_path)!=expected['data']:
            raise RuntimeError('The catalogue changed outside this list. Reload it before making further changes.')
        write_json(_catalogue_path,state['data'])
        _catalogue=copy.deepcopy(state['data']);refresh(context,persist=False)
        s=context.scene.halo_bridge
        for row in s.assets:row.checked=row.asset_id in state['checked']
        for i,row in enumerate(s.assets):
            if row.asset_id==state['active'] and row_visible(s,row):s.active_index=i;break
        source.pop();destination.append(entry)
        _message=('Redid' if self.redo else 'Undid')+' asset-list change.'

class HBListAction(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.list_action';bl_label='Manage checked assets'
    bl_description='Hide, unhide, or delete checked catalogue entries; placed objects, original maps and cached files are kept'
    action:EnumProperty(items=[('HIDE','Hide',''),('UNHIDE','Unhide',''),('DELETE','Delete from list','')])
    asset_id:StringProperty()
    @classmethod
    def description(cls,context,properties):
        if properties.action=='HIDE':return 'Move these catalogue entries to Hidden Assets; placed objects remain visible and the original list order is preserved'
        if properties.action=='UNHIDE':return 'Return these entries to Imported Assets at their original positions'
        return 'Delete checked entries from this catalogue only; placed objects and files are kept. Re-index the map to restore deleted entries'
    def run(self,context):
        global _message
        data=ensure_catalogue(context)
        ids={self.asset_id} if self.asset_id else set(checked_ids(context))
        matches=[a for a in data['assets'] if a['id'] in ids]
        if not matches:raise RuntimeError('Check at least one asset in this tab first.')
        before=list_snapshot(context)
        path=Path(config(context)['cache'])/'catalogue.json'
        write_json(path.with_name('catalogue.before-list-edit.json'),data)
        # Preserve ordering by marking hidden entries in place, never moving rows.
        if self.action=='DELETE':data['assets']=[a for a in data['assets'] if a['id'] not in ids]
        else:
            for a in matches:a['hidden']=self.action=='HIDE'
        for a in context.scene.halo_bridge.assets:
            if a.asset_id in ids:a.checked=False
        refresh(context)
        remember_list(context,before)
        verb={'DELETE':'Deleted from list','HIDE':'Hidden','UNHIDE':'Restored'}[self.action]
        _message=verb+': '+str(len(matches))+' asset(s). Placed objects are unchanged.'

class HBPlaceChecked(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.place_checked';bl_label='Place checked assets'
    bl_description='Place checked models together at the 3D cursor; load checked materials without changing existing objects. Failed extractions are listed in the report'
    entire_map:BoolProperty(default=False)
    @classmethod
    def description(cls,context,properties):
        if properties.entire_map:return 'Import the named map terrain and static placements at their original world coordinates'
        return cls.bl_description
    def run(self,context):
        if self.entire_map:return bpy.ops.halo_bridge.import_map_scene()
        cfg=config(context)
        data=ensure_catalogue(context)
        ids=set(checked_ids(context))
        assets=[dict(a) for a in data['assets'] if a['id'] in ids]
        if not assets:raise RuntimeError('Check at least one asset in this tab first.')
        if any(a['game']!=cfg['game'] for a in assets):raise RuntimeError('Uncheck assets from a different or unverified game.')
        target=context.active_object
        if target and target.get('hb_preview'):target=context.scene.halo_bridge.preview_previous_object
        materials=any(a['kind']=='material' for a in assets)
        if not target or target.type!='MESH':target=None
        context.view_layer.update()
        preview_matrix=next((o.matrix_world.copy() for o in context.scene.objects if o.get('hb_preview') and len(assets)==1 and o.get('hb_asset_id')==assets[0]['id']),None)
        origin=context.scene.cursor.location.copy()
        stop_preview(context)
        def extract_all(cancel):
            global _message
            paths=[];failures=[]
            for index,asset in enumerate(assets):
                if cancel.is_set():raise jobs.Cancelled('Batch placement cancelled before creating objects.')
                _message='Extracting '+str(index+1)+'/'+str(len(assets))+': '+asset['name']
                try:paths.append((asset,jobs.extract(asset,cfg,cancel)))
                except jobs.Cancelled:raise
                except Exception as e:failures.append(asset['name']+' ('+asset['id']+'): '+str(e))
            return paths,failures
        def done(result):
            global _message,_error
            paths,failures=result
            created=[]
            old_materials=list(target.data.materials) if materials and target else []
            old_slot=target.active_material_index if materials and target else 0
            loaded_materials=0
            previous_selection=list(context.selected_objects);previous_active=context.active_object
            try:
                for index,(asset,path) in enumerate(paths):
                    _message='Placing '+str(index+1)+'/'+str(len(paths))+': '+asset['name']
                    if asset['kind']=='material':
                        meta=read_json(path);mat=blender_ops.material(meta['materials'][0],Path(path).parent)
                        mat['hb_game']=asset['game'];mat['hb_asset_id']=asset['id'];mat.use_fake_user=True;mat.asset_mark()
                        # Loading a material never changes an already placed object.
                        loaded_materials+=1
                    else:
                        # Include objects created by an importer even if it fails midway.
                        before=set(context.scene.objects)
                        try:obj=blender_ops.place(asset,path,cfg,location=origin)
                        finally:created.extend(o for o in context.scene.objects if o not in before)
                        if preview_matrix is not None:
                            obj.data=obj.data.copy();map_scene.center_mesh_origin(obj.data);obj.matrix_world=preview_matrix
                        obj.asset_mark();context.view_layer.update()
                    yield
                bpy.ops.object.select_all(action='DESELECT')
                for obj in created:obj.select_set(True)
                if created:context.view_layer.objects.active=created[-1]
                elif target:target.select_set(True);context.view_layer.objects.active=target
            except BaseException:
                for obj in created:
                    if obj.name in bpy.data.objects:bpy.data.objects.remove(obj,do_unlink=True)
                if materials and target:
                    target.data.materials.clear()
                    for mat in old_materials:target.data.materials.append(mat)
                    target.active_material_index=old_slot
                for obj in previous_selection:
                    if obj.name in context.view_layer.objects:obj.select_set(True)
                if previous_active and previous_active.name in context.view_layer.objects:context.view_layer.objects.active=previous_active
                raise
            _message='Placed '+str(len(created))+' object(s); loaded '+str(loaded_materials)+' material(s).'
            if failures:
                _error='Skipped '+str(len(failures))+' asset(s):\n\n'+'\n\n'.join(failures)
                text=bpy.data.texts.get('HaloBridge diagnostics') or bpy.data.texts.new('HaloBridge diagnostics');text.clear();text.write(_error)
                _message+=' Skipped '+str(len(failures))+'. Open report for details.'
        start(context,extract_all,done,'Preparing '+str(len(assets))+' checked asset(s)…',undo=True)

class HBImportMapScene(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.import_map_scene';bl_label='Import entire .map'
    bl_description='Reconstruct the map terrain and static object placements at original positions, rotations and scales in a separate collection. Prepare exports the current meshes as static geometry with generated collision; original gameplay is not reconstructed'
    def run(self,context):
        cfg=config(context);name=context.scene.halo_bridge.map_name
        stop_preview(context)
        start(context,lambda cancel:jobs.extract_map_scene(cfg,name,cancel,set_message),lambda manifest:finish_map_scene(context,manifest),'Reading original map layout…')
        _task.application_budget=.05


_campaign_items=[]
_campaign_retired=[]


class HBChooseCampaignLevel(bpy.types.Operator):
    bl_idname='halo_bridge.choose_campaign_level';bl_label='Choose campaign level'
    bl_description='Search the Halo 2: Anniversary campaign levels installed with MCC; choosing one fills the filename without importing'
    bl_property='choice'
    choice:EnumProperty(items=lambda self,context:_campaign_items)
    @classmethod
    def poll(cls,context):return _task is None
    def invoke(self,context,event):
        global _campaign_items
        names=jobs.h2a_campaign_levels(bpy.path.abspath(context.scene.halo_bridge.maps))
        if not names:
            self.report({'WARNING'},'No campaign levels found. Select MCC\'s groundhog maps folder; the campaign is in halo2\\preload\\paks of the same install.')
            return {'CANCELLED'}
        _campaign_retired.append(_campaign_items)
        _campaign_items=[(name,name,'Use '+name,index) for index,name in enumerate(names)]
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}
    def execute(self,context):
        if self.choice not in {item[0] for item in _campaign_items}:return {'CANCELLED'}
        context.scene.halo_bridge.h2a_campaign_level=self.choice
        return {'FINISHED'}


class HBImportH2ACampaign(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.import_h2a_campaign';bl_label='Import campaign level'
    bl_description=('Import a Halo 2: Anniversary campaign level\'s remastered geometry and textures (Saber3D .pck), '
                    'placed in classic Halo 2 world coordinates. Prepare converts its materials to Halo 3 shaders and '
                    'generates collision; AI, weapons, vehicles and scripts are not imported')
    def run(self,context):
        cfg=config(context);name=context.scene.halo_bridge.h2a_campaign_level
        stop_preview(context)
        start(context,lambda cancel:jobs.extract_h2a_campaign_scene(cfg,name,cancel,set_message),
              lambda manifest:finish_map_scene(context,manifest,source='Anniversary campaign'),'Reading Anniversary campaign level…')
        _task.application_budget=.05


def set_message(message):
    global _message
    _message=message


SHADOWS_OFF_NOTE=' EEVEE shadows were turned off for a faster viewport (Folders and Setup > Viewport Shadows).'

def faster_level_viewport(context):
    """After a whole-level import: turn off EEVEE shadows, which overflow on Halo-sized levels."""
    return compat.set_eevee_shadows(context.scene,False)


def finish_map_scene(context,manifest,source='Original map layout'):
    """Create the objects of an extracted map scene and write its report (a generator)."""
    global _message
    data=read_json(manifest)
    yield from map_scene.import_scene(context,manifest,set_message,skies=context.scene.halo_bridge.import_sky)
    freed=jobs.discard_h2a_campaign_meshes(manifest) if source=='Anniversary campaign' else 0
    # Without "Import sky" the level's own sky isn't used; Sapien Sky decides (default sky).
    if games.GAMES[context.scene.halo_bridge.game].get('sapien_enabled') and context.scene.halo_bridge.import_sky:context.scene.halo_bridge.sky_scenario=data['scenario']
    warnings=data.get('warnings',[])
    report=source+': '+data['scenario']+'\n\n'
    report+='Terrain BSPs: '+str(data['decoded_bsps'])+'/'+str(data['expected_bsps'])+'\n'
    report+='\n'.join(k+': '+str(v) for k,v in data.get('counts',{}).items())
    report+='\n\nImport scope:\n'+'\n'.join(data.get('limitations',[]))
    if warnings:report+='\n\nMissing or approximated elements:\n'+'\n'.join(warnings)
    text=bpy.data.texts.get('HaloBridge map import report') or bpy.data.texts.new('HaloBridge map import report');text.clear();text.write(report)
    _message=('Imported original map base' if source=='Original map layout'
              else 'Imported Anniversary campaign level '+data['scenario'].rsplit('\\',1)[-1] if source=='Anniversary campaign'
              else 'Imported '+data['scenario'].rsplit('\\',1)[-1]+' from the Editing Kit')+': '+str(len(data['placements']))+' mesh placements; terrain BSPs '+str(data['decoded_bsps'])+'/'+str(data['expected_bsps'])+'. '+str(len(warnings))+' warnings. See map import report.'
    if freed:_message+=' Freed '+str(round(freed/2**20))+' MB of temporary geometry files.'
    if faster_level_viewport(context):_message+=SHADOWS_OFF_NOTE
    if data['decoded_bsps']!=data['expected_bsps']:
        issues=['Incomplete import: '+str(data['decoded_bsps'])+'/'+str(data['expected_bsps'])+' terrain BSPs. This scene is not ready for Sapien preparation.']
        issues.extend(w for w in warnings if w.startswith('BSP '))
        record_failure(ValidationError(issues,'Map extraction'))
        bpy.ops.halo_bridge.report_diagnostics()

_scenario_items=[]
_scenario_retired=[]


class HBChooseScenario(bpy.types.Operator):
    bl_idname='halo_bridge.choose_scenario';bl_label='Choose Editing Kit scenario'
    bl_description='Search the .scenario tags in the selected game\'s Editing Kit; choosing one fills the scenario path without importing'
    bl_property='choice'
    choice:EnumProperty(items=lambda self,context:_scenario_items)
    @classmethod
    def poll(cls,context):return _task is None
    def invoke(self,context,event):
        global _scenario_items
        kit=Path(bpy.path.abspath(context.scene.halo_bridge.kit))
        classic=games.GAMES[context.scene.halo_bridge.game].get('classic')
        names=(classic_scenario.scenarios(kit) if classic else scenario_scene.scenarios(kit)) if context.scene.halo_bridge.kit else []
        if not names:
            self.report({'WARNING'},'No .scenario tags found under '+str(kit/'tags')+'. Choose the '+games.GAMES[context.scene.halo_bridge.game]['label']+' Editing Kit folder and extract its tag archives.');return {'CANCELLED'}
        _scenario_retired.append(_scenario_items)
        _scenario_items=[(name,name,'Use '+name,index) for index,name in enumerate(names)]
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}
    def execute(self,context):
        if self.choice not in {item[0] for item in _scenario_items}:return {'CANCELLED'}
        context.scene.halo_bridge.scenario_path=self.choice
        return {'FINISHED'}


class HBImportScenario(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.import_scenario';bl_label='Import level from .scenario'
    bl_description='Build the level from its Editing Kit .scenario tag: BSP geometry from the source files stored in the tags, every scenery, crate, machine, control and vehicle placement, and the tag shader on each surface. Unedited scenery stays original scenery when preparing for Sapien. Halo: Reach kits carry no source files, so Reach geometry comes from the installed map'
    def run(self,context):
        cfg=config(context);s=context.scene.halo_bridge
        game=games.GAMES[s.game]
        if not game.get('scenario_enabled'):raise RuntimeError('Editing Kit scenario import is not available for '+game['label']+'.')
        if not s.kit or not (Path(cfg['kit'])/'tags').is_dir():raise RuntimeError('Choose the '+game['label']+' Editing Kit folder ('+game.get('kit','')+', it contains tool.exe and tags) first.')
        scenario=scenario_scene.safe_tag(s.scenario_path)
        stop_preview(context)
        if game.get('classic'):
            def build(cancel):
                built=classic_scenario.build_map(cfg,scenario,cancel,set_message)
                return jobs.extract_map_scene(classic_scenario.map_config(cfg,built),built.name,cancel,set_message)
            start(context,build,lambda manifest:finish_map_scene(context,manifest,'Editing Kit scenario'),'Building '+scenario_scene.leaf(scenario)+' with the Editing Kit Tool...')
            _task.application_budget=.05
            return
        def progress(message):
            global _message
            _message=message
        def done(manifest):
            global _message
            data=read_json(manifest)
            yield from scenario_scene.import_scene(context,manifest,progress,skies=context.scene.halo_bridge.import_sky)
            if context.scene.halo_bridge.import_sky:context.scene.halo_bridge.sky_scenario=data['scenario']
            text=bpy.data.texts.get('HaloBridge scenario import report') or bpy.data.texts.new('HaloBridge scenario import report')
            text.clear();text.write(scenario_scene.report(data))
            warnings=data.get('warnings',[])
            _message=('Imported '+scenario_scene.leaf(data['scenario'])+' from the Editing Kit: '+str(len(data['placements']))+' objects; BSPs with source geometry '
                      +str(data['decoded_bsps'])+'/'+str(data['expected_bsps'])+'. '+str(len(warnings))+' notes. See HaloBridge scenario import report.')
            if faster_level_viewport(context):_message+=SHADOWS_OFF_NOTE
            if data['decoded_bsps']!=data['expected_bsps']:
                record_failure(ValidationError(['Some BSPs have no embedded source geometry: '+str(data['decoded_bsps'])+'/'+str(data['expected_bsps'])+' imported.']+[w for w in warnings if w.startswith('BSP ')],'Scenario import'))
                bpy.ops.halo_bridge.report_diagnostics()
        start(context,lambda cancel:scenario_scene.extract(cfg,scenario,cancel,progress),done,'Reading Editing Kit scenario '+scenario_scene.leaf(scenario)+'...')
        _task.application_budget=.05


class HBIndexScenario(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.index_scenario';bl_label='Index .scenario Assets'
    bl_description='List every distinct object, instanced mesh and shader used by the chosen Editing Kit .scenario in the Indexed Asset List, without placing the level. Uses the same cached build as Import level from .scenario'
    def run(self,context):
        cfg=config(context);s=context.scene.halo_bridge
        game=games.GAMES[s.game]
        if not game.get('scenario_enabled'):raise RuntimeError('Editing Kit scenario indexing is not available for '+game['label']+'.')
        if not s.kit or not (Path(cfg['kit'])/'tags').is_dir():raise RuntimeError('Choose the '+game['label']+' Editing Kit folder ('+game.get('kit','')+', it contains tool.exe and tags) first.')
        scenario=scenario_scene.safe_tag(s.scenario_path)
        base=read_json(Path(cfg['cache'])/'catalogue.json',{'version':1,'assets':[]})
        def progress(message):
            global _message
            _message=message
        def work(cancel):
            if game.get('classic'):
                built=classic_scenario.build_map(cfg,scenario,cancel,progress)
                out=Path(cfg['cache'])/'indexes'/('scenario_'+built.stem+'.json')
                result=jobs.helper('extractor',dict(operation='index',game=cfg['game'],map=str(built),output=str(out)),Path(cfg['cache'])/'jobs',cancel)
                return classic_scenario.mark_rows(indexed_assets(result),scenario)
            manifest=scenario_scene.extract(cfg,scenario,cancel,progress)
            return scenario_scene.index_assets(manifest,cfg)
        def done(rows):
            global _catalogue,_message
            before=list_snapshot(context);before['data']=copy.deepcopy(base);before['path']=str((Path(cfg['cache'])/'catalogue.json').resolve())
            _catalogue=merge_assets(base,rows);refresh(context);remember_list(context,before)
            kinds={}
            for row in rows:kinds[row['kind']]=kinds.get(row['kind'],0)+1
            _message=('Indexed '+str(len(rows))+' .scenario assets from '+scenario_scene.leaf(scenario)+': '
                      +', '.join(str(v)+' '+{'scenery':'scenery','model':'objects','instance':'instanced meshes','material':'shaders'}.get(k,k) for k,v in sorted(kinds.items()))+'.')
        start(context,work,done,'Indexing Editing Kit scenario '+scenario_scene.leaf(scenario)+'...')


class HBPreviewToggle(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.toggle_preview';bl_label='Preview On / Off';bl_options={'REGISTER','UNDO'}
    bl_description='Turn live previews on or off: selecting another asset updates the preview; turning off removes it, even while loading'
    def execute(self,context):
        global _message
        if context.scene.halo_bridge.preview_enabled or preview_active(context):
            stop_preview(context)
            _message='Preview off. Ready to place assets.'
            return {'FINISHED'}
        return Guard.execute(self,context)
    def run(self,context):
        context.scene.halo_bridge.preview_enabled=True
        selection_changed(context.scene.halo_bridge,context)

class HBViewDistance(bpy.types.Operator):
    bl_idname='halo_bridge.view_distance';bl_label='Remove Grey Blender Fog (View Distance)'
    bl_description='Set every 3D View to Clip Start 0.1 and Clip End 999999 so whole levels are not cut off or greyed out in the distance'
    def execute(self,context):
        units=context.scene.unit_settings
        scale=units.scale_length if units.system!='NONE' else 1.0
        count=compat.clear_view_fog(bpy.data.screens,unit_scale=scale)
        self.report({'INFO'},'View distance set on '+str(count)+' 3D View(s): Clip Start 0.1, Clip End 999999 (scene units).')
        return {'FINISHED'}

class HBViewportShadows(bpy.types.Operator):
    bl_idname='halo_bridge.viewport_shadows';bl_label='Viewport Shadows'
    bl_description='Turn EEVEE shadows on or off for this scene. Off is much faster on whole Halo levels and removes the "Shadow buffer full" error; Halo lighting is baked, so Material Preview looks almost the same. This is the Render Properties > Shadows setting'
    @classmethod
    def poll(cls,context):return compat.has_eevee_shadow_switch(context.scene)
    def execute(self,context):
        on=not compat.eevee_shadows(context.scene)
        compat.set_eevee_shadows(context.scene,on)
        self.report({'INFO'},'EEVEE shadows '+('on.' if on else 'off: faster viewport on large levels.'))
        for area in context.screen.areas:area.tag_redraw()
        return {'FINISHED'}

class HBGround(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.ground';bl_label='Create starter level shell template';bl_options={'REGISTER','UNDO'}
    bl_description='Add a paintable Jungle terrain plane, a visible sky boundary wall and Master Chief for scale (not exported). Textures and the model are extracted from your 010_jungle.map'
    def run(self,context):
        cfg=export_config(context)
        if cfg['game']!='halo3':raise RuntimeError('The starter template uses Halo 3 assets (Jungle terrain and Master Chief). Set Export to Sapien to Halo 3, or build your own floor for '+games.GAMES[cfg['game']]['label']+'.')
        mp=Path(cfg['maps'])/'010_jungle.map'
        if not mp.is_file():raise RuntimeError('The starter template needs 010_jungle.map for its terrain shader and Master Chief. Check the Halo 3 maps folder.')
        ground,chief=indexed_assets(dict(map=str(mp),assets=[
            dict(name='Jungle ground',tag='levels\\solo\\010_jungle\\shaders\\terrain\\terrain_000',kind='material',section=-1),
            dict(name='masterchief',tag='objects\\characters\\masterchief\\masterchief',kind='model',section=-1)]))
        def extract(cancel):
            return jobs.extract(ground,cfg,cancel),jobs.extract(chief,cfg,cancel)
        def done(paths):
            global _message
            blender_ops.starter_template(context,cfg,paths[0],chief,paths[1])
            _message='Created the starter template: paintable terrain, sky boundary and Master Chief for scale (not exported). Material Preview and long view distance are on.'
        start(context,extract,done,'Loading starter template terrain and Master Chief…')

class HBScanShaders(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.scan_shaders';bl_label='Scan existing shaders'
    bl_description='List existing .shader tags from the selected Editing Kit; no new shaders are created'
    def run(self,context):
        global _message
        _message='Found '+str(shader_choices.scan(games.destination(context.scene.halo_bridge).kit))+' existing shaders.'
        context.scene.halo_bridge.shader_level='ALL'
        context.scene.halo_bridge.shader_choice='NONE'

class HBChooseShader(bpy.types.Operator):
    bl_idname='halo_bridge.choose_shader';bl_label='Search existing shaders'
    bl_description='Search every scanned shader by name or folder, then assign your choice to the active material'
    bl_property='choice'
    shader_kit:StringProperty(options={'HIDDEN','SKIP_SAVE'})
    shader_category:StringProperty(default='ALL',options={'HIDDEN','SKIP_SAVE'})
    choice:EnumProperty(items=shader_choices.search_items)
    def invoke(self,context,event):
        settings=context.scene.halo_bridge
        self.shader_kit=games.destination(settings).kit
        self.shader_category='ALL'
        self.choice='NONE'
        context.window_manager.invoke_search_popup(self)
        return {'RUNNING_MODAL'}
    def execute(self,context):
        settings=context.scene.halo_bridge
        if self.shader_kit!=games.destination(settings).kit:
            self.report({'WARNING'},'The Editing Kit changed. Open the shader picker again.')
            return {'CANCELLED'}
        if self.choice=='NONE':return {'CANCELLED'}
        settings.shader_choice=self.choice
        return {'FINISHED'}

class HBShader(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.shader';bl_label='Assign shader to active material';bl_options={'REGISTER','UNDO'}
    bl_description='Set the active material slot on the selected object to use this existing Halo shader in Sapien. All objects sharing that material are affected. Use Load Halo Shader Textures/Masks to refresh the Blender preview'
    def run(self,context):
        global _message
        from .catalog import material_name
        obj=context.active_object
        if not obj or not obj.active_material:raise RuntimeError('Select an object with an active material.')
        settings=context.scene.halo_bridge
        tag=(settings.shader_path if settings.shader_manual else settings.shader_choice).replace('/','\\')
        if tag=='NONE':raise RuntimeError('Scan existing shaders and choose one first.')
        export_review.shader_file(games.destination(settings).kit,tag);obj.active_material['hb_shader']=tag
        obj.active_material['hb_shader_game']=settings.export_target
        _message='Assigned '+tag.rsplit('\\',1)[-1]+' to material '+obj.active_material.name+'. Load shader textures to refresh its Blender preview.'

_vehicle_items_cache={}

def vehicle_items(operator,context):
    obj=context.active_object if context else None
    raw=obj.get('hb_vehicle_matches','[]') if obj else '[]'
    if raw not in _vehicle_items_cache:
        rows=json.loads(raw)
        _vehicle_items_cache[raw]=[(r['vehicle'],r['vehicle'].rsplit('\\',1)[-1],r['vehicle'],i) for i,r in enumerate(rows)]
    return _vehicle_items_cache[raw]

class HBFindVehicle(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.find_vehicle';bl_label='Find matching original vehicles'
    bl_description='Find vehicle tags in the destination Editing Kit whose render model matches the selected imported object; select a variant afterward'
    def run(self,context):
        obj=context.active_object
        if not obj or obj.type!='MESH':raise RuntimeError('Select the imported vehicle model in the 3D View first.')
        vehicles.validate_preview(obj);cfg=export_config(context)
        name=obj.name;source=obj['hb_source_tag'];directory=Path(cfg['cache'])/'jobs';out=directory/('vehicle-matches-'+str(time.time_ns())+'.json')
        def done(result):
            global _message
            target=bpy.data.objects.get(name)
            if target!=obj or target.get('hb_source_tag')!=source:raise RuntimeError('The selected object changed; find matching vehicles again.')
            matches=result.get('matches',[]);target['hb_vehicle_matches']=json.dumps(matches)
            if not matches:raise RuntimeError('No installed Halo 3 vehicle tag references this model. Check that the Editing Kit tags are extracted.')
            _message='Found '+str(len(matches))+' matching vehicle tag(s). Choose the original vehicle variant under Selected Asset.'
        start(context,lambda cancel:jobs.helper('tags',dict(operation='resolve_vehicles',kit=cfg['kit'],sources=[source],output=str(out)),directory,cancel),done,'Finding matching Halo 3 vehicle tags...')

class HBChooseVehicle(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.choose_vehicle';bl_label='Use original vehicle tag'
    bl_description='Export the selected object as an original vehicle placement, keeping its game collision and behavior instead of static mesh geometry'
    bl_property='choice';bl_options={'REGISTER','UNDO'}
    choice:EnumProperty(items=vehicle_items)
    target_name:StringProperty(options={'HIDDEN','SKIP_SAVE'})
    def invoke(self,context,event):
        if not context.active_object:return {'CANCELLED'}
        self.target_name=context.active_object.name
        context.window_manager.invoke_search_popup(self);return {'RUNNING_MODAL'}
    def run(self,context):
        global _message
        obj=context.active_object
        if not obj or (self.target_name and obj.name!=self.target_name):raise RuntimeError('Select the same object and choose its vehicle again.')
        vehicles.validate_preview(obj)
        rows=json.loads(obj.get('hb_vehicle_matches','[]'))
        if not any(r['vehicle']==self.choice and r['render']==obj['hb_source_tag'] for r in rows):raise RuntimeError('Find matching vehicles for this model first.')
        obj['hb_vehicle_tag']=self.choice;obj['hb_vehicle_render']=obj['hb_source_tag']
        if not obj.get('hb_vehicle_id'):obj['hb_vehicle_id']=blender_ops.new_id()
        _message=obj.name+' will export as an original vehicle: '+self.choice

class HBVehicleStatic(bpy.types.Operator):
    bl_idname='halo_bridge.vehicle_static';bl_label='Use static mesh instead';bl_options={'REGISTER','UNDO'}
    bl_description='Export the selected object as static geometry again; vertex limits apply and vehicle behavior is not included'
    def execute(self,context):
        obj=context.active_object
        if obj and 'hb_vehicle_tag' in obj:del obj['hb_vehicle_tag']
        return {'FINISHED'}

class HBCustomMaterial(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.custom_material';bl_label='Create editable material';bl_options={'REGISTER','UNDO'}
    bl_description='Make a separate editable material for the active slot. It exports as a baked, level-local Halo 3 shader, leaving stock tags unchanged'
    mode:EnumProperty(items=[('terrain','Terrain','Grass, rock and dirt with a paint mask'),('colors','Colors','Masked texture tint colors')])
    def run(self,context):
        global _message
        mat=editable_materials.make(context,self.mode)
        if editable_materials.exports_terrain_shader(mat):
            _message='Created '+mat.name+'. Choose layer images and their repeat, then paint the mask (Add layer for up to four textures). Save texture edits in the blend before closing. Preparation exports a Halo 3 terrain shader.'
        else:
            _message='Created '+mat.name+'. Choose layer images or colors, then paint the mask. Save texture edits in the blend before closing. Preparation bakes the UV texture into a custom Halo shader.'

class HBCustomLoadImage(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.custom_load_image';bl_label='Load layer image';bl_options={'REGISTER','UNDO'}
    bl_description='Load a texture into this editable material layer'
    filepath:StringProperty(subtype='FILE_PATH')
    node_name:StringProperty()
    material_name:StringProperty()
    def invoke(self,context,event):
        self.material_name=context.active_object.active_material.name
        context.window_manager.fileselect_add(self);return {'RUNNING_MODAL'}
    def run(self,context):
        mat=bpy.data.materials.get(self.material_name)
        if not mat or not mat.get('hb_custom_shader'):raise RuntimeError('Select the editable material again.')
        node=mat.node_tree.nodes.get(self.node_name)
        if not node or node.type!='TEX_IMAGE':raise RuntimeError('The texture layer changed. Choose it again.')
        image=bpy.data.images.load(self.filepath,check_existing=False)
        if self.node_name in ('Paint Mask','Original Blend') or 'Normal' in self.node_name:image.colorspace_settings.name='Non-Color'
        image.pack();node.image=image

class HBCustomPaint(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.custom_paint';bl_label='Paint selected texture'
    bl_description='Paint the selected layer on the model in Texture Paint mode; uses the active UV map'
    paint_channel:IntProperty(default=-1)
    node_name:StringProperty(default='Paint Mask')
    layer:EnumProperty(items=[('GRASS','Grass','Black mask: grass'),('ROCK','Rock','Red mask: rock'),('DIRT','Dirt','Green mask: dirt'),('LAYER4','Layer 4','Blue mask: layer 4')])
    def run(self,context):
        obj=context.active_object;mat=obj.active_material if obj else None
        if not mat or not mat.get('hb_custom_shader'):raise RuntimeError('Select an editable material first.')
        node=mat.node_tree.nodes.get(self.node_name)
        if not node or not node.image:raise RuntimeError('Choose an image for this texture first.')
        mat.node_tree.nodes.active=node
        if obj.mode!='TEXTURE_PAINT':bpy.ops.object.mode_set(mode='TEXTURE_PAINT')
        paint=context.tool_settings.image_paint;paint.mode='IMAGE';paint.canvas=node.image
        for area in context.screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.shading.type='MATERIAL'
                compat.draw_tool(context,area)
        # Blender 4.3+ brushes are assets; compat picks a mix-blend draw brush on every version.
        brush=compat.texture_paint_brush(context,paint,'HaloBridge Texture Draw')
        if self.node_name=='Paint Mask':
            palette=((1,0,0),(0,1,0),(0,0,1),(1,1,1),(0,0,0))
            color=palette[self.paint_channel] if self.paint_channel>=0 else {'GRASS':(0,0,0),'ROCK':(1,0,0),'DIRT':(0,1,0),'LAYER4':(0,0,1)}[self.layer]
            compat.set_paint_color(context,paint,brush,color)


class HBAddTerrainLayer(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.add_terrain_layer';bl_label='Add terrain layer';bl_options={'REGISTER','UNDO'}
    bl_description='Add a fourth paintable layer (painted with blue in the mask). Halo 3 terrain shaders have at most four layers'
    def run(self,context):
        global _message
        obj=context.active_object;mat=obj.active_material if obj else None
        tex=editable_materials.add_terrain_layer(mat)
        _message='Added '+tex.name+'. It starts as a copy of layer 1: choose its image, then paint it with its Paint button.'

class HBCustomPack(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.custom_pack';bl_label='Pack texture edits into blend'
    bl_description='Store the current editable images inside the blend file; save the blend afterward to retain painted changes'
    def run(self,context):
        global _message
        mat=context.active_object.active_material
        editable_materials.pack(mat);_message='Texture edits packed. Save your blend file to keep them.'

class HBReadShaderTextures(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.read_shader_textures';bl_label='Load Halo Shader Textures/Masks for Currently selected Material'
    bl_description='Read the active shader from the chosen .map, including its color-change mask. Use the map and import-game settings matching this asset'
    def run(self,context):
        obj=context.active_object;mat=obj.active_material if obj else None
        if not mat or not mat.get('hb_shader'):raise RuntimeError('Select an imported Halo material first.')
        cfg=config(context);source=Path(cfg['maps'])/context.scene.halo_bridge.map_name
        out=Path(cfg['cache'])/'shader_previews'/str(time.time_ns());slot=obj.active_material_index
        tag=mat['hb_shader']
        if mat.get('hb_custom_shader'):
            raise RuntimeError('This material is already editable. Load source textures on a stock material slot to keep your paint and colors.')
        assets=ensure_catalogue(context)['assets']
        source_asset=next((a for a in assets if a.get('id')==obj.get('hb_asset_id')), {})
        matches=[Path(a['map']) for a in assets if a.get('kind')=='material' and a.get('game','halo3')==cfg['game']
                 and a.get('tag','').casefold()==tag.casefold() and a.get('map')]
        origin=Path(source_asset.get('map') or source)
        source=next((p for p in (origin,source,*matches) if p in matches and p.is_file()),origin)
        def done(result):
            global _message
            if obj.name not in context.scene.objects or obj.data.materials[slot]!=mat:raise RuntimeError('The selected material changed during extraction.')
            data=read_json(out/'preview.json');replacement=blender_ops.material(data['materials'][0],out)
            if obj.data.users>1:obj.data=obj.data.copy()
            obj.data.materials[slot]=replacement
            from . import regular_preview
            regular_preview.paired_transparency(obj.data)
            _message='Loaded source shader textures. Create an editable terrain or color material to customize and export them.'
        start(context,lambda cancel:jobs.helper('extractor',dict(operation='material',game=cfg['game'],map=str(source),tag=tag,output=str(out)),Path(cfg['cache'])/'jobs',cancel),done,'Reading shader textures and masks...')

class HBModelPartToggle(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.model_part_toggle';bl_label='Toggle model part';bl_options={'REGISTER','UNDO'}
    bl_description='Show or hide this region/permutation without changing any part positions. Only enabled surfaces are exported'
    choice:StringProperty()
    region:StringProperty()
    def run(self,context):
        obj=context.active_object
        if not obj or not obj.get('hb_parts_path'):raise RuntimeError('Select a model with part metadata.')
        selected=model_parts.enabled(obj)
        targets={self.choice} if self.choice else {key for key,value in model_parts.choices(obj).items() if value[0]==self.region}
        if targets<=selected:selected-=targets
        else:selected|=targets
        model_parts.apply(obj,selected)

class HBModelRegionExpand(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.model_region_expand';bl_label='Expand/collapse model region'
    bl_description='Show or hide the variant list for this region without changing enabled geometry'
    region:StringProperty()
    def run(self,context):
        obj=context.active_object
        if not obj or not obj.get('hb_parts_path'):raise RuntimeError('Select a model with part metadata.')
        opened=set(json.loads(obj.get('hb_parts_open','[]')))
        if self.region in opened:opened.remove(self.region)
        else:opened.add(self.region)
        obj['hb_parts_open']=json.dumps(sorted(opened))

class HBModelPartsSeparate(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.model_parts_separate';bl_label='Separate enabled parts into objects';bl_options={'REGISTER','UNDO'}
    bl_description='Turn model parts into independent mesh objects at their current positions. Undo restores the combined model and toggles'
    all_variants:BoolProperty(default=False,options={'SKIP_SAVE'})
    @classmethod
    def description(cls,context,properties):
        return ('Separate every region and variant, including disabled ones, into independent objects. Alternatives stay at their original positions and may overlap. Undo restores the combined model.' if properties.all_variants else 'Separate only enabled parts into independent objects at their current positions. Undo restores the combined model.')
    def run(self,context):
        global _message
        obj=context.active_object
        if not obj or not obj.get('hb_parts_path'):raise RuntimeError('Select a placed model with part metadata.')
        count=len(model_parts.separate(context,obj,all_variants=self.all_variants))
        _message=f'Separated {count} independent model parts. Select any piece in the Outliner to move or edit it.'
        if self.all_variants:_message+=' Disabled variants are included; alternatives may overlap because their original positions are preserved.'

class HBChooseSky(bpy.types.Operator):
    bl_idname='halo_bridge.choose_sky';bl_label='Choose sky from map'
    bl_description='Apply the chosen map sky; the selected scenario is shown below and saved with the scene'
    bl_property='choice'
    choice:EnumProperty(items=lambda self,context:skies.items(context.scene.halo_bridge,context) if context else [])
    def execute(self,context):
        s=context.scene.halo_bridge
        s.sky_choice=self.choice;s.sky_selected=self.choice
        s.sky_scenario=self.choice if self.choice!='AUTO' else 'levels\\multi\\isolation\\isolation'
        return {'FINISHED'}

class HBChooseGameSky(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.choose_game_sky';bl_label='Choose sky'
    bl_description='Place the chosen sky model in the Sapien Sky collection. Preparation rebuilds it as a sky for the Sapien destination with converted textures; resize or move it in Blender if needed'
    bl_property='choice'
    choice:EnumProperty(items=lambda self,context:skies.foreign_items(context.scene.halo_bridge,context) if context else [])
    def run(self,context):
        s=context.scene.halo_bridge
        if self.choice=='NONE':return
        game=skies.sky_game(s);profile=games.profile(s,game)
        cfg=dict(config(context),**{k:bpy.path.abspath(v) if k in ('kit','cache','maps') else v for k,v in profile.items()})
        asset=next((a for a in skies.catalogue_skies(s,game) if a['id']==self.choice),None)
        if asset is None:raise RuntimeError('That sky is no longer in the '+games.GAMES[game]['label']+' asset list. Index its map again.')
        stop_preview(context)
        def done(result):
            global _message
            path,lighting=result
            obj=sky_export.place(context,asset,path,cfg)
            if lighting:obj['hb_sky_lighting']=json.dumps(lighting)  # the Halo 2 sky's sun and sky light
            _message='Sapien sky: '+asset['name']+' from '+games.GAMES[game]['label']+'. It is in the Sapien Sky collection and is rebuilt as a converted sky when you prepare the level.'
            context.view_layer.objects.active=obj
        def work(cancel):
            path=jobs.extract(asset,cfg,cancel)
            try:lighting=jobs.sky_lighting(asset,cfg,cancel)
            except Exception:lighting=None  # the sky still works; its level is then lit with a Halo 3 sky
            return path,lighting
        start(context,work,done,'Extracting sky '+asset['name']+'…',undo=True)

class HBSetSkyGame(bpy.types.Operator):
    bl_idname='halo_bridge.set_sky_game';bl_label='Sky game'
    bl_description='Game to take the Sapien sky from'
    bl_property='game'
    game:EnumProperty(items=skies.GAME_ITEMS)
    def execute(self,context):
        context.scene.halo_bridge.sky_game=self.game
        return {'FINISHED'}

class HBRemoveGameSky(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.remove_game_sky';bl_label='Remove sky object'
    bl_description='Delete the converted sky object from the Sapien Sky collection'
    def run(self,context):
        global _message
        for obj in [o for o in context.scene.objects if o.get(sky_export.PROPERTY)]:bpy.data.objects.remove(obj,do_unlink=True)
        _message='Removed the sky object.'

class HBRefreshSkies(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.refresh_skies';bl_label='Scan for map skies'
    bl_description='Scan installed Editing Kit scenarios for usable sky references; includes maps beyond the current asset index'
    def run(self,context):
        cfg=export_config(context);directory=Path(cfg['cache'])/'jobs';out=directory/('skies-'+str(time.time_ns())+'.json')
        def done(result):
            global _message
            result['kit']=cfg['kit']
            write_json(Path(cfg['cache'])/'sky-catalogue.json',result);skies.invalidate()
            _message='Found skies from '+str(len(result['items']))+' maps. Choose one from the Sky dropdown under Sapien Sky (Experimental). Use Generate Test Lighting for Sapien Level during preparation.'
        start(context,lambda cancel:jobs.helper('tags',dict(operation='list_skies',kit=cfg['kit'],output=str(out)),directory,cancel),done,'Finding skies in Editing Kit maps...')

_prepare_running=False
_prepare_status='Ready to prepare the current scene.'
_prepare_activity=None
_activity_text_stamps={}


def sync_activity_texts(force=False):
    if not _prepare_activity:return
    visible={area.spaces.active.text.name for screen in bpy.data.screens for area in screen.areas
             if area.type=='TEXT_EDITOR' and area.spaces.active.text}
    for name,path in (('HaloBridge preparation activity',str(_prepare_activity.path)),
                      ('HaloBridge compiler output',_prepare_activity.current_log)):
        if not path or (not force and name not in visible):continue
        try:
            source=Path(path);stamp=(path,source.stat().st_mtime_ns,source.stat().st_size)
            if _activity_text_stamps.get(name)==stamp:continue
            with source.open('rb') as stream:
                stream.seek(max(0,stamp[2]-1048576));data=stream.read().decode('utf-8',errors='replace')
            text=bpy.data.texts.get(name) or bpy.data.texts.new(name)
            text.clear();text.write('Live log (refreshes while preparing). Full file: '+path+'\n\n'+data)
            _activity_text_stamps[name]=stamp
        except OSError:pass


class HBActivityLog(bpy.types.Operator):
    bl_idname='halo_bridge.activity_log';bl_label='Open preparation activity log'
    bl_description='Show timestamped preparation events or raw compiler output in a live Text Editor; full logs are also saved in the HaloBridge jobs folder'
    raw:BoolProperty(default=False)
    def execute(self,context):
        if not _prepare_activity:return {'CANCELLED'}
        sync_activity_texts(force=True)
        name='HaloBridge compiler output' if self.raw else 'HaloBridge preparation activity'
        text=bpy.data.texts.get(name)
        if not text:return {'CANCELLED'}
        context.area.type='TEXT_EDITOR';context.area.spaces.active.text=text
        return {'FINISHED'}


def remove_old_exports(folder):
    """Each Prepare writes a new level_<time>.ASS (often over 1 GB); earlier ones are never read again."""
    for old in Path(folder).glob('level_*.ASS'):
        try:old.unlink()
        except OSError:pass


def prepare_status(message,running=False):
    global _prepare_status,_prepare_running
    _prepare_status=message;_prepare_running=running
    if _prepare_activity:
        _prepare_activity.ended=None if running else time.monotonic()
        if not running:_prepare_activity.event(message)


def prepare_button_text():
    return '(LOADING...PLEASE WAIT) Preparing current scene for sapien' if _prepare_running else 'Prepare current scene for sapien'


_pending_prepare_warning=None

def preparation_warnings(context,cfg):
    original_scenery.reset_cache()
    original_scenery.plan(context.scene,cfg)
    blockers=invisible_blocks.plan(context.scene,cfg)
    vehicle_placements=vehicles.plan(context.scene,cfg)
    warnings=geometry_export.warnings(context.scene)
    if blockers:warnings.append(str(len(blockers))+' invisible block(s) will use their original Halo 3 scenery and collision tags. Their preview materials are not required or exported.')
    if vehicle_placements:warnings.append(str(len(vehicle_placements))+' original vehicle(s) will be placed using their game tags. Vehicle physics and behavior come from the selected tag. Editable Colors materials are baked and applied to matching shader slots on a level-local vehicle copy.')
    selected=[o for o in geometry_export.objects(context.scene) if not geometry_export.is_sky(o)]
    issues,_,_=export_review.inspect(selected,cfg)
    if issues:
        lines=export_review.messages(issues)
        report=bpy.data.texts.get('HaloBridge export exclusions') or bpy.data.texts.new('HaloBridge export exclusions')
        report.clear();report.write('Objects with export problems (entire objects omitted only if skipping is enabled):\n\n'+'\n\n'.join(lines))
        if not cfg.get('skip_invalid'):
            raise ValidationError(lines+['Fix these objects, or enable Skip objects with export problems and prepare again to review the exclusions.'])
        if len(issues)==len(selected):raise ValidationError(lines+['No exportable objects remain. At least one valid mesh is required.'])
        warnings.extend('WILL NOT EXPORT — '+line for line in lines)
    return warnings

def draw_review_actions(layout,token,enabled=True):
    # Blender's native operator buttons expose alert/pressed states, not RGB fills.
    # Keep the affirmative action distinct without changing the user's global theme.
    row=layout.row();row.enabled=enabled;row.alert=False;row.scale_y=1.3
    op=row.operator('halo_bridge.confirm_prepare',text='Continue with warnings',icon='CHECKMARK',depress=True)
    op.token=token;op.accept=True
    row=layout.row();row.enabled=enabled;row.alert=True;row.scale_y=1.15
    op=row.operator('halo_bridge.confirm_prepare',text='Cancel',icon='CANCEL')
    op.token=token;op.accept=False


def _can_popup():
    # popup_menu without a real window (background mode) crashes Blender 5.2; the sidebar keeps the review.
    return not bpy.app.background

def confirm_map_warnings(context,cfg,error):
    global _pending_prepare_warning,_error,_message,_reported_issues
    # Reviewable limitations are not failed builds. Keep the decision available
    # in the sidebar even when Blender dismisses the transient popup.
    _error=''
    _reported_issues=[]
    _message='Preparation needs confirmation. Choose Continue with warnings or Cancel above the Prepare button.'
    token=str(time.time_ns())
    _pending_prepare_warning=dict(token=token,scene=context.scene.as_pointer(),config=dict(cfg),issues=list(error.issues))
    def draw(menu,ctx):
        layout=menu.layout
        layout.label(text=str(len(error.issues))+' warning(s) found. Continue exporting current geometry?',icon='ERROR')
        layout.label(text='Edits and deletions are exported. Original map geometry is never substituted.')
        layout.label(text='Required-file and compiler errors may still prevent completion.')
        layout.separator()
        for issue in error.issues[:8]:
            for line in textwrap.wrap(issue,width=95):layout.label(text=line)
        if len(error.issues)>8:layout.label(text='All '+str(len(error.issues))+' warnings are above the Prepare button.')
        layout.separator()
        draw_review_actions(layout,token)
    if _can_popup():context.window_manager.popup_menu(draw,title='Prepare for Sapien: review warnings',icon='ERROR')

class HBConfirmPrepare(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.confirm_prepare';bl_label='Continue with warnings'
    bl_description='Continue exporting current meshes after reviewing limitations, or cancel without preparing'
    bl_options={'INTERNAL'}
    token:StringProperty(options={'HIDDEN','SKIP_SAVE'})
    accept:BoolProperty(default=False,options={'HIDDEN','SKIP_SAVE'})
    def run(self,context):
        global _pending_prepare_warning,_message
        pending=_pending_prepare_warning
        if not pending or pending['token']!=self.token:raise RuntimeError('This confirmation expired. Prepare again.')
        _pending_prepare_warning=None
        if not self.accept:
            _message='Preparation cancelled. No level files were written.';prepare_status(_message);return {'CANCELLED'}
        if pending['scene']!=context.scene.as_pointer() or pending['config']!=export_config(context):
            raise RuntimeError('The scene or setup changed. Prepare again to review current warnings.')
        current=preparation_warnings(context,pending['config'])
        if current!=pending['issues']:
            raise RuntimeError('The detected issues changed. Prepare again to review the current list.')
        # One error boundary: nested bpy operators turn the detailed validation
        # error into a generic RuntimeError and overwrite its diagnostic report.
        return HBPrepare.run(self,context,warnings_accepted=True)

class HBDecimateDense(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.decimate_dense';bl_label='Add Decimate to dense objects now';bl_options={'REGISTER','UNDO'}
    bl_description='Add the Decimate modifier now (instead of when preparing) so you can check each object and change its Ratio in Modifier Properties first. Objects that already have it are left alone'
    def run(self,context):
        global _message
        from . import dense_meshes
        s=context.scene.halo_bridge
        added=dense_meshes.add(context.scene,s.decimate_threshold,s.decimate_ratio)
        _message=('Added a Decimate modifier ('+format(s.decimate_ratio,'.2f')+') to '+str(len(added))+' object(s): '+', '.join(o.name for o in added[:5])+(' ...' if len(added)>5 else '')+'. Select one and change its Ratio in Modifier Properties if needed.'
                  if added else 'No exported object over '+format(s.decimate_threshold,',')+' triangles is missing the modifier.')

class HBAddPortals(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.add_portals';bl_label='Add portal grid';bl_options={'REGISTER','UNDO'}
    bl_description='Add vertical +portal planes across the level (one "HaloBridge Portals" object in a Portals collection, replacing an earlier grid). Halo Tool cuts the level structure into clusters at them: big or very dense levels stay under Halo 3\'s per-section limits and draw faster. Move or delete planes freely; any object made only of +portal faces is used'
    def run(self,context):
        global _message
        from . import portals
        s=context.scene.halo_bridge
        units=float(context.scene.get('hb_working_units',100))
        count=portals.add_grid(context.scene,s.portal_spacing,units)
        _message=(str(count)+' +portal plane(s) added every '+format(s.portal_spacing,'g')+' world units.' if count else
                  'The level is smaller than the spacing; no portal planes were needed.')

class HBRetryRejected(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.retry_rejected';bl_label='Retry objects Tool rejected';bl_options={'REGISTER','UNDO'}
    bl_description='Include the objects Halo Tool rejected in earlier preparations again (an object is also retried automatically once you change it)'
    def run(self,context):
        global _message
        rejected=tool_rejected(context.scene)
        for obj in rejected:
            for key in ('hb_tool_rejected','hb_tool_rejected_shape'):
                if key in obj:del obj[key]
        _message=str(len(rejected))+' object(s) will be included in the next preparation.'

class HBPrepare(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.prepare';bl_label='Prepare current scene for sapien'
    bl_description='Compile current meshes, edits and modifiers as static geometry with generated surface collision; optionally build draft lighting, then test in Sapien'
    warnings_accepted:BoolProperty(default=False,options={'HIDDEN','SKIP_SAVE'})
    def invoke(self,context,event):
        if _task or _prepare_running:return {'CANCELLED'}
        prepare_status('Starting scene preparation...',True)
        scene=context.scene.as_pointer()
        for area in context.screen.areas:area.tag_redraw()
        def begin():
            if bpy.context.scene.as_pointer()!=scene:
                prepare_status('Preparation cancelled: active scene changed.');return
            bpy.ops.halo_bridge.prepare('EXEC_DEFAULT')
        bpy.app.timers.register(begin,first_interval=.15)
        return {'FINISHED'}
    def run(self,context,warnings_accepted=None):
        if warnings_accepted is None:warnings_accepted=self.warnings_accepted
        if not _retrying:
            # A new preparation starts from the usual portals and cluster size; the level may have changed.
            for key in RETRY_SETTINGS:
                if key in context.scene:del context.scene[key]
        prepare_status('Validating current scene...',True)
        reconcile_preview_copies(context)
        s=context.scene.halo_bridge
        if s.decimate_dense:
            from . import dense_meshes
            added=dense_meshes.add(context.scene,s.decimate_threshold,s.decimate_ratio)
            if added:prepare_status('Added a Decimate modifier ('+format(s.decimate_ratio,'.2f')+') to '+str(len(added))+' object(s) over '+format(s.decimate_threshold,',')+' triangles: '+', '.join(o.name for o in added[:5])+(' ...' if len(added)>5 else ''),True)
        cfg=export_config(context)
        safe_level(cfg['level']);build.ensure_sapien_closed()
        out=Path(cfg['cache'])/'projects'/cfg['level']/'export'/('level_'+str(__import__('time').time_ns())+'.ASS');out.parent.mkdir(parents=True,exist_ok=True)
        remove_old_exports(out.parent)
        last_redraw=[0.0]
        source_scene=context.scene.as_pointer()
        def report_progress(message):
            global _message
            _message=message;prepare_status(message,True)
            # Background compiler callbacks only update plain strings. Blender RNA
            # and redraw requests are restricted to main-thread scene conversion.
            if threading.current_thread() is threading.main_thread() and not bpy.app.background:
                now=time.monotonic()
                if now-last_redraw[0]>.25 and bpy.context.scene.as_pointer()==source_scene:
                    last_redraw[0]=now
                    for area in context.screen.areas:area.tag_redraw()
                    if bpy.ops.wm.redraw_timer.poll():bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP',iterations=1)
        def done(path):
            global _message,_box_retry
            _box_retry=0
            _message='Ready: '+path;prepare_status('Finished. Level prepared for Sapien.')
            skipped=set(s.lower() for s in cfg.get('lighting_skipped_shaders',[]))
            if skipped:
                users=sorted({o.name for o in geometry_export.objects(context.scene) for m in getattr(o.data,'materials',[]) or []
                              if m and m.get('hb_shader','').replace('/','\\').lower() in skipped})
                if users:cfg.setdefault('compiler_warnings',[]).append('Objects using the shader(s) test lighting could not process: '+', '.join(users[:20])+(' ...' if len(users)>20 else ''))
                _message+='\nTest lighting was skipped; see the preparation report.'
            issues=cfg.get('compiler_warnings',[])
            if issues:
                _message+='\nPrepared with '+str(len(issues))+' geometry warning(s). Open the preparation report for affected objects.'
                prepare_status('Finished with '+str(len(issues))+' geometry warning(s). Review the preparation report before playtesting.')
                report=bpy.data.texts.get('HaloBridge preparation report')
                if report:report.write('\n\nCompiler geometry warnings (level built, but these surfaces need attention):\n'+'\n'.join(issues))
            if context.scene.halo_bridge.open_sapien:open_sapien(cfg)
        warnings=preparation_warnings(context,cfg)
        if warnings and not warnings_accepted:
            prepare_status('Waiting for confirmation: review preparation warnings.')
            confirm_map_warnings(context,cfg,ValidationError(warnings,'Geometry export warnings'));return
        if context.scene.halo_bridge.sky_selected=='AUTO' and context.scene.halo_bridge.sky_choice in ('AUTO',''):
            manifests={o.get('hb_map_manifest') for o in geometry_export.objects(context.scene) if o.get('hb_map_manifest')}
            sources={read_json(p,{}).get('scenario','') for p in manifests}
            if len(sources)==1:
                candidate=next(iter(sources))
                if candidate and (Path(cfg['kit'])/'tags'/(candidate+'.scenario')).is_file():cfg['sky_scenario']=candidate
        global _prepare_activity
        _prepare_activity=PreparationActivity(Path(cfg['cache'])/'jobs'/('preparation-'+str(time.time_ns())+'.log'),report_progress)
        progress=_prepare_activity
        progress.stage(1,'Export current scene meshes')
        # The level file is written by the Halo toolset in background Blender processes,
        # reusing every unchanged mesh from the last preparation (ass_parts.py).
        cfg['ass_parts']=str(Path(cfg['cache'])/'projects'/cfg['level']/'ass_pieces');cfg['defer_ass']=True
        def finish(placements):
            report=bpy.data.texts.get('HaloBridge preparation report') or bpy.data.texts.new('HaloBridge preparation report')
            report.clear();report.write('Current Blender meshes exported. Edits, transforms, modifiers and deletions are included.\nStructure geometry: '+cfg.get('structure_source','current scene')+'\nSky: '+(('converted from '+cfg['sky_object']['name']) if cfg.get('sky_object') else cfg.get('sky_scenario','default'))+'\n\n'+'\n'.join(warnings))
            skipped=cfg.get('skipped_objects') or {}
            if skipped:
                report.write('\n\nLeft out (Skip objects with export problems):\n'+'\n'.join(name+': '+'; '.join(reasons) for name,reasons in skipped.items())+'\n')
                progress('Left out '+str(len(skipped))+' object(s) with export problems; they are listed in the preparation report (HaloBridge preparation report in the Text Editor).')
            for name,route in cfg.get('collision_routes',{}).items():report.write(f'\n{name}: {route}')
            if cfg.get('uv_repairs'):report.write('\n\nInvalid texture coordinates repaired (scene meshes unchanged):\n'+'\n'.join(cfg['uv_repairs']))
            job=cfg.pop('ass_job',None)
            def compile(cancel):
                if job:
                    from . import ass_parts
                    ass_parts.run(job,cancel,progress)
                return build.prepare(cfg,out,placements,cancel,progress)
            start(bpy.context,compile,done,'Compiling current scene geometry...')
            _task.is_prepare=True
        def exporting():
            # Runs from poll() a little per tick, so Blender keeps redrawing and responding.
            try:placements=yield from geometry_export.export_steps(cfg,out,progress=progress)
            except ReferenceError as error:
                raise RuntimeError('An object was deleted or changed while preparation was reading the scene ('+str(error)+'). Prepare again, and leave the scene alone until stage 2 starts.') from error
            finish(placements)
        start(context,lambda cancel:None,lambda result:exporting(),'Exporting current scene meshes...')
        _task.is_prepare=True;_task.application_budget=.06


def open_sapien(cfg):
    build.ensure_sapien_closed()
    level=safe_level(cfg['level']);tag=Path(cfg['kit'])/'tags/levels/multi'/level/(level+'.scenario')
    if not tag.is_file():raise RuntimeError('Prepare this level successfully before opening Sapien.')
    process=subprocess.Popen([str(Path(cfg['kit'])/'sapien.exe'),str(tag)],cwd=cfg['kit'])
    def verify_launch():
        global _message,_error
        code=process.poll()
        if code is not None:
            _message='Sapien closed during startup. The prepared level is saved.'
            _error='Sapien exited with code '+str(code)+'. Open '+str(tag)+' from Sapien, started in '+cfg['kit']+'.'
            text=bpy.data.texts.get('HaloBridge diagnostics') or bpy.data.texts.new('HaloBridge diagnostics');text.clear();text.write(_error)
        return None
    bpy.app.timers.register(verify_launch,first_interval=5)

class HBOpen(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.open';bl_label='Open in Sapien'
    bl_description='Launch Sapien with the successfully prepared scenario for this output level; prepare the level first'
    def run(self,context):open_sapien(export_config(context))

class HBResolve(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.resolve';bl_label='Resolve conflict: use Blender'
    bl_description='Confirm that the next export may replace conflicting Sapien edits to Blender-owned placements; independently added Sapien content is kept'
    def invoke(self,context,event):return context.window_manager.invoke_props_dialog(self,width=440)
    def draw(self,context):
        self.layout.label(text='Next export will replace Sapien edits to Blender-owned placements.')
        self.layout.label(text='Sapien-owned objects and gameplay settings will be kept.')
    def run(self,context):
        cfg=export_config(context);build.ensure_sapien_closed();safe_level(cfg['level'])
        path=Path(cfg['cache'])/'projects'/cfg['level']/'manifest.json';manifest=read_json(path)
        if not manifest:raise RuntimeError('No previously successful export for this level.')
        def done(result):
            global _message
            write_json(path.with_suffix('.before-resolution.json'),manifest)
            manifest['state']=result['state'];write_json(path,manifest)
            _message='Conflict resolved explicitly. Prepare for Sapien to use Blender placements.'
        start(context,lambda cancel:jobs.helper('tags',dict(operation='inspect',kit=cfg['kit'],scenario=manifest['scenario'],output=str(Path(cfg['cache'])/'jobs/resolve.json')),Path(cfg['cache'])/'jobs',cancel),done,'Reading current placement state…')

class HBCancel(bpy.types.Operator):
    bl_idname='halo_bridge.cancel';bl_label='Cancel job'
    bl_description='Request cancellation of the current background job; preview loading stops and level builds restore the previous successful output'
    def execute(self,context):
        if _task and getattr(_task,'preview_generation',None) is not None:stop_preview(context)
        if _task:_task.cancel.set()
        return {'FINISHED'}

class HBReportDiagnostics(bpy.types.Operator):
    bl_idname='halo_bridge.report_diagnostics';bl_label='Report HaloBridge issues'
    bl_description='Write all detected issues to Blender Info and preserve the full diagnostic report'
    bl_options={'INTERNAL'}
    def execute(self,context):
        for issue in globals().get('_reported_issues',[]):self.report({'WARNING'},issue)
        self.report({'WARNING'},_message)
        return {'FINISHED'}

class HBDiagnostics(bpy.types.Operator):
    bl_idname='halo_bridge.diagnostics';bl_label='Open diagnostic report'
    bl_description='Show the latest HaloBridge error details in this area using Blender\'s Text Editor'
    text_name:StringProperty(default='HaloBridge diagnostics')
    def execute(self,context):
        text=bpy.data.texts.get(self.text_name) or bpy.data.texts.new(self.text_name)
        context.area.type='TEXT_EDITOR';context.area.spaces.active.text=text
        text.cursor_set(0,character=0)
        region=next((r for r in context.area.regions if r.type=='WINDOW'),None)
        if region:
            with context.temp_override(area=context.area,region=region):
                bpy.ops.text.move(type='FILE_TOP')
                bpy.ops.text.scroll(lines=-1000000)
        return {'FINISHED'}

_icon_token=None
_icons={}
def asset_icons():
    global _icon_token,_icons
    if _task:return {}
    token=(len(bpy.data.objects),len(bpy.data.materials))
    if token!=_icon_token:
        _icons={}
        for pool in (bpy.data.objects,bpy.data.materials):
            for obj in pool:
                asset_id=obj.get('hb_asset_id')
                if asset_id and obj.preview:_icons[asset_id]=obj.preview.icon_id
        _icon_token=token
    return _icons

class HB_UL_assets(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        icon_id=asset_icons().get(item.asset_id,0)
        layout.prop(item,'checked',text='')
        layout.label(text=item.name,icon_value=icon_id,icon='NONE' if icon_id else ('MATERIAL' if item.kind=='material' else 'OUTLINER_OB_MESH'))
        if item.kind=='material':layout.label(text='Material')
        if item.kind=='model':layout.label(text='Static model',icon='INFO')
        row=layout.row();row.enabled=_task is None
        op=row.operator('halo_bridge.list_action',text='',icon='HIDE_ON' if item.hidden else 'HIDE_OFF',emboss=False)
        op.action='UNHIDE' if item.hidden else 'HIDE';op.asset_id=item.asset_id
    def filter_items(self,context,data,propname):
        s=context.scene.halo_bridge;items=getattr(data,propname)
        visible=visibility_predicate(s)
        return [self.bitflag_filter_item if visible(i) else 0 for i in items],[]

class HBSelectCollisionIssues(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.select_collision_issues';bl_label='Select assets missing export collision'
    bl_description='Select placed assets that lack an exportable collision source, so you can replace or remove them; scene geometry is not changed'
    def run(self,context):
        global _message
        objects=[o for o in context.view_layer.objects if o.type=='MESH' and blender_ops.collision_issue(o)]
        if not objects:raise RuntimeError('No placed assets with missing export collision were found.')
        bpy.ops.object.select_all(action='DESELECT')
        selected_objects=[]
        for obj in objects:
            if obj.visible_get() and not obj.hide_select:obj.select_set(True);selected_objects.append(obj)
        if selected_objects:context.view_layer.objects.active=selected_objects[0]
        _message=f'Selected {len(selected_objects)} of {len(objects)} assets missing export collision. Hidden or selection-locked objects remain unselected. Choose a matching scenery or instance and use Swap selected object.'

def draw_messages(layout,context,popover=False):
    width=48 if popover else max(24,min(85,int((context.region.width if context.region else 360)/7)-5))
    notice=layout.box()
    heading=notice.row();heading.alert=bool(_error or _pending_prepare_warning);heading.scale_y=1.3
    heading.label(text='ACTION REQUIRED' if _error else ('REVIEW PREPARATION WARNINGS' if _pending_prepare_warning else 'Working…' if _task else 'Status'),icon='ERROR' if _error or _pending_prepare_warning else 'INFO')
    body=notice.column();body.alert=bool(_error)
    for paragraph in _message.splitlines():
        for line in textwrap.wrap(paragraph,width=width) or ['']:body.label(text=line)
    if _task:
        row=notice.row();row.alert=True;row.operator('halo_bridge.cancel',icon='CANCEL')
    if _error:
        row=notice.row();row.alert=True;row.operator('halo_bridge.diagnostics',icon='ERROR')
        if 'CONFLICT' in _error:
            row=notice.row();row.alert=True;row.scale_y=1.4
            row.operator('halo_bridge.resolve',text='Resolve Conflict: Use Blender',icon='FILE_REFRESH')
    if bpy.data.texts.get('HaloBridge map import report'):
        layout.operator('halo_bridge.diagnostics',text='Open map import report',icon='INFO').text_name='HaloBridge map import report'
    if bpy.data.texts.get('HaloBridge preparation report'):
        layout.operator('halo_bridge.diagnostics',text='Open preparation report',icon='INFO').text_name='HaloBridge preparation report'
    if bpy.data.texts.get('HaloBridge original copy report'):
        layout.operator('halo_bridge.diagnostics',text='Open original copy report',icon='INFO').text_name='HaloBridge original copy report'

class HBMessages(bpy.types.Panel):
    bl_label='HaloBridge Warnings and Messages';bl_idname='HB_PT_messages';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='HaloBridge';bl_order=-10
    def draw(self,context):draw_messages(self.layout,context)

class HBMessagesPopover(bpy.types.Panel):
    bl_label='HaloBridge Warnings and Messages';bl_idname='HB_PT_messages_popover';bl_space_type='VIEW_3D';bl_region_type='HEADER';bl_ui_units_x=28
    def draw(self,context):draw_messages(self.layout,context,popover=True)

def draw_message_header(self,context):
    row=self.layout.row(align=True)
    row.alert=bool(_error or _pending_prepare_warning)
    row.popover(panel='HB_PT_messages_popover',text='HaloBridge Warnings and Messages',icon='ERROR' if _error else 'INFO')
    row.label(text=textwrap.shorten(_message.replace('\n',' '),width=65,placeholder='…'))

class HBCenterMapOrigins(Guard,bpy.types.Operator):
    bl_idname='halo_bridge.center_map_origins';bl_label='Origin to Geometry - all scene meshes';bl_options={'REGISTER','UNDO'}
    bl_description='Run Blender Origin to Geometry (Median Center) on every mesh in this scene, including authored, hidden and previously centered meshes'
    def run(self,context):
        global _message
        if context.mode!='OBJECT':raise RuntimeError('Switch to Object Mode first.')
        count=map_scene.center_existing_origins(context)
        _message=f'Set Origin to Geometry for {count} scene meshes.'

class HBPanel(bpy.types.Panel):
    bl_label='HaloBridge';bl_idname='HB_PT_main';bl_space_type='VIEW_3D';bl_region_type='UI';bl_category='HaloBridge'
    def draw(self,context):
        l=self.layout;s=context.scene.halo_bridge
        row=l.row();row.enabled=_task is None;row.prop(s,'game')
        # Every section collapses except the warnings, preparation status and Prepare button.
        _,box=compat.section(l,'hb_setup','Folders and Setup','PREFERENCES')
        if box:
            game=games.GAMES[s.game]
            for n in ('kit','maps'):box.prop(s,n,text=game['label']+(' Editing Kit' if n=='kit' else ' .map Files'))
            row=box.row();row.operator('halo_bridge.detect',depress=True);row.operator('halo_bridge.check_setup')
            row=box.row();row.enabled=_task is None;row.operator('halo_bridge.ground',depress=True)
            box.operator('halo_bridge.view_distance',icon='HIDE_OFF')
            if compat.has_eevee_shadow_switch(context.scene):
                shadows=compat.eevee_shadows(context.scene)
                box.operator('halo_bridge.viewport_shadows',text='Viewport Shadows: On (Slower on large levels)' if shadows else 'Viewport Shadows: Off (Faster)',
                             icon='LIGHT_SUN' if shadows else 'SHADING_SOLID',depress=not shadows)
            row=box.row();row.enabled=_task is None
            sky_state='ON' if s.import_sky else 'OFF'
            row.prop(s,'import_sky',text='Import sky with the level: '+sky_state,toggle=True,icon='WORLD')
            if game.get('scenario_enabled'):
                level=box.box();level.label(text='Import level from .scenario',icon='WORLD_DATA')
                row=level.row(align=True);row.enabled=_task is None
                row.prop(s,'scenario_path',text='')
                row.operator('halo_bridge.choose_scenario',text='',icon='DOWNARROW_HLT')
                row=level.row();row.enabled=_task is None;row.scale_y=1.2
                row.operator('halo_bridge.import_scenario',icon='IMPORT',depress=True)
                row=level.row();row.enabled=_task is None
                row.operator('halo_bridge.index_scenario',icon='ASSET_MANAGER',depress=True)
                note=('Placements from the kit tags; Reach geometry from the matching .map.' if s.game=='reach'
                      else 'The kit\'s Tool builds a map from the tags first.' if game.get('classic')
                      else 'Reads the level tags directly. Textures from the matching .map.')
                level.label(text=note,icon='INFO')
            if s.game=='h2a':
                # Halo 2: Anniversary campaign (Saber3D .pck), above the groundhog .map import.
                campaign=box.box();campaign.label(text='Import Anniversary campaign level',icon='WORLD')
                row=campaign.row(align=True);row.enabled=_task is None
                row.prop(s,'h2a_campaign_level',text='')
                row.operator('halo_bridge.choose_campaign_level',text='',icon='DOWNARROW_HLT')
                row=campaign.row();row.enabled=_task is None;row.scale_y=1.2
                row.operator('halo_bridge.import_h2a_campaign',icon='IMPORT',depress=True)
                row=campaign.row();row.enabled=_task is None
                row.operator('halo_bridge.index_h2a_campaign',icon='ASSET_MANAGER',depress=True)
                row=campaign.row();row.enabled=_task is None
                row.prop(s,'max_texture_size',text='Reduce Texture Size')
                campaign.label(text='Remastered visuals from halo2\\preload\\paks, in Halo 2 coordinates.',icon='INFO')
            maps=box.box();maps.label(text='Import entire .map',icon='FILE_BLEND')
            if s.game=='h2a':maps.label(text='Anniversary levels import from MCC\'s groundhog maps.',icon='INFO')
            maps.label(text='Choose .map file')
            row=maps.row(align=True);row.enabled=_task is None
            row.prop(s,'map_name',text='')
            row.operator('halo_bridge.choose_map',text='',icon='DOWNARROW_HLT')
            row=maps.row();row.enabled=_task is None
            row.operator('halo_bridge.import_map_scene',depress=True)
            row=maps.row();row.enabled=_task is None
            row.operator('halo_bridge.index',icon='ASSET_MANAGER',depress=True)
            box.operator('halo_bridge.center_map_origins')
            box.prop(s,'advanced')
            if s.advanced:
                box.prop(s,'cache',text='Storage location')
                box.label(text='Existing projects need their original records.')
        _,assets=compat.section(l,'hb_assets','Indexed Asset List','ASSET_MANAGER')
        if assets:
            assets.prop(s,'follow_outliner')
            row=assets.row()
            for redo,icon in ((False,'LOOP_BACK'),(True,'LOOP_FORWARDS')):
                control=row.row();control.enabled=_task is None and history_available(redo)
                control.operator('halo_bridge.list_history',text='Redo' if redo else 'Undo',icon=icon).redo=redo
            row=assets.row(align=True);row.prop(s,'asset_tab',expand=True)
            grid=assets.grid_flow(columns=3,align=True)
            for category in ('vegetation','rocks','structures','water','materials'):grid.prop(s,'show_'+category,toggle=True)
            assets.prop(s,'filter_level')
            row=assets.row(align=True);row.prop(s,'filter_source',expand=True)
            width=max(24,int(context.region.width/7)-6)
            for key in ('map','scenario'):
                if s.filter_source in ('ALL',key.upper()):
                    note=assets.column(align=True);note.scale_y=.8
                    for line in textwrap.wrap(SOURCE_SUMMARIES[key],width=width):note.label(text=line)
            search=assets.box().row(align=True)
            search.prop(s,'search',text='Search Assets',icon='VIEWZOOM')
            clear=search.row(align=True);clear.enabled=bool(s.search)
            clear.operator('halo_bridge.clear_search',text='',icon='X')
            if s.asset_tab=='HIDDEN' and not any(a.hidden for a in s.assets):
                empty=assets.box();empty.separator(factor=2)
                for line in ('Your Hidden Assets will show up','here when you [Hide] them.'):
                    row=empty.row();row.alignment='CENTER';row.label(text=line)
                empty.separator(factor=2)
            else:assets.template_list('HB_UL_assets','',s,'assets',s,'active_index',rows=7)
            visible=visibility_predicate(s)
            assets.label(text=str(sum(1 for item in s.assets if visible(item)))+' of '+str(len(s.assets))+' indexed assets shown')
            on=s.preview_enabled
            toggle=assets.row();toggle.enabled=on or _task is None
            toggle.operator('halo_bridge.toggle_preview',text='Preview Mode: ON' if on else 'Preview Mode: OFF',depress=on,icon=compat.icon('STRIP_COLOR_04','SEQUENCE_COLOR_04') if on else compat.icon('STRIP_COLOR_01','SEQUENCE_COLOR_01'))
            count=len(checked_ids(context))
            row=assets.row(align=True);row.operator('halo_bridge.check_assets',text='Select all').check=True
            row.operator('halo_bridge.check_assets',text='Clear checks').check=False;row.label(text=str(count)+' checked')
            row=assets.row();row.enabled=_task is None and count>0
            op=row.operator('halo_bridge.list_action',text='Unhide' if s.asset_tab=='HIDDEN' else 'Hide',icon='HIDE_ON' if s.asset_tab=='HIDDEN' else 'HIDE_OFF')
            op.action='UNHIDE' if s.asset_tab=='HIDDEN' else 'HIDE'
            row=assets.row();row.enabled=_task is None and count>0
            row.operator('halo_bridge.list_action',text='Delete checked from list',icon='TRASH').action='DELETE'
            row=assets.row();place=row.row();place.enabled=_task is None;place.operator('halo_bridge.place',depress=s.preview_enabled,icon='ADD')
        active=context.active_object
        if active and active.get('hb_parts_path'):
            _,parts=compat.section(l,'hb_parts','Model Parts and Variants','OUTLINER_OB_MESH')
            if parts:
                parts.label(text='Toggle parts; their positions stay unchanged.')
                choices=model_parts.choices(active);enabled=model_parts.enabled(active)
                opened=set(json.loads(active.get('hb_parts_open','[]')))
                for region in dict.fromkeys(value[0] for value in choices.values()):
                    group={key:value for key,value in choices.items() if value[0]==region}
                    row=parts.row(align=False);row.enabled=_task is None
                    arrow=row.row();arrow.ui_units_x=1.3
                    op=arrow.operator('halo_bridge.model_region_expand',text='',icon='TRIA_DOWN' if region in opened else 'TRIA_RIGHT');op.region=region
                    row.separator(factor=.5)
                    check=row.row();check.ui_units_x=1.3
                    op=check.operator('halo_bridge.model_part_toggle',text='',icon='CHECKBOX_HLT' if set(group)<=enabled else 'CHECKBOX_DEHLT');op.region=region;op.choice=''
                    row.label(text=region)
                    if region in opened:
                        for key,value in group.items():
                            row=parts.row();row.enabled=_task is None
                            op=row.operator('halo_bridge.model_part_toggle',text='    '+value[1],icon='CHECKBOX_HLT' if key in enabled else 'CHECKBOX_DEHLT',emboss=False);op.choice=key;op.region=''
                row=parts.row();row.enabled=_task is None and not active.get('hb_preview')
                row.operator('halo_bridge.model_parts_separate',icon='UNLINKED').all_variants=False
                row=parts.row();row.enabled=_task is None and not active.get('hb_preview')
                row.operator('halo_bridge.model_parts_separate',text='Separate all parts and variants into objects',icon='OUTLINER_OB_MESH').all_variants=True
                if active.get('hb_preview'):parts.label(text='Place first to select individual pieces.',icon='INFO')
        _,box=compat.section(l,'hb_selected','Selected Asset','OBJECT_DATA')
        if box:
            try:material_selected=selected(context)['kind']=='material'
            except Exception:material_selected=False
            material_target=context.active_object
            if material_target and material_target.get('hb_preview'):
                material_target=s.preview_previous_object
            has_material_target=material_target is not None and material_target.type=='MESH' and not material_target.get('hb_preview')
            box.label(text='Material only',icon='MATERIAL')
            apply=box.row();apply.enabled=_task is None and material_selected and has_material_target
            apply.operator('halo_bridge.place',text='Apply material to selected object').apply_material=True
            if not material_selected:box.label(text='Choose a material in the Asset List.',icon='INFO')
            elif not has_material_target:box.label(text='Select a mesh in the 3D View.',icon='INFO')
            try:
                asset=selected(context)
                status='Exports the current mesh as static geometry with generated collision.' if asset['kind']=='model' else asset.get('status','')
                for line in textwrap.wrap(status,width=44):box.label(text=line)
                box.label(text=('.scenario: ' if asset.get('source')=='scenario' else '.map: ')+asset['level'])
                if asset.get('section',-1)>=0:box.label(text=asset['tag'].rsplit('\\',1)[-1]+' / section '+str(asset['section']))
                icon_id=asset_icons().get(asset['id'],0)
                if icon_id:box.template_icon(icon_value=icon_id,scale=6)
            except Exception:pass
            try:_,reason=replacement_target(context,selected(context))
            except Exception:reason='Choose an asset in the list to use as the replacement.'
            row=box.row();row.enabled=_task is None and not reason
            op=row.operator('halo_bridge.place',text='Swap selected object(s) to selected index asset');op.replace_selected=True
            if reason:
                for line in textwrap.wrap(reason,width=max(24,int(context.region.width/7)-6)):box.label(text=line)
            active=context.active_object
            if active and active.type=='MESH' and not vehicles.selected_vehicle(active) and not active.get('hb_preview'):
                # The selected 3D object's own collision.
                box.separator();box.label(text='Collision: '+active.name,icon='MOD_PHYSICS')
                box.prop(active,'hb_static_collision',text='')
                if len(getattr(context,'selected_objects',None) or ())>1:
                    box.label(text='Right-click > Copy to Selected for all selected.',icon='INFO')
            if active and active.type=='MESH' and games.native(active) and games.GAMES[s.export_target]['sapien_enabled'] and active.get('hb_source_tag'):
                box.separator();box.label(text='Original '+games.GAMES[s.export_target]['label']+' Vehicle',icon='AUTO')
                for line in textwrap.wrap('3D object: '+active.name,width=max(24,int(context.region.width/7)-6)):box.label(text=line)
                row=box.row();row.enabled=_task is None;row.operator('halo_bridge.find_vehicle')
                if json.loads(active.get('hb_vehicle_matches','[]')):
                    row=box.row();row.enabled=_task is None;row.operator('halo_bridge.choose_vehicle',icon='VIEWZOOM')
                if active.get('hb_vehicle_tag'):
                    for line in textwrap.wrap('Vehicle: '+active['hb_vehicle_tag'],width=max(24,int(context.region.width/7)-6)):box.label(text=line)
                    box.operator('halo_bridge.vehicle_static')
        active=context.active_object
        _,box=compat.section(l,'hb_materials','Shaders','MATERIAL')
        if box:
            active_material=active.active_material if active and active.type=='MESH' else None
            if active_material:
                box.label(text='Object: '+active.name,icon='OBJECT_DATA')
                box.label(text='Active material: '+active_material.name,icon='MATERIAL')
                if active_material.users>1:box.label(text='Shared material: affects other users.',icon='INFO')
            else:box.label(text='Select an object with a material.',icon='INFO')
            box.separator()
            box.operator('halo_bridge.scan_shaders',icon='FILE_REFRESH')
            box.prop(s,'shader_manual')
            if s.shader_manual:box.prop(s,'shader_path')
            else:
                choices=shader_choices.items(s,context)
                shader=s.shader_choice
                label=shader.replace('\\','/').rsplit('/',1)[-1] if shader and shader!='NONE' else 'Choose an existing shader...'
                row=box.row();row.enabled=len(choices)>1
                row.operator('halo_bridge.choose_shader',text=label,icon='VIEWZOOM')
            row=box.row();row.enabled=active_material is not None and _task is None
            row.operator('halo_bridge.shader',icon='CHECKMARK')
            box.label(text='Sets the shader used in Sapien.')
        _,edit=compat.section(l,'hb_editable','Editable Materials (Experimental)','BRUSH_DATA')
        if edit:
            draw_editable_materials(edit,context)
        _,box=compat.section(l,'hb_sky','Sapien Sky (Experimental)','WORLD')
        if box:
            width=max(24,int(context.region.width/7)-6)
            destination=games.destination(s).game
            box.label(text='Choose the sky used in Sapien.')
            row=box.row();row.enabled=_task is None
            if s.get('sky_game') is None:row.operator_menu_enum('halo_bridge.set_sky_game','game',text='Game: '+games.GAMES[destination]['label'])
            else:row.prop(s,'sky_game',text='Game')
            if skies.kit_sky(s):
                selected_sky=s.sky_selected if s.sky_selected!='AUTO' else (s.sky_choice or 'AUTO')
                label=selected_sky.replace('\\','/').rsplit('/',1)[-1] if selected_sky!='AUTO' else 'Original map / default sky'
                row=box.row();row.enabled=_task is None;row.operator('halo_bridge.refresh_skies',icon='FILE_REFRESH')
                row=box.row(align=True);row.enabled=_task is None
                row.label(text='Sky:')
                row.operator_menu_enum('halo_bridge.choose_sky','choice',text=label,icon='WORLD')
                available=max(0,len(skies.items(s,context))-1)
                box.label(text=str(available)+' map skies available' if available else 'Scan for map skies to populate this dropdown.',icon='INFO')
                if selected_sky!='AUTO':
                    for line in textwrap.wrap('Selected: '+selected_sky,width=width):box.label(text=line)
            else:
                current=sky_export.sky_object(context.scene)
                label=current.name.removeprefix('Sapien sky - ') if current else 'Choose a sky...'
                row=box.row(align=True);row.enabled=_task is None
                row.label(text='Sky:')
                row.operator_menu_enum('halo_bridge.choose_game_sky','choice',text=label,icon='WORLD')
                available=max(0,len(skies.foreign_items(s,context))-1)
                game_label=games.GAMES[skies.sky_game(s)]['label']
                if not available:
                    for line in textwrap.wrap('Index a '+game_label+' .map or .scenario (switch Import game) to list its skies.',width=width):box.label(text=line,icon='INFO')
                else:box.label(text=str(available)+' '+game_label+' skies indexed',icon='INFO')
                for line in textwrap.wrap('Rebuilt as a '+games.GAMES[destination]['label']+' sky with converted textures. Lighting, fog and animated sky effects are not converted.',width=width):box.label(text=line)
                if current:
                    row=box.row();row.enabled=_task is None;row.operator('halo_bridge.remove_game_sky',icon='TRASH')
                elif skies.sky_game(s)!=destination:
                    box.label(text='No sky chosen: preparation will stop.',icon='ERROR')
        _,box=compat.section(l,'hb_prepare','(Experimental) Sapien Map Preparation','SCENE_DATA')
        if box:
            box.prop(s,'export_target')
            if s.game!=s.export_target:
                box.label(text='Mixed-game meshes convert to the destination.')
        if s.export_target=='reach':
            if box:
                box.label(text='Reach Sapien export is not available yet.',icon='INFO')
                box.label(text='Choose Halo 3 to prepare this scene.')
            return
        if box:
            box.label(text='Output Level Name (without .map)')
            box.prop(s,'level',text='')
            box.label(text='Current meshes: generated static collision.')
            box.prop(s,'max_texture_size')
            box.prop(s,'water_shader')
            box.prop(s,'effect_standins')
            box.prop(s,'decimate_dense')
            if s.decimate_dense:
                row=box.row(align=True);row.prop(s,'decimate_ratio');row.prop(s,'decimate_threshold')
                row=box.row();row.enabled=_task is None
                row.operator('halo_bridge.decimate_dense',icon='MOD_DECIM')
                box.label(text='Adjust each object\'s ratio in Modifier Properties.',icon='INFO')
            row=box.row(align=True);row.enabled=_task is None
            row.operator('halo_bridge.add_portals',icon='MOD_BOOLEAN');row.prop(s,'portal_spacing')
            box.prop(s,'skip_invalid')
            rejected=tool_rejected(context.scene)
            if rejected:
                row=box.row();row.enabled=_task is None
                row.operator('halo_bridge.retry_rejected',text='Retry '+str(len(rejected))+' object(s) Tool rejected',icon='FILE_REFRESH')
            box.prop(s,'quick_test')
            box.prop(s,'show_tool_markers')
            box.prop(s,'lighting')
            if s.lighting:
                box.prop(s,'h2_lightmaps')
                if s.h2_lightmaps:
                    # Halo 2 settings only while Halo 2's own lighting is used.
                    h2=box.box();h2.label(text='Halo 2 lighting',icon='LIGHT_SUN')
                    h2.prop(s,'h2_lightmap_brightness')
                    h2.label(text='Halo 2 sky light (1 = default):')
                    row=h2.row(align=True);row.prop(s,'h2_sun_strength');row.prop(s,'h2_sky_strength')
                box.prop(s,'lighting_baker')
                if s.lighting_baker=='H3LM':
                    box.prop(s,'h3lm_path')
                    row=box.row(align=True);row.prop(s,'h3lm_quality',text='Quality');row.prop(s,'h3lm_ao')
                    box.prop(s,'h3lm_per_pixel')
                    if not build.h3lm_exe(bpy.path.abspath(s.h3lm_path) if s.h3lm_path else ''):
                        box.label(text='Choose the folder with h3lm-lm.exe.',icon='ERROR')
                    if s.h3lm_ao:box.label(text='Ambient occlusion darkens corners and interiors.',icon='INFO')
            box.prop(s,'open_sapien')
        l.label(text='HaloBridge Warnings and Messages',icon='INFO')
        draw_messages(l,context)
        status=l.box();status.label(text='Map Preparation Status',icon='INFO')
        width=max(24,int(context.region.width/7))
        if _prepare_activity:
            status.label(text=_prepare_activity.phase)
            elapsed=int((_prepare_activity.ended or time.monotonic())-_prepare_activity.started)
            status.label(text=f'Total elapsed: {elapsed//60:02}:{elapsed%60:02}')
            status.label(text='Stage counts do not estimate time remaining.')
            upcoming=('Scene export','Materials','Geometry and collision','Sky and scenario','Lighting / final checks')[_prepare_activity.stage_number:]
            if upcoming and _prepare_running:
                for line in textwrap.wrap('Still to run: '+', '.join(upcoming),width=width):status.label(text=line)
        for paragraph in _prepare_status.splitlines():
            for line in textwrap.wrap(paragraph,width=width):status.label(text=line)
        if _prepare_activity:
            status.separator();status.label(text='Recent preparation activity',icon='TIME')
            for entry in _prepare_activity.recent[-3:]:
                for line in textwrap.wrap(entry,width=width):status.label(text=line)
            status.operator('halo_bridge.activity_log',text='Open live activity log',icon='TEXT')
            row=status.row();row.enabled=bool(_prepare_activity.current_log)
            row.operator('halo_bridge.activity_log',text='Open live compiler output',icon='CONSOLE').raw=True
        if _task and getattr(_task,'is_prepare',False):status.operator('halo_bridge.cancel',text='Cancel preparation',icon='CANCEL')
        if _pending_prepare_warning and _pending_prepare_warning['scene']==context.scene.as_pointer():
            review=l.box();heading=review.row();heading.alert=True;heading.scale_y=1.25
            heading.label(text='Review preparation warnings',icon='ERROR')
            for issue in _pending_prepare_warning['issues']:
                for line in textwrap.wrap(issue,width=width):review.label(text=line)
            draw_review_actions(review,_pending_prepare_warning['token'],_task is None and not _prepare_running)
        row=l.row();row.enabled=_task is None and not _prepare_running
        row.scale_y=1.3;row.operator('halo_bridge.prepare',text=prepare_button_text(),icon='EXPORT',depress=True)
        row=l.row();row.enabled=_task is None;row.scale_y=1.2;row.operator('halo_bridge.open',icon='PLAY',depress=True)


def draw_editable_materials(edit,context):
    """Editable material controls; each terrain shader layer is its own collapsible section."""
    target=context.active_object;material=target.active_material if target and target.type=='MESH' else None
    usable=_task is None and material is not None and not target.get('hb_preview') if target else False
    row=edit.row();row.enabled=usable
    row.operator('halo_bridge.read_shader_textures')
    row=edit.row();row.enabled=usable
    if not vehicles.selected_vehicle(target):
        row.operator('halo_bridge.custom_material',text='Create paintable terrain').mode='terrain'
    row.operator('halo_bridge.custom_material',text='Create editable colors').mode='colors'
    if not (material and material.get('hb_custom_shader')):return
    edit.label(text='Paint exports on this vehicle placement.' if vehicles.selected_vehicle(target) else
               'Exports as a Halo 3 terrain shader (full-resolution tiled layers).' if editable_materials.exports_terrain_shader(material) else
               'Bakes to custom Halo 3 textures on preparation.')
    edit.prop(material,'hb_resolution',text='Texture resolution')
    edit.prop(material,'hb_show_repeat',text='Repeat settings',icon='TRIA_DOWN' if material.hb_show_repeat else 'TRIA_RIGHT',emboss=False)
    nodes=material.node_tree.nodes
    layers=json.loads(material.get('hb_layers','[]'))
    shown=set()
    def image_row(parent,name,label=None,paint=True):
        node=nodes.get(name)
        if not node or node.type!='TEX_IMAGE':return
        shown.add(name)
        parent.label(text=(label or name)+(' — '+node.label if node.label and node.label!=name else ''))
        row=parent.row(align=True);row.template_ID(node,'image')
        row.operator('halo_bridge.custom_load_image',text='',icon='FILE_FOLDER').node_name=name
        if paint and name!='Paint Mask':row.operator('halo_bridge.custom_paint',text='',icon='BRUSH_DATA').node_name=name
        tiling=nodes.get(name+' Tiling')
        if tiling and material.hb_show_repeat:
            row=parent.row(align=True)
            for axis in range(3):row.prop(tiling.inputs[1],'default_value',index=axis,text='XYZ'[axis])
    if material['hb_custom_shader']=='terrain':
        # Layered Halo terrain has up to four shaders (blend channels R, G, B, A); the
        # fallback terrain editor has three. Each one collapses to a header with its Paint button.
        groups=[('Shader '+str(i+1),'Shader '+str(i+1),i,None) for i in range(len(layers))] if layers else \
               [('Grass','Shader 1',0,'GRASS'),('Rock','Shader 2',1,'ROCK'),('Dirt','Shader 3',2,'DIRT'),('Layer 4','Shader 4',3,'LAYER4')]
        groups=[g for g in groups if layers or nodes.get(g[0])]
        for node_name,title,index,legacy in groups:
            node=nodes.get(node_name)
            texture=node.label if node and node.label and node.label!=node_name else ''
            header,body=compat.section(edit,'hb_layer_'+str(index),title+(' — '+texture if texture else ''),'TEXTURE',default_closed=True)
            op=header.operator('halo_bridge.custom_paint',text='Paint '+title if header is body else 'Paint',icon='BRUSH_DATA')
            if layers:op.paint_channel=index
            else:op.layer=legacy
            if body:
                for suffix,label in (('',title),(' Detail',title+' detail'),(' Normal',title+' normal')):image_row(body,node_name+suffix,label)
            else:
                shown.update(node_name+suffix for suffix in ('',' Detail',' Normal'))
        count=editable_materials.terrain_layer_count(material) if editable_materials.exports_terrain_shader(material) else editable_materials.MAX_TERRAIN_LAYERS
        if count<editable_materials.MAX_TERRAIN_LAYERS:
            edit.operator('halo_bridge.add_terrain_layer',text='Add layer '+str(count+1)+(' (paint with white)' if layers else ' (paint with blue)'),icon='ADD')
        if layers:
            image_row(edit,'Original Blend')
            edit.operator('halo_bridge.custom_paint',text='Paint original blend').paint_channel=4
        else:
            image_row(edit,'Paint Mask',paint=False)
        shown.add('Paint Mask')
        for node in nodes:
            if node.type=='TEX_IMAGE' and node.name not in shown:image_row(edit,node.name)
    else:
        for name in ('Base Texture','Paint Mask','Normal Texture'):image_row(edit,name)
        edit.label(text=material.get('hb_mask_source','Color mask'))
        for index in range(1,5):edit.prop(nodes['Color '+str(index)].inputs[2],'default_value',text='Color '+str(index))
        edit.label(text='Mask channels R / G / B / Alpha control colors 1–4.')
    edit.operator('halo_bridge.custom_pack',icon='PACKAGE')
    edit.label(text='Use one UV tile (0–1). Original tags stay unchanged.')


classes=(HBChooseScenario,HBImportScenario,HBIndexScenario,HBCustomMaterial,HBCustomLoadImage,HBCustomPaint,HBAddTerrainLayer,HBCustomPack,HBReadShaderTextures,HBModelRegionExpand,HBModelPartToggle,HBModelPartsSeparate,HBChooseMap,HBFindVehicle,HBChooseVehicle,HBVehicleStatic,HBActivityLog,HBApplyExtracted,HBAsset,HBSettings,HBDetect,HBCheckSetup,HBScan,HBIndex,HBIndexH2ACampaign,HBPlace,HBClearSearch,HBCheckAssets,HBListHistory,HBListAction,HBPlaceChecked,HBImportMapScene,HBChooseCampaignLevel,HBImportH2ACampaign,HBViewDistance,HBViewportShadows,HBPreviewToggle,HBGround,HBScanShaders,HBChooseShader,HBShader,HBChooseSky,HBChooseGameSky,HBSetSkyGame,HBRemoveGameSky,HBRefreshSkies,HBDecimateDense,HBAddPortals,HBRetryRejected,HBPrepare,HBConfirmPrepare,HBOpen,HBResolve,HBCancel,HBDiagnostics,HBReportDiagnostics,HBSelectCollisionIssues,HBCenterMapOrigins,HB_UL_assets,HBMessages,HBMessagesPopover,HBPanel)

def shadows_off_by_default():
    """Viewport Shadows start Off (faster) once per scene; the button's later choice is kept."""
    for scene in bpy.data.scenes:
        try:
            if scene.get('hb_shadows_default') or not compat.has_eevee_shadow_switch(scene):continue
            compat.set_eevee_shadows(scene,False);scene['hb_shadows_default']=True
        except Exception:pass  # restricted context while a file is loading; the next load retries

@persistent
def load_catalogue(_=None):
    global _catalogue,_message
    s=bpy.context.scene.halo_bridge
    shadows_off_by_default()
    from . import regular_preview
    for mat in bpy.data.materials:regular_preview.refresh_gain(mat)
    changed,folders=source_names.restore()
    if folders and not _task:
        def done(unresolved):
            global _message
            count,_=source_names.restore()
            _message='Source material and texture names updated.'
            if unresolved:_message+=' Some texture names could not be recovered because their source map or catalogue is unavailable.'
        directory=Path(config(bpy.context)['cache'])/'jobs'
        start(bpy.context,lambda cancel:source_names.fetch_names(folders,directory,cancel),done,'Looking up original Halo texture names...')
    if s.cache:
        try:
            ensure_catalogue(bpy.context,force=True)
            refresh(bpy.context,persist=False)
            if not _task:_message='Catalogue loaded. Search for an asset to place.'
        except Exception as e:_message='Could not load catalogue: '+str(e)

def register():
    for cls in classes:bpy.utils.register_class(cls)
    bpy.types.VIEW3D_HT_header.append(draw_message_header)
    bpy.types.Scene.halo_bridge=PointerProperty(type=HBSettings)
    bpy.types.Object.hb_static_collision=EnumProperty(name='Static collision',items=[('AUTO','(Default) Automatic','Prefer matching original collision from the source Editing Kit, then use a box or mesh fallback'),('SURFACE','Mesh surfaces','Build collision from eligible material surfaces'),('BOX','Simple box','Use one solid bounding box around eligible geometry, including gaps inside it'),('NO_LEAVES','No leaf collision','Vegetation: see-through surfaces (leaf cards, cut-out or blended materials) are walked through; trunks and other solid surfaces keep their collision'),('NONE','No collision','Rendered only: players, vehicles and projectiles pass through the whole object')],default='AUTO')
    bpy.types.Material.hb_show_repeat=BoolProperty(default=False)
    bpy.types.Material.hb_resolution=EnumProperty(items=[(str(n),str(n),'',n) for n in (512,1024,2048,4096)],get=lambda m:int(m.get('hb_bake_size',1024)),set=lambda m,n:m.__setitem__('hb_bake_size',n))
    bpy.types.Material.hb_collision_mode=EnumProperty(name='Export collision',description='Controls collision generated from this material during static scene export',items=[('AUTO','Automatic','Halo foliage shaders and explicit render-only materials do not generate collision; other surfaces remain collidable'),('SOLID','Collidable','Generate collision from these surfaces, including foliage'),('RENDER_ONLY','Render only (no collision)','Keep these surfaces visible but omit them from collision; useful for leaf cards and decorative foliage')],default='AUTO')
    navigation.register()
    bpy.app.handlers.undo_pre.append(cancel_before_history)
    bpy.app.handlers.redo_pre.append(cancel_before_history)
    bpy.app.handlers.load_post.append(load_catalogue)
    bpy.app.handlers.depsgraph_update_post.append(paste_selection_updated)
    bpy.app.timers.register(load_catalogue,first_interval=.1)
    bpy.app.timers.register(check_preview_copies,first_interval=.25,persistent=True)

def unregister():
    navigation.unregister()
    for handlers in (bpy.app.handlers.undo_pre,bpy.app.handlers.redo_pre):
        if cancel_before_history in handlers:handlers.remove(cancel_before_history)
    bpy.types.VIEW3D_HT_header.remove(draw_message_header)
    if _task:_task.cancel.set()
    if bpy.app.timers.is_registered(preview_tick):bpy.app.timers.unregister(preview_tick)
    if bpy.app.timers.is_registered(poll):bpy.app.timers.unregister(poll)
    if bpy.app.timers.is_registered(load_catalogue):bpy.app.timers.unregister(load_catalogue)
    if bpy.app.timers.is_registered(check_preview_copies):bpy.app.timers.unregister(check_preview_copies)
    if load_catalogue in bpy.app.handlers.load_post:bpy.app.handlers.load_post.remove(load_catalogue)
    if paste_selection_updated in bpy.app.handlers.depsgraph_update_post:bpy.app.handlers.depsgraph_update_post.remove(paste_selection_updated)
    del bpy.types.Scene.halo_bridge
    del bpy.types.Object.hb_static_collision
    del bpy.types.Material.hb_show_repeat
    del bpy.types.Material.hb_resolution
    del bpy.types.Material.hb_collision_mode
    for cls in reversed(classes):bpy.utils.unregister_class(cls)

