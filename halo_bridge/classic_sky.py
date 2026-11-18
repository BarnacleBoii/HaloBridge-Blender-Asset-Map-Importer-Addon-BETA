"""Halo 2 sky layers: unlit, alpha-blended or additive, as the game draws them.

Halo 2 skies are several shells around the camera, each with a "sky" shader
template (transparent\\sky_*). The extractor reports each layer's color map, its
tiling, an optional coverage mask (clouds) or detail map, a tint, and whether
the layer is added or alpha-blended. The Blender preview reproduces that
unlit, and preparation bakes each layer into one RGBA texture for a Halo 3
sky shader with the same blending.
"""
import json
from pathlib import Path
import bpy
import numpy as np
from . import compat

MAX_BAKE = 2048
OPAQUE_ALPHA = 254 / 255  # every texel at least this opaque: the layer hides what is behind it


def mode(meta):
    value = (meta.get('options') or {}).get('sky')
    return value if value in ('alpha', 'additive') else None


def _texture(nodes, links, coords, directory, entry, color=True):
    path = Path(directory) / entry['path']
    if not path.is_file():
        raise RuntimeError('Missing texture: ' + str(path))
    image = bpy.data.images.load(str(path), check_existing=True)
    if not color:
        image.colorspace_settings.name = 'Non-Color'
    node = nodes.new('ShaderNodeTexImage')
    node.image = image
    node.label = (entry.get('name') or '').replace('/', '\\').split('\\')[-1] or entry['usage']
    node.interpolation = 'Linear'
    scale = nodes.new('ShaderNodeVectorMath')
    scale.operation = 'MULTIPLY'
    scale.inputs[1].default_value = (*[float(x) for x in entry.get('tiling', (1, 1))[:2]], 1)
    links.new(coords.outputs['UV'], scale.inputs[0])
    links.new(scale.outputs[0], node.inputs['Vector'])
    return node


def apply(mat, meta, directory):
    """Rebuild mat as an unlit Halo 2 sky layer; returns False when meta is not one."""
    blend = mode(meta)
    if not blend:
        return False
    textures = {t['usage']: t for t in meta.get('textures', [])}
    if 'diffuse' not in textures:
        return False
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    coords = nodes.new('ShaderNodeTexCoord')
    base = _texture(nodes, links, coords, directory, textures['diffuse'])
    color = base.outputs['Color']
    if 'diffuse_detail' in textures:
        detail = _texture(nodes, links, coords, directory, textures['diffuse_detail'])
        mix = nodes.new('ShaderNodeVectorMath')
        mix.operation = 'MULTIPLY'
        links.new(color, mix.inputs[0])
        links.new(detail.outputs['Color'], mix.inputs[1])
        color = mix.outputs[0]
    tint = next((t['color'] for t in meta.get('tints', []) if t.get('usage') == 'albedo'), None)
    if tint:
        tinted = nodes.new('ShaderNodeVectorMath')
        tinted.operation = 'MULTIPLY'
        tinted.inputs[1].default_value = tuple(tint[:3])
        links.new(color, tinted.inputs[0])
        color = tinted.outputs[0]
    emission = nodes.new('ShaderNodeEmission')
    links.new(color, emission.inputs['Color'])
    clear = nodes.new('ShaderNodeBsdfTransparent')
    if blend == 'additive':
        add = nodes.new('ShaderNodeAddShader')
        links.new(emission.outputs[0], add.inputs[0])
        links.new(clear.outputs[0], add.inputs[1])
        links.new(add.outputs[0], out.inputs['Surface'])
    else:
        mask = _texture(nodes, links, coords, directory, textures['transparency'], color=False) if 'transparency' in textures else base
        shader = nodes.new('ShaderNodeMixShader')
        links.new(mask.outputs['Alpha'], shader.inputs[0])
        links.new(clear.outputs[0], shader.inputs[1])
        links.new(emission.outputs[0], shader.inputs[2])
        links.new(shader.outputs[0], out.inputs['Surface'])
    for index, node in enumerate(nodes):
        node.location = (-300 * (len(nodes) - index), 0)
    out.location = (300, 0)
    compat.set_alpha(mat, 'blend')
    mat.use_backface_culling = False
    if hasattr(mat, 'shadow_method'):
        mat.shadow_method = 'NONE'
    if hasattr(mat, 'use_transparent_shadow'):
        mat.use_transparent_shadow = True
    mat['hb_sky_blend'] = blend
    mat['hb_sky_layer'] = json.dumps(dict(textures=list(textures.values()), tint=tint))
    return True


