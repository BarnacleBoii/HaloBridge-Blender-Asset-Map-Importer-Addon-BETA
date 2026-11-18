"""UV-painted materials baked to level-local Halo shaders; original tags stay intact."""
import json
import uuid
from pathlib import Path
import bpy
from . import compat, cross_game


def image_node(mat, name, image, uv, tile=(1,1), data=False):
    nodes=mat.node_tree.nodes;links=mat.node_tree.links
    node=nodes.new('ShaderNodeTexImage');node.name=name;node.label=name;node.image=image
    mapping=nodes.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.name=name+' Tiling'
    mapping.inputs[1].default_value=(tile[0],tile[1],1)
    links.new(uv,mapping.inputs[0]);links.new(mapping.outputs[0],node.inputs['Vector'])
    return node


def make(context, mode):
    obj=context.active_object
    if not obj or obj.type!='MESH' or not obj.data.uv_layers:raise ValueError('Select a mesh with a UV map first.')
    if obj.get('hb_preview'):raise ValueError('Place the asset first before creating editable materials.')
    if obj.get('hb_vehicle_tag') and mode!='colors':raise ValueError('Select Create editable colors for vehicle paint.')
    if obj.mode!='OBJECT':bpy.ops.object.mode_set(mode='OBJECT')
    old=obj.active_material
    if not old or not compat.nodes_enabled(old):raise ValueError('Apply an imported material first.')
    old_bsdf=next((n for n in old.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
    if not old_bsdf:raise ValueError('Select a material with a Principled shader.')
    try:source=cross_game.texture(old_bsdf.inputs['Base Color'])
    except ValueError:source=None
    source_textures=json.loads(old.get('hb_texture_sources','[]'))
    diffuse=[t for t in source_textures if t['usage']=='diffuse']
    if not source and diffuse:
        chosen=next((t for t in diffuse if t.get('blend_channel')==2),diffuse[0])
        image=bpy.data.images.load(str(Path(old['hb_texture_directory'])/chosen['path']),check_existing=True)
        source=(image,None,tuple(chosen['tiling']))
    if not source:raise ValueError('The current material needs a base-color image. Choose a plain imported material first.')
    base,_,tile=source
    layered = mode=='terrain' and any(t['usage']=='blend' for t in source_textures) and any(t.get('blend_channel') in (1,2,4,8) for t in diffuse)
    normal=None if layered else cross_game.texture(old_bsdf.inputs['Normal'])
    mat=bpy.data.materials.new(old.name+' - Editable '+mode.title());compat.enable_nodes(mat)
    mat['hb_custom_shader']=mode;mat['hb_custom_id']=uuid.uuid4().hex;mat['hb_bake_size']=1024
    mat['hb_source_shader']=old.get('hb_shader','');mat['hb_shader']=old.get('hb_shader','')
    compat.set_alpha(mat,compat.alpha_mode(old));mat.use_backface_culling=old.use_backface_culling
    # Registered properties are not dictionary items in Blender 5.
    if hasattr(mat,'hb_collision_mode'):mat.hb_collision_mode=getattr(old,'hb_collision_mode','AUTO')
    if hasattr(old,'ass_jms'):
        for flag in ('two_sided','transparent_1_sided','transparent_2_sided','render_only','collision_only'):
            if hasattr(old.ass_jms,flag):setattr(mat.ass_jms,flag,getattr(old.ass_jms,flag))
    nodes=mat.node_tree.nodes;links=mat.node_tree.links;nodes.clear()
    uv=nodes.new('ShaderNodeTexCoord').outputs['UV']
    bsdf=nodes.new('ShaderNodeBsdfPrincipled');bsdf.name='HaloBridge Surface'
    output=nodes.new('ShaderNodeOutputMaterial');links.new(bsdf.outputs[0],output.inputs['Surface'])
    if layered:
        from . import layered_preview
        layered_preview.apply(mat,{'textures':source_textures},old['hb_texture_directory'],editable=True)
        compat.set_alpha(mat,'opaque')
        if obj.data.users>1:obj.data=obj.data.copy()
        uv_layer=obj.data.uv_layers.active
        loops=[i for face in obj.data.polygons if face.material_index==obj.active_material_index for i in face.loop_indices]
        if loops:
            low=[min(uv_layer.data[i].uv[a] for i in loops) for a in (0,1)]
            high=[max(uv_layer.data[i].uv[a] for i in loops) for a in (0,1)]
            if min(low)<0 or max(high)>1:
                span=[max(hi-lo,1e-8) for hi,lo in zip(high,low)]
                # Mask uses a unique tile; source images retain their original sample coordinates.
                for i in loops:
                    old_uv=uv_layer.data[i].uv.copy()
                    uv_layer.data[i].uv=[(old_uv[a]-low[a])/span[a] for a in (0,1)]
                for n in list(nodes):
                    if n.type!='TEX_IMAGE' or n.name=='Paint Mask':continue
                    mapping=n.inputs['Vector'].links[0].from_node
                    scale=nodes.new('ShaderNodeVectorMath');scale.operation='MULTIPLY'
                    offset=nodes.new('ShaderNodeVectorMath');offset.operation='ADD'
                    links.new(mapping.inputs[0].links[0].from_socket,scale.inputs[0])
                    scale.inputs[1].default_value=(*span,1);offset.inputs[1].default_value=(*low,0)
                    links.new(scale.outputs[0],offset.inputs[0]);links.new(offset.outputs[0],mapping.inputs[0])
        obj.data.materials[obj.active_material_index]=mat
        return mat
    mask=bpy.data.images.new(mat.name+' Paint Mask',width=1024,height=1024,alpha=True)
    mask.colorspace_settings.name='Non-Color';mask.generated_color=(0,0,0,1) if mode=='terrain' else (1,0,0,0)
    mat['hb_mask_source']='Painted mask; Color 1 initially covers this whole material'
    if mode=='colors' and old.get('hb_change_mask_image'):
        found=bpy.data.images.get(old['hb_change_mask_image'])
        if found:
            bpy.data.images.remove(mask);mask=found.copy();mask.name=mat.name+' Color Mask';mask.colorspace_settings.name='Non-Color';mat['hb_mask_source']='Original Halo color-change mask'
    mask.pack()
    masknode=image_node(mat,'Paint Mask',mask,uv)
    channels=nodes.new('ShaderNodeSeparateColor');links.new(masknode.outputs['Color'],channels.inputs[0])
    basecopy=base.copy();basecopy.name=mat.name+' Base';basecopy.pack()
    if mode=='terrain':
        layers=[]
        for name in ('Grass','Rock','Dirt'):
            image=basecopy if name=='Grass' else basecopy.copy();layer_tile=tile
            channel={'Grass':2,'Rock':1,'Dirt':4}[name]
            chosen=next((t for t in diffuse if t.get('blend_channel')==channel),None)
            if chosen:
                image=bpy.data.images.load(str(Path(old['hb_texture_directory'])/chosen['path']),check_existing=False);image.pack();layer_tile=tuple(chosen['tiling'])
            tex=image_node(mat,name,image,uv,layer_tile)
            layers.append(tex.outputs['Color'])
        for index in range(2):
            mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MIX'
            links.new(channels.outputs[index],mix.inputs[0]);links.new(layers[0] if index==0 else previous,mix.inputs[1]);links.new(layers[index+1],mix.inputs[2]);previous=mix.outputs[0]
        links.new(previous,bsdf.inputs['Base Color'])
        compat.set_alpha(mat,'opaque')
    else:
        tex=image_node(mat,'Base Texture',basecopy,uv,tile);previous=tex.outputs['Color']
        for index in range(4):
            tint=nodes.new('ShaderNodeMixRGB');tint.name='Color '+str(index+1);tint.label=tint.name;tint.blend_type='MULTIPLY';tint.inputs[2].default_value=(1,1,1,1)
            links.new(channels.outputs[index] if index<3 else masknode.outputs['Alpha'],tint.inputs[0]);links.new(previous,tint.inputs[1]);previous=tint.outputs[0]
        links.new(previous,bsdf.inputs['Base Color'])
        if compat.is_transparent(mat):links.new(tex.outputs['Alpha'],bsdf.inputs['Alpha'])
    if mode=='terrain' and all(any(t['usage']=='normal' and t.get('blend_channel')==channel for t in source_textures) for channel in (2,1,4)):
        normal_outputs=[]
        for name,channel in (('Grass',2),('Rock',1),('Dirt',4)):
            t=next(t for t in source_textures if t['usage']=='normal' and t.get('blend_channel')==channel)
            image=bpy.data.images.load(str(Path(old['hb_texture_directory'])/t['path']),check_existing=False);image.colorspace_settings.name='Non-Color';image.pack()
            normal_outputs.append(image_node(mat,name+' Normal',image,uv,t['tiling']).outputs['Color'])
        for index in range(2):
            mix=nodes.new('ShaderNodeMixRGB');mix.blend_type='MIX';links.new(channels.outputs[index],mix.inputs[0]);links.new(normal_outputs[0] if index==0 else previous,mix.inputs[1]);links.new(normal_outputs[index+1],mix.inputs[2]);previous=mix.outputs[0]
        normalnode=nodes.new('ShaderNodeNormalMap');links.new(previous,normalnode.inputs['Color']);links.new(normalnode.outputs[0],bsdf.inputs['Normal'])
    elif normal:
        n=image_node(mat,'Normal Texture',normal[0].copy(),uv,normal[2]);n.image.pack()
        normalnode=nodes.new('ShaderNodeNormalMap');links.new(n.outputs['Color'],normalnode.inputs['Color']);links.new(normalnode.outputs[0],bsdf.inputs['Normal'])
    for i,node in enumerate(nodes):node.location=((i%5)*230,-(i//5)*220)
    nodes.active=masknode;masknode.select=True
    if obj.data.users>1:obj.data=obj.data.copy()
    obj.data.materials[obj.active_material_index]=mat
    return mat


# ---- Paintable terrain -------------------------------------------------------
# Two editors share the "terrain" mode:
#  * simple: made from a plain texture (layers Grass/Rock/Dirt/Layer 4, chosen by
#    black/red/green/blue in the Paint Mask);
#  * layered: made from a stock Halo terrain shader (layers "Shader N", see
#    layered_preview; the Paint Mask overrides the shader's original blend map).
# Both export as a real Halo 3 shader_terrain, never as one stretched bake.
SIMPLE_LAYERS = ('Grass', 'Rock', 'Dirt', 'Layer 4')
MAX_TERRAIN_LAYERS = 4  # Halo 3 shader_terrain has material_0 .. material_3.
CHANNEL_INDEX = {1: 0, 2: 1, 4: 2, 8: 3}


def is_paintable_terrain(mat):
    """The simple editor (made from a plain material)."""
    if not mat or mat.get('hb_custom_shader') != 'terrain' or mat.get('hb_layers') or not compat.nodes_enabled(mat):
        return False
    nodes = mat.node_tree.nodes
    return bool(nodes.get('Paint Mask') and nodes.get('Grass') and nodes.get('Grass Tiling'))


def is_layered_terrain(mat):
    """The layered editor (made from a stock Halo terrain shader)."""
    if not mat or mat.get('hb_custom_shader') != 'terrain' or not mat.get('hb_layers') or not compat.nodes_enabled(mat):
        return False
    nodes = mat.node_tree.nodes
    return bool(nodes.get('Paint Mask') and nodes.get('Shader 1'))


def exports_terrain_shader(mat):
    return is_paintable_terrain(mat) or is_layered_terrain(mat)


def _layer_names(mat):
    if is_layered_terrain(mat):
        return [n for n in json.loads(mat['hb_layers']) if mat.node_tree.nodes.get(n)]
    return [n for n in SIMPLE_LAYERS if mat.node_tree.nodes.get(n)]


def terrain_layer_count(mat):
    return len(_layer_names(mat))


def _layer_channels(mat):
    """Original blend-map channel of each layered-editor layer (0 = added layer, no original weight)."""
    names = json.loads(mat['hb_layers'])
    stored = json.loads(mat.get('hb_layer_channels') or '[]')
    return stored if len(stored) == len(names) else [1 << i for i in range(len(names))]


def _copy_image_node(mat, source, name):
    """A new image node using a copy of source's image and the same UV mapping."""
    nodes = mat.node_tree.nodes; links = mat.node_tree.links
    tiling = nodes.get(source.name + ' Tiling')
    image = source.image.copy(); image.name = mat.name + ' ' + name
    image.colorspace_settings.name = source.image.colorspace_settings.name; image.pack()
    tex = nodes.new('ShaderNodeTexImage'); tex.name = name; tex.label = name; tex.image = image
    mapping = nodes.new('ShaderNodeVectorMath'); mapping.operation = 'MULTIPLY'; mapping.name = name + ' Tiling'
    mapping.inputs[1].default_value = tiling.inputs[1].default_value[:] if tiling else (1, 1, 1)
    links.new(tiling.inputs[0].links[0].from_socket if tiling else source.inputs['Vector'].links[0].from_socket, mapping.inputs[0])
    links.new(mapping.outputs[0], tex.inputs['Vector'])
    return tex


def _mix(mat, blend, factor, a, b):
    nodes = mat.node_tree.nodes; links = mat.node_tree.links
    node = nodes.new('ShaderNodeMixRGB'); node.blend_type = blend
    for socket, value in ((node.inputs[0], factor), (node.inputs[1], a), (node.inputs[2], b)):
        if isinstance(value, (int, float)): socket.default_value = value
        elif isinstance(value, tuple): socket.default_value = value
        else: links.new(value, socket)
    return node.outputs[0]


def _insert_after(mat, socket, make):
    """Replace what feeds socket with make(previous_output)."""
    previous = socket.links[0].from_socket
    mat.node_tree.links.new(make(previous), socket)


def _add_simple_layer(mat):
    nodes = mat.node_tree.nodes
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    channels = next((l.to_node for l in nodes['Paint Mask'].outputs['Color'].links if l.to_node.type == 'SEPARATE_COLOR'), None)
    if not bsdf or not channels or not bsdf.inputs['Base Color'].is_linked:
        raise ValueError('This terrain material was changed by hand. Create the paintable terrain again.')
    blue = channels.outputs[2]
    tex = _copy_image_node(mat, nodes['Grass'], 'Layer 4')
    _insert_after(mat, bsdf.inputs['Base Color'], lambda prev: _mix(mat, 'MIX', blue, prev, tex.outputs['Color']))
    normal_map = next((n for n in nodes if n.type == 'NORMAL_MAP'), None)
    if nodes.get('Grass Normal') and normal_map and normal_map.inputs['Color'].is_linked:
        normal = _copy_image_node(mat, nodes['Grass Normal'], 'Layer 4 Normal')
        _insert_after(mat, normal_map.inputs['Color'], lambda prev: _mix(mat, 'MIX', blue, prev, normal.outputs['Color']))
    return tex


def _add_layered_layer(mat):
    """Next "Shader N" in the layered editor, shown where the mask is painted white."""
    nodes = mat.node_tree.nodes
    names = json.loads(mat['hb_layers'])
    bsdf = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
    divides = [n for n in nodes if n.type == 'MATH' and n.operation == 'DIVIDE' and n.inputs[1].is_linked]
    try:
        total = divides[0].inputs[1].links[0].from_node
        fourth = total.inputs[1].links[0].from_node.inputs[1].links[0].from_socket  # min(r, g, b): white
        weight = next(l.to_node for l in divides[0].outputs[0].links if l.to_node.type == 'MIX_RGB')
        strength = weight.inputs[0].links[0].from_socket
    except (IndexError, StopIteration):
        raise ValueError('This terrain material was changed by hand. Create the paintable terrain again.')
    if not bsdf or not bsdf.inputs['Base Color'].is_linked:
        raise ValueError('This terrain material was changed by hand. Create the paintable terrain again.')
    links = mat.node_tree.links
    share = nodes.new('ShaderNodeMath'); share.operation = 'DIVIDE'
    links.new(fourth, share.inputs[0]); links.new(total.outputs[0], share.inputs[1])
    # New layer: no weight in the original blend, the painted share where painted.
    layer_weight = _mix(mat, 'MIX', strength, (0, 0, 0, 1), share.outputs[0])
    name = 'Shader ' + str(len(names) + 1)
    tex = _copy_image_node(mat, nodes['Shader 1'], name)
    weighted = _mix(mat, 'MULTIPLY', 1.0, tex.outputs['Color'], layer_weight)
    _insert_after(mat, bsdf.inputs['Base Color'], lambda prev: _mix(mat, 'ADD', 1.0, prev, weighted))
    normal_map = next((n for n in nodes if n.type == 'NORMAL_MAP'), None)
    if nodes.get('Shader 1 Normal') and normal_map and normal_map.inputs['Color'].is_linked:
        normal = _copy_image_node(mat, nodes['Shader 1 Normal'], name + ' Normal')
        weighted_normal = _mix(mat, 'MULTIPLY', 1.0, normal.outputs['Color'], layer_weight)
        _insert_after(mat, normal_map.inputs['Color'], lambda prev: _mix(mat, 'ADD', 1.0, prev, weighted_normal))
    channels = _layer_channels(mat) + [0]
    mat['hb_layers'] = json.dumps(names + [name]); mat['hb_layer_channels'] = json.dumps(channels)
    return tex


def add_terrain_layer(mat):
    """Add one more layer (up to Halo's four); it starts as a copy of layer 1."""
    if not exports_terrain_shader(mat):
        raise ValueError('Select a paintable terrain material made with Create paintable terrain.')
    if terrain_layer_count(mat) >= MAX_TERRAIN_LAYERS:
        raise ValueError('Halo 3 terrain shaders have at most four layers, and this terrain already has four.')
    tex = _add_layered_layer(mat) if is_layered_terrain(mat) else _add_simple_layer(mat)
    for i, node in enumerate(mat.node_tree.nodes): node.location = ((i % 5) * 230, -(i // 5) * 220)
    return tex


def terrain_weights(mask_pixels, layers):
    """Simple editor: blend weights per layer from the paint mask.

    The preview mixes layer 2 over layer 1 by red, layer 3 over that by green and
    layer 4 by blue, so each weight is that mix's share and they always sum to 1.
    """
    import numpy as np
    r, g, b = (np.clip(mask_pixels[:, :, i], 0, 1) for i in range(3))
    if layers < 4: b = np.zeros_like(b)
    if layers < 3: g = np.zeros_like(g)
    weights = np.zeros(mask_pixels.shape[:2] + (4,), dtype=np.float32)
    weights[:, :, 0] = (1 - r) * (1 - g) * (1 - b)
    weights[:, :, 1] = r * (1 - g) * (1 - b)
    weights[:, :, 2] = g * (1 - b)
    weights[:, :, 3] = b
    return weights


def layered_weights(paint, original, channels):
    """Layered editor: the preview's weights (layered_preview.apply) per layer.

    paint and original are float arrays sampled on the same grid. Where the mask is
    black the original blend shows; painted red/green/blue/white select layers 1-4.
    """
    import numpy as np
    r, g, b = (np.clip(paint[:, :, i], 0, 1) for i in range(3))
    strength = np.maximum(np.maximum(r, g), b)
    fourth = np.minimum(np.minimum(r, g), b)
    shares = [r - fourth, g - fourth, b - fourth, fourth]
    total = shares[0] + shares[1] + shares[2] + shares[3]
    weights = np.zeros(paint.shape[:2] + (4,), dtype=np.float32)
    for index, channel in enumerate(channels[:4]):
        painted = np.divide(shares[index], total, out=np.zeros_like(total), where=total > 0)
        base = original[:, :, CHANNEL_INDEX[channel]] if channel in CHANNEL_INDEX else 0
        weights[:, :, index] = base * (1 - strength) + painted * strength
    return weights


def uv_transform(mat, node):
    """(scale, offset) with texture coordinate = UV * scale + offset, as Halo's xform."""
    nodes = mat.node_tree.nodes
    tiling = nodes.get(node.name + ' Tiling')
    if not tiling:
        return (1., 1.), (0., 0.)
    tile = tuple(float(v) for v in tiling.inputs[1].default_value[:2])
    source = tiling.inputs[0].links[0].from_node if tiling.inputs[0].is_linked else None
    # make() remaps UVs outside 0-1 as ((uv * span) + low) before the tiling.
    if source is not None and source.type == 'VECT_MATH' and source.operation == 'ADD' and source.inputs[0].is_linked:
        low = tuple(float(v) for v in source.inputs[1].default_value[:2])
        span = tuple(float(v) for v in source.inputs[0].links[0].from_node.inputs[1].default_value[:2])
        return (span[0] * tile[0], span[1] * tile[1]), (low[0] * tile[0], low[1] * tile[1])
    return tile, (0., 0.)


def _sample(data, width, height, scale, offset):
    """Nearest-pixel sample of data over a width x height UV grid, repeating like Blender."""
    import numpy as np
    u = ((np.arange(width) + .5) / width) * scale[0] + offset[0]
    v = ((np.arange(height) + .5) / height) * scale[1] + offset[1]
    x = np.floor(u * data.shape[1]).astype(int) % data.shape[1]
    y = np.floor(v * data.shape[0]).astype(int) % data.shape[0]
    return data[y[:, None], x[None, :]]


def terrain_shader(mat, folder, progress=None):
    """Paintable terrain as a real Halo 3 shader_terrain.

    Each layer keeps its own full-resolution texture and tiling; only the painted
    mask becomes the (untiled) blend map. Baking everything into one image would
    stretch a single texture over the whole terrain.
    """
    validate(mat); pack(mat); folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    nodes = mat.node_tree.nodes
    name = 'terrain_' + mat['hb_custom_id'][:20]
    names = _layer_names(mat)
    if progress: progress('Writing terrain blend map for ' + mat.name)
    paint_node = nodes['Paint Mask']; paint = cross_game.pixels(paint_node.image)
    if is_layered_terrain(mat):
        original = nodes.get('Original Blend')
        data = cross_game.pixels(original.image) if original and original.image else None
        height = min(4096, max(paint.shape[0], data.shape[0] if data is not None else 0))
        width = min(4096, max(paint.shape[1], data.shape[1] if data is not None else 0))
        painted = _sample(paint, width, height, *uv_transform(mat, paint_node))
        base = _sample(data, width, height, *uv_transform(mat, original)) if data is not None else __import__('numpy').zeros_like(painted)
        weights = layered_weights(painted, base, _layer_channels(mat))
    else:
        weights = terrain_weights(paint, len(names))
    blend = folder / (name + '_blend.tif')
    cross_game.save_pixels(weights, blend)
    layers = []
    for index, layer in enumerate(names):
        if progress: progress('Writing terrain layer ' + str(index + 1) + ' for ' + mat.name)
        entry = {}
        for suffix, usage in (('', 'base_map'), (' Detail', 'detail_map'), (' Normal', 'normal_map')):
            node = nodes.get(layer + suffix)
            if not node or not node.image:
                if usage == 'base_map': raise ValueError('Choose an image for terrain layer ' + str(index + 1) + '.')
                continue
            path = folder / (name + '_m' + str(index) + '_' + usage.split('_')[0] + '.tif')
            cross_game.write_image(node.image, path)
            scale, offset = uv_transform(mat, node)
            entry[usage] = str(path)
            entry[usage.split('_')[0] + '_scale'] = [scale[0], scale[1]]
            entry[usage.split('_')[0] + '_offset'] = [offset[0], offset[1]]
        entry['scale'] = entry['base_scale']
        layers.append(entry)
    return dict(name=name, tiling=(1., 1.), maps={'blend_map': str(blend)}, terrain=True, layers=layers)


def validate(mat):
    if not compat.nodes_enabled(mat):raise ValueError('Enable material nodes for the editable material.')
    allowed={'BSDF_PRINCIPLED','OUTPUT_MATERIAL','TEX_COORD','TEX_IMAGE','VECT_MATH','MIX_RGB','SEPARATE_COLOR','NORMAL_MAP','RGB','VALUE','MATH','UVMAP','REROUTE'}
    for node in mat.node_tree.nodes:
        if node.type not in allowed:raise ValueError('Unsupported editable-material node: '+node.name+'. This exporter supports UV/image-based materials.')
        if node.type=='TEX_IMAGE' and (not node.image or not all(node.image.size)):raise ValueError('Choose an image for '+node.name)
        if node.type=='TEX_COORD' and any(s.is_linked for s in node.outputs if s.name!='UV'):raise ValueError('Editable materials must use UV coordinates.')
    if not any(n.type=='BSDF_PRINCIPLED' for n in mat.node_tree.nodes):raise ValueError('Missing Principled shader.')
    if int(mat.get('hb_bake_size',1024)) not in (512,1024,2048,4096):raise ValueError('Texture resolution must be 512, 1024, 2048 or 4096.')


def repeats_on_uv_tiles(mat):
    """Recognize the color editor's unit-period UV graph before allowing wrapped UVs."""
    if mat.get('hb_custom_shader') != 'colors':
        return False
    for node in mat.node_tree.nodes:
        if node.type == 'TEX_COORD':
            if any(link.to_node.type != 'VECT_MATH' or link.to_socket != link.to_node.inputs[0]
                   for link in node.outputs['UV'].links):
                return False
        elif node.type == 'VECT_MATH':
            if node.operation != 'MULTIPLY' or node.inputs[1].is_linked:
                return False
            if any(not float(v).is_integer() for v in node.inputs[1].default_value[:2]):
                return False
            if any(link.to_node.type != 'TEX_IMAGE' or link.to_socket.name != 'Vector'
                   for link in node.outputs[0].links):
                return False
        elif node.type == 'TEX_IMAGE':
            if node.extension != 'REPEAT' or node.projection != 'FLAT':
                return False
            if any(link.from_node.type != 'VECT_MATH' for link in node.inputs['Vector'].links):
                return False
        elif node.type == 'UVMAP':
            return False
    return True


def pack(mat):
    for node in mat.node_tree.nodes:
        if node.type=='TEX_IMAGE' and node.image:node.image.pack()


def bake(mat, folder, progress=None):
    """Bake base-color nodes with emission, so lighting is never baked in."""
    validate(mat);pack(mat);folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    name='custom_'+mat['hb_custom_id'][:20];size=int(mat.get('hb_bake_size',1024))
    original_scene=bpy.context.window.scene
    scene=bpy.data.scenes.new('HaloBridge texture bake');copy=mat.copy();mesh=bpy.data.meshes.new('Bake UV tile');obj=bpy.data.objects.new('Bake UV tile',mesh)
    images=[];maps={}
    try:
        scene.collection.objects.link(obj);mesh.from_pydata([(0,0,0),(1,0,0),(1,1,0),(0,1,0)],[],[(0,1,2,3)])
        uv=mesh.uv_layers.new(name='UVMap')
        for loop,co in zip(uv.data,[(0,0),(1,0),(1,1),(0,1)]):loop.uv=co
        mesh.materials.append(copy);scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1
        bpy.context.window.scene=scene;obj.select_set(True);bpy.context.view_layer.objects.active=obj
        nodes=copy.node_tree.nodes;links=copy.node_tree.links
        bsdf=next(n for n in nodes if n.type=='BSDF_PRINCIPLED');output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL' and n.is_active_output)
        emission=nodes.new('ShaderNodeEmission');links.new(emission.outputs[0],output.inputs['Surface'])
        sources=[('base_map',bsdf.inputs['Base Color'],True)]
        if bsdf.inputs['Normal'].is_linked:
            normal=bsdf.inputs['Normal'].links[0].from_node
            if normal.type!='NORMAL_MAP':raise ValueError('Use a Normal Map node for editable normal textures.')
            sources.append(('normal_map',normal.inputs['Color'],False))
        if compat.is_transparent(mat):sources.append(('alpha_map',bsdf.inputs['Alpha'],False))
        for usage,socket,color in sources:
            if progress:progress('Baking '+mat.name+' / '+usage+' ('+str(size)+' x '+str(size)+')')
            for link in list(emission.inputs['Color'].links):links.remove(link)
            if socket.is_linked:links.new(socket.links[0].from_socket,emission.inputs['Color'])
            else:
                value=socket.default_value;emission.inputs['Color'].default_value=(value,value,value,1) if isinstance(value,(float,int)) else value
            image=bpy.data.images.new(name+' '+usage,width=size,height=size,alpha=True);images.append(image)
            image.colorspace_settings.name='sRGB' if color else 'Non-Color'
            target=nodes.new('ShaderNodeTexImage');target.image=image;nodes.active=target
            result=bpy.ops.object.bake(type='EMIT',margin=0,use_clear=True)
            if result!={'FINISHED'}:raise RuntimeError('Texture bake did not finish.')
            path=folder/(name+'_'+usage+'.tif');image.filepath_raw=str(path);image.file_format='TIFF';image.save();maps[usage]=str(path);nodes.remove(target)
        return dict(name=name,tiling=(1.,1.),maps=maps)
    finally:
        bpy.context.window.scene=original_scene
        bpy.data.objects.remove(obj,do_unlink=True);bpy.data.meshes.remove(mesh);bpy.data.materials.remove(copy);bpy.data.scenes.remove(scene)
        for image in images:bpy.data.images.remove(image)
