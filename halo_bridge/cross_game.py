"""Convert other games' imported preview materials into project-local destination shaders.

Any material whose shader comes from a game other than the Sapien destination
(Reach, ODST in a Halo 3 level, Halo CE, Halo 2, ...) is rebuilt from its
preview textures. Halo 3 and ODST share tag paths, so a shader that already
exists in the destination kit is reused instead of converted.
"""
import hashlib
import json
from pathlib import Path
import bpy
import numpy as np
from .diagnostics import ValidationError
from . import compat, games


def _kit_has_shader(kit,tag):
    if not kit or not tag:return False
    from .export_review import shader_file
    try:shader_file(kit,tag);return True
    except ValueError:return False


def converts(obj,mat,config=None):
    """True when this material must be rebuilt from its preview textures."""
    target=(config or {}).get('game') or games.target_game()
    if not games.needs_conversion(obj,mat,target):return False
    source=games.material_game(obj,mat,target)
    if games.shares_tags(source,target) and config and _kit_has_shader(config.get('kit'),mat.get('hb_shader','')):
        return False
    return True


def reach_materials(objects,config=None):
    """Materials needing conversion (name kept for compatibility; covers every source game)."""
    return {m.as_pointer():m for o in objects for m in o.data.materials
            if m and not m.name.startswith('+') and (m.get('hb_custom_shader') or converts(o,m,config))}

converted_materials=reach_materials


def texture(socket):
    if not socket.is_linked:return None
    link=socket.links[0];node=link.from_node;channel=link.from_socket.name
    if node.type=='NORMAL_MAP':return texture(node.inputs['Color'])
    if node.type=='SEPARATE_COLOR':
        result=texture(node.inputs[0])
        return (result[0],{'Red':0,'Green':1,'Blue':2}[channel],result[2]) if result else None
    if node.type!='TEX_IMAGE' or not node.image:
        raise ValueError('Unsupported material nodes. Use the imported image textures or assign a Halo 3 shader.')
    tile=(1.,1.)
    if node.inputs['Vector'].is_linked:
        mapping=node.inputs['Vector'].links[0].from_node
        if mapping.type=='VECT_MATH' and mapping.operation=='MULTIPLY':tile=tuple(mapping.inputs[1].default_value[:2])
        elif mapping.type!='TEX_COORD':raise ValueError('Unsupported texture mapping; use imported UV mapping.')
    if not all(np.isfinite(x) and x>0 for x in tile):raise ValueError('Texture tiling must be positive.')
    return node.image,3 if channel=='Alpha' else None,tile


def _recorded(mat,usage):
    """The material's original texture of this usage, from its import metadata."""
    import json
    try:entries=json.loads(mat.get('hb_texture_sources','[]'))
    except ValueError:return None
    entry=next((t for t in entries if t.get('usage')==usage),None)
    if not entry:return None
    path=Path(mat.get('hb_texture_directory',''))/entry['path']
    if not path.is_file():raise ValueError('Missing texture: '+str(path))
    image=bpy.data.images.load(str(path),check_existing=True)
    if usage=='normal':image.colorspace_settings.name='Non-Color'
    tile=tuple(float(x) for x in (entry.get('tiling') or (1.,1.))[:2])
    if not all(np.isfinite(x) and x>0 for x in tile):tile=(1.,1.)
    channel={1:0,2:1,4:2}.get(entry.get('channels',8),3)
    return image,channel,tile


