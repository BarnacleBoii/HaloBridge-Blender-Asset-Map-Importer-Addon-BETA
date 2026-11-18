"""Preview supported Halo albedo operations using their named texture parameters."""
from pathlib import Path
import bpy
from . import compat


# Halo 3 "double-multiplies" each detail map over the base map: x2 in the game's
# gamma-encoded colour. Blender's nodes work on linear colour (sRGB images are
# decoded), where the same x2 is 2^2.2. Using a plain 2 made detailed surfaces
# roughly half as bright as in game.
DETAIL_GAIN = 2.0 ** 2.2
GAIN_LABEL = 'Halo detail gain'


def refresh_gain(mat):
    """Brighten detail previews made by older versions (x2 / x4). Returns True if changed."""
    mode = mat.get('hb_regular_preview') if mat else None
    if not mode or not mat.node_tree:
        return False
    wanted = DETAIL_GAIN ** 2 if mode in ('two_detail', 'two_detail_overlay') else DETAIL_GAIN
    old = (4.0,) if mode in ('two_detail', 'two_detail_overlay') else (2.0,)
    changed = False
    for node in mat.node_tree.nodes:
        if node.bl_idname == 'ShaderNodeVectorMath' and node.operation == 'SCALE':
            value = node.inputs['Scale'].default_value
            if node.label == GAIN_LABEL or any(abs(value - v) < 1e-6 for v in old):
                if abs(value - wanted) > 1e-6:
                    node.inputs['Scale'].default_value = wanted; changed = True
                node.label = GAIN_LABEL
    return changed


def apply(mat, meta, directory):
    mode = meta.get('options', {}).get('albedo')
    if meta.get('source_game') != 'halo3' or mode not in ('default', 'detail_blend', 'two_detail', 'two_detail_overlay'):
        return
    textures = {t.get('parameter'): t for t in meta['textures']}
    required = ['base_map', 'detail_map']
    if mode != 'default':
        required.append('detail_map2')
    if mode == 'two_detail_overlay':
        required.append('detail_map_overlay')
    if any(name not in textures for name in required):
        return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    uv = nodes.new('ShaderNodeTexCoord').outputs['UV']
    maps = {}
    for name in required:
        texture = textures[name]
        node = nodes.new('ShaderNodeTexImage')
        node.name = name
        node.label = texture['name'].split(chr(92))[-1]
        node.image = bpy.data.images.load(str(Path(directory)/texture['path']), check_existing=True)
        mapping = nodes.new('ShaderNodeVectorMath')
        mapping.operation = 'MULTIPLY'
        mapping.inputs[1].default_value = (*texture['tiling'], 1)
        links.new(uv, mapping.inputs[0])
        links.new(mapping.outputs[0], node.inputs['Vector'])
        maps[name] = node

    def multiply(a, b):
        node = nodes.new('ShaderNodeMixRGB')
        node.blend_type = 'MULTIPLY'
        node.inputs[0].default_value = 1
        links.new(a, node.inputs[1])
        links.new(b, node.inputs[2])
        return node.outputs[0]

    base = maps['base_map']
    detail = maps['detail_map'].outputs['Color']
    if mode in ('detail_blend', 'two_detail_overlay'):
        blend = nodes.new('ShaderNodeMixRGB')
        links.new(base.outputs['Alpha'], blend.inputs[0])
        links.new(detail, blend.inputs[1])
        links.new(maps['detail_map2'].outputs['Color'], blend.inputs[2])
        detail = blend.outputs[0]
    color = multiply(base.outputs['Color'], detail)
    if mode in ('two_detail', 'two_detail_overlay'):
        overlay = 'detail_map2' if mode == 'two_detail' else 'detail_map_overlay'
        color = multiply(color, maps[overlay].outputs['Color'])
    gain = nodes.new('ShaderNodeVectorMath')
    gain.operation = 'SCALE'; gain.label = GAIN_LABEL
    gain.inputs['Scale'].default_value = DETAIL_GAIN ** 2 if mode in ('two_detail', 'two_detail_overlay') else DETAIL_GAIN
    links.new(color, gain.inputs[0])
    color = gain.outputs[0]
    if mode == 'default':
        tint = next((t for t in meta.get('tints', []) if t['usage'] == 'albedo'), None)
        if tint:
            rgb = nodes.new('ShaderNodeRGB')
            rgb.outputs[0].default_value = tint['color']
            color = multiply(color, rgb.outputs[0])
    links.new(color, nodes.get('Principled BSDF').inputs['Base Color'])
    mat['hb_regular_preview'] = mode


def paired_transparency(mesh):
    """Cull backfaces only where every transparent triangle has an opposite mate."""
    from collections import defaultdict
    mesh.calc_loop_triangles()
    slots = defaultdict(lambda: defaultdict(list))
    for face in mesh.loop_triangles:
        if face.material_index >= len(mesh.materials):
            continue
        mat = mesh.materials[face.material_index]
        if not mat or not compat.is_transparent(mat):
            continue
        key = tuple(sorted(tuple(mesh.vertices[i].co) for i in face.vertices))
        slots[face.material_index][key].append(face.normal.copy())
    for slot, groups in slots.items():
        if groups and all(len(normals) == 2 and normals[0].dot(normals[1]) < -0.999 for normals in groups.values()):
            # Use a local material copy so single-sided users retain their preview.
            original = mesh.materials[slot]
            if original.get('hb_paired_transparency'):
                continue
            mat = original.copy()
            mat.name = original.name + ' - paired faces'
            mat.use_backface_culling = True
            mat['hb_paired_transparency'] = True
            # Avoid registering this geometry-specific copy as the source material.
            if 'hb_material_key' in mat:
                del mat['hb_material_key']
            mesh.materials[slot] = mat