def _pixels(path):
    image = bpy.data.images.load(str(path), check_existing=True)
    if not image.has_data:
        image.reload()
    w, h = image.size
    data = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(data)
    return data.reshape(h, w, 4)


def _resample(data, width, height, tiling):
    """The texture repeated tiling times over width x height, wrapping, with bilinear filtering:
    a layer's textures are enlarged to the largest one's size (Coagulation's 256 cloud mask to
    2048), and picking the nearest texel made each one a visible square."""
    h, w = data.shape[:2]
    fy = (np.arange(height) + .5) / height * tiling[1] * h - .5
    fx = (np.arange(width) + .5) / width * tiling[0] * w - .5
    y0 = np.floor(fy).astype(int); x0 = np.floor(fx).astype(int)
    ty = (fy - y0).astype(np.float32)[:, None, None]; tx = (fx - x0).astype(np.float32)[None, :, None]
    y0, y1 = y0 % h, (y0 + 1) % h
    x0, x1 = x0 % w, (x0 + 1) % w
    top = data[y0[:, None], x0[None, :]] * (1 - tx) + data[y0[:, None], x1[None, :]] * tx
    bottom = data[y1[:, None], x0[None, :]] * (1 - tx) + data[y1[:, None], x1[None, :]] * tx
    return (top * (1 - ty) + bottom * ty).astype(np.float32)


def bake(mat, folder, key):
    """One RGBA texture over the layer's UV tile: tiled color x detail x tint, with
    the layer's alpha (its mask for clouds). Returns a converted-shader entry."""
    from .cross_game import save_pixels
    layer = json.loads(mat.get('hb_sky_layer', '{}'))
    directory = Path(mat.get('hb_texture_directory', ''))
    textures = {t['usage']: t for t in layer.get('textures', [])}
    loaded = {usage: _pixels(directory / entry['path']) for usage, entry in textures.items()}
    tiling = {usage: [max(float(x), 1e-6) for x in entry.get('tiling', (1, 1))[:2]] for usage, entry in textures.items()}
    width = height = 1
    for usage, data in loaded.items():
        width = max(width, int(round(data.shape[1] * tiling[usage][0])))
        height = max(height, int(round(data.shape[0] * tiling[usage][1])))
    width, height = min(width, MAX_BAKE), min(height, MAX_BAKE)
    base = _resample(loaded['diffuse'], width, height, tiling['diffuse'])
    rgb = base[:, :, :3].copy()
    if 'diffuse_detail' in loaded:
        rgb *= _resample(loaded['diffuse_detail'], width, height, tiling['diffuse_detail'])[:, :, :3]
    if layer.get('tint'):
        rgb *= np.array(layer['tint'][:3], dtype=np.float32)
    if mat.get('hb_sky_blend') == 'additive':
        alpha = np.ones((height, width), dtype=np.float32)
    elif 'transparency' in loaded:
        alpha = _resample(loaded['transparency'], width, height, tiling['transparency'])[:, :, 3]
    else:
        alpha = base[:, :, 3]
    data = np.concatenate([np.clip(rgb, 0, 1), alpha[:, :, None]], axis=2)
    path = Path(folder) / (key + '_base.tif')
    save_pixels(data, path, color=True)
    entry = dict(name=key, tiling=(1.0, 1.0), maps={'base_map': str(path)}, blend=mat['hb_sky_blend'])
    # An alpha-blended layer that covers everything (Coagulation's blue sky dome) can be drawn
    # opaque without changing how it looks; the sky export uses that for the backmost layer.
    entry['covers'] = bool(mat['hb_sky_blend'] == 'alpha' and float(alpha.min()) >= OPAQUE_ALPHA)
    return entry