def details(mat):
    """The material's tiling detail maps from its import metadata, as (image, tiling) pairs:
    [] , [detail] (multiplied over the base) or [first, second] (a Halo 2 detail_blend
    shader: the base map's alpha blends the two, 0 = first). Neutral default maps are left out.
    Only Halo 2 shaders, whose detail maps multiply the base color by two like Halo 3's."""
    if not mat.get('hb_h2_template'):return []
    try:entries=json.loads(mat.get('hb_texture_sources','[]'))
    except ValueError:return []
    found=[t for t in entries if t.get('usage')=='diffuse_detail' and not str(t.get('name','')).lower().startswith('shaders\\default_bitmaps')]
    blended=sorted((t for t in found if t.get('blend_channel') in (1,2)),key=lambda t:t['blend_channel'])
    if len(blended)==2:found=blended
    elif len(found)!=1 or found[0].get('blend_channel'):return []
    result=[]
    for entry in found:
        path=Path(mat.get('hb_texture_directory',''))/entry['path']
        if not path.is_file():raise ValueError('Missing texture: '+str(path))
        tile=tuple(float(x) for x in (entry.get('tiling') or (1.,1.))[:2])
        if not all(np.isfinite(x) and x>0 for x in tile):tile=(1.,1.)
        result.append((bpy.data.images.load(str(path),check_existing=True),tile))
    return result


def sources(mat):
    """(base, normal, alpha) texture sources: (image, channel, tiling) or None each.

    Simple preview node trees (and user edits to them) are read from the nodes.
    Layered/detail previews (Halo 3, ODST, Halo 2 ...) fall back to the textures
    recorded when the material was imported.
    """
    bsdf=next((n for n in mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None) if compat.nodes_enabled(mat) else None
    transparent=compat.is_transparent(mat)
    try:
        if not bsdf:raise ValueError('No Principled preview material found.')
        base=texture(bsdf.inputs['Base Color']);normal=texture(bsdf.inputs['Normal'])
        alpha=texture(bsdf.inputs['Alpha']) if transparent else None
        return base,normal,alpha,bsdf
    except ValueError:
        if not mat.get('hb_texture_sources'):raise
    base=_recorded(mat,'diffuse')
    alpha=None
    if transparent:
        alpha=_recorded(mat,'transparency') or (base and (base[0],3,base[2]))
    if base:base=(base[0],None,base[2])
    return base,_recorded(mat,'normal'),alpha,bsdf


def pixels(image):
    if not image.has_data:image.reload()
    w,h=image.size
    if not w or not h:raise ValueError('Missing texture: '+image.filepath)
    result=np.empty(w*h*4,dtype=np.float32);image.pixels.foreach_get(result)
    return result.reshape(h,w,4)


def image_signature(image,*extra):
    """Identity of an unedited, file-backed source image, or None when it can't be trusted
    (packed, generated or edited in Blender). Lets a repeat preparation reuse a converted
    texture instead of loading and converting the source again."""
    try:
        if image.packed_file or image.is_dirty or image.source!='FILE':return None
        source=Path(bpy.path.abspath(image.filepath))
        stat=source.stat()
    except (OSError,AttributeError,ValueError):return None
    return json.dumps([2,str(source).lower(),stat.st_mtime_ns,stat.st_size,image.colorspace_settings.name,MAX_BITMAP,*extra],default=str)


def reusable(path,signature):
    path=Path(path)
    if not signature or not path.is_file():return False
    try:return path.with_name(path.name+'.source').read_text(encoding='utf-8')==signature
    except OSError:return False


def remember(path,signature):
    if signature:Path(path).with_name(Path(path).name+'.source').write_text(signature,encoding='utf-8')


def write_image(image,path):
    signature=image_signature(image,'image')
    if reusable(path,signature):return
    save_pixels(pixels(image),path,color=image.colorspace_settings.name!='Non-Color')
    remember(path,signature)


def sampled(data,width,height,ratio):
    # Wrap UVs just like the imported image nodes; different resolutions are allowed.
    y=(np.floor((np.arange(height)+.5)/height*ratio[1]*data.shape[0]).astype(int)%data.shape[0])
    x=(np.floor((np.arange(width)+.5)/width*ratio[0]*data.shape[1]).astype(int)%data.shape[1])
    return data[y[:,None],x[None,:]]


TOOL_MAX_BITMAP=4096  # Halo 3 Tool rejects larger bitmaps (Halo 2: Anniversary has 8192-wide textures).
# Halo 3's own textures are mostly 512-1024 wide, a few 2048: converted textures are kept at most
# this size by default (the Texture size setting), so memory and load times stay close to Halo 3's.
DEFAULT_BITMAP=2048
MAX_BITMAP=DEFAULT_BITMAP

def fit(data):
    """Halve (2x2 average) until both sides are at most MAX_BITMAP (never more than Tool's limit)."""
    limit=min(MAX_BITMAP,TOOL_MAX_BITMAP)
    while max(data.shape[:2])>limit:
        h,w=data.shape[:2]
        if h%2:data=np.concatenate([data,data[-1:]],axis=0);h+=1
        if w%2:data=np.concatenate([data,data[:,-1:]],axis=1);w+=1
        data=data.reshape(h//2,2,w//2,2,data.shape[2]).mean(axis=(1,3))
        if min(data.shape[:2])<1:break
    return data

def save_pixels(data,path,color=False):
    data=fit(data)
    image=bpy.data.images.new('HaloBridge converted texture',width=data.shape[1],height=data.shape[0],alpha=True)
    try:
        image.colorspace_settings.name='sRGB' if color else 'Non-Color'
        image.pixels.foreach_set(np.ascontiguousarray(data,dtype=np.float32).ravel())
        image.filepath_raw=str(path);image.file_format='TIFF';image.save()
    finally:bpy.data.images.remove(image)


H2_WATER_COLOR=(0.035,0.075,0.085)  # dark blue-green, the pool's look under Halo 2's sky reflection

def h2_water(mat,folder,key):
    """A Halo 2 water shader as dark water: a constant colour with the wave map as bump map."""
    folder=Path(folder)
    base=folder/(key+'_base.tif')
    data=np.empty((4,4,4),dtype=np.float32);data[:]=(*H2_WATER_COLOR,1.0);save_pixels(data,base,color=True)
    maps={'base_map':str(base)};scales={}
    waves=_recorded(mat,'diffuse')
    if waves:
        image,_,tile=waves;image.colorspace_settings.name='Non-Color'
        path=folder/(key+'_normal.tif');write_image(image,path);maps['normal_map']=str(path)
        if tile!=(1.,1.):scales['normal_map']=list(tile)
    entry=dict(name=key,tiling=(1.,1.),maps=maps)
    if scales:entry['scales']=scales
    return entry

def prepare(objects,folder,progress=None,materials=None,config=None):
    steps=prepare_steps(objects,folder,progress,materials,config)
    while True:
        try:next(steps)
        except StopIteration as done:return done.value


def surface_material(mat,config):
    """The Halo 3 global material (footsteps, impacts) for a converted Halo 2 material, or ''."""
    h2ek=config.get('h2_kit') if config else None
    if not h2ek or not mat.get('hb_shader') or not config.get('kit'):return ''
    from . import standins
    return standins.h3_material(standins.h2_material_name(h2ek,mat['hb_shader']),standins.h3_material_names(config['kit']))


def prepare_steps(objects,folder,progress=None,materials=None,config=None):
    """prepare() one material at a time: yields between materials so Blender can redraw.
    With the level's config, Halo 2 effects get Halo 3 stand-in shaders (standins.py) and
    converted shaders keep Halo 2's surface material."""
    from . import standins
    progress=progress or (lambda message:None)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    result={};issues=[]
    materials=reach_materials(objects) if materials is None else materials
    custom_ids=set()
    for index,(pointer,mat) in enumerate(materials.items(),1):
        yield
        progress(f'Preparing material {index}/{len(materials)}: '+mat.get('hb_label',mat.name))
        try:
            if mat.get('hb_custom_shader'):
                from . import editable_materials
                import uuid
                if mat.get('hb_custom_id') in custom_ids:mat['hb_custom_id']=uuid.uuid4().hex
                custom_ids.add(mat.get('hb_custom_id'))
                # Paintable terrain becomes a real shader_terrain so each layer keeps
                # its own resolution and tiling; other editable materials are baked.
                if editable_materials.exports_terrain_shader(mat):result[pointer]=editable_materials.terrain_shader(mat,folder,progress)
                else:result[pointer]=editable_materials.bake(mat,folder,progress)
                continue
            key='reach_'+hashlib.sha256((mat.get('hb_conversion_id',mat.name)+'|'+mat.get('hb_shader','')).encode()).hexdigest()[:20]
            if mat.get('hb_sky_blend') and mat.get('hb_sky_layer'):
                # Halo 2 sky layer: one baked RGBA texture, blended like the original.
                from . import classic_sky
                result[pointer]=classic_sky.bake(mat,folder,key);continue
            standin=standins.standin(mat.get('hb_h2_template'),config,mat.get('hb_h1_class','')) if config is not None else None
            if standin:
                # A Halo 3 shader drawing the same effect (copied into the level, not converted).
                progress('Halo 3 shader for '+mat.get('hb_label',mat.name)+': '+standin)
                result[pointer]=dict(name=key,tiling=(1.,1.),standin=standin);continue
            if '\\water\\' in str(mat.get('hb_h2_template','')).lower():
                # Halo 2 water (water_pool_cube ...) gets its colour from a reflection cube map and
                # a fresnel ramp; its only flat texture is the wave normal map, which shows purple
                # as a colour. It becomes dark water with the waves as its bump map.
                result[pointer]=h2_water(mat,folder,key);continue
            base,normal,alpha,bsdf=sources(mat)
            if not bsdf and not base:raise ValueError('No Principled preview material found.')
            maps={};tile=base[2] if base else (1.,1.)
            path=folder/(key+'_base.tif')
            if base:write_image(base[0],path)
            else:
                data=np.empty((4,4,4),dtype=np.float32);data[:]=tuple(bsdf.inputs['Base Color'].default_value);save_pixels(data,path,color=True)
            maps['base_map']=str(path)
            scales={}
            # Detail maps keep their own size and repeat in the shader (bitmap scale), as in the
            # original: baking 60 repeats into one texture would blur them away.
            for label,(image,uv) in zip(('detail_map','detail_map2'),details(mat)):
                path=folder/(key+'_'+label.replace('_map','')+'.tif');write_image(image,path)
                maps[label]=str(path);scales[label]=[uv[i]/tile[i] for i in range(2)]
            for label,source in (('normal_map',normal),('alpha_map',alpha)):
                if source is None:continue
                image,channel,uv=source;path=folder/(key+('_normal.tif' if label=='normal_map' else '_alpha.tif'))
                ratio=tuple(uv[i]/tile[i] for i in range(2))
                if label=='normal_map' and ratio!=(1.,1.) and min(ratio)>=1:
                    # A bump map that repeats more often than the base map repeats in the shader too.
                    write_image(image,path);scales[label]=list(ratio)
                elif label=='normal_map' and ratio==(1.,1.):write_image(image,path)
                else:
                    signature=image_signature(image,label,channel,ratio)
                    if not reusable(path,signature):
                        data=pixels(image);data=sampled(data,data.shape[1],data.shape[0],ratio)
                        if label=='alpha_map':
                            channel=channel if channel is not None else 0
                            mask=data[:,:,channel].copy();data=np.repeat(mask[:,:,None],4,axis=2)
                        save_pixels(data,path);remember(path,signature)
                maps[label]=str(path)
            result[pointer]=dict(name=key,tiling=tile,maps=maps)
            if scales:result[pointer]['scales']=scales
            if mat.get('hb_transparent') in ('alpha','additive'):
                # Halo 2 see-through layers (Ascension's cloud sea, glows): unlit and blended as in
                # Halo 2 (base map alpha = coverage, or added), not alpha-tested into solid sheets.
                maps.pop('alpha_map',None)
                result[pointer]['blend']=mat['hb_transparent'];result[pointer]['additive']=mat['hb_transparent']=='additive'
        except Exception as error:issues.append(mat.get('hb_label',mat.name)+': '+str(error))
    if issues:raise ValidationError(issues,'Material conversion')
    # Halo 2's surface material (footsteps, impact effects) on the converted shaders.
    for pointer,mat in materials.items():
        entry=result.get(pointer)
        if entry is None or entry.get('standin') or entry.get('terrain') or mat.get('hb_sky_layer'):continue
        try:surface=surface_material(mat,config)
        except Exception:surface=''
        if surface:entry['material']=surface
    return result
